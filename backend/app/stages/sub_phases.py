"""Sub-phase definitions for Sticky-Only Strategy (Spec 13).

每個 sub-phase 對應 spec §8 五階段地圖中的一個 cell。包含：
  - id              "1.1a", "1.1b", ..., "4.3"
  - parent_micro_phase  對應現有 12-micro-phase 系統的 macro bucket（向下相容）
  - macro_stage     "discover" / "define" / "develop" / "deliver"
  - comm_modes      該 sub-phase 內的互動模式序列（可能含轉換，例 silent_write → reveal_round）
  - zones           本 sub-phase 啟用的 zone id 列表
  - target_count    達到便條數即可推進下一互動模式 / 下一 sub-phase（None 表示由 Supervisor 推進）
  - stability_timeout_seconds  silent_rearrange 連續無動作 N 秒自動推進
  - gate_modules    內容護欄模組（見 canvas/content_gate.py）
  - templates       便條紙文字模板識別碼（見 canvas/text_templates.py）

Spec 規定：
  - Phase 0 由現有 lobby 機制處理，不在本檔
  - 1.1a/1.1b/1.1c/1.1d 對應 Phase 1-1 的四個動作
  - 1.6 同時啟用 Empathy/Persona/Journey 三個模板
  - 4.1 拆為 a–f 六個子任務
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SubPhase:
    """單一 sub-phase 配置。"""

    id: str
    parent_micro_phase: str
    macro_stage: str
    name_zh: str
    comm_modes: tuple[str, ...] = ("discussion",)
    zones: tuple[str, ...] = ()
    target_count: int | None = None
    stability_timeout_seconds: int = 30
    gate_modules: tuple[str, ...] = ()
    templates: tuple[str, ...] = ()
    # 互動模式轉換訊號（依序）：
    # - "count":      target_count 達到
    # - "all_revealed":  reveal_round 所有人都唸完
    # - "stability":  silent_rearrange 連續無動作
    # - "supervisor":  Supervisor 主動推進
    transition_signals: tuple[str, ...] = ("supervisor",)


# 合法 comm_mode 列舉（schema-style）
COMM_MODES: frozenset[str] = frozenset({
    "silent_write",
    "reveal_round",
    "silent_rearrange",
    "discussion",
})


# ---------------------------------------------------------------------------
# Sub-phase registry — spec §8
# ---------------------------------------------------------------------------

SUB_PHASES: dict[str, SubPhase] = {
    # ── Phase 1 Discover ─────────────────────────────────────────
    "1.1a": SubPhase(
        id="1.1a",
        parent_micro_phase="1.1",
        macro_stage="discover",
        name_zh="經驗分享破冰",
        comm_modes=("reveal_round",),
        zones=("icebreaker_zone",),
        target_count=5,
        transition_signals=("all_revealed", "supervisor"),
    ),
    "1.1b": SubPhase(
        id="1.1b",
        parent_micro_phase="1.1",
        macro_stage="discover",
        name_zh="獨立列利害關係人",
        comm_modes=("silent_write",),
        zones=("stakeholder_private",),
        target_count=12,
        templates=("stakeholder",),
        transition_signals=("count", "supervisor"),
    ),
    "1.1c": SubPhase(
        id="1.1c",
        parent_micro_phase="1.1",
        macro_stage="discover",
        name_zh="揭示與歸類利害關係人",
        comm_modes=("reveal_round", "silent_rearrange"),
        zones=("stakeholder_public",),
        target_count=None,
        stability_timeout_seconds=30,
        transition_signals=("all_revealed", "stability", "supervisor"),
    ),
    "1.1d": SubPhase(
        id="1.1d",
        parent_micro_phase="1.1",
        macro_stage="discover",
        name_zh="Scope rationale",
        comm_modes=("discussion",),
        zones=("scope_zone",),
        templates=("scope_rationale",),
    ),
    "1.2": SubPhase(
        id="1.2",
        parent_micro_phase="1.2",
        macro_stage="discover",
        name_zh="分工調查",
        comm_modes=("discussion",),
        zones=("division_zone",),
    ),
    "1.3": SubPhase(
        id="1.3",
        parent_micro_phase="1.2",
        macro_stage="discover",
        name_zh="設計調查策略",
        comm_modes=("discussion",),
        zones=("interview_strategy_zone",),
    ),
    "1.4": SubPhase(
        id="1.4",
        parent_micro_phase="1.2",
        macro_stage="discover",
        name_zh="實地調查",
        comm_modes=("discussion",),
        zones=(),  # offline — 線下進行
    ),
    "1.5": SubPhase(
        id="1.5",
        parent_micro_phase="1.2",
        macro_stage="discover",
        name_zh="原始捕捉（延緩詮釋）",
        comm_modes=("silent_write",),
        zones=("raw_wall",),
        target_count=15,
        gate_modules=("no_interpretation",),
        templates=("raw_observation",),
        transition_signals=("count", "supervisor"),
    ),
    "1.6": SubPhase(
        id="1.6",
        parent_micro_phase="1.3",
        macro_stage="discover",
        name_zh="結構化模板（Empathy / Persona / Journey）",
        comm_modes=("discussion",),
        zones=(
            "empathy_says", "empathy_thinks", "empathy_does", "empathy_feels",
            "persona_card",
            "journey_map",
        ),
        gate_modules=("empathy_says_no_inference",),
    ),

    # ── Phase 2 Define ───────────────────────────────────────────
    "2.1": SubPhase(
        id="2.1",
        parent_micro_phase="2.1",
        macro_stage="define",
        name_zh="需求歸類",
        comm_modes=("silent_rearrange",),
        zones=("need_cluster_zone",),
        stability_timeout_seconds=30,
        transition_signals=("stability", "supervisor"),
    ),
    "2.2": SubPhase(
        id="2.2",
        parent_micro_phase="2.2",
        macro_stage="define",
        name_zh="POV 多候選生成",
        comm_modes=("silent_write", "reveal_round"),
        zones=("pov_wall",),
        target_count=3,
        gate_modules=("no_solution_language",),
        templates=("pov",),
        transition_signals=("count", "all_revealed", "supervisor"),
    ),
    "2.3": SubPhase(
        id="2.3",
        parent_micro_phase="2.2",
        macro_stage="define",
        name_zh="Socratic 追問",
        comm_modes=("discussion",),
        zones=("pov_wall",),
        gate_modules=("no_solution_language",),
    ),
    "2.4": SubPhase(
        id="2.4",
        parent_micro_phase="2.2",
        macro_stage="define",
        name_zh="既有解盤點",
        comm_modes=("discussion",),
        zones=("existing_solutions_zone",),
        gate_modules=("no_solution_language",),
    ),
    "2.5": SubPhase(
        id="2.5",
        parent_micro_phase="2.3",
        macro_stage="define",
        name_zh="建立收斂準則",
        comm_modes=("discussion",),
        zones=("define_criteria_sidebar",),
        templates=("criteria",),
        gate_modules=("no_solution_language",),
    ),
    "2.6": SubPhase(
        id="2.6",
        parent_micro_phase="2.3",
        macro_stage="define",
        name_zh="投票收斂",
        comm_modes=("discussion",),
        zones=("pov_wall", "define_criteria_sidebar"),
        gate_modules=("no_solution_language",),
    ),
    "2.7": SubPhase(
        id="2.7",
        parent_micro_phase="2.3",
        macro_stage="define",
        name_zh="改寫 HMW",
        comm_modes=("discussion",),
        zones=("hmw_dock",),
        templates=("hmw",),
        gate_modules=("no_solution_language",),
    ),

    # ── Phase 3 Develop ──────────────────────────────────────────
    "3.1": SubPhase(
        id="3.1",
        parent_micro_phase="3.1",
        macro_stage="develop",
        name_zh="選定 HMW",
        comm_modes=("discussion",),
        zones=("hmw_dock",),
        gate_modules=("no_feasibility_talk",),
    ),
    "3.2": SubPhase(
        id="3.2",
        parent_micro_phase="3.1",
        macro_stage="develop",
        name_zh="各自寫點子（發散）",
        comm_modes=("silent_write",),
        zones=("idea_pool",),
        target_count=20,
        gate_modules=("no_feasibility_talk",),
        templates=("idea",),
        transition_signals=("count", "supervisor"),
    ),
    "3.3": SubPhase(
        id="3.3",
        parent_micro_phase="3.2",
        macro_stage="develop",
        name_zh="揭示、結合、激發",
        comm_modes=("reveal_round", "discussion"),
        zones=("idea_pool",),
        gate_modules=("no_feasibility_talk",),
        transition_signals=("all_revealed", "supervisor"),
    ),
    "3.4": SubPhase(
        id="3.4",
        parent_micro_phase="3.3",
        macro_stage="develop",
        name_zh="多樣性檢查與 Category-shift",
        comm_modes=("discussion",),
        zones=("idea_pool",),
        gate_modules=("no_feasibility_talk",),
    ),

    # ── Phase 4 Deliver ──────────────────────────────────────────
    "4.1a": SubPhase(
        id="4.1a",
        parent_micro_phase="4.1",
        macro_stage="deliver",
        name_zh="可行性篩選",
        comm_modes=("discussion",),
        zones=("idea_pool",),
    ),
    "4.1b": SubPhase(
        id="4.1b",
        parent_micro_phase="4.1",
        macro_stage="deliver",
        name_zh="建立 Deliver 收斂準則",
        comm_modes=("discussion",),
        zones=("deliver_criteria_sidebar",),
        templates=("criteria",),
    ),
    "4.1c": SubPhase(
        id="4.1c",
        parent_micro_phase="4.1",
        macro_stage="deliver",
        name_zh="投票收斂解法",
        comm_modes=("discussion",),
        zones=("idea_pool", "deliver_criteria_sidebar"),
    ),
    "4.1d": SubPhase(
        id="4.1d",
        parent_micro_phase="4.1",
        macro_stage="deliver",
        name_zh="口頭闡明假設",
        comm_modes=("discussion",),
        zones=("hypothesis_wall",),
        templates=("hypothesis",),
    ),
    "4.1e": SubPhase(
        id="4.1e",
        parent_micro_phase="4.1",
        macro_stage="deliver",
        name_zh="定義 Task Ticket",
        comm_modes=("discussion",),
        zones=("task_area",),
        templates=("task_ticket",),
    ),
    "4.1f": SubPhase(
        id="4.1f",
        parent_micro_phase="4.1",
        macro_stage="deliver",
        name_zh="雛形製作（low-fidelity first）",
        comm_modes=("discussion",),
        zones=("prototype_zone",),
        gate_modules=("no_production_code",),
    ),
    "4.2": SubPhase(
        id="4.2",
        parent_micro_phase="4.2",
        macro_stage="deliver",
        name_zh="內部 Debrief",
        comm_modes=("discussion",),
        zones=("debrief_q1", "debrief_q2", "debrief_q3"),
    ),
    "4.3": SubPhase(
        id="4.3",
        parent_micro_phase="4.3",
        macro_stage="deliver",
        name_zh="決定去向（Close / Loop-D / Loop-F）",
        comm_modes=("discussion",),
        zones=("direction_zone",),
        templates=("direction",),
    ),
}


# 嚴格順序（用於 advance/next 推導）
SUB_PHASE_ORDER: tuple[str, ...] = (
    "1.1a", "1.1b", "1.1c", "1.1d",
    "1.2", "1.3", "1.4", "1.5", "1.6",
    "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7",
    "3.1", "3.2", "3.3", "3.4",
    "4.1a", "4.1b", "4.1c", "4.1d", "4.1e", "4.1f",
    "4.2", "4.3",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_sub_phase(sub_phase_id: str) -> SubPhase:
    """Get SubPhase by id. Raises KeyError if not found."""
    return SUB_PHASES[sub_phase_id]


def get_next_sub_phase(current: str) -> str | None:
    """Return the next sub-phase id, or None if at the end."""
    try:
        idx = SUB_PHASE_ORDER.index(current)
    except ValueError as exc:
        raise KeyError(f"Unknown sub_phase id: {current!r}") from exc

    next_idx = idx + 1
    if next_idx >= len(SUB_PHASE_ORDER):
        return None
    return SUB_PHASE_ORDER[next_idx]


def get_sub_phases_of(parent_micro_phase: str) -> list[SubPhase]:
    """All sub-phases under a given parent micro_phase id (e.g. '1.1')."""
    return [
        sp for sp in SUB_PHASES.values()
        if sp.parent_micro_phase == parent_micro_phase
    ]


def get_first_sub_phase_of_macro(macro_stage: str) -> str | None:
    """First sub-phase id for the given macro_stage."""
    for sub_phase_id in SUB_PHASE_ORDER:
        if SUB_PHASES[sub_phase_id].macro_stage == macro_stage:
            return sub_phase_id
    return None


def validate_sub_phase_advance(from_id: str, to_id: str) -> bool:
    """Forward advancement only (next-in-sequence)."""
    return get_next_sub_phase(from_id) == to_id


def is_sub_phase_macro_boundary(from_id: str, to_id: str) -> bool:
    """True if transition crosses macro stages."""
    if from_id not in SUB_PHASES or to_id not in SUB_PHASES:
        return False
    return SUB_PHASES[from_id].macro_stage != SUB_PHASES[to_id].macro_stage


def get_active_comm_mode(sub_phase_id: str, mode_index: int = 0) -> str:
    """Return the active comm_mode at given index within a sub-phase's mode sequence."""
    sp = get_sub_phase(sub_phase_id)
    if mode_index >= len(sp.comm_modes):
        return sp.comm_modes[-1]
    return sp.comm_modes[mode_index]


def has_multi_mode(sub_phase_id: str) -> bool:
    """True if sub-phase transitions through more than one comm_mode."""
    return len(get_sub_phase(sub_phase_id).comm_modes) > 1
