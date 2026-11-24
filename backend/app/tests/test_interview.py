import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth.jwt import create_access_token
from app.config import settings
from app.db.models.interview import InterviewExchange
from app.db.models.user import User
from app.db.session import get_db_session
from app.interview.provider import GenerationError, InterviewReply, get_interview_provider
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

    async def generate(self, instructions, messages):
        self.requests.append((instructions, messages))
        self.entered.set()
        if self.release is not None:
            await self.release.wait()
        if self.fail:
            raise GenerationError("temporary")
        return InterviewReply("我會依這個情況找地方。", "mock-interview")


@pytest.fixture
async def interview_client(db_session):
    db_session.add_all([
        User(email="interviewer@example.test", password_hash="unused", display_name="Interview Student"),
        User(email="other@example.test", password_hash="unused", display_name="Other Student"),
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
