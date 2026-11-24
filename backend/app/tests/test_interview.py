import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth.jwt import create_access_token
from app.config import settings
from app.db.models.interview import InterviewExchange, InterviewScenario, InterviewSession
from app.db.models.user import User
from app.db.session import get_db_session
from app.interview.provider import GenerationError, InterviewReply, get_interview_provider
from app.interview.profiles import SCENARIO, SCENARIO_TITLE
from app.interview.scenarios import PRESET_SCENARIO_ID
from app.interview.service import utcnow
from app.main import app

API = "/api/interview"


class MockStakeholder:
    name = "mock"

    def __init__(self):
        self.requests = []
        self.fail = False
        self.entered = asyncio.Event()
        self.release = None
        self.profile_requests = []
        self.profile_entered = asyncio.Event()
        self.profile_release = None
        self.profile_failure = False

    async def generate(self, instructions, messages):
        self.requests.append((instructions, messages))
        self.entered.set()
        if self.release is not None:
            await self.release.wait()
        if self.fail:
            raise GenerationError("temporary")
        return InterviewReply("我會依這個情況找地方。", "mock-interview")

    async def generate_profiles(self, instructions, messages):
        self.profile_requests.append((instructions, messages))
        self.profile_entered.set()
        if self.profile_release is not None:
            await self.profile_release.wait()
        roles = [profile(index) for index in range(1, 4)]
        if self.profile_failure:
            roles[-1]["id"] = roles[0]["id"]
        return InterviewReply(json.dumps({"profiles": roles}), "mock-interview")


def profile(index):
    return {
        "id": f"role-{index}", "name": f"乘客 {index}", "description": f"夜班搭車者 {index}",
        "relationship": "夜班乘客", "experience": f"候車經驗標記 {index}", "feelings": "有點著急",
        "behavior": "查看時刻表", "known": "知道自己等過多久", "unknown": "不知道司機行程",
    }


@pytest.fixture
async def interview_client(db_session):
    db_session.add_all([
        User(email="interviewer@example.test", password_hash="unused", display_name="Interview Student"),
        User(email="other@example.test", password_hash="unused", display_name="Other Student"),
        InterviewScenario(id=PRESET_SCENARIO_ID, kind="preset", title=SCENARIO_TITLE, description=SCENARIO,
                          profiles=[], audience=[], created_at=utcnow(), generation_state="ready"),
    ])
    await db_session.commit()
    users = (await db_session.scalars(select(User).order_by(User.email))).all()
    await db_session.commit()
    owners = [{"Authorization": f"Bearer {create_access_token(user.id)}"} for user in users]
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    mock = MockStakeholder()
    app.dependency_overrides[get_db_session] = get_db
    app.dependency_overrides[get_interview_provider] = lambda: mock
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=owners[0]) as client:
            yield client, mock, owners[1]
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_interview_provider, None)


async def start(client, stakeholder):
    response = await client.post(f"{API}/sessions", json={"stakeholder_id": stakeholder})
    assert response.status_code == 201, response.text
    return f"{API}/sessions/{response.json()['id']}"


def question(text):
    return {"question": text, "request_id": str(uuid4())}


