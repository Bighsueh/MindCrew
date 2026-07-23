"""Unit tests for B12_off_topic_redirect（spec 15 v2.0 §2.3.1，Phase 42 B2）。

B12：一般離題——規則外/meta 提問「答完收束」＋整體跑題「主動拉回」。
門檻 0.7、無 dedup（B2 裁定）。judge 以 monkeypatch 隔離。
"""

from __future__ import annotations

import pytest

from app.agents.llm_judge import JudgeResult
from app.agents.supervisor import triggers_b
from app.agents.supervisor.triggers_b import detect_b_triggers


def _ctx(content: str = "現在是哪一關？") -> dict:
    return {
        "current_sub_phase": "2.3",
        "time_budget_used_pct": 10.0,
        "phase_intent": "transitional",
        "_deliverable_done": False,
        "recent_chat": [{"sender": "小明", "sender_id": "human_creator", "content": content}],
    }


def _judge_stub(off_topic_conf: float):
    """回傳一個 fake judge_content：只有 off_topic 模組依指定信心 violate，其餘 pass。"""

    async def _fake(text: str, rule_module: str, context: dict | None = None,
                    **kwargs) -> JudgeResult:
        if rule_module == "off_topic":
            return JudgeResult(
                verdict="violate",
                confidence=off_topic_conf,
                reasoning_zh="規則外提問",
                rule_module=rule_module,
            )
        return JudgeResult(
            verdict="pass", confidence=0.9, reasoning_zh="ok", rule_module=rule_module
        )

    return _fake


def _fired_ids(fired: list[tuple[str, dict]]) -> set[str]:
    return {tid for tid, _ in fired}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b12_fires_on_off_topic_question(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(triggers_b, "judge_content", _judge_stub(0.85))
    fired = await detect_b_triggers(_ctx("現在是哪一關？"))
    assert "B12_off_topic_redirect" in _fired_ids(fired)
    payload = dict(fired)["B12_off_topic_redirect"]
    assert payload["speaker"] == "小明"
    assert "哪一關" in payload["matched_phrase"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b12_below_threshold_does_not_fire(monkeypatch: pytest.MonkeyPatch) -> None:
    # B2 裁定：門檻 0.7——信心 0.65 不開火。
    monkeypatch.setattr(triggers_b, "judge_content", _judge_stub(0.65))
    fired = await detect_b_triggers(_ctx())
    assert "B12_off_topic_redirect" not in _fired_ids(fired)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b12_no_chat_does_not_fire(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(triggers_b, "judge_content", _judge_stub(0.95))
    ctx = _ctx()
    ctx["recent_chat"] = []
    fired = await detect_b_triggers(ctx)
    assert "B12_off_topic_redirect" not in _fired_ids(fired)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b12_skips_supervisor_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(triggers_b, "judge_content", _judge_stub(0.95))
    ctx = _ctx()
    ctx["recent_chat"] = [{"sender": "AI 引導者", "sender_id": "supervisor", "content": "現在是哪一關？"}]
    fired = await detect_b_triggers(ctx)
    assert "B12_off_topic_redirect" not in _fired_ids(fired)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b12_forwards_owning_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """judge_content 無 owning_user_id 會保守跳過（永不 violate）——
    detect_b_triggers 必須把 ctx['_owning_user_id'] 轉傳給 judge。"""
    captured: list = []

    async def _capture(text: str, rule_module: str, context: dict | None = None,
                       owning_user_id=None, **kwargs) -> JudgeResult:
        captured.append((rule_module, owning_user_id))
        return JudgeResult(verdict="pass", confidence=0.9, reasoning_zh="ok",
                           rule_module=rule_module)

    monkeypatch.setattr(triggers_b, "judge_content", _capture)
    ctx = _ctx()
    ctx["_owning_user_id"] = "owner-uuid"
    await detect_b_triggers(ctx)
    assert captured, "judge_content 未被呼叫"
    for rule_module, owning in captured:
        assert owning == "owner-uuid", f"{rule_module} 未轉傳 owning_user_id"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b12_suppressed_in_free_ranging_phases(monkeypatch: pytest.MonkeyPatch) -> None:
    """自由發想關（0.0a 暖場／1.1a 聊經驗）不跑 off_topic——避免把怪用途/個人經驗誤判離題狂 fire
    （docker live 2026-06-19 揪出 B12 在 1.1a 98 次 fire 餓死 A 佇列）。"""
    monkeypatch.setattr(triggers_b, "judge_content", _judge_stub(0.95))
    for sp in ("0.0a", "1.1a"):
        ctx = _ctx("我講一個我自己的：上次去超市結帳才發現環保袋忘在車上")
        ctx["current_sub_phase"] = sp
        fired = await detect_b_triggers(ctx)
        assert "B12_off_topic_redirect" not in _fired_ids(fired), sp


@pytest.mark.unit
@pytest.mark.asyncio
async def test_b12_still_fires_in_structured_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    """結構化關（如 2.3）仍正常運行 off_topic（不在 _NO_OFF_TOPIC_PHASES）。"""
    monkeypatch.setattr(triggers_b, "judge_content", _judge_stub(0.95))
    ctx = _ctx("欸我們等下午餐吃什麼？")
    ctx["current_sub_phase"] = "2.3"
    fired = await detect_b_triggers(ctx)
    assert "B12_off_topic_redirect" in _fired_ids(fired)


@pytest.mark.unit
def test_b12_not_in_dedup_eligible() -> None:
    # B2 裁定：無 dedup——每次離題都該被接住。
    from app.agents.supervisor.router import _DEDUP_ELIGIBLE_TRIGGERS

    assert "B12_off_topic_redirect" not in _DEDUP_ELIGIBLE_TRIGGERS


@pytest.mark.unit
def test_off_topic_rule_prompt_registered() -> None:
    from app.agents.llm_judge import list_supported_modules

    assert "off_topic" in list_supported_modules()
