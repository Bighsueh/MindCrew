"""Zone system — 過渡實作（Spec 04-06 v4.25 §5.2；目標版面模型＝section）.

Zone 是「畫在白板上的視覺框 + 後端的座標範圍判定」。
每個 zone 包含：
  - id              識別碼
  - phase_visible   哪些 sub-phase 啟用此 zone
  - allowed_colors  歷史欄位（#34 後便條色＝作者色，不再 enforce；保留供查詢）
  - gate_modules    語言護欄模組
  - default_bounds  畫框時的預設座標（會被 register/grow 覆寫）
  - visual          前端繪製提示（frame_shape / title_sticky）

RC1 帶模型（spec 10 v2.0 §2.3 / spec 27 §5，2026-07-03）：
  - default_bounds 由「5 個同錨 (100,100) 的重疊矩形」改為**互不重疊的預堆疊
    水平帶**（依各牆首次啟用的格序由上而下）——未註冊時的 fallback 也不塌陷。
  - 實際 seed 位置由 section 模型推導（`zone_seed.compute_zone_band_bounds`：
    開在既有內容之下），default_bounds 的 y 只是無內容時的靜態藍圖。
  - `define_criteria_sidebar` 從右側窄欄（2150,100,240×1200）正名為一般帶——
    spec 27 §3.1 準則本就是自己的 section；舊窄欄正是實機截圖「綠色直欄」
    症狀來源。id 保留不改（registry / 測試相容）。

Phase 42 C1（spec 22 v2.0 §3 / 23 v2.0 §4 / 27 v3.0 §5）：
  - 隨格移除的 zone 全刪：task_clarification_zone（0.2）、scope_zone（舊 1.1d）、
    division_zone（舊 1.2）、interview_strategy_zone（1.3）、raw_wall（1.5）、
    empathy_×4／persona_card／journey_map（1.6）、need_cluster_zone（併入痛點牆）。
  - 利害關係人牆（stakeholder_public）沿用，1.1b–1.1d 全程啟用（群標籤、高/中/低
    label 都貼於此）；無任何私人區（#18）。
  - 新增痛點牆（pain_wall）：1.2 發想（按利害關係人群掛載）＋ 2.1 就地按主題橫切重歸類。
  - 框標題文案全面留空（#13，沿 B1 icebreaker 先例）：「現在在哪一關」的視覺錨點由
    組長進場貼的標題便條（kind=label，sub_phase_entry 固定文案）承擔，框不再重複貼標題
    ——也一併消掉舊標題的英文外漏（#25「POV / Problem Statement」「HMW dock」「Define」）。
  - define 側 zone（pov_wall／existing_solutions_zone／define_criteria_sidebar／hmw_dock）
    結構保留為過渡實作，2.x 行為細節（選定 section 接線、收口/配對閘）＝批次 C2。
"""

from __future__ import annotations

from dataclasses import dataclass


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
    """Zone 定義。

    templates＝**接受清單**（spec 23 v2.1 §4.1.1）：此區可收哪些結構化便條，
    不等於強制。強制比對只在 ``template_required_sub_phases`` 所列 sub_phase
    成立，且為「match 任一」；其餘 sub_phase 自由文字放行（Phase 42 補正 R1／P0-2）。
    """

    id: str
    phase_visible: tuple[str, ...]
    allowed_colors: tuple[str, ...]
    gate_modules: tuple[str, ...] = ()
    default_bounds: Bounds | None = None
    visual: ZoneVisual | None = None
    templates: tuple[str, ...] = ()
    template_required_sub_phases: tuple[str, ...] = ()
    description: str = ""


# 合法顏色列舉
COLORS: frozenset[str] = frozenset({"yellow", "pink", "blue", "green"})


# ---------------------------------------------------------------------------
# Zone registry — 新 5＋7 格使用的牆面（spec 04-06 v4.25 §5.2 表）
# ---------------------------------------------------------------------------