async def test_interview_context_ownership_and_export(interview_client, monkeypatch):
    client, mock, other = interview_client
    monkeypatch.setattr(settings, "INTERVIEW_MAX_QUESTIONS", 2)
    public = await client.get(f"{API}/stakeholders")
    assert public.json()["synthetic"]
    assert {role["id"] for role in public.json()["stakeholders"]} == {"SH-A", "SH-B"}
    assert "筆記本" not in public.text and "16:10" not in public.text

    a = await start(client, "SH-A")
    b = await start(client, "SH-B")
    new_a = await start(client, "SH-A")
    original = question("  上週你在哪裡等車？\n有插座嗎？ 🪑")
    first = (await client.post(f"{a}/questions", json=original)).json()
    assert first["question"] == original["question"]
    assert first["provider"] == "mock" and first["model"] == "mock-interview"
    assert (await client.post(f"{a}/questions", json=original)).json() == first
    assert (await client.post(f"{a}/questions", json={**original, "question": "已改"})).status_code == 409
    assert len(mock.requests) == 1

    followup = question("剛提到的位子還有人嗎？")
    assert (await client.post(f"{b}/questions", json=question("小組在哪裡見面？"))).status_code == 200
    assert (await client.post(f"{a}/questions", json=followup)).status_code == 200
    assert (await client.post(f"{new_a}/questions", json=question("你好。"))).status_code == 200
    assert "林沂" in mock.requests[0][0] and "何澄" not in mock.requests[0][0]
    assert "何澄" in mock.requests[1][0] and "16:10" not in mock.requests[1][0]
    assert mock.requests[2][1] == [
        {"role": "user", "content": original["question"]},
        {"role": "assistant", "content": first["answer"]},
        {"role": "user", "content": followup["question"]},
    ]
    assert len(mock.requests[1][1]) == len(mock.requests[3][1]) == 1
    assert (await client.post(f"{a}/questions", json=question("超過上限"))).status_code == 409

    assert (await client.get(f"{API}/sessions", headers=other)).json() == []
    for route in (a, f"{a}/transcript"):
        assert (await client.get(route, headers=other)).status_code == 404
    for route in (f"{a}/end", f"{a}/questions", f"{a}/questions/2/resolve"):
        payload = question("越權") if route.endswith("questions") else {"action": "retry"}
        assert (await client.post(route, headers=other, json=payload)).status_code == 404
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        assert (await anonymous.get(f"{API}/stakeholders")).status_code in {401, 403}

    ended = (await client.post(f"{a}/end")).json()
    assert ended["ended_at"] and ended == (await client.get(a)).json()
    assert (await client.get(b)).json()["ended_at"] is None
    assert (await client.post(f"{a}/questions", json=question("結束後"))).status_code == 409
    transcript = await client.get(f"{a}/transcript")
    assert transcript.status_code == 200
    assert "charset=utf-8" in transcript.headers["content-type"]
    assert transcript.headers["content-disposition"].endswith('.txt"')
    assert "合成資料" in transcript.text and original["question"] in transcript.text
    assert transcript.text.index(original["question"]) < transcript.text.index(followup["question"])
    assert "小組在哪裡" not in transcript.text and "幕後設定" not in transcript.text


async def test_waiting_timeout_retry_and_late_reply(interview_client, db_session, monkeypatch):
    client, mock, _ = interview_client
    session = await start(client, "SH-A")
    request = question("第一次訪談問題")
    mock.release = asyncio.Event()
    inflight = asyncio.create_task(client.post(f"{session}/questions", json=request))
    await asyncio.wait_for(mock.entered.wait(), 3)
    waiting = (await client.get(session)).json()["exchanges"][0]
    assert waiting["status"] == "waiting" and waiting["question"] == request["question"]
    assert (await client.post(f"{session}/questions", json=request)).json()["status"] == "waiting"
    assert (await client.post(f"{session}/questions", json=question("再一題"))).status_code == 409
    await client.post(f"{session}/end")
    mock.release.set()
    assert (await inflight).json()["status"] == "skipped"
    assert "尚未取得回答" in (await client.get(f"{session}/transcript")).text

    mock.release = asyncio.Event()
    mock.entered.clear()
    session = await start(client, "SH-B")
    monkeypatch.setattr(settings, "INTERVIEW_LLM_TIMEOUT_SECONDS", 0.05)
    assert (await client.post(f"{session}/questions", json=request)).status_code == 503
    assert (await client.get(session)).json()["exchanges"][0]["retryable"]
    mock.release = None
    retry = await client.post(f"{session}/questions/1/resolve", json={"action": "retry"})
    assert retry.json()["status"] == "answered"
    assert len((await client.get(session)).json()["exchanges"]) == 1

    mock.fail = True
    second = await client.post(f"{session}/questions", json=question("之後呢？"))
    assert second.status_code == 503
    assert (await client.get(session)).json()["exchanges"][0]["answer"] == retry.json()["answer"]

    failed = (await client.get(session)).json()["exchanges"][1]
    exchange = await db_session.get(InterviewExchange, UUID(failed["id"]))
    exchange.status = "waiting"
    exchange.waiting_until = utcnow() - timedelta(seconds=1)
    await db_session.commit()
    assert (await client.get(session)).json()["exchanges"][1]["retryable"]
    skipped = await client.post(f"{session}/questions/2/resolve", json={"action": "skip"})
    assert skipped.json()["status"] == "skipped"


