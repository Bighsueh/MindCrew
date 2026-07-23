"""Sub-phase definitions — 第一鑽石 5＋7 格（Spec 22 v2.0 / 04-06 v4.25，Phase 42 C1）.

結構（SUB_PHASE_ORDER）：
  0.0a（暖場）→ 1.1a–1.1d、1.2（發現 5 格）→ 2.1–2.7（定義 7 格）

每個 sub-phase 包含：
  - id              "1.1a", "1.1b", ..., "2.7"
  - parent_micro_phase  micro 桶（6 桶：0.0 / 1.1 / 1.2 / 2.1 / 2.2 / 2.3）
  - macro_stage     "warmup" / "discover" / "define"
  - name_zh         in-scene 大白話名稱（spec 22 §2.3；無講義標籤、無英文縮寫 #25）
  - comm_modes      互動模式（reveal_round / discussion / threaded_reveal）
  - zones           本 sub-phase 啟用的 zone id（靜態 ZONES 為過渡實作，spec 04-06 §5.2）
  - target_count    量爆軟上限（僅影響提醒；spec 16 §2.4）
  - gate_modules    內容護欄模組（見 canvas/content_gate.py）
  - templates       便條紙文字模板識別碼（見 canvas/text_templates.py）
  - min_artifact_counts  推進硬閘張數（intensity 1.0 基準；spec 22 §4.3 / spec 25 v2.0）

Spec 對齊備忘：
  - 0.1/0.2 與 1.3–1.6 已於 v2.0 正式移除（spec 22 §2.2/§2.3）；既有資料由
    migration backfill 就近映射（spec 22 §11.1）。
  - macro 邊界：discover→define ＝ 新 1.2 完成；define→completed ＝ 2.7 配對閘。
  - `no_interpretation` gate 全系統移除；1.2 改掛「禁跳功能」軟擋（no_feature_jump）。
  - 2.6 收口閘（selection_pairing）／2.7 配對閘（hmw_pairing）為 Spec 25 v2.0 特殊鍵
    （Phase 42 C2 落地）：min_artifact_counts 值固定 1＝啟用旗標，實際判定由
    canvas/artifact_gate.py helper 動態計算（不隨 intensity 縮放）。
  - 真人 gate（per-cell）不在本表——由 round_lock 逐關解鎖型態表（訊號層，spec 20 v2.0）；
    Phase 42 C2 裁定：真人拍板/確認維持訊號層、不硬擋 advance（避死鎖；偏離 spec 22 §4.3／
    25 §5.1c，見 prompts/progress.md 偏離表），結構閘＋time-box 強制收口保證流程不死。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeliverableRequirement:
    """Spec 14 A9: 推進下一 sub-phase 前的產出物檢查。

    v2.0 配置現況「多為空」（spec 25 §2.4）：顏色 deliverables 全移除（#34 便條色＝作者色）、
    scope_rationale 隨舊 1.1d 刪除；機制保留供未來使用。
    """

    zone_id: str                  # 必須有便條的 zone
    min_count: int = 1            # 至少 N 張便條
    template_id: str | None = None  # 若指定，便條必須符合該 template
    color: str | None = None      # 若指定，便條須為該色
    description_zh: str = ""      # advance 失敗時的提示


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
    # Spec 14 A9: deliverable check for advance gate
    deliverables_required: tuple[DeliverableRequirement, ...] = ()
    # spec/22 §4: 最小 artifact 計數，由 Spec 25 artifact_gate 在 advance 前 enforce。
    # 空 dict 表示無強制要求。key 為 template_id（或 Spec 25 定義的特殊鍵），value 為最小張數。
    min_artifact_counts: dict[str, int] = field(default_factory=dict)
    # 互動模式轉換訊號（宣告用途；實際推進＝組長節奏推進＋watcher 兜底，04-06 §5.8）：
    # - "count":      target_count / min_artifact_counts 達到
    # - "all_revealed":  reveal_round 所有人都唸完
    # - "supervisor":  Supervisor 主動推進
    transition_signals: tuple[str, ...] = ("supervisor",)


# 合法 comm_mode 列舉（schema-style）
# Phase 41 (Spec 27 v2.4)：移除 silent_write / silent_rearrange（沉默模式）。
COMM_MODES: frozenset[str] = frozenset({
    "reveal_round",
    "discussion",
    "threaded_reveal",
})


# ---------------------------------------------------------------------------
# Sub-phase registry — spec 22 v2.0 §2.3
# ---------------------------------------------------------------------------

SUB_PHASES: dict[str, SubPhase] = {
    # ── 暖場 macro stage：目標導向破冰（spec 28 v2.0）──────────────
    "0.0a": SubPhase(
        id="0.0a",
        parent_micro_phase="0.0",
        macro_stage="warmup",
        name_zh="破冰時間｜額外用途發想",
        comm_modes=("discussion",),
        zones=("icebreaker_zone",),
        transition_signals=("supervisor",),
    ),

    # ── 發現階段（discover）5 格：只打開、不收攏 ─────────────────
    "1.1a": SubPhase(
        id="1.1a",
        parent_micro_phase="1.1",
        macro_stage="discover",
        # 個人經驗＝原料（assumption-based），往下帶、不是聊完就丟。
        # 軟格：產出訊號（每位 crew 接過 ≥1 自身經驗＋真人 ≥1）由組長訊號面板判讀。
        name_zh="經驗分享",
        comm_modes=("discussion",),
        zones=("icebreaker_zone",),
        target_count=5,
        transition_signals=("supervisor",),
    ),
    "1.1b": SubPhase(
        id="1.1b",
        parent_micro_phase="1.1",
        macro_stage="discover",
        # 硬格：不重複利害關係人 ≥8（intensity 縮放）；便條只寫名字、理由在聊天講。
        # 全公開無私人區（#18）；獨立精神靠組長話術＋貼上時去重；廣度只當提醒不擋推進。
        name_zh="發想利害關係人",
        comm_modes=("discussion",),
        zones=("stakeholder_public",),
        target_count=12,
        templates=("stakeholder",),
        min_artifact_counts={"stakeholder": 8},
        transition_signals=("count", "supervisor"),
    ),
    "1.1c": SubPhase(
        id="1.1c",
        parent_micro_phase="1.1",
        macro_stage="discover",
        # 軟格：禁拖動——輪流唸＋口頭歸群＋貼群標籤（kind=label），空間整理由硬邏輯工具執行。
        # 產出訊號（無遊離散張＋2–5 群）由組長訊號面板判讀。
        name_zh="一起歸類",
        comm_modes=("reveal_round",),
        zones=("stakeholder_public",),
        target_count=None,
        transition_signals=("all_revealed", "supervisor"),
    ),
    "1.1d": SubPhase(
        id="1.1d",
        parent_micro_phase="1.1",
        macro_stage="discover",
        # 軟格：高/中/低用 label 便條輕量標記；只排序、不刪人、不寫理由（收斂全留定義階段）。
        # 舊「決定範圍與理由」（scope_rationale deliverable）已隨 v2.0 整格抽換移除。
        name_zh="排先後順序",
        comm_modes=("discussion",),
        zones=("stakeholder_public",),
        transition_signals=("supervisor",),
    ),
    "1.2": SubPhase(
        id="1.2",
        parent_micro_phase="1.2",
        macro_stage="discover",
        # 硬格＋discover→define macro 邊界：具體痛點 ≥6（口頭目標 8 不入閘）＋
        # 每個高優先群 ≥1（結構附加條件，artifact_gate 逐群檢查）。
        # 接話式按利害關係人群：聊定才貼、掛對應群下；「跳到功能」＝提醒＋軟擋（非硬 gate）。
        name_zh="發想痛點與情境",
        comm_modes=("threaded_reveal",),
        zones=("pain_wall",),
        target_count=12,
        gate_modules=("no_feature_jump",),
        min_artifact_counts={"pain_point": 6},
        transition_signals=("count", "supervisor"),
    ),

    # ── 定義階段（define）7 格：收斂到一句設計題目 ─────────────────
    "2.1": SubPhase(
        id="2.1",
        parent_micro_phase="2.1",
        macro_stage="define",
        # 硬格：主題群標籤 ≥3（每群 ≥1 張痛點為附加條件，C2 落地逐群檢查）。
        # 按主題橫切重歸類（同主題可跨利害關係人）；唯一不掛禁解法護欄的定義階段格；
        # crew 先示範拖曳（#26）、真人「拖＋說」（#27，round_lock enforce）。
        name_zh="痛點歸類",
        comm_modes=("discussion",),
        zones=("pain_wall",),
        templates=("problem_candidate",),
        min_artifact_counts={"problem_candidate": 3},
        transition_signals=("count", "supervisor"),
    ),
    "2.2": SubPhase(
        id="2.2",
        parent_micro_phase="2.2",
        macro_stage="define",
        # 硬格：合格問題定義 ≥3。格式「某使用者 需要 某需求，因為 某洞察」；
        # 每張 ≥2 筆痛點來源關聯（cites，#30）——cites 計入條件於 C2 接進 artifact_gate。
        name_zh="問題定義",
        comm_modes=("reveal_round",),
        zones=("pov_wall",),
        target_count=6,
        gate_modules=("no_solution_language",),
        templates=("problem_statement",),
        min_artifact_counts={"problem_statement": 3},
        transition_signals=("count", "all_revealed", "supervisor"),
    ),
    "2.3": SubPhase(
        id="2.3",
        parent_micro_phase="2.2",
        macro_stage="define",
        # 軟格：聊定才貼、同鏈自動歸群、禁搬動；根源在 2.6 當判斷依據用掉。
        name_zh="追問根源",
        comm_modes=("threaded_reveal",),
        zones=("pov_wall",),
        gate_modules=("no_solution_language",),
        transition_signals=("supervisor",),
    ),
    "2.4": SubPhase(
        id="2.4",
        parent_micro_phase="2.2",
        macro_stage="define",
        # 軟格：找「真缺口」供 2.6 用；最易脫口解法＝禁解法護欄重點區。
        name_zh="盤點現有解法",
        comm_modes=("threaded_reveal",),
        zones=("existing_solutions_zone",),
        gate_modules=("no_solution_language",),
        transition_signals=("supervisor",),
    ),
    "2.5": SubPhase(
        id="2.5",
        parent_micro_phase="2.3",
        macro_stage="define",
        # 軟格：格式「準則：名稱｜衡量方式：…」；準則＝2.6 唯一的尺；
        # crew 多扛、真人挑/補/確認（#31）。
        name_zh="訂收斂準則",
        comm_modes=("discussion",),
        zones=("define_criteria_sidebar",),
        templates=("criteria",),
        gate_modules=("no_solution_language",),
        transition_signals=("supervisor",),
    ),
    "2.6": SubPhase(
        id="2.6",
        parent_micro_phase="2.3",
        macro_stage="define",
        # 硬格（收口閘）：選定區 problem_statement ∈ [1,3] 且每張配合格選定理由
        # （selection_pairing 特殊鍵，Spec 25 v2.0 §3.2，artifact_gate helper 判定）。
        # 真人拍板（round_lock 訊號層）＋組長收口；time-box 到走強制收口兜底
        # （advance_router 補 time_box_forced 理由，spec 16 §4.3 / 04-06 §5.8）。
        # 選定區＝動態往下開的 section（#32，C0 open_section 工具）；全程無投票。
        name_zh="依準則挑問題定義",
        comm_modes=("discussion",),
        zones=("pov_wall", "define_criteria_sidebar"),
        # 2026-07-13 live 揪出：2.6 是唯一沒掛 templates 的產出關 → prompt 的
        # 「便條紙文字格式」整段不出現 → crew 從沒看過選定理由格式，實機寫成
        # 「選定＋符合影響力：…」（過不了 selection_reason regex）。templates 只被
        # prompt 層消費（無 gate 副作用），補上即讓 crew 拿到 spec 23 §2.5 格式。
        templates=("selection_reason",),
        gate_modules=("no_solution_language",),
        min_artifact_counts={"selection_pairing": 1},
        transition_signals=("supervisor",),
    ),
    "2.7": SubPhase(
        id="2.7",
        parent_micro_phase="2.3",
        macro_stage="define",
        # 硬格（配對閘）＋define→completed macro 邊界：每張選定問題定義配 1 張設計題目
        # （hmw_pairing 特殊鍵，Spec 25 v2.0 §3.3，artifact_gate helper 判定；張數＝選定
        # 數，v1.0 hmw≥3 取消）。設計題目 from 關聯＝cites 指向選定問題定義。
        # 藍色 deliverable 移除（#34 便條色＝作者色）；視覺標記＝kind 驅動外框＋角標
        # 「設計題目」（前端文字句型辨識）；便條文字禁英文縮寫（hmw 模板 forbidden_terms）。
        name_zh="改寫設計題目",
        comm_modes=("discussion",),
        zones=("hmw_dock",),
        templates=("hmw",),
        gate_modules=("no_solution_language",),
        min_artifact_counts={"hmw_pairing": 1},
        transition_signals=("supervisor",),
    ),
}


# 嚴格順序（用於 advance/next 推導）— spec 22 §2.4。
# 2.7 為第一鑽石終局，其後不再 advance（define→completed）。
SUB_PHASE_ORDER: tuple[str, ...] = (
    "0.0a",                                   # 暖場（warmup macro，spec 28）
    "1.1a", "1.1b", "1.1c", "1.1d", "1.2",    # 發現階段 5 格
    "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7",  # 定義階段 7 格
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_sub_phase(sub_phase_id: str) -> SubPhase:
    """Get SubPhase by id. Raises KeyError if not found."""
    return SUB_PHASES[sub_phase_id]


def is_hard_gate(sp: SubPhase) -> bool:
    """True 若此 sub-phase 是硬格（有 deliverable 或 artifact 計數推進閘）。

    硬格＝``deliverables_required`` 或 ``min_artifact_counts`` 非空；現況命中 6 格：
    1.1b / 1.2 / 2.1 / 2.2 / 2.6 / 2.7（spec 22 §4.3）。供 progression watcher 與
    advance_router 的真人硬閘（G01）共用同一判準，避免兩處清單漂移。
    """
    return bool(sp.deliverables_required) or bool(sp.min_artifact_counts)


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


# 每個 macro stage 進入時要落到的第一個 sub-phase（spec 22 §2.4）。
_STAGE_TO_FIRST_SUB: dict[str, str] = {
    "warmup": "0.0a",
    "discover": "1.1a",
    "define": "2.1",
}


def get_first_sub_phase_of_macro(macro_stage: str) -> str | None:
    """First sub-phase id for the given macro_stage（明確 map 優先,否則順序掃描）。"""
    explicit = _STAGE_TO_FIRST_SUB.get(macro_stage)
    if explicit is not None:
        return explicit
    for sub_phase_id in SUB_PHASE_ORDER:
        if SUB_PHASES[sub_phase_id].macro_stage == macro_stage:
            return sub_phase_id
    return None


def get_first_sub_phase_of_micro(micro_phase: str) -> str | None:
    """First sub-phase id whose parent_micro_phase matches the given micro_phase.

    例：``get_first_sub_phase_of_micro("2.2") -> "2.2"``、``"1.1" -> "1.1a"``。
    用於 advance_micro_phase / advance_stage 路徑重置 timer 時找到正確的 sub_phase。
    """
    for sub_phase_id in SUB_PHASE_ORDER:
        if SUB_PHASES[sub_phase_id].parent_micro_phase == micro_phase:
            return sub_phase_id
    return None


def validate_sub_phase_advance(from_id: str, to_id: str) -> bool:
    """Forward advancement only (next-in-sequence)."""
    return get_next_sub_phase(from_id) == to_id


def is_sub_phase_macro_boundary(from_id: str, to_id: str) -> bool:
    """True if transition crosses macro stages.

    spec 22 §11.2：``is_sub_phase_macro_boundary("1.2", "2.1") is True``（discover→define）。
    """
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
