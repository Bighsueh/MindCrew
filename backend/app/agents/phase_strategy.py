"""Phase Strategy — 每個 Micro Phase 的溝通配置。

取代靜態 Round Orchestrator，定義三個維度：
- comm_strategy: 溝通策略 (OO/ST/SS)
- comm_goal: 溝通目標 (合作/辯論/競爭)
- supervisor_mode: Supervisor 行為模式 (facilitator/participant/silent)

Phase 19 refactor: ``protagonist`` 與 ``suppressed`` 改以
:class:`CognitiveLens` 描述。執行期由
:func:`app.agents.personas.resolver.resolve_protagonist_seat` 動態解析
為具體的 ``seat_role``。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.personas.lens import CognitiveLens


@dataclass(frozen=True)
class PhaseStrategy:
    """每個 Micro Phase 的溝通配置。"""

    micro_phase: str
    comm_strategy: str  # "one_by_one" | "simultaneous" | "simultaneous_summarizer"
    comm_goal: str  # "direct_cooperation" | "debate" | "mild_competition"
    supervisor_mode: str  # "facilitator" | "participant" | "silent"
    protagonist_lens: CognitiveLens | None
    suppressed_lenses: list[CognitiveLens] = field(default_factory=list)
    summarize_interval: int = 0
    max_rounds_before_eval: int = 10


PHASE_STRATEGIES: dict[str, PhaseStrategy] = {
    # ── Phase 1: DISCOVER ──────────────────────────────────
    "1.1": PhaseStrategy(
        micro_phase="1.1",
        comm_strategy="one_by_one",
        comm_goal="direct_cooperation",
        supervisor_mode="facilitator",
        protagonist_lens=CognitiveLens.EMPATHY,
        suppressed_lenses=[CognitiveLens.STRUCTURE, CognitiveLens.FEASIBILITY],
        summarize_interval=0,
        max_rounds_before_eval=8,
    ),
    "1.2": PhaseStrategy(
        micro_phase="1.2",
        comm_strategy="simultaneous_summarizer",
        comm_goal="direct_cooperation",
        supervisor_mode="participant",
        protagonist_lens=None,
        suppressed_lenses=[CognitiveLens.STRUCTURE],
        summarize_interval=6,
        max_rounds_before_eval=15,
    ),
    "1.3": PhaseStrategy(
        micro_phase="1.3",
        comm_strategy="simultaneous_summarizer",
        comm_goal="debate",
        supervisor_mode="participant",
        protagonist_lens=CognitiveLens.STRUCTURE,
        suppressed_lenses=[],
        summarize_interval=5,
        max_rounds_before_eval=10,
    ),
    # ── Phase 2: DEFINE ────────────────────────────────────
    "2.1": PhaseStrategy(
        micro_phase="2.1",
        comm_strategy="one_by_one",
        comm_goal="debate",
        supervisor_mode="facilitator",
        protagonist_lens=CognitiveLens.STRUCTURE,
        suppressed_lenses=[],
        summarize_interval=0,
        max_rounds_before_eval=10,
    ),
    "2.2": PhaseStrategy(
        micro_phase="2.2",
        comm_strategy="simultaneous_summarizer",
        comm_goal="debate",
        supervisor_mode="participant",
        protagonist_lens=CognitiveLens.STRUCTURE,
        suppressed_lenses=[],
        summarize_interval=5,
        max_rounds_before_eval=10,
    ),
    "2.3": PhaseStrategy(
        micro_phase="2.3",
        comm_strategy="simultaneous_summarizer",
        comm_goal="mild_competition",
        supervisor_mode="participant",
        protagonist_lens=None,
        suppressed_lenses=[],
        summarize_interval=5,
        max_rounds_before_eval=8,
    ),
    # ── Phase 3: DEVELOP ───────────────────────────────────
    "3.1": PhaseStrategy(
        micro_phase="3.1",
        comm_strategy="simultaneous",
        comm_goal="direct_cooperation",
        supervisor_mode="silent",
        protagonist_lens=CognitiveLens.CREATIVITY,
        suppressed_lenses=[CognitiveLens.STRUCTURE, CognitiveLens.FEASIBILITY],
        summarize_interval=0,
        max_rounds_before_eval=20,
    ),
    "3.2": PhaseStrategy(
        micro_phase="3.2",
        comm_strategy="simultaneous_summarizer",
        comm_goal="debate",
        supervisor_mode="participant",
        protagonist_lens=CognitiveLens.STRUCTURE,
        suppressed_lenses=[],
        summarize_interval=5,
        max_rounds_before_eval=10,
    ),
    "3.3": PhaseStrategy(
        micro_phase="3.3",
        comm_strategy="simultaneous_summarizer",
        comm_goal="mild_competition",
        supervisor_mode="participant",
        protagonist_lens=CognitiveLens.FEASIBILITY,
        suppressed_lenses=[],
        summarize_interval=4,
        max_rounds_before_eval=8,
    ),
    # ── Phase 4: DELIVER ───────────────────────────────────
    "4.1": PhaseStrategy(
        micro_phase="4.1",
        comm_strategy="one_by_one",
        comm_goal="debate",
        supervisor_mode="facilitator",
        protagonist_lens=CognitiveLens.FEASIBILITY,
        suppressed_lenses=[],
        summarize_interval=0,
        max_rounds_before_eval=10,
    ),
    "4.2": PhaseStrategy(
        micro_phase="4.2",
        comm_strategy="simultaneous_summarizer",
        comm_goal="debate",
        supervisor_mode="facilitator",
        protagonist_lens=CognitiveLens.STRUCTURE,
        suppressed_lenses=[CognitiveLens.CREATIVITY],
        summarize_interval=4,
        max_rounds_before_eval=8,
    ),
    "4.3": PhaseStrategy(
        micro_phase="4.3",
        comm_strategy="simultaneous_summarizer",
        comm_goal="debate",
        supervisor_mode="participant",
        protagonist_lens=CognitiveLens.EMPATHY,
        suppressed_lenses=[],
        summarize_interval=4,
        max_rounds_before_eval=10,
    ),
}


def get_phase_strategy(micro_phase: str) -> PhaseStrategy | None:
    """查詢指定 Micro Phase 的溝通配置。"""
    return PHASE_STRATEGIES.get(micro_phase)