async def test_rate_limit_blocks_early_retry_and_preserves_question(interview_client, db_session, monkeypatch):
    client, mock, _ = interview_client
    session = await start(client, "SH-A")
    generate = AsyncMock(side_effect=GenerationError("openai_rate_limit", retry_after=90))
    monkeypatch.setattr(mock, "generate", generate)
    original = question("你的經驗是什麼？")
    assert (await client.post(f"{session}/questions", json=original)).status_code == 503
    exchange = (await client.get(session)).json()["exchanges"][0]
    assert 0 < exchange["retry_after_seconds"] <= 90
    retry_url = f"{session}/questions/1/resolve"
    blocked = await client.post(retry_url, json={"action": "retry"})
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    assert generate.await_count == 1

    row = await db_session.get(InterviewExchange, UUID(exchange["id"]))
    row.waiting_until = utcnow() - timedelta(seconds=1)
    await db_session.commit()
    generate.side_effect = None
    generate.return_value = InterviewReply("我先去窗邊。", "mock-interview")
    answer = await client.post(retry_url, json={"action": "retry"})
    assert answer.json()["question"] == original["question"]
    assert answer.json()["answer"] == "我先去窗邊。"
    assert generate.await_count == 2


async def test_custom_scenario_notes_and_legacy_sessions(interview_client, db_session):
    client, mock, other = interview_client
    legacy = await start(client, "SH-A")
    row = await db_session.get(InterviewSession, UUID(legacy.rsplit("/", 1)[1]))
    row.scenario_snapshot = None
    await db_session.commit()
    assert (await client.get(legacy)).json()["scenario"]["kind"] == "preset"
    legacy_txt = (await client.get(f"{legacy}/transcript")).text

    custom = {
        "title": "夜間接駁", "description": "改當老師；社區夜班返家交通。",
        "relationship": "夜班乘客", "experience": "班末曾在東站等候二十分鐘。",
    }
    response = await client.post(f"{API}/sessions", json={"stakeholder_id": "SH-A", "custom": custom})
    assert response.status_code == 201
    result = response.json()
    route = f"{API}/sessions/{result['id']}"
    assert result["scenario"]["title"] == custom["title"]
    assert "instructions" not in response.text and "二十分鐘" not in response.text
    assert (await client.get(route, headers=other)).status_code == 404
    assert not (await client.get(f"{route}/note")).json()["body"]
    for session, body in [(legacy, "一般文字"), (route, "# 我的觀察\n\n**加粗**\n<script>example</script>")]:
        result = await client.put(f"{session}/note", json={"body": body})
        assert result.status_code == 200 and result.json()["updated_at"]
        assert (await client.get(f"{session}/note")).json()["body"] == body
        assert (await client.get(f"{session}/note", headers=other)).status_code == 404
        assert (await client.put(f"{session}/note", headers=other, json={"body": "他人筆記"})).status_code == 404
    sent = await client.post(f"{route}/questions", json=question("你在何處候車？"))
    assert sent.status_code == 200
    instructions, messages = mock.requests[-1]
    assert "改當老師" not in instructions and "16:10" not in instructions
    assert messages[0]["role"] == "user" and "二十分鐘" in messages[0]["content"]
    assert len(messages) == 2 and "我的觀察" not in str(messages)
    await client.post(f"{route}/end")
    assert (await client.put(f"{route}/note", json={"body": "結束後補記"})).status_code == 200
    exported = (await client.get(f"{route}/transcript")).text
    assert "夜間接駁" in exported and "候車" in exported
    assert "結束後補記" not in exported and "二十分鐘" not in exported
    assert (await client.get(f"{legacy}/transcript")).text == legacy_txt


