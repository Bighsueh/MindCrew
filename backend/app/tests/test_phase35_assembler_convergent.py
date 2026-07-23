"""Phase 35: Crew assembler 在 convergent 階段不再注入時間壓力指令 (spec/16 §6.5.4)."""

from __future__ import annotations

import pytest

from app.agents.prompts.assembler import PromptAssembler


_DIRECTIVE_MARKER = "【時間壓力指令】"


def _make_context(
    *,
    current_micro_phase: str,
    time_pressure_level: str,
) -> dict:
    """Build a minimal crew context with timer pressure injected."""
    return {
        "my_seat": "crew_1",
        "current_stage": "discover",
        "current_micro_phase": current_micro_phase,
        "stage_duration_minutes": 5,
        "seats": [
            {"role": "supervisor", "type": "ai"},
            {"role": "crew_1", "type": "ai"},
        ],
        "canvas_state": {"total_notes": 3, "groups": [], "ungrouped": [], "notes": []},
        "recent_chat": [],
        "project_name": "測試專案",
        "project_description": "測試用",
        "time_pressure_level": time_pressure_level,
        "time_budget_used_pct": 80.0,
    }


def _system_text(context: dict) -> str:
    msgs = PromptAssembler().assemble(context)
    return msgs[0]["content"] if msgs else ""


@pytest.mark.unit
def test_divergent_tight_injects_pressure_directive() -> None:
    # 發散階段（micro_phase 1.1 = divergent）+ tight → 應注入指令
    ctx = _make_context(current_micro_phase="1.1", time_pressure_level="tight")
    text = _system_text(ctx)
    assert _DIRECTIVE_MARKER in text


@pytest.mark.unit
def test_convergent_tight_does_not_inject_pressure_directive() -> None:
    # 收斂階段（micro_phase 1.3 = convergent）+ tight → 不應注入（避免雙重壓力）
    ctx = _make_context(current_micro_phase="1.3", time_pressure_level="tight")
    text = _system_text(ctx)
    assert _DIRECTIVE_MARKER not in text


@pytest.mark.unit
def test_calm_does_not_inject_pressure_directive() -> None:
    # calm 等級無論意圖都不注入
    ctx = _make_context(current_micro_phase="1.1", time_pressure_level="calm")
    text = _system_text(ctx)
    assert _DIRECTIVE_MARKER not in text


@pytest.mark.unit
def test_transitional_tight_does_not_inject_pressure_directive() -> None:
    # transitional 階段（0.x / 1.2 / 2.x 等過渡）也不注入
    # 任何不是 "divergent" 的 phase_intent 都應 skip
    ctx = _make_context(current_micro_phase="2.2", time_pressure_level="tight")
    # 2.2 在 phase_intent.py 是 transitional（micro_phase）
    text = _system_text(ctx)
    assert _DIRECTIVE_MARKER not in text


@pytest.mark.unit
def test_divergent_critical_injects_pressure_directive() -> None:
    # critical 也是 inject 範圍
    ctx = _make_context(current_micro_phase="1.1", time_pressure_level="critical")
    text = _system_text(ctx)
    assert _DIRECTIVE_MARKER in text
