"""暖場 macro stage（warmup）— Phase 42 B1 目標導向重設計測試（spec 28 v2.0）。

涵蓋（phase-42.md B1 驗證清單）：
- 骨架不變式：warmup 為第一 macro stage、0.0/0.0a 歸屬、入口落點、macro 邊界。
- 固定時長：三 preset 0.0a 預算＝300 秒（硬 5 分）、軟檢核點 180 秒、custom 強制覆寫。
- 三情境分支：classify_scenario（達標提前/軟到未達/硬到未達/進行中）。
- 退場公式（§5.1＋live 防死鎖偏離）：(達標 AND 全員參與) OR 硬上限——warmup_status.ready。
- 推進 gate：組長提早宣布 → 擋下＋內容層缺項；ready → 放行。
- Evaluator：只寫邊界訊號、不再直接推進（橋接必經的結構保證）。
- watcher 兜底：硬上限 AND 組長失能（雙條件）；樣板含橋接。
- 雙工具 gate：0.0a R1＝貼AND聊、R2+＝任一（round_lock 型態表）。
- cap 8（crew）／cap 1（組長限示範）／0.0a 去重觸發。
- goal 縮放 8/11/16/20（intensity 細節另見 test_intensity_scaling）。
- MC／樂隊 prompt 內容（v2.0 元素齊、v1.0 殘文清零）。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agents.stage_advancement import _STAGE_ORDER, get_next_stage
from app.stages.micro_phases import (
    get_first_micro_phase_for_stage,
    get_macro_stage,
    is_macro_boundary,
)
from app.stages.sub_phases import SUB_PHASES, get_first_sub_phase_of_macro
from app.timer.calculator import (
    PRESETS,
    WARMUP_HARD_BUDGET_MINUTES,
    WARMUP_SOFT_SECONDS,
    compute_sub_phase_budgets,
)


class TestWarmupStageSkeleton:
    def test_warmup_is_first_macro_stage(self) -> None:
        assert _STAGE_ORDER[0] == "warmup"
        assert get_next_stage("warmup") == "discover"

    def test_micro_and_sub_belong_to_warmup(self) -> None:
        assert get_macro_stage("0.0") == "warmup"
        assert SUB_PHASES["0.0a"].macro_stage == "warmup"
        assert SUB_PHASES["0.0a"].parent_micro_phase == "0.0"

    def test_entry_points(self) -> None:
        assert get_first_micro_phase_for_stage("warmup") == "0.0"
        assert get_first_sub_phase_of_macro("warmup") == "0.0a"
        assert get_first_micro_phase_for_stage("discover") == "1.1"
        assert get_first_sub_phase_of_macro("discover") == "1.1a"

    def test_warmup_to_discover_is_macro_boundary(self) -> None:
        # Phase 42 C1：micro 0.1 移除——discover 首桶＝1.1。
        assert is_macro_boundary("0.0", "1.1") is True

    def test_icebreaker_zone_visible_in_0_0a(self) -> None:
        from app.canvas.zones import ZONES
        assert "0.0a" in ZONES["icebreaker_zone"].phase_visible


# ---------------------------------------------------------------------------
# 固定時長：軟 3／硬 5 分、所有 preset 相同（spec 16 §2.1/§4.4 v2.0；#19 唯一例外）
# ---------------------------------------------------------------------------

class TestWarmupFixedDuration:
    def test_constants(self) -> None:
        assert WARMUP_HARD_BUDGET_MINUTES == 5
        assert WARMUP_SOFT_SECONDS == 180

    def test_all_presets_warmup_budget_is_300s(self) -> None:
        for pid, cfg in PRESETS.items():
            assert cfg.macro_budgets["warmup"] == 5, pid
            assert compute_sub_phase_budgets(cfg)["0.0a"] == 300, pid

    def test_schema_default_warmup_is_5(self) -> None:
        from app.timer.schemas import TimerConfig
        assert TimerConfig().macro_budgets["warmup"] == 5

    @pytest.mark.asyncio
    async def test_initialize_project_forces_fixed_warmup_for_custom(self) -> None:
        """custom 帶舊值（warmup=2、0.0a=2）→ initialize_project 強制覆寫成 5。"""
        from app.timer.schemas import TimerConfig
        from app.timer.service import TimerService

        captured: dict = {}

        class _FakeSession:
            async def execute(self, stmt):  # noqa: ANN001
                # update(Project).values(...) — 攔截寫入值
                captured.update(stmt.compile().params)

            async def commit(self) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):  # noqa: ANN002
                return False

        cfg = TimerConfig(
            total_session_minutes=120,
            macro_budgets={"warmup": 2, "discover": 70, "define": 48},
            sub_phase_overrides={"0.0a": 2, "1.1a": 10},
            preset_id="custom",
        )
        with patch(
            "app.timer.service.async_session_factory", new=lambda: _FakeSession()
        ):
            result = await TimerService.initialize_project(uuid4(), config=cfg)

        assert result.macro_budgets["warmup"] == 5
        assert result.sub_phase_overrides["0.0a"] == 5
        assert result.sub_phase_overrides["1.1a"] == 10  # 其餘 override 不動
        assert captured["timer_config"]["macro_budgets"]["warmup"] == 5


# ---------------------------------------------------------------------------
# 三情境（spec 28 §5.2）＋退場公式（§5.1）— progression/warmup_exit.py
# ---------------------------------------------------------------------------

from app.progression.warmup_exit import classify_scenario  # noqa: E402


class TestScenarioClassification:
    def test_goal_reached_is_scenario_1_anytime(self) -> None:
        # 3 分內達標、3–5 分中途達標 → 都立即進情境 1
        assert classify_scenario(True, False, False) == 1
        assert classify_scenario(True, True, False) == 1
        assert classify_scenario(True, True, True) == 1

    def test_soft_reached_unmet_is_scenario_2(self) -> None:
        assert classify_scenario(False, True, False) == 2

    def test_hard_reached_unmet_is_scenario_3(self) -> None:
        assert classify_scenario(False, True, True) == 3

    def test_in_progress_is_none(self) -> None:
        assert classify_scenario(False, False, False) is None


def _patch_status_inputs(
    *,
    note_count: int | None,
    goal_intensity_cfg=None,
    elapsed: int | None,
    human_ok: bool = True,
    missing_crews: tuple[str, ...] = (),
):
    """warmup_status 的四個資料源全 patch（純單元、不碰 DB/Redis/canvas）。"""
    from app.progression import warmup_exit as we

    return (
        patch.object(we, "_count_warmup_notes", new=AsyncMock(return_value=note_count)),
        patch.object(
            we, "_participation",
            new=AsyncMock(return_value=(human_ok, missing_crews)),
        ),
        patch(
            "app.timer.service.TimerService.get_config",
            new=AsyncMock(return_value=goal_intensity_cfg),
        ),
        patch(
            "app.timer.service.TimerService.get_used_seconds",
            new=AsyncMock(return_value=elapsed),
        ),
    )


class TestWarmupExitFormula:
    @pytest.mark.asyncio
    async def test_goal_reached_early_is_ready(self) -> None:
        """達標提前：60 秒就湊滿 → ready（不等任何時間）。"""
        from app.progression.warmup_exit import warmup_status

        patches = _patch_status_inputs(note_count=20, elapsed=60)
        with patches[0], patches[1], patches[2], patches[3]:
            st = await warmup_status(uuid4())
        assert st.goal == 20  # config None → intensity 1.0
        assert st.goal_reached and st.ready
        assert st.scenario == 1
        assert not st.soft_reached and not st.hard_reached

    @pytest.mark.asyncio
    async def test_goal_reached_but_crew_missing_blocks(self) -> None:
        """達標但有 crew 沒玩到 → 全員參與不滿足、不 ready（缺項點名）。"""
        from app.progression.warmup_exit import warmup_status

        patches = _patch_status_inputs(
            note_count=20, elapsed=60, missing_crews=("小美",),
        )
        with patches[0], patches[1], patches[2], patches[3]:
            st = await warmup_status(uuid4())
        assert st.goal_reached and not st.ready
        assert any("小美" in m for m in st.missing_zh)

    @pytest.mark.asyncio
    async def test_human_not_participated_blocks(self) -> None:
        from app.progression.warmup_exit import warmup_status

        patches = _patch_status_inputs(note_count=20, elapsed=60, human_ok=False)
        with patches[0], patches[1], patches[2], patches[3]:
            st = await warmup_status(uuid4())
        assert not st.ready
        assert any("還沒聽到你的點子" in m for m in st.missing_zh)

    @pytest.mark.asyncio
    async def test_hard_limit_unmet_is_ready_scenario_3(self) -> None:
        """硬上限 5 分到、未達標 → ready（坦白收尾、不硬卡）＋情境 3。"""
        from app.progression.warmup_exit import warmup_status

        patches = _patch_status_inputs(note_count=9, elapsed=301)
        with patches[0], patches[1], patches[2], patches[3]:
            st = await warmup_status(uuid4())
        assert st.hard_reached and st.ready
        assert st.scenario == 3

    @pytest.mark.asyncio
    async def test_soft_reached_unmet_not_ready_scenario_2(self) -> None:
        """軟 3 分到、未達標 → 不 ready（情境 2＝宣布延長，不收尾）。"""
        from app.progression.warmup_exit import warmup_status

        patches = _patch_status_inputs(note_count=13, elapsed=185)
        with patches[0], patches[1], patches[2], patches[3]:
            st = await warmup_status(uuid4())
        assert st.soft_reached and not st.hard_reached
        assert not st.ready
        assert st.scenario == 2
        assert any("13" in m and "20" in m for m in st.missing_zh)

    @pytest.mark.asyncio
    async def test_timer_not_started_only_goal_path(self) -> None:
        """timer 未啟動（elapsed None）→ 軟硬皆 False，仍可走達標路徑。"""
        from app.progression.warmup_exit import warmup_status

        patches = _patch_status_inputs(note_count=20, elapsed=None)
        with patches[0], patches[1], patches[2], patches[3]:
            st = await warmup_status(uuid4())
        assert st.ready and st.scenario == 1

    @pytest.mark.asyncio
    async def test_canvas_unreadable_is_conservative(self) -> None:
        """白板讀不到（note_count None）→ 不視為達標；缺項提示看不清楚、先繼續玩。"""
        from app.progression.warmup_exit import warmup_status

        patches = _patch_status_inputs(note_count=None, elapsed=60)
        with patches[0], patches[1], patches[2], patches[3]:
            st = await warmup_status(uuid4())
        assert not st.goal_reached and not st.ready
        assert any("看不清楚" in m for m in st.missing_zh)


class TestWarmupGoalScaling:
    def test_goal_scales_8_11_16_20(self) -> None:
        """spec 16 §2.4：40→8、60→11、90→16、custom(1.0)→20（地板 8）。"""
        from app.timer.scaling import effective_warmup_goal

        assert effective_warmup_goal(PRESETS["timer_preset_40min"]) == 8
        assert effective_warmup_goal(PRESETS["timer_preset_60min"]) == 11
        assert effective_warmup_goal(PRESETS["timer_preset_90min"]) == 16
        assert effective_warmup_goal(None) == 20


# ---------------------------------------------------------------------------
# 推進 gate：組長宣布收尾走 §5.1 公式（advance_router 暖場分支）
# ---------------------------------------------------------------------------

class TestWarmupAdvanceGate:
    @pytest.mark.asyncio
    async def test_gate_delegates_to_warmup_exit_and_blocks(self) -> None:
        from app.progression.advance_router import gates_pass_with_reason

        with patch(
            "app.progression.warmup_exit.warmup_gate",
            new=AsyncMock(return_value=(False, "暖場便條目前 5 張、目標 8 張")),
        ):
            passed, reason = await gates_pass_with_reason(uuid4(), "0.0a")
        assert passed is False
        assert "目標 8 張" in reason

    @pytest.mark.asyncio
    async def test_gate_passes_when_ready(self) -> None:
        from app.progression.advance_router import gates_pass_with_reason

        with patch(
            "app.progression.warmup_exit.warmup_gate",
            new=AsyncMock(return_value=(True, "")),
        ):
            passed, reason = await gates_pass_with_reason(uuid4(), "0.0a")
        assert passed is True and reason == ""

    @pytest.mark.asyncio
    async def test_supervisor_early_advance_blocked_end_to_end(self) -> None:
        """組長提早 advance（stage 跨界）→ blocked 字串帶內容層缺項。"""
        from app.progression.advance_router import (
            execute_advance_target,
            resolve_advance_target,
        )

        target = resolve_advance_target("0.0a")
        assert target.kind == "stage" and target.from_stage == "warmup"
        with patch(
            "app.progression.warmup_exit.warmup_gate",
            new=AsyncMock(return_value=(False, "使用者還沒玩到")),
        ):
            result = await execute_advance_target(
                project_id=uuid4(), agent_id="agent_supervisor", target=target,
            )
        assert result.startswith("sub_advance_blocked:artifact_gate:")
        assert "使用者還沒玩到" in result


# ---------------------------------------------------------------------------
# Evaluator：只寫邊界訊號、不再直接推進（橋接必經＝常態唯一路徑是組長宣布）
# ---------------------------------------------------------------------------

def _make_evaluator():
    from app.agents.evaluator import StageEvaluator
    return StageEvaluator(project_id=uuid4(), agent_id="agent_supervisor")


def _fake_status(**overrides):
    from app.progression.warmup_exit import WarmupStatus

    base = dict(
        note_count=20, goal=20, elapsed_seconds=60,
        soft_reached=False, hard_reached=False, goal_reached=True,
        human_participated=True, missing_crews=(),
        scenario=1, ready=True, missing_zh=(),
    )
    base.update(overrides)
    return WarmupStatus(**base)


@pytest.mark.asyncio
async def test_evaluator_warmup_ready_writes_boundary_signal_no_advance():
    ev = _make_evaluator()
    sig = AsyncMock()
    with (
        patch(
            "app.progression.warmup_exit.warmup_status",
            new=AsyncMock(return_value=_fake_status()),
        ),
        patch("app.progression.boundary_signal.set_boundary_signal", new=sig),
    ):
        result = await ev._evaluate_warmup(recent_chat=[])
    assert result.passed is True
    assert result.action_taken == "boundary_signal"  # 不是 advanced_to_*
    sig.assert_awaited_once()
    assert sig.call_args.kwargs["ready"] is True
    assert sig.call_args.kwargs["sub_phase"] == "0.0a"


@pytest.mark.asyncio
async def test_evaluator_warmup_not_ready_reports_missing():
    ev = _make_evaluator()
    sig = AsyncMock()
    with (
        patch(
            "app.progression.warmup_exit.warmup_status",
            new=AsyncMock(return_value=_fake_status(
                goal_reached=False, ready=False, scenario=None, note_count=3,
                missing_zh=("暖場便條目前 3 張、目標 20 張——還可以再衝一波",),
            )),
        ),
        patch("app.progression.boundary_signal.set_boundary_signal", new=sig),
    ):
        result = await ev._evaluate_warmup(recent_chat=[])
    assert result.passed is False and result.action_taken == "none"
    assert sig.call_args.kwargs["ready"] is False
    assert any("3 張" in w for w in sig.call_args.kwargs["weak_areas"])


def test_evaluator_has_no_direct_advance_anymore():
    """B1 結構保證：evaluator 不再有任何直接推進入口（橋接必經）。"""
    ev = _make_evaluator()
    assert not hasattr(ev, "_advance_stage")
    assert not hasattr(ev, "_advance_micro_phase")


# ---------------------------------------------------------------------------
# watcher 兜底：硬上限 AND 組長失能（雙條件，spec 28 §5.4）＋樣板含橋接
# ---------------------------------------------------------------------------

from app.progression import supervisor_activity as _sa  # noqa: E402
from app.progression import watcher as _w  # noqa: E402


class TestWarmupWatcherBackstop:
    @pytest.mark.asyncio
    async def test_no_advance_before_hard_limit_even_if_stalled(self) -> None:
        pid = uuid4()
        with (
            patch.object(_w, "_get_used_pct", new=AsyncMock(return_value=80.0)),
            patch.object(_sa, "supervisor_stalled", new=AsyncMock(return_value=True)),
            patch.object(_w, "_advance", new=AsyncMock()) as adv,
        ):
            await _w._check_one(pid, "0.0a")
        adv.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_advance_at_hard_limit_when_supervisor_alive(self) -> None:
        """硬上限到、組長健在 → 情境 3 是組長的事，watcher 不動。"""
        pid = uuid4()
        with (
            patch.object(_w, "_get_used_pct", new=AsyncMock(return_value=120.0)),
            patch.object(_sa, "supervisor_stalled", new=AsyncMock(return_value=False)),
            patch.object(_w, "_advance", new=AsyncMock()) as adv,
        ):
            await _w._check_one(pid, "0.0a")
        adv.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_advance_when_hard_limit_and_stalled(self) -> None:
        pid = uuid4()
        with (
            patch.object(_w, "_get_used_pct", new=AsyncMock(return_value=101.0)),
            patch.object(_sa, "supervisor_stalled", new=AsyncMock(return_value=True)),
            patch.object(_w, "_advance", new=AsyncMock()) as adv,
        ):
            await _w._check_one(pid, "0.0a")
        adv.assert_awaited_once()
        assert adv.call_args.kwargs.get("reason") == "warmup_time_box"
        assert adv.call_args.kwargs.get("skip_gate_check") is True

    @pytest.mark.asyncio
    async def test_backstop_template_contains_bridge(self) -> None:
        """兜底樣板＝坦白收尾＋橋接精神（不假裝達標）。"""
        pid = uuid4()
        said: list[str] = []

        async def _capture(project_id, body, stage):  # noqa: ANN001
            said.append(body)

        with patch.object(_w, "_say", new=_capture):
            await _w._announce_transition(pid, "0.0a", "1.1a", "warmup_time_box")
        assert len(said) == 1
        assert "換個角度看熟悉東西" in said[0]
        assert "暖場" in said[0]
        assert "達標" not in said[0]  # 不假裝達標、也不提內部判定


# ---------------------------------------------------------------------------
# 雙工具 gate（0.0a 教學回合；權威測試在 test_round_lock，這裡鎖型態表）
# ---------------------------------------------------------------------------

class TestWarmupDualToolGate:
    def test_round1_requires_note_and_chat(self) -> None:
        from app.agents.round_lock import gate_types_for

        types, mode = gate_types_for("0.0a", 1)
        assert set(types) == {"note", "chat"} and mode == "all"

    def test_round2_plus_any_tool(self) -> None:
        from app.agents.round_lock import gate_types_for

        types, mode = gate_types_for("0.0a", 2)
        assert set(types) == {"note", "chat"} and mode == "any"


# ---------------------------------------------------------------------------
# canvas：cap 8／組長限示範 1／0.0a 去重觸發（spec 28 §3.2/§4/§6）
# ---------------------------------------------------------------------------

class TestWarmupNoteCaps:
    def test_cap_constants(self) -> None:
        from app.canvas.tools_manipulation import (
            _WARMUP_PER_AGENT_NOTE_CAP,
            _WARMUP_SUPERVISOR_NOTE_CAP,
        )

        assert _WARMUP_PER_AGENT_NOTE_CAP == 8
        assert _WARMUP_SUPERVISOR_NOTE_CAP == 1

    def test_warmup_dedupe_enabled(self) -> None:
        from app.canvas.tools_manipulation import _should_dedupe_sub_phase

        assert _should_dedupe_sub_phase("0.0a") is True

    @pytest.mark.asyncio
    async def test_crew_ninth_note_rejected(self) -> None:
        from app.canvas.analyzer import CanvasAnalysis
        from app.canvas.clustering import ClusterState
        from app.canvas.spatial import SpatialNote

        author_tag = "張志強(ai)"
        notes = [
            SpatialNote(
                id=f"n{i}", text=f"暖場點子{i}", x=0, y=0, width=200, height=150,
                color="yellow", author_type="ai", created_at="",
                author_name=author_tag, kind="content",
            )
            for i in range(8)
        ]
        analysis = CanvasAnalysis(notes=notes, cluster_state=ClusterState())
        with (
            patch("app.canvas.tools_manipulation.get_spatial_analyzer") as mock_sa,
            patch("app.canvas.tools_manipulation.canvas_ops") as mock_ops,
        ):
            mock_sa.return_value.analyze = AsyncMock(return_value=analysis)
            mock_ops.add_note = AsyncMock(return_value="new_id")

            from app.canvas.tools_manipulation import tool_create_note
            result = await tool_create_note(
                project_id=uuid4(), text="第九張", author_id="agent_x",
                author_name="張志強", author_type="ai", sub_phase_id="0.0a",
            )
        assert result["success"] is False
        assert result["rejection"]["rule_name"] == "warmup_per_agent_note_cap"
        mock_ops.add_note.assert_not_called()

    @pytest.mark.asyncio
    async def test_supervisor_second_demo_note_rejected(self) -> None:
        """組長已貼 1 張示範 → 第 2 張內容便條被擋（限示範，spec 28 §4）。"""
        from app.canvas.analyzer import CanvasAnalysis
        from app.canvas.clustering import ClusterState
        from app.canvas.spatial import SpatialNote

        demo = SpatialNote(
            id="demo", text="掰直當烤棉花糖的長叉", x=0, y=0, width=200, height=150,
            color="yellow", author_type="ai", created_at="",
            author_name="阿哲(ai)", kind="content",
        )
        analysis = CanvasAnalysis(notes=[demo], cluster_state=ClusterState())
        with (
            patch("app.canvas.tools_manipulation.get_spatial_analyzer") as mock_sa,
            patch("app.canvas.tools_manipulation.canvas_ops") as mock_ops,
        ):
            mock_sa.return_value.analyze = AsyncMock(return_value=analysis)
            mock_ops.add_note = AsyncMock(return_value="new_id")

            from app.canvas.tools_manipulation import tool_create_note
            result = await tool_create_note(
                project_id=uuid4(), text="再丟一個妙用", author_id="agent_supervisor",
                author_name="阿哲", author_type="ai", sub_phase_id="0.0a",
                seat_role="supervisor",
            )
        assert result["success"] is False
        assert result["rejection"]["rule_name"] == "warmup_per_agent_note_cap"
        assert "示範" in result["rejection"]["reason_zh"]

    @pytest.mark.asyncio
    async def test_supervisor_label_note_not_capped(self) -> None:
        """標題便條（kind=label）不吃 cap——組長已有示範便條仍可貼標題。"""
        from app.canvas.analyzer import CanvasAnalysis
        from app.canvas.clustering import ClusterState
        from app.canvas.spatial import SpatialNote
        from app.canvas.tools_manipulation import CreateNoteOutcome

        demo = SpatialNote(
            id="demo", text="掰直當烤棉花糖的長叉", x=0, y=0, width=200, height=150,
            color="yellow", author_type="ai", created_at="",
            author_name="阿哲(ai)", kind="content",
        )
        analysis = CanvasAnalysis(notes=[demo], cluster_state=ClusterState())
        with (
            patch("app.canvas.tools_manipulation.get_spatial_analyzer") as mock_sa,
            patch("app.canvas.tools_manipulation.canvas_ops") as mock_ops,
            patch(
                "app.canvas.tools_manipulation._resolve_concept_position",
                new=AsyncMock(return_value=(120.0, 120.0)),
            ),
            patch(
                "app.canvas.tools_manipulation._evaluate_create_gates",
                new=AsyncMock(return_value=CreateNoteOutcome(
                    success=True, zone_id="icebreaker_zone",
                )),
            ),
        ):
            mock_sa.return_value.analyze = AsyncMock(return_value=analysis)
            mock_sa.return_value.invalidate_semantic_cache = AsyncMock()
            mock_ops.add_note = AsyncMock(return_value="label_id")

            from app.canvas.tools_manipulation import tool_create_note
            result = await tool_create_note(
                project_id=uuid4(), text="破冰時間｜額外用途發想",
                author_id="agent_supervisor", author_name="阿哲", author_type="ai",
                sub_phase_id="0.0a", kind="label", seat_role="supervisor",
            )
        assert result["success"] is True


# ---------------------------------------------------------------------------
# A1 trigger / zone 標題（#13）
# ---------------------------------------------------------------------------

class TestWarmupEntryTouchpoints:
    def test_a1_announce_includes_0_0a(self) -> None:
        from app.agents.supervisor.triggers_a import _ANNOUNCE_PHASES

        assert "0.0a" in _ANNOUNCE_PHASES

    def test_icebreaker_zone_title_no_longer_hardcoded(self) -> None:
        from app.canvas.zones import ZONES

        assert ZONES["icebreaker_zone"].visual.title_sticky == ""

    def test_old_15char_45s_model_removed(self) -> None:
        from app.progression import watcher as w

        for sym in (
            "_HUMAN_PARTICIPATION_SUB_PHASES",
            "_human_participated_in_warmup",
            "_warmup_human_ready",
            "_WARMUP_SUBSTANTIVE_MIN_CHARS",
        ):
            assert not hasattr(w, sym), sym


# ---------------------------------------------------------------------------
# 暖場版訊號面板（三情境收尾指引）
# ---------------------------------------------------------------------------

class TestWarmupSignalPanel:
    @pytest.mark.asyncio
    async def test_panel_shows_progress_and_scenario_hint(self) -> None:
        from app.progression.signal_panel import build_signal_panel

        with (
            patch(
                "app.progression.warmup_exit.warmup_status",
                new=AsyncMock(return_value=_fake_status(
                    note_count=13, goal=20, goal_reached=False,
                    elapsed_seconds=185, soft_reached=True,
                    ready=False, scenario=2,
                )),
            ),
            patch(
                "app.agents.round_lock.get_state",
                new=AsyncMock(return_value={
                    "has_human": True, "round": 2, "waiting": False,
                    "ai_crew_total": 3, "crews_acted": [],
                    "human_satisfied": False,
                    "required": {"note": True, "chat": True, "mode": "any"},
                }),
            ),
        ):
            panel = await build_signal_panel(uuid4(), "0.0a")
        assert panel is not None
        assert "13 / 目標 20" in panel
        assert "軟目標 3 分鐘、硬上限 5 分鐘" in panel
        assert "宣布把時間延長到 5 分鐘" in panel  # 情境 2 指引

    @pytest.mark.asyncio
    async def test_panel_goal_reached_hint(self) -> None:
        from app.progression.signal_panel import build_signal_panel

        with (
            patch(
                "app.progression.warmup_exit.warmup_status",
                new=AsyncMock(return_value=_fake_status()),
            ),
            patch(
                "app.agents.round_lock.get_state",
                new=AsyncMock(return_value={"has_human": False, "round": 1, "waiting": False}),
            ),
        ):
            panel = await build_signal_panel(uuid4(), "0.0a")
        assert panel is not None
        assert "已達標" in panel
        assert "收尾橋接" in panel  # 情境 1 指引


# ---------------------------------------------------------------------------
# Prompt 層：MC 腳本 v2.0 元素齊、v1.0 殘文清零；樂隊回合鎖節制
# ---------------------------------------------------------------------------

class TestWarmupGame:
    def test_fifteen_items_with_demo_seed(self) -> None:
        from app.agents.prompts.warmup_game import WARMUP_ITEMS

        assert len(WARMUP_ITEMS) == 15
        for it in WARMUP_ITEMS:
            assert it.name and it.demo_seed
            assert len(it.alt_uses) >= 1

    def test_pick_item_deterministic(self) -> None:
        from app.agents.prompts.warmup_game import pick_item

        assert pick_item("project-xyz") == pick_item("project-xyz")
        picks = {pick_item(f"p{i}").name for i in range(60)}
        assert len(picks) >= 5

    def test_mc_prompt_v2_scaffold(self) -> None:
        """開場鷹架：標題 label、唯一示範便條、目標宣告、便條規則、雙工具教學。"""
        from app.agents.prompts.warmup_game import (
            WARMUP_TITLE_LABEL,
            pick_item,
            render_warmup_mc_prompt,
        )

        it = pick_item("proj")
        mc = render_warmup_mc_prompt(it)
        assert it.name in mc and it.demo_seed in mc
        assert WARMUP_TITLE_LABEL in mc
        assert 'kind="label"' in mc
        assert "示範便條只能這一張" in mc
        assert "宣告團隊目標" in mc
        assert "貼一張便條" in mc and "聊天室" in mc  # 雙工具
        assert "set_user_task" in mc
        assert "不可以代貼" in mc

    def test_mc_prompt_three_scenarios_and_bridge(self) -> None:
        from app.agents.prompts.warmup_game import pick_item, render_warmup_mc_prompt

        mc = render_warmup_mc_prompt(pick_item("proj"))
        assert "達標" in mc and "延長" in mc and "五分鐘" in mc
        assert "坦白" in mc or "老實說" in mc
        assert "收尾橋接" in mc and "advance_sub_phase" in mc
        assert "不可逐字背稿" in mc
        assert "這個我沒想到" in mc  # 慶祝清單外點子

    def test_mc_prompt_v1_framing_removed(self) -> None:
        from app.agents.prompts.warmup_game import pick_item, render_warmup_mc_prompt

        mc = render_warmup_mc_prompt(pick_item("proj"))
        assert "先別急著貼便條" not in mc
        assert "比爛" not in mc  # 「求巧不比爛」框架作廢
        assert "四拍" not in mc
        assert "示範用**講的**就好" not in mc

    def test_band_prompt_round_lock_restraint(self) -> None:
        from app.agents.prompts.warmup_game import pick_item, render_warmup_band_prompt

        band = render_warmup_band_prompt(pick_item("proj"))
        assert "被組長點到名才接" in band
        assert "每回合至多一則" in band
        assert "最妙的留給人" in band
        assert "永不批評" in band
        assert "group_id" in band  # 不分群提醒


class TestWarmupAssemblerInjection:
    def _ctx(self, seat: str) -> dict:
        return {
            "my_seat": seat,
            "current_stage": "warmup",
            "current_sub_phase": "0.0a",
            "project_id": "proj-1",
            "phase_strategy": {"supervisor_mode": "facilitator"},
        }

    def test_supervisor_gets_mc_prompt(self) -> None:
        from app.agents.prompts.assembler import PromptAssembler
        from app.agents.prompts.warmup_game import pick_item

        msgs = PromptAssembler().assemble(self._ctx("supervisor"))
        system = "\n".join(m["content"] for m in msgs if m["role"] == "system")
        item = pick_item("proj-1")
        assert "組長 MC" in system and item.demo_seed in system

    def test_crew_gets_band_prompt(self) -> None:
        from app.agents.prompts.assembler import PromptAssembler

        msgs = PromptAssembler().assemble(self._ctx("crew_1"))
        system = "\n".join(m["content"] for m in msgs if m["role"] == "system")
        assert "你是樂隊" in system and "被組長點到名才接" in system


class TestWarmupRetarget:
    """Phase 38 retarget 不變式（B1 沿用）。"""

    def test_open_share_surge_removed(self) -> None:
        from app.agents.turn_controller import _OPEN_SHARE_SUB_PHASES

        assert _OPEN_SHARE_SUB_PHASES == frozenset()

    def test_one_one_a_restored_to_discover(self) -> None:
        sp = SUB_PHASES["1.1a"]
        assert sp.macro_stage == "discover"
        assert "暖場破冰" not in sp.name_zh

    def test_icebreaker_zone_shared_by_warmup_and_discover(self) -> None:
        from app.canvas.zones import ZONES

        assert ZONES["icebreaker_zone"].phase_visible == ("0.0a", "1.1a")


# ---------------------------------------------------------------------------
# B1 review 補測：_participation 真實 state 形狀／_count_warmup_notes label 排除／
# initialize_project 已知 preset 路徑（覆蓋 review 確認的三個 HIGH 測試缺口）
# ---------------------------------------------------------------------------


class TestParticipationLogic:
    @staticmethod
    def _state(**overrides):
        base = {
            "has_human": True, "round": 1, "waiting": False,
            "ai_crew_total": 2, "crews_acted": [],
            "human_satisfied": False,
            "required": {"note": True, "chat": True, "mode": "all"},
            "human_inputs": [], "participated_crews": [], "ai_crew": ["crew_1", "crew_2"],
        }
        base.update(overrides)
        return base

    @pytest.mark.asyncio
    async def test_round_2_means_human_participated(self) -> None:
        from app.progression.warmup_exit import _participation

        with patch(
            "app.agents.round_lock.get_state",
            new=AsyncMock(return_value=self._state(
                round=2, participated_crews=["crew_1", "crew_2"],
            )),
        ):
            human_ok, missing = await _participation(uuid4())
        assert human_ok is True and missing == ()

    @pytest.mark.asyncio
    async def test_round1_human_inputs_fallback(self) -> None:
        """round 仍是 1 但本回合已有過檢核輸入 → 視為已參與。"""
        from app.progression.warmup_exit import _participation

        with patch(
            "app.agents.round_lock.get_state",
            new=AsyncMock(return_value=self._state(
                human_inputs=["note"], participated_crews=["crew_1", "crew_2"],
            )),
        ):
            human_ok, missing = await _participation(uuid4())
        assert human_ok is True and missing == ()

    @pytest.mark.asyncio
    async def test_round1_no_inputs_not_participated_and_missing_crews(self) -> None:
        from app.progression.warmup_exit import _participation

        with (
            patch(
                "app.agents.round_lock.get_state",
                new=AsyncMock(return_value=self._state(
                    participated_crews=["crew_1"],
                )),
            ),
            patch(
                "app.agents.personas.display.resolve_display_name",
                new=lambda seat: f"夥伴{seat[-1]}",
            ),
        ):
            human_ok, missing = await _participation(uuid4())
        assert human_ok is False
        assert missing == ("夥伴2",)  # crew_2 還沒出聲，以顯示名回報

    @pytest.mark.asyncio
    async def test_all_ai_short_circuit(self) -> None:
        from app.progression.warmup_exit import _participation

        with patch(
            "app.agents.round_lock.get_state",
            new=AsyncMock(return_value=self._state(has_human=False)),
        ):
            human_ok, missing = await _participation(uuid4())
        assert human_ok is True and missing == ()


class TestCountWarmupNotes:
    @pytest.mark.asyncio
    async def test_labels_excluded_content_counted(self) -> None:
        from app.canvas.analyzer import CanvasAnalysis
        from app.canvas.clustering import ClusterState
        from app.canvas.spatial import SpatialNote
        from app.progression.warmup_exit import _count_warmup_notes

        def _note(i: int, kind: str) -> SpatialNote:
            return SpatialNote(
                id=f"n{i}", text=f"t{i}", x=0, y=0, width=200, height=150,
                color="yellow", author_type="ai", created_at="",
                author_name="x(ai)", kind=kind,
            )

        notes = [_note(0, "label"), _note(1, "content"), _note(2, "content"),
                 _note(3, "label")]
        analysis = CanvasAnalysis(notes=notes, cluster_state=ClusterState())
        with patch("app.canvas.analyzer.get_spatial_analyzer") as mock_sa:
            mock_sa.return_value.analyze = AsyncMock(return_value=analysis)
            assert await _count_warmup_notes(uuid4()) == 2

    @pytest.mark.asyncio
    async def test_analyzer_failure_returns_none(self) -> None:
        from app.progression.warmup_exit import _count_warmup_notes

        with patch("app.canvas.analyzer.get_spatial_analyzer") as mock_sa:
            mock_sa.return_value.analyze = AsyncMock(side_effect=RuntimeError("boom"))
            assert await _count_warmup_notes(uuid4()) is None


class TestInitializeProjectKnownPreset:
    @pytest.mark.asyncio
    async def test_known_preset_resolved_then_forced(self) -> None:
        """已知 preset＋無 overrides → 先還原權威 preset、再疊固定暖場（縮放 overrides 保留）。"""
        from app.timer.schemas import TimerConfig
        from app.timer.service import TimerService

        class _FakeSession:
            async def execute(self, stmt):  # noqa: ANN001
                pass

            async def commit(self) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):  # noqa: ANN002
                return False

        # 模擬前端只送部分欄位（無 sub_phase_overrides）＋ 舊 warmup 值。
        cfg = TimerConfig(
            total_session_minutes=40,
            intensity=0.4,
            macro_budgets={"warmup": 2, "discover": 23, "define": 15},
            preset_id="timer_preset_40min",
        )
        with patch(
            "app.timer.service.async_session_factory", new=lambda: _FakeSession()
        ):
            result = await TimerService.initialize_project(uuid4(), config=cfg)

        assert result.preset_id == "timer_preset_40min"
        assert result.macro_budgets["warmup"] == 5      # 強制固定
        assert result.macro_budgets["discover"] == 21   # 權威 preset 還原
        assert result.sub_phase_overrides["0.0a"] == 5
        # Phase 42 C1：preset 不再帶逐格絕對分鐘表（逐格上限由比例表推導，
        # spec 16 v2.0 §2.1）——權威 preset 只固定 0.0a。
        assert set(result.sub_phase_overrides.keys()) == {"0.0a"}


class TestWarmupHardLimitFinalOverride:
    """B1 live 驗收偏離（鐵律 #6）：硬上限＝最終覆蓋——crew 失能不參與不可卡死暖場。"""

    @pytest.mark.asyncio
    async def test_hard_limit_with_missing_crew_still_ready(self) -> None:
        from app.progression.warmup_exit import warmup_status

        patches = _patch_status_inputs(
            note_count=4, elapsed=301, missing_crews=("結構化專家",),
        )
        with patches[0], patches[1], patches[2], patches[3]:
            st = await warmup_status(uuid4())
        assert st.hard_reached
        assert st.ready  # 防死鎖：硬上限後全員參與不再阻擋（spec 28 §5.3 為準）
        assert st.scenario == 3

    @pytest.mark.asyncio
    async def test_hard_limit_human_absent_still_ready(self) -> None:
        """真人 AFK＋硬上限 → 照樣放行（對照 2026-06-08 盲測 1.1b 死鎖教訓）。"""
        from app.progression.warmup_exit import warmup_status

        patches = _patch_status_inputs(note_count=4, elapsed=320, human_ok=False)
        with patches[0], patches[1], patches[2], patches[3]:
            st = await warmup_status(uuid4())
        assert st.ready