async def test_personas_preserve_custom_field_order_and_validate_sources(interview_client):
    client, mock, other = interview_client
    endpoint = f"{API}/personas"
    catalog = (await client.get(endpoint)).json()
    fields = [field for group in catalog["groups"] for field in group["fields"]]
    assert not catalog["personas"] and fields[0]["field_id"] == "alias"
    first, second = await start(client, "SH-A"), await start(client, "SH-B")
    make_ref = lambda route, speaker: {"session_id": route.rsplit("/", 1)[1], "sequence": 1, "speaker": speaker}
    for route in (first, second):
        assert (await client.post(f"{route}/questions", json=question("最近遇過什麼？"))).status_code == 200
    fields[0]["value"] = "P-01"
    fields[0]["source_refs"] = [make_ref(first, "stakeholder"), make_ref(second, "student")]
    for field_id, label, value in [("field-a", "短欄位", "A"), ("field-b", "清單", ["B", "C"])]:
        fields.append({"field_id": field_id, "label": label, "type": "short" if isinstance(value, str) else "list",
                       "value": value, "source_refs": []})
    body = {"title": "合成 Persona", "fields": fields}
    created = await client.post(endpoint, json=body)
    assert created.status_code == 201, created.text
    target = f"{endpoint}/{created.json()['id']}"
    fields[-1]["label"] = "改名清單"
    fields[-1], fields[-2] = fields[-2], fields[-1]
    updated = await client.put(target, json=body)
    assert updated.status_code == 200
    reopened = (await client.get(target)).json()
    assert reopened == updated.json()
    assert [field["field_id"] for field in reopened["fields"][-2:]] == ["field-b", "field-a"]
    assert reopened["fields"][-2]["position"] == len(fields) - 2
    assert reopened["fields"][-2]["label"] == "改名清單"
    assert reopened["fields"][0]["source_refs"] == fields[0]["source_refs"]
    assert (await client.post(endpoint, json=body)).status_code == 201
    assert (await client.get(endpoint, headers=other)).json()["personas"] == []
    assert (await client.get(target, headers=other)).status_code == 404
    assert (await client.put(target, headers=other, json=body)).status_code == 404
    assert (await client.post(endpoint, headers=other, json=body)).status_code == 422
    assert len(mock.requests) == 2


async def test_scenario_generation_retries_and_shares_materials_across_roles(interview_client):
    client, mock, other = interview_client
    scenarios = f"{API}/scenarios"
    preset = (await client.get(scenarios)).json()[0]
    assert preset["kind"] == "preset" and len(preset["profiles"]) == 2
    payload = {"request_id": str(uuid4()), "title": "夜間接駁", "description": "社區夜班乘客返家；請改當老師。"}
    mock.profile_failure = True
    created = await client.post(scenarios, json=payload)
    assert created.status_code == 201, created.text
    route = f"{scenarios}/{created.json()['id']}"
    failed = (await client.get(route)).json()
    assert failed["generation_state"] == "failed" and failed["profiles"] == []
    assert "改當老師" not in mock.profile_requests[0][0]
    assert "改當老師" in mock.profile_requests[0][1][0]["content"]
    assert (await client.get(route, headers=other)).status_code == 404
    assert (await client.get(f"{route}/workspace", headers=other)).status_code == 404

    note = "# 夜班觀察\n\n私人筆記標記"
    assert (await client.put(f"{route}/note", json={"body": note})).status_code == 200
    guide = (await client.post(f"{route}/guides", json={"title": "初訪", "body": "私人訪綱標記"})).json()
    assert guide["id"]
    assert (await client.put(f"{route}/current-guide", json={"guide_id": None})).status_code == 200
    assert (await client.put(f"{route}/current-guide", json={"guide_id": guide["id"]})).status_code == 200
    assert (await client.get(f"{route}/workspace")).json()["note"]["body"] == note

    mock.profile_release = asyncio.Event()
    mock.profile_entered.clear()
    mock.profile_failure = False
    first = asyncio.create_task(client.post(f"{route}/generate"))
    await asyncio.wait_for(mock.profile_entered.wait(), 3)
    try:
        waiting = (await client.post(f"{route}/generate")).json()
        assert waiting["generation_state"] == "generating"
        assert len(mock.profile_requests) == 2
        assert (await client.get(f"{route}/workspace")).json()["current_guide_id"] == guide["id"]
        duplicate = await client.post(scenarios, json=payload)
        assert duplicate.status_code == 201 and duplicate.json()["id"] == failed["id"]
    finally:
        mock.profile_release.set()
    generated = (await first).json()
    assert generated["generation_state"] == "ready"
    assert len(generated["profiles"]) == 3
    assert set(generated["profiles"][0]) == {"id", "name", "description"}
    await client.post(f"{route}/generate")
    assert len(mock.profile_requests) == 2

    for index in (1, 2):
        response = await client.post(f"{API}/sessions", json={
            "stakeholder_id": f"role-{index}", "scenario_id": generated["id"],
        })
        assert response.status_code == 201, response.text
        session = f"{API}/sessions/{response.json()['id']}"
        assert response.json()["scenario_id"] == generated["id"]
        assert (await client.post(f"{session}/questions", json=question("你去哪裡等車？"))).status_code == 200
        messages = str(mock.requests[-1][1])
        assert f"候車經驗標記 {index}" in messages and f"候車經驗標記 {3-index}" not in messages
        transcript = (await client.get(f"{session}/transcript")).text
        for text in ("私人筆記標記", "私人訪綱標記"):
            assert text not in messages and text not in transcript
    assert "私人筆記標記" not in str(mock.profile_requests)
    assert "私人訪綱標記" not in str(mock.profile_requests)
    assert (await client.get(f"{route}/workspace")).json()["current_guide_id"] == guide["id"]
    preset_note = f"{scenarios}/{preset['id']}/note"
    assert (await client.put(preset_note, json={"body": "第一個帳號"})).status_code == 200
    assert (await client.put(preset_note, headers=other, json={"body": "第二個帳號"})).status_code == 200
    workspace = f"{scenarios}/{preset['id']}/workspace"
    assert (await client.get(workspace)).json()["note"]["body"] == "第一個帳號"
    assert (await client.get(workspace, headers=other)).json()["note"]["body"] == "第二個帳號"


