"""Phase Strategy — 每個 Micro Phase 的溝通配置。

取代靜態 Round Orchestrator，定義三個維度：
- comm_strategy: 溝通策略（OO/ST/SS）
- comm_goal: 溝通目標（合作/辯論/競爭）
- supervisor_mode: Supervisor 行為模式（facilitator/participant/silent）
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PhaseStrategy:
    """每個 Micro Phase 的溝通配置。"""

    micro_phase: str  # "1.1", "1.2", ...
    comm_strategy: str  # "one_by_one" | "simultaneous" | "simultaneous_summarizer"
    comm_goal: str  # "direct_cooperation" | "debate" | "mild_competition"
    supervisor_mode: str  # "facilitator" | "participant" | "silent"
    protagonist: str | None  # "crew_1", "crew_2", ... 或 None
    suppressed: list[str] = field(default_factory=list)
    summarize_interval: int = 0  # Supervisor 每隔 N 則新訊息做一次摘要（SS 策略用）
    max_rounds_before_eval: int = 10  # 最大輪數後強制觸發評估


PHASE_STRATEGIES: dict[str, PhaseStrategy] = {
    # ── Phase 1: DISCOVER ──────────────────────────────────
    "1.1": PhaseStrategy(
        micro_phase="1.1",
        comm_strategy="one_by_one",
        comm_goal="direct_cooperation",
        supervisor_mode="facilitator",  # 主導暖場，逐一邀請
        protagonist="crew_1",  # Empathy 主角
        suppressed=["crew_2", "crew_4"],
        summarize_interval=0,  # OO 不需要 summarize
        max_rounds_before_eval=8,
    ),
    "1.2": PhaseStrategy(
        micro_phase="1.2",
        comm_strategy="simultaneous_summarizer",
        comm_goal="direct_cooperation",
        supervisor_mode="participant",  # 參與討論 + 定期彙整
        protagonist=None,  # 全員擴展
        suppressed=["crew_2"],
        summarize_interval=6,  # 每 6 則新訊息 Supervisor 做一次彙整
        max_rounds_before_eval=15,
    ),
    "1.3": PhaseStrategy(
        micro_phase="1.3",
        comm_strategy="simultaneous_summarizer",
        comm_goal="debate",
        supervisor_mode="participant",
        protagonist="crew_2",  # Structure 主導分群
        suppressed=[],
        summarize_interval=5,
        max_rounds_before_eval=10,
    ),
    # ── Phase 2: DEFINE ────────────────────────────────────
    "2.1": PhaseStrategy(
        micro_phase="2.1",
        comm_strategy="one_by_one",
        comm_goal="debate",
        supervisor_mode="facilitator",
        protagonist="crew_2",
        suppressed=[],
        summarize_interval=0,
        max_rounds_before_eval=10,
    ),
    "2.2": PhaseStrategy(
        micro_phase="2.2",
        comm_strategy="simultaneous_summarizer",
        comm_goal="debate",
        supervisor_mode="participant",
        protagonist="crew_2",
        suppressed=[],
        summarize_interval=5,
        max_rounds_before_eval=10,
    ),
    "2.3": PhaseStrategy(
        micro_phase="2.3",
        comm_strategy="simultaneous_summarizer",
        comm_goal="mild_competition",
        supervisor_mode="participant",
        protagonist=None,
        suppressed=[],
        summarize_interval=5,
        max_rounds_before_eval=8,
    ),
    # ── Phase 3: DEVELOP ───────────────────────────────────
    "3.1": PhaseStrategy(
        micro_phase="3.1",
        comm_strategy="simultaneous",  # 純 ST，不打斷發散
        comm_goal="direct_cooperation",
        supervisor_mode="silent",  # 只在能量降低時才催化
        protagonist="crew_3",
        suppressed=["crew_2", "crew_4"],
        summarize_interval=0,
        max_rounds_before_eval=20,
    ),
    "3.2": PhaseStrategy(
        micro_phase="3.2",
        comm_strategy="simultaneous_summarizer",
        comm_goal="debate",
        supervisor_mode="participant",
        protagonist="crew_2",
        suppressed=[],
        summarize_interval=5,
        max_rounds_before_eval=10,
    ),
    "3.3": PhaseStrategy(
        micro_phase="3.3",
        comm_strategy="simultaneous_summarizer",
        comm_goal="mild_competition",
        supervisor_mode="participant",
        protagonist="crew_4",
        suppressed=[],
        summarize_interval=4,
        max_rounds_before_eval=8,
    ),
    # ── Phase 4: DELIVER ───────────────────────────────────
    "4.1": PhaseStrategy(
        micro_phase="4.1",
        comm_strategy="one_by_one",
        comm_goal="debate",
        supervisor_mode="facilitator",
        protagonist="crew_4",
        suppressed=[],
        summarize_interval=0,
        max_rounds_before_eval=10,
    ),
    "4.2": PhaseStrategy(
        micro_phase="4.2",
        comm_strategy="simultaneous_summarizer",
        comm_goal="debate",
        supervisor_mode="facilitator",
        protagonist="crew_2",
        suppressed=["crew_3"],
        summarize_interval=4,
        max_rounds_before_eval=8,
    ),
    "4.3": PhaseStrategy(
        micro_phase="4.3",
        comm_strategy="simultaneous_summarizer",
        comm_goal="debate",
        supervisor_mode="participant",
        protagonist="crew_1",
        suppressed=[],
        summarize_interval=4,
        max_rounds_before_eval=10,
    ),
}


def get_phase_strategy(micro_phase: str) -> PhaseStrategy | None:
    """查詢指定 Micro Phase 的溝通配置。"""
    return PHASE_STRATEGIES.get(micro_phase)