ZONES: dict[str, Zone] = {
    # ── 暖場＋發現階段 ────────────────────────────────────
    "icebreaker_zone": Zone(
        id="icebreaker_zone",
        # 0.0a＝暖場破冰牆；1.1a＝經驗牆（兩格共用，spec 28 / 22 v2.0）。
        phase_visible=("0.0a", "1.1a"),
        allowed_colors=("yellow", "pink"),
        # 放大到足以容納全員分享的便條；範圍涵蓋預設落點 region:center(~840,1000)。
        default_bounds=Bounds(x=100, y=100, w=1700, h=1400),
        # Phase 42 B1 (#13)：框標題留空——視覺錨點＝組長進場標題便條（kind=label）。
        visual=ZoneVisual("rectangle", ""),
        description="暖場破冰 / 發現階段經驗分享",
    ),
    "stakeholder_public": Zone(
        id="stakeholder_public",
        # Phase 42 C1：1.1b 發想、1.1c 歸類（群標籤）、1.1d 排序（高/中/低 label）
        # 全在同一面公共牆（#18 無私人區；獨立發想由反echo prompt＋去重 gate 承載）。
        phase_visible=("1.1b", "1.1c", "1.1d"),
        allowed_colors=("yellow", "pink"),
        templates=("stakeholder",),
        # 內容便條＝只寫名字（spec 23 §4.1.1 強制表）；群標籤／高中低走 kind=label。
        template_required_sub_phases=("1.1b", "1.1c", "1.1d"),
        default_bounds=Bounds(x=100, y=1620, w=2000, h=800),
        visual=ZoneVisual("rectangle", ""),
        description="利害關係人牆（全公共）：發想、歸類、排先後順序",
    ),
    "pain_wall": Zone(
        id="pain_wall",
        # Phase 42 C1（spec 22 §3.2 / 27 §3.1）：1.2 痛點按利害關係人群掛載；
        # 2.1 就地按主題橫切重歸類（主題群標籤 problem_candidate 亦貼於此）。
        phase_visible=("1.2", "2.1"),
        allowed_colors=("yellow", "pink"),
        # 痛點便條＝自由文字（spec 23 §4.1.1：本牆**無**強制 sub_phase）；
        # problem_candidate 只是 2.1 主題群標籤的接受身分（kind=label 本就跳過 gate）。
        # P0-2 修復：舊 code 把 templates 當「全部強制」→ >15 字痛點便條全被
        # problem_candidate regex 誤殺；接受清單語意下不再比對。
        templates=("problem_candidate",),
        default_bounds=Bounds(x=100, y=2540, w=2200, h=1000),
        visual=ZoneVisual("rectangle", ""),
        description="痛點牆：誰在什麼情況卡住了（按群掛載；定義階段就地按主題重歸類）",
    ),

    # ── 定義階段（過渡實作；行為細節＝批次 C2）──────────────
    "pov_wall": Zone(
        id="pov_wall",
        phase_visible=("2.2", "2.3", "2.6"),
        allowed_colors=("yellow", "green"),
        gate_modules=("no_solution_language",),
        # Phase 42 C1：pov 模板自 2.2 移除（spec 23 v2.0 併入 problem_statement；
        # regex 改寫＝C2，本表先收斂 accepted templates）。
        templates=("problem_statement",),
        # 只有 2.2 強制問題定義句型；2.3 根源概念＝自由文字放行（spec 23 §4.1.1）。
        template_required_sub_phases=("2.2",),
        default_bounds=Bounds(x=100, y=3660, w=2000, h=1200),
        visual=ZoneVisual("rectangle", ""),
        description="問題定義牆（2.3 追問根源的概念便條同鏈歸群於此）",
    ),
    "existing_solutions_zone": Zone(
        id="existing_solutions_zone",
        phase_visible=("2.4",),
        allowed_colors=("yellow", "pink"),
        gate_modules=("no_solution_language",),
        default_bounds=Bounds(x=100, y=4980, w=1500, h=600),
        visual=ZoneVisual("rectangle", ""),
        description="現有解法區：市面上已經有什麼",
    ),
    "define_criteria_sidebar": Zone(
        id="define_criteria_sidebar",
        phase_visible=("2.5", "2.6"),
        allowed_colors=("green",),
        templates=("criteria",),
        template_required_sub_phases=("2.5", "2.6"),
        default_bounds=Bounds(x=100, y=5700, w=2000, h=500),
        visual=ZoneVisual("rectangle", ""),
        description="準則區：用什麼尺來挑",
    ),
    "hmw_dock": Zone(
        id="hmw_dock",
        # 過渡實作：spec 23 v2.0 §4.2 目標＝設計題目直接配在選定 section 的問題定義旁
        # （hmw_dock 移除）；選定 section 行為接線＝批次 C2，本格過渡期仍用此停泊區。
        phase_visible=("2.7",),
        allowed_colors=("blue", "pink"),
        templates=("hmw",),
        template_required_sub_phases=("2.7",),
        default_bounds=Bounds(x=100, y=6320, w=2000, h=400),
        visual=ZoneVisual("rectangle", ""),
        description="設計題目：我們可以怎麼…？（過渡實作，C2 改配選定區）",
    ),
}


# 牆面的 in-scene 短名（spec 04-06 v4.25 §5.2 表）——框標題留空後，
# 「這格是哪面牆」的文字表達（move-delta 語意化、log）由本表供應。
ZONE_NAMES_ZH: dict[str, str] = {
    "icebreaker_zone": "破冰與經驗牆",
    "stakeholder_public": "利害關係人牆",
    "pain_wall": "痛點牆",
    "pov_wall": "問題定義牆",
    "existing_solutions_zone": "現有解法區",
    "define_criteria_sidebar": "準則區",
    "hmw_dock": "設計題目區",
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