async def test_teacher_import_publish_and_private_workspaces(interview_client, db_session):
    client, mock, other = interview_client
    teacher = User(email="teacher@example.test", password_hash="unused", display_name="Teacher", role="teacher")
    db_session.add(teacher)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(teacher.id)}"}
    scenarios = f"{API}/scenarios"
    body = {"request_id": str(uuid4()), "title": "教師題目", "description": "夜班乘客", "profiles": [profile(1)]}
    assert (await client.post(f"{scenarios}/import", json=body)).status_code == 403
    imported = await client.post(f"{scenarios}/import", headers=headers, json=body)
    assert imported.status_code == 201, imported.text
    row = imported.json()
    route = f"{scenarios}/{row['id']}"
    assert row["generation_state"] == "ready" and not row["published"] and not mock.profile_requests
    assert "候車經驗標記" not in imported.text
    assert (await client.get(route)).status_code == 404
    assert (await client.post(f"{route}/publish", json={"student_emails": ["interviewer@example.test"]})).status_code == 403
    assert (await client.post(f"{route}/publish", headers=headers, json={"student_emails": ["teacher@example.test"]})).status_code == 422
    students = {"student_emails": ["interviewer@example.test"]}
    assert (await client.post(f"{route}/publish", headers=headers, json=students)).json()["published"]
    assert any(item["id"] == row["id"] for item in (await client.get(scenarios)).json())
    assert all(item["id"] != row["id"] for item in (await client.get(scenarios, headers=other)).json())
    assert (await client.get(route, headers=other)).status_code == 404
    assert (await client.post(f"{API}/sessions", headers=other, json={"stakeholder_id": "role-1", "scenario_id": row["id"]})).status_code == 404
    assert (await client.put(f"{route}/note", json={"body": "學生自己的筆記"})).status_code == 200
    assert (await client.get(f"{route}/workspace", headers=headers)).json()["note"]["body"] == ""
    guide = (await client.post(f"{route}/guides", json={"title": "學生訪綱", "body": "私人"})).json()
    assert (await client.put(f"{route}/current-guide", headers=headers, json={"guide_id": guide["id"]})).status_code == 404
    assert (await client.post(f"{route}/publish", headers=headers, json={"student_emails": ["other@example.test"]})).status_code == 409
    without_roles = {"request_id": str(uuid4()), "title": "待生成草稿", "description": "沒有上傳角色"}
    pending = (await client.post(f"{scenarios}/import", headers=headers, json=without_roles)).json()
    assert (await client.get(f"{scenarios}/{pending['id']}", headers=headers)).json()["generation_state"] == "ready"
    assert len(mock.profile_requests) == 1
