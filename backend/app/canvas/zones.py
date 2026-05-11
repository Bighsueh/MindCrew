"""Zone system — Sticky-Only Strategy (Spec 13).

Zone 是「畫在白板上的視覺框 + 後端的座標範圍判定」。
每個 zone 包含：
  - id              識別碼
  - phase_visible   哪些 sub-phase 啟用此 zone
  - allowed_colors  限制可建立的便條顏色
  - gate_modules    語言護欄模組
  - default_bounds  畫框時的預設座標（會被 Supervisor draw_zone 覆寫）
  - visual          前端繪製提示（frame_shape / title_sticky）
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Bounds:
    x: float
    y: float
    w: float
    h: float

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.x + self.w and self.y <= y <= self.y + self.h


@dataclass(frozen=True)
class ZoneVisual:
    frame_shape: str  # "rectangle" | "quadrant" | "swimlane" | "sidebar"
    title_sticky: str
    border_color: str = "#94A3B8"
    fill_pattern: str = "dotted"


@dataclass(frozen=True)
class Zone:
    """Zone 定義。"""

    id: str
    phase_visible: tuple[str, ...]
    allowed_colors: tuple[str, ...]
    gate_modules: tuple[str, ...] = ()
    default_bounds: Bounds | None = None
    visual: ZoneVisual | None = None
    templates: tuple[str, ...] = ()
    description: str = ""


# 合法顏色列舉
COLORS: frozenset[str] = frozenset({"yellow", "pink", "blue", "green"})


# ---------------------------------------------------------------------------
# Zone registry — 所有 sub-phase 用到的 zones
# ---------------------------------------------------------------------------

ZONES: dict[str, Zone] = {
    # ── Phase 1 Discover ────────────────────────────────────
    "icebreaker_zone": Zone(
        id="icebreaker_zone",
        phase_visible=("1.1a",),
        allowed_colors=("yellow", "pink"),
        default_bounds=Bounds(x=100, y=100, w=800, h=400),
        visual=ZoneVisual("rectangle", "破冰｜經驗分享"),
        description="開場 icebreaker，分享自身經驗",
    ),
    "stakeholder_private": Zone(
        id="stakeholder_private",
        phase_visible=("1.1b",),
        allowed_colors=("yellow",),
        templates=("stakeholder",),
        default_bounds=Bounds(x=100, y=100, w=2000, h=600),
        visual=ZoneVisual("rectangle", "獨立列利害關係人（私區）"),
        description="每人各自寫，互相看不到",
    ),
    "stakeholder_public": Zone(
        id="stakeholder_public",
        phase_visible=("1.1c",),
        allowed_colors=("yellow", "pink"),
        default_bounds=Bounds(x=100, y=100, w=2000, h=800),
        visual=ZoneVisual("rectangle", "利害關係人公區（揭示 + 歸類）"),
        description="揭示與歸類",
    ),
    "scope_zone": Zone(
        id="scope_zone",
        phase_visible=("1.1d",),
        allowed_colors=("yellow", "pink"),
        templates=("scope_rationale",),
        default_bounds=Bounds(x=100, y=100, w=1200, h=600),
        visual=ZoneVisual("rectangle", "Scope rationale"),
    ),
    "division_zone": Zone(
        id="division_zone",
        phase_visible=("1.2",),
        allowed_colors=("yellow", "pink"),
        default_bounds=Bounds(x=100, y=100, w=1200, h=500),
        visual=ZoneVisual("rectangle", "分工調查"),
    ),
    "interview_strategy_zone": Zone(
        id="interview_strategy_zone",
        phase_visible=("1.3",),
        allowed_colors=("yellow", "pink"),
        default_bounds=Bounds(x=100, y=100, w=1500, h=700),
        visual=ZoneVisual("rectangle", "調查策略設計"),
    ),
    "raw_wall": Zone(
        id="raw_wall",
        phase_visible=("1.5", "1.6"),
        allowed_colors=("yellow",),
        gate_modules=("no_interpretation",),
        templates=("raw_observation",),
        default_bounds=Bounds(x=100, y=100, w=2200, h=1200),
        visual=ZoneVisual("rectangle", "Raw Wall（原始觀察，延緩詮釋）"),
    ),
    "empathy_says": Zone(
        id="empathy_says",
        phase_visible=("1.6",),
        allowed_colors=("yellow",),
        gate_modules=("empathy_says_no_inference",),
        default_bounds=Bounds(x=100, y=1400, w=550, h=400),
        visual=ZoneVisual("quadrant", "Says（說了什麼）"),
    ),
    "empathy_thinks": Zone(
        id="empathy_thinks",
        phase_visible=("1.6",),
        allowed_colors=("yellow",),
        default_bounds=Bounds(x=650, y=1400, w=550, h=400),
        visual=ZoneVisual("quadrant", "Thinks（可能在想）"),
    ),
    "empathy_does": Zone(
        id="empathy_does",
        phase_visible=("1.6",),
        allowed_colors=("yellow",),
        default_bounds=Bounds(x=100, y=1800, w=550, h=400),
        visual=ZoneVisual("quadrant", "Does（做了什麼）"),
    ),
    "empathy_feels": Zone(
        id="empathy_feels",
        phase_visible=("1.6",),
        allowed_colors=("yellow",),
        default_bounds=Bounds(x=650, y=1800, w=550, h=400),
        visual=ZoneVisual("quadrant", "Feels（感受）"),
    ),
    "persona_card": Zone(
        id="persona_card",
        phase_visible=("1.6",),
        allowed_colors=("yellow", "pink"),
        default_bounds=Bounds(x=1300, y=1400, w=500, h=800),
        visual=ZoneVisual("rectangle", "Persona 角色卡"),
    ),
    "journey_map": Zone(
        id="journey_map",
        phase_visible=("1.6",),
        allowed_colors=("yellow", "pink"),
        default_bounds=Bounds(x=100, y=2300, w=2000, h=500),
        visual=ZoneVisual("swimlane", "Customer Journey Map"),
    ),

    # ── Phase 2 Define ──────────────────────────────────────
    "need_cluster_zone": Zone(
        id="need_cluster_zone",
        phase_visible=("2.1",),
        allowed_colors=("yellow", "pink"),
        default_bounds=Bounds(x=100, y=100, w=2200, h=1000),
        visual=ZoneVisual("rectangle", "需求歸類"),
    ),
    "pov_wall": Zone(
        id="pov_wall",
        phase_visible=("2.2", "2.3", "2.6"),
        allowed_colors=("yellow", "green"),  # green = vote dots
        gate_modules=("no_solution_language",),
        templates=("pov",),
        default_bounds=Bounds(x=100, y=100, w=2000, h=1200),
        visual=ZoneVisual("rectangle", "POV 牆"),
    ),
    "existing_solutions_zone": Zone(
        id="existing_solutions_zone",
        phase_visible=("2.4",),
        allowed_colors=("yellow", "pink"),
        gate_modules=("no_solution_language",),
        default_bounds=Bounds(x=100, y=100, w=1500, h=600),
        visual=ZoneVisual("rectangle", "既有解盤點"),
    ),
    "define_criteria_sidebar": Zone(
        id="define_criteria_sidebar",
        phase_visible=("2.5", "2.6"),
        allowed_colors=("green",),
        templates=("criteria",),
        default_bounds=Bounds(x=2150, y=100, w=240, h=1200),
        visual=ZoneVisual("sidebar", "Define 收斂準則"),
    ),
    "hmw_dock": Zone(
        id="hmw_dock",
        phase_visible=("2.7", "3.1"),
        allowed_colors=("blue", "pink"),
        templates=("hmw",),
        default_bounds=Bounds(x=100, y=100, w=2000, h=400),
        visual=ZoneVisual("rectangle", "HMW dock"),
    ),

    # ── Phase 3 Develop ─────────────────────────────────────
    "idea_pool": Zone(
        id="idea_pool",
        phase_visible=("3.2", "3.3", "3.4", "4.1a", "4.1c"),
        allowed_colors=("yellow", "pink", "green"),
        gate_modules=("no_feasibility_talk",),  # 3.x; 4.1 會 override
        templates=("idea",),
        default_bounds=Bounds(x=100, y=500, w=2200, h=1500),
        visual=ZoneVisual("rectangle", "Idea pool"),
    ),

    # ── Phase 4 Deliver ─────────────────────────────────────
    "deliver_criteria_sidebar": Zone(
        id="deliver_criteria_sidebar",
        phase_visible=("4.1b", "4.1c"),
        allowed_colors=("green",),
        templates=("criteria",),
        default_bounds=Bounds(x=2150, y=100, w=240, h=1200),
        visual=ZoneVisual("sidebar", "Deliver 收斂準則"),
    ),
    "hypothesis_wall": Zone(
        id="hypothesis_wall",
        phase_visible=("4.1d", "4.1e"),
        allowed_colors=("yellow", "pink"),
        templates=("hypothesis",),
        default_bounds=Bounds(x=100, y=100, w=2000, h=800),
        visual=ZoneVisual("rectangle", "假設牆"),
    ),
    "task_area": Zone(
        id="task_area",
        phase_visible=("4.1e", "4.1f"),
        allowed_colors=("yellow", "pink"),
        templates=("task_ticket",),
        default_bounds=Bounds(x=100, y=900, w=2000, h=600),
        visual=ZoneVisual("rectangle", "Task 區"),
    ),
    "prototype_zone": Zone(
        id="prototype_zone",
        phase_visible=("4.1f",),
        allowed_colors=("yellow", "pink"),
        gate_modules=("no_production_code",),
        default_bounds=Bounds(x=100, y=1500, w=2000, h=800),
        visual=ZoneVisual("rectangle", "Prototype 區"),
    ),
    "debrief_q1": Zone(
        id="debrief_q1",
        phase_visible=("4.2",),
        allowed_colors=("yellow",),
        default_bounds=Bounds(x=100, y=100, w=700, h=600),
        visual=ZoneVisual("rectangle", "Q1：信念更新"),
    ),
    "debrief_q2": Zone(
        id="debrief_q2",
        phase_visible=("4.2",),
        allowed_colors=("yellow",),
        default_bounds=Bounds(x=850, y=100, w=700, h=600),
        visual=ZoneVisual("rectangle", "Q2：回應檢查"),
    ),
    "debrief_q3": Zone(
        id="debrief_q3",
        phase_visible=("4.2",),
        allowed_colors=("yellow",),
        default_bounds=Bounds(x=1600, y=100, w=700, h=600),
        visual=ZoneVisual("rectangle", "Q3：回溯反省"),
    ),
    "direction_zone": Zone(
        id="direction_zone",
        phase_visible=("4.3",),
        allowed_colors=("green", "pink"),
        templates=("direction",),
        default_bounds=Bounds(x=100, y=100, w=1500, h=400),
        visual=ZoneVisual("rectangle", "決定去向（Close / Loop-D / Loop-F）"),
    ),
}


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_zone(zone_id: str) -> Zone:
    """Get Zone by id. Raises KeyError if not found."""
    return ZONES[zone_id]


def get_active_zones(sub_phase_id: str) -> list[Zone]:
    """Return all zones active in the given sub-phase."""
    return [z for z in ZONES.values() if sub_phase_id in z.phase_visible]


def resolve_zone_by_position(
    x: float,
    y: float,
    sub_phase_id: str,
    project_zone_bounds: dict[str, Bounds] | None = None,
) -> Zone | None:
    """根據座標解析便條落在哪個 zone。

    `project_zone_bounds` 是該 project 已 register 的實際 bounds（覆寫 default）。
    若為 None，使用 default_bounds。
    """
    active = get_active_zones(sub_phase_id)
    for zone in active:
        bounds = None
        if project_zone_bounds and zone.id in project_zone_bounds:
            bounds = project_zone_bounds[zone.id]
        elif zone.default_bounds:
            bounds = zone.default_bounds
        if bounds and bounds.contains(x, y):
            return zone
    return None


def zone_allows_color(zone: Zone, color: str) -> bool:
    return color in zone.allowed_colors
