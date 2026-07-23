"""Tests for unified LLM judge layer (Phase 18 Step A0)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from app.agents.llm_judge import (
    JudgeResult,
    is_violating,
    judge_batch,
    judge_content,
    list_supported_modules,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _mock_redis(monkeypatch):
    """Avoid Redis cache; force re-evaluation."""
    class _Fake:
        async def get(self, *a, **kw): return None
        async def set(self, *a, **kw): pass
        async def aclose(self): pass

    async def fake_get_redis():
        return _Fake()

    monkeypatch.setattr("app.agents.llm_judge._get_redis", fake_get_redis)


@pytest.fixture(autouse=True)
def _disable_trace(monkeypatch):
    """Skip DB writes in tests."""
    async def noop(*a, **kw): pass
    monkeypatch.setattr("app.agents.llm_judge._record_to_trace", noop)


@pytest.fixture
def mock_llm_pass(monkeypatch):
    """Mock LLM returning pass verdict."""
    fake = AsyncMock()
    fake.chat_completion = AsyncMock(return_value=type("R", (), {
        "content": '{"verdict": "pass", "confidence": 0.9, "reasoning": "純引用"}'
    })())
    monkeypatch.setattr(
        "app.agents.llm_judge.LLMProviderFactory.get_service",
        lambda: fake,
    )
    return fake


@pytest.fixture
def mock_llm_violate(monkeypatch):
    """Mock LLM returning violate verdict."""
    fake = AsyncMock()
    fake.chat_completion = AsyncMock(return_value=type("R", (), {
        "content": '{"verdict": "violate", "confidence": 0.85, "reasoning": "明顯解法用語"}'
    })())
    monkeypatch.setattr(
        "app.agents.llm_judge.LLMProviderFactory.get_service",
        lambda: fake,
    )
    return fake


@pytest.fixture
def mock_llm_failure(monkeypatch):
    """Mock LLM raising an exception."""
    fake = AsyncMock()
    fake.chat_completion = AsyncMock(side_effect=RuntimeError("LLM timeout"))
    monkeypatch.setattr(
        "app.agents.llm_judge.LLMProviderFactory.get_service",
        lambda: fake,
    )
    return fake


class TestSingleJudge:
    _USER = UUID("00000000-0000-0000-0000-000000000001")

    async def test_pass_verdict(self, mock_llm_pass) -> None:
        result = await judge_content(
            text='"我都搞不清楚要按哪裡"｜情緒：焦躁',
            rule_module="no_interpretation",
            owning_user_id=self._USER,
        )
        assert result.verdict == "pass"
        assert result.confidence == 0.9
        assert result.fallback_used is False

    async def test_violate_verdict(self, mock_llm_violate) -> None:
        result = await judge_content(
            text="做一個結帳優化 App",
            rule_module="no_solution_language",
            context={"sub_phase": "2.2", "zone": "pov_wall"},
            owning_user_id=self._USER,
        )
        assert result.verdict == "violate"
        assert is_violating(result) is True

    async def test_llm_failure_falls_back_to_pass(self, mock_llm_failure) -> None:
        result = await judge_content(
            text="任何文字",
            rule_module="no_solution_language",
        )
        assert result.verdict == "pass"
        assert result.fallback_used is True
        assert result.confidence == 0.0

    async def test_empty_text_passes_immediately(self) -> None:
        # No LLM mock — should never reach LLM
        result = await judge_content(text="", rule_module="no_solution_language")
        assert result.verdict == "pass"

    async def test_whitespace_only_passes(self) -> None:
        result = await judge_content(text="   \n  ", rule_module="no_solution_language")
        assert result.verdict == "pass"


class TestBatchJudge:
    async def test_batch_single_call_for_multiple_rules(self, monkeypatch) -> None:
        # Setup mock LLM returning all-pass JSON
        fake = AsyncMock()
        fake.chat_completion = AsyncMock(return_value=type("R", (), {
            "content": (
                '{"no_solution_language": {"verdict": "pass", "confidence": 0.9, "reasoning": "ok"},'
                '"no_criticism": {"verdict": "pass", "confidence": 0.9, "reasoning": "ok"}}'
            )
        })())
        monkeypatch.setattr(
            "app.agents.llm_judge.LLMProviderFactory.get_service",
            lambda: fake,
        )

        batch = await judge_batch(
            text="使用者覺得這個按鈕太小",
            rule_modules=["no_solution_language", "no_criticism"],
            owning_user_id=UUID("00000000-0000-0000-0000-000000000001"),
        )
        # Only one LLM call regardless of rule count
        assert fake.chat_completion.await_count == 1
        assert batch.results["no_solution_language"].verdict == "pass"
        assert batch.results["no_criticism"].verdict == "pass"

    async def test_batch_handles_missing_rule_response(self, monkeypatch) -> None:
        # LLM returns only one rule's result
        fake = AsyncMock()
        fake.chat_completion = AsyncMock(return_value=type("R", (), {
            "content": '{"no_solution_language": {"verdict": "pass", "confidence": 0.9, "reasoning": "ok"}}'
        })())
        monkeypatch.setattr(
            "app.agents.llm_judge.LLMProviderFactory.get_service",
            lambda: fake,
        )

        batch = await judge_batch(
            text="x",
            rule_modules=["no_solution_language", "no_criticism"],
        )
        # Missing rule falls back to pass
        assert batch.results["no_criticism"].fallback_used is True
        assert batch.results["no_criticism"].verdict == "pass"

    async def test_batch_llm_failure_all_pass(self, mock_llm_failure) -> None:
        batch = await judge_batch(
            text="任何",
            rule_modules=["no_solution_language", "no_criticism"],
        )
        assert all(r.verdict == "pass" for r in batch.results.values())
        assert all(r.fallback_used for r in batch.results.values())


class TestVerdictHelpers:
    def test_is_violating_high_confidence(self) -> None:
        r = JudgeResult(
            verdict="violate", confidence=0.85,
            reasoning_zh="x", rule_module="m",
        )
        assert is_violating(r) is True

    def test_is_violating_low_confidence(self) -> None:
        r = JudgeResult(
            verdict="violate", confidence=0.4,
            reasoning_zh="x", rule_module="m",
        )
        # Below default 0.6 → not block
        assert is_violating(r) is False

    def test_is_violating_pass_verdict(self) -> None:
        r = JudgeResult(
            verdict="pass", confidence=0.99,
            reasoning_zh="x", rule_module="m",
        )
        assert is_violating(r) is False

    def test_is_violating_borderline_verdict(self) -> None:
        r = JudgeResult(
            verdict="borderline", confidence=0.7,
            reasoning_zh="x", rule_module="m",
        )
        assert is_violating(r) is False  # borderline 不擋


class TestSupportedModules:
    def test_includes_all_phase_17_gates(self) -> None:
        modules = set(list_supported_modules())
        # Phase 42 C1：no_interpretation／empathy_says_no_inference 隨舊 1.5/1.6
        # 移除；新增 no_feature_jump（1.2 跳功能軟擋二判）。
        required = {
            "no_solution_language",
            "no_feature_jump",
            "no_feasibility_talk",
            "no_production_code",
        }
        assert required <= modules
        assert "no_interpretation" not in modules
        assert "empathy_says_no_inference" not in modules

    def test_includes_phase_18_new_modules(self) -> None:
        modules = set(list_supported_modules())
        new = {
            "no_criticism",
            "pov_quality",
            "mention_detection",
            "deliverable_quality",
            "debrief_depth",
            "task_hypothesis_alignment",
            "silence_type",
            "category_diversity",
        }
        assert new <= modules


class TestParseRobustness:
    async def test_malformed_json_falls_back(self, monkeypatch) -> None:
        fake = AsyncMock()
        fake.chat_completion = AsyncMock(return_value=type("R", (), {
            "content": "not valid json at all"
        })())
        monkeypatch.setattr(
            "app.agents.llm_judge.LLMProviderFactory.get_service",
            lambda: fake,
        )

        result = await judge_content(
            text="x", rule_module="no_solution_language",
        )
        assert result.fallback_used is True
        assert result.verdict == "pass"

    async def test_invalid_verdict_normalized_to_borderline(self, monkeypatch) -> None:
        fake = AsyncMock()
        fake.chat_completion = AsyncMock(return_value=type("R", (), {
            "content": '{"verdict": "maybe", "confidence": 0.5, "reasoning": "x"}'
        })())
        monkeypatch.setattr(
            "app.agents.llm_judge.LLMProviderFactory.get_service",
            lambda: fake,
        )

        result = await judge_content(
            text="x",
            rule_module="no_solution_language",
            owning_user_id=UUID("00000000-0000-0000-0000-000000000001"),
        )
        assert result.verdict == "borderline"
