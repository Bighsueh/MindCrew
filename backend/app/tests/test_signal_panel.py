"""「本關訊號」面板（Phase 42 A1，progression/signal_panel.py）＋ serializer 渲染。

決定性測試：mock gate / DB / timer，驗證面板各行與 supervisor-only 隔離
（crew context 無 key → serializer 不渲染）。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.canvas.artifact_gate import ArtifactGateResult
from app.progression import signal_panel as panel
from app.stages.sub_phases import get_sub_phase


def _patch_human(has_human: bool, chars: int):
    """A2：真人參與行改讀回合鎖權威狀態（round_lock.get_state）。

    沿用既有 (has_human, chars) 介面對映情境：chars>0=本回合已有有效參與；
    chars==0=尚無有效輸入（凍結等待）；has_human=False=全 AI 房。
    """
    _req = {"note": True, "chat": False, "move": False, "confirm": False, "mode": "any"}
    if not has_human:
        state = {"has_human": False, "round": 1, "waiting": False}
    elif chars > 0:
        state = {
            "has_human": True, "round": 1, "waiting": False,
            "human_satisfied": True, "crews_acted": [], "ai_crew_total": 3,
            "required": _req,
        }
    else:
        state = {
            "has_human": True, "round": 1, "waiting": True,
            "human_satisfied": False, "crews_acted": ["crew_1"], "ai_crew_total": 1,
            "required": _req,
        }
    return patch(
        "app.agents.round_lock.get_state",
        new=AsyncMock(return_value=state),
    )


@pytest.mark.asyncio
async def test_panel_hard_cell_renders_counts_with_zh_labels() -> None:
    """硬格：gate 計數用 spec 23 中文標籤、含現量/門檻與缺口。"""
    pid = uuid4()
    sp = get_sub_phase("1.1b")
    assert sp.min_artifact_counts, "前提：1.1b 應有 min_artifact_counts"
    gate = ArtifactGateResult(
        passed=False,
        counts={"stakeholder": 3},
        requirements={"stakeholder": 8},
        missing={"stakeholder": 5},
    )
    hp = _patch_human(True, 20)
    with (
        patch(
            "app.canvas.artifact_gate.check_artifact_gate",
            new=AsyncMock(return_value=gate),
        ),
        hp,
        patch(
            "app.progression.boundary_signal.get_boundary_signal",
            new=AsyncMock(return_value=None),
        ),
    ):
        text = await panel.build_signal_panel(
            pid, "1.1b",
            time_budget_used_pct=45.0,
            cluster_count=2,
            current_micro_phase="1.1",
        )
    assert text is not None
    assert text.startswith("【本關訊號】")
    assert "利害關係人 3/8" in text and "還差 5" in text
    assert "stakeholder" not in text
    assert "使用者已經有有效參與了" in text
    assert "白板群數：2" in text
    assert "已用 45%" in text


@pytest.mark.asyncio
async def test_panel_soft_cell_says_no_hard_gate() -> None:
    pid = uuid4()
    sp = get_sub_phase("1.1a")
    if sp.min_artifact_counts or sp.deliverables_required:
        pytest.skip("1.1a 在現行結構下非軟格（結構已改，測試需 retarget）")
    hp = _patch_human(False, 0)
    with (
        hp,
        patch(
            "app.progression.boundary_signal.get_boundary_signal",
            new=AsyncMock(return_value=None),
        ),
    ):
        text = await panel.build_signal_panel(
            pid, "1.1a", time_budget_used_pct=10.0,
        )
    assert text is not None
    assert "本關沒有硬性產出門檻" in text
    assert "全 AI 房" in text


@pytest.mark.asyncio
async def test_panel_timebox_reached_prompts_honest_closure() -> None:
    pid = uuid4()
    hp = _patch_human(True, 0)
    gate = ArtifactGateResult(passed=True, counts={}, requirements={}, missing={})
    with (
        patch(
            "app.canvas.artifact_gate.check_artifact_gate",
            new=AsyncMock(return_value=gate),
        ),
        hp,
        patch(
            "app.progression.boundary_signal.get_boundary_signal",
            new=AsyncMock(return_value=None),
        ),
    ):
        text = await panel.build_signal_panel(
            pid, "1.1b", time_budget_used_pct=105.0,
        )
    assert text is not None
    assert "時間已用完" in text and "誠實收尾" in text
    assert "等使用者" in text


@pytest.mark.asyncio
async def test_panel_boundary_signal_rendered_when_ready() -> None:
    pid = uuid4()
    hp = _patch_human(True, 30)
    gate = ArtifactGateResult(passed=True, counts={}, requirements={}, missing={})
    with (
        patch(
            "app.canvas.artifact_gate.check_artifact_gate",
            new=AsyncMock(return_value=gate),
        ),
        hp,
        patch(
            "app.progression.boundary_signal.get_boundary_signal",
            new=AsyncMock(return_value={"ready": True, "weak_areas": []}),
        ),
    ):
        text = await panel.build_signal_panel(
            pid, "1.1b", time_budget_used_pct=50.0, current_micro_phase="1.1",
        )
    assert text is not None
    assert "內容評估" in text and "可以宣布往下" in text


@pytest.mark.asyncio
async def test_panel_unknown_sub_phase_returns_none() -> None:
    assert await panel.build_signal_panel(uuid4(), "9.9z") is None


class TestSerializerPassthrough:
    _BASE_CTX = {
        "project_name": "測試專案",
        "current_stage": "discover",
        "stage_duration_minutes": 5,
        "canvas_state": {},
        "recent_chat": [],
        "seats": [],
    }

    def test_supervisor_context_renders_panel(self) -> None:
        from app.agents.prompts.context_serializer import build_context_description

        ctx = dict(self._BASE_CTX)
        ctx["sub_phase_signals"] = "【本關訊號】\n- 產出：利害關係人 3/8（還差 5）"
        text = build_context_description(ctx)
        assert "【本關訊號】" in text
        assert "利害關係人 3/8" in text

    def test_crew_context_without_key_has_no_panel(self) -> None:
        from app.agents.prompts.context_serializer import build_context_description

        text = build_context_description(dict(self._BASE_CTX))
        assert "【本關訊號】" not in text


# ---------------------------------------------------------------------------
# Phase 42（1.1a 隊友沉默修復）：全員分享訊號行
# ---------------------------------------------------------------------------


class TestShareLine:
    """1.1a build_signal_panel 的「全員分享」行（spec 22 1.1a）。"""

    @staticmethod
    def _share(has_human=True, human_shared=True, missing_names=(), missing_seats=()):
        from app.progression.share_experience import ShareStatus

        return ShareStatus(
            has_human=has_human,
            human_shared=human_shared,
            missing_crews=tuple(missing_names),
            missing_crew_seats=tuple(missing_seats),
            all_shared=(not missing_seats) and human_shared,
        )

    @pytest.mark.asyncio
    async def test_missing_crew_listed(self) -> None:
        ss = self._share(missing_names=("阿明", "小美"), missing_seats=("crew_2", "crew_3"))
        with _patch_human(True, 20):
            out = await panel.build_signal_panel(uuid4(), "1.1a", share_status=ss)
        assert "全員分享" in out
        assert "阿明" in out and "小美" in out
        assert "還沒分享過自身經驗" in out

    @pytest.mark.asyncio
    async def test_all_shared(self) -> None:
        ss = self._share(human_shared=True, missing_names=(), missing_seats=())
        with _patch_human(True, 20):
            out = await panel.build_signal_panel(uuid4(), "1.1a", share_status=ss)
        assert "大家都分享過自身經驗了" in out

    @pytest.mark.asyncio
    async def test_all_ai_room(self) -> None:
        ss = self._share(has_human=False, human_shared=True)
        with _patch_human(False, 0):
            out = await panel.build_signal_panel(uuid4(), "1.1a", share_status=ss)
        assert "全 AI 房" in out

    @pytest.mark.asyncio
    async def test_non_share_phase_has_no_share_line(self) -> None:
        # 非 1.1a：_share_line 回 None，面板不含「全員分享」。
        with _patch_human(True, 20):
            out = await panel.build_signal_panel(uuid4(), "1.2", share_status=None)
        assert out is None or "全員分享" not in out
