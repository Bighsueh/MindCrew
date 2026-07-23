"""Artifact-count gate（spec 25 v2.0，Phase 42 C1）.

This gate runs BEFORE ``advance_sub_phase`` / ``advance_stage`` to enforce
the ``min_artifact_counts`` declared on each ``SubPhase``.

v2.0（Phase 42 C1）計數語意：
- **牆面計數鍵**（短文字模板純文字分類不可靠，spec 23 v2.0 §2.0）：
  ``stakeholder``＝利害關係人牆內 ``kind != label`` 張數（去重在貼上時 enforce，
  gate 不重複去重）；``pain_point``＝痛點牆內 ``kind != label`` 張數（痛點＝自由
  文字無模板，spec 25 §2.3）。
- **結構附加條件**（spec 25 §2.3 step 5）：1.2 每個高優先群（1.1d 標「高」的
  利害關係人群）≥1 張痛點，違規寫入 ``reasons_zh``（大白話，#29）。
- **2.1 主題群數**＝痛點牆內掛痛點的相異 ``concept_group_id`` 數（spec 23 §2.3；
  「每群 ≥1 痛點」由計數天然保證）。**2.2 問題定義**僅計入 ``cites`` 含 ≥2 筆痛點
  關聯者（spec 25 §2.3）。
- **特殊鍵（Phase 42 C2）**：``persona_complete`` 已隨 1.6/Persona 移除（§3.1）；
  ``selection_pairing``（2.6 收口閘，§3.2）／``hmw_pairing``（2.7 配對閘，§3.3）
  由 helper 動態判定（選定區成員＝動態 section 帶內便條），失敗以 ``reasons_zh`` 承載。
- intensity 縮放沿用 spec 16 §2.4（``effective_min_artifact_counts``，地板 1）。

Complementary to ``check_deliverables``（zone-bounded，v2.0 配置多為空）與
真人參與 gate（spec 20 v2.0 round_lock）；三層分工見 spec 25 §2.4。
Teacher / force-advance flows bypass this gate.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.canvas.text_templates import validate_template
from app.canvas.zones import ZONES, Bounds
from app.stages.sub_phases import SUB_PHASES

logger = logging.getLogger(__name__)


# Spec 25 v2.0 §3：特殊配對鍵（flat count 無法表達的跨便條組合條件）。
# selection_pairing（2.6 收口閘）／hmw_pairing（2.7 配對閘）由 helper 動態判定，
# 不走 flat template count。min_artifact_counts 中其值固定為 1＝啟用旗標（§3.4），
# 實際 requirement（2.6 上下限 1–3、2.7=N）由 helper 計算、不隨 intensity 縮放。
SPECIAL_KEYS: frozenset[str] = frozenset({"selection_pairing", "hmw_pairing"})

# 牆面計數鍵 → 所在 zone（過渡實作；section 版面引擎落地後改 section 成員查詢）。
_WALL_COUNT_KEYS: dict[str, str] = {
    "stakeholder": "stakeholder_public",
    "pain_point": "pain_wall",
}

# 1.1d 高優先標籤判定：kind=label 且文字以「高」開頭的短標籤（如「高」「高優先」）。
_HIGH_PRIORITY_MAX_LEN = 4


@dataclass(frozen=True)
class ArtifactGateResult:
    """Result of an artifact-gate check.

    Attributes:
        passed: True iff all requirements（含結構附加條件）are met.
        counts: ``{key: actual_count}`` for every required key.
        requirements: ``{key: min_count}`` from the sub_phase config.
        missing: ``{key: shortfall_count}`` — only includes keys where actual < min.
        reasons_zh: 結構性違規的大白話句子（spec 25 §2.2；#29 不講機制名）。
    """

    passed: bool
    counts: dict[str, int] = field(default_factory=dict)
    requirements: dict[str, int] = field(default_factory=dict)
    missing: dict[str, int] = field(default_factory=dict)
    reasons_zh: tuple[str, ...] = ()


def _classify_text(text: str) -> str | None:
    """Lightweight template detection: return the first template_id whose
    regex matches the text, or None.

    Used to count stickies by template (gate is project-scoped, not zone-scoped).
    Phase 42 C1：候選集收斂為現役模板（spec 23 v2.0 §2.0；牆面計數鍵不走此路）。
    短文字模板（stakeholder／problem_candidate）regex 高度重疊、純文字分類不可靠，
    一律以牆面＋kind 界定，不入候選。
    """
    if not text or not text.strip():
        return None
    from app.canvas.text_templates import TEMPLATES

    # selection_reason 隨批次 C2 進 TEMPLATES 後自動納入；未註冊的 id 必須跳過
    # （validate_template 對未知 id 回 passed=True，會把所有文字誤分類）。
    candidates = (
        "problem_statement",
        "hmw",
        "criteria",
        "selection_reason",
    )
    for tid in candidates:
        if tid not in TEMPLATES:
            continue
        if validate_template(text, tid).passed:
            return tid
    return None


def _aggregate_template_counts(notes: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for note in notes:
        text = getattr(note, "text", None) or getattr(note, "content", "") or ""
        tid = _classify_text(text)
        if tid is None:
            continue
        counts[tid] = counts.get(tid, 0) + 1
    return counts


async def _zone_bounds(project_id: UUID, zone_id: str) -> Bounds | None:
    """Registered bounds 優先、否則 default_bounds（與落點 snap 同口徑）。"""
    zone = ZONES.get(zone_id)
    if zone is None:
        return None
    try:
        from app.canvas.zone_registry import get_all_zones_for_project

        registered = await get_all_zones_for_project(project_id)
        if zone_id in registered:
            return registered[zone_id]
    except Exception:  # pragma: no cover - registry 不可達時退 default
        pass
    return zone.default_bounds


def _notes_in_bounds(notes: list[Any], bounds: Bounds) -> list[Any]:
    return [
        n for n in notes
        if bounds.contains(float(getattr(n, "x", 0.0)), float(getattr(n, "y", 0.0)))
    ]


async def _count_wall_notes(
    project_id: UUID, notes: list[Any], zone_id: str
) -> int:
    """牆面計數：zone 內 ``kind != label`` 的便條張數。"""
    bounds = await _zone_bounds(project_id, zone_id)
    if bounds is None:
        return 0
    return sum(
        1 for n in _notes_in_bounds(notes, bounds)
        if getattr(n, "kind", "content") != "label"
    )


def _is_high_priority_label(note: Any) -> bool:
    if getattr(note, "kind", "content") != "label":
        return False
    text = (getattr(note, "text", None) or getattr(note, "content", "") or "").strip()
    return bool(text) and text.startswith("高") and len(text) <= _HIGH_PRIORITY_MAX_LEN


def _high_priority_group_reasons(notes: list[Any]) -> list[str]:
    """1.2 結構附加條件：每個高優先群 ≥1 張痛點（spec 25 §2.3 step 5）。

    - 高優先群＝帶 concept_group_id 的「高」label 便條所指的群（1.1d 產出）。
    - 該群的痛點＝同 concept_group_id 的 ``kind != label`` 便條（1.2 掛群下）。
    - 「高」label 沒帶群關聯時無從歸屬，不計入條件（gate 變寬鬆、不誤卡）。
    """
    high_groups: dict[str, str] = {}
    for n in notes:
        if not _is_high_priority_label(n):
            continue
        gid = getattr(n, "concept_group_id", None)
        if gid:
            high_groups.setdefault(str(gid), str(gid))

    if not high_groups:
        return []

    covered: set[str] = set()
    for n in notes:
        if getattr(n, "kind", "content") == "label":
            continue
        gid = getattr(n, "concept_group_id", None)
        if gid and str(gid) in high_groups:
            covered.add(str(gid))

    shortfall = len(high_groups) - len(covered)
    if shortfall <= 0:
        return []
    return [
        f"排在優先的那幾群裡，還有 {shortfall} 群連一條具體的卡住情況都沒有——"
        "先回到那幾群，想想他們在什麼情況下會卡住。"
    ]


def _structural_reasons(sub_phase_id: str, notes: list[Any]) -> list[str]:
    """結構附加條件（spec 25 §2.3 step 5）。

    - 1.2：每個高優先群 ≥1 張痛點（C1）。
    - 2.1「每個主題群底下 ≥1 張痛點」由群計數本身天然保證（只計掛痛點的群，
      見 ``_count_theme_groups``），不另出 reasons_zh。
    """
    if sub_phase_id == "1.2":
        return _high_priority_group_reasons(notes)
    return []


# ── Phase 42 C2：2.1 / 2.2 計數語意（spec 25 v2.0 §2.3）─────────────────


def _notes_by_id(notes: list[Any]) -> dict[str, Any]:
    return {str(getattr(n, "id", "")): n for n in notes if getattr(n, "id", None)}


async def _count_theme_groups(project_id: UUID, notes: list[Any]) -> int:
    """2.1 主題群數＝痛點牆內「掛有 ≥1 張痛點便條的群」數（spec 23 v2.0 §2.3）。

    以 ``kind != label`` 便條的相異 ``concept_group_id`` 計（每個這樣的群至少 1 張痛點，
    天然滿足「每群 ≥1 痛點」附加條件）；無群關聯的散張不計。主題標籤（problem_candidate
    便條）為人類可見的群名，由 prompt/組長驅動，**不作計數真理來源**（避開 label 不帶
    群關聯的脆弱點，C1 live ④）。
    """
    bounds = await _zone_bounds(project_id, "pain_wall")
    if bounds is None:
        return 0
    groups: set[str] = set()
    for n in _notes_in_bounds(notes, bounds):
        if getattr(n, "kind", "content") == "label":
            continue
        gid = getattr(n, "concept_group_id", None)
        if gid:
            groups.add(str(gid))
    return len(groups)


def _count_problem_statements_with_cites(
    notes: list[Any], notes_by_id: dict[str, Any]
) -> int:
    """2.2 問題定義計入條件：通過模板 **且** ``cites`` 含 ≥2 筆痛點便條關聯（spec 25 §2.3）。

    cite 須能對回現存的 ``kind != label`` 便條（痛點來源）；手打文字編號不解析（#30）。
    """
    count = 0
    for n in notes:
        text = getattr(n, "text", None) or getattr(n, "content", "") or ""
        if not validate_template(text, "problem_statement").passed:
            continue
        valid = {
            c for c in (getattr(n, "cites", None) or ())
            if c in notes_by_id and getattr(notes_by_id[c], "kind", "content") != "label"
        }
        if len(valid) >= 2:
            count += 1
    return count


# ── Phase 42 C2：選定 section 與特殊鍵（spec 25 v2.0 §3.2 / §3.3）──────────


async def _selection_members(project_id: UUID, notes: list[Any]) -> list[Any]:
    """選定區成員界定已升格至 ``sections.selection_members``（單一真理來源，

    gate/closing/perception 共用，避免「哪張被選中」多處發散）。此處保留薄包裝以維持
    既有呼叫點不變。"""
    from app.canvas.sections import selection_members

    return await selection_members(project_id, notes)


def _is_problem_statement(note: Any) -> bool:
    text = getattr(note, "text", None) or getattr(note, "content", "") or ""
    return validate_template(text, "problem_statement").passed


def _note_text(note: Any) -> str:
    return getattr(note, "text", None) or getattr(note, "content", "") or ""


# 「符合準則：<名稱>」的名稱擷取——名稱段止於破折號／標點／行尾
# （對齊 spec 23 §2.5 格式「選定｜符合準則：〔準則名稱〕——〔說明〕」）。
_CRITERION_NAME_RE = re.compile(
    r"符合準則[:：]\s*([^，,。｜|\n—–\-]{1,30})"
)
# criteria 便條（spec 23 §2.5「準則：[名稱]｜衡量方式：…」）的名稱段。
_CRITERIA_TITLE_RE = re.compile(r"準則[:：]\s*([^｜|\n]{1,30})")


def criteria_notes(notes: list[Any]) -> list[Any]:
    """全牆中通過 criteria 模板的便條（2.5 準則；準則指名判定的比對母集）。"""
    return [n for n in notes if validate_template(_note_text(n), "criteria").passed]


def _names_criterion(reason_text: str, criteria: list[Any]) -> bool:
    """理由指名的準則名稱是否對得上現存準則便條（雙向子字串，空白正規化）。"""
    m = _CRITERION_NAME_RE.search(reason_text)
    if not m:
        return False
    stated = re.sub(r"\s+", "", m.group(1))
    if not stated:
        return False
    for c in _criteria_name_texts(criteria):
        if stated in c or c in stated:
            return True
    return False


def _criteria_name_texts(criteria: list[Any]) -> list[str]:
    """準則便條的名稱段（無名稱段時退全文），空白正規化。"""
    out: list[str] = []
    for c in criteria:
        text = _note_text(c)
        m = _CRITERIA_TITLE_RE.search(text)
        out.append(re.sub(r"\s+", "", m.group(1) if m else text))
    return out


def is_qualified_selection_reason(note: Any, criteria: list[Any]) -> bool:
    """合格選定理由（spec 25 §3.2／23 §2.5／27 §14.4b；Phase 42 補正 R1／P1-1）。

    ＝ time_box_forced（強制收口豁免），或同時滿足：
      (a) 通過 ``selection_reason`` 模板；
      (b) **真的指到 ≥1 條現存準則**——主判定＝「符合準則：」後的名稱對準則便條
          名稱雙向子字串比對；比不到名稱時走 cites 輔助（cites 指向任一準則便條）。
    修復前只驗 (a)，編造準則名照樣過閘（spec 25 §3.2「必指 ≥1 條 2.5 準則」被架空）。
    """
    if bool(getattr(note, "time_box_forced", False)):
        return True
    text = _note_text(note)
    if not validate_template(text, "selection_reason").passed:
        return False
    if _names_criterion(text, criteria):
        return True
    criteria_ids = {str(getattr(c, "id", "")) for c in criteria} - {""}
    return any(str(cid) in criteria_ids for cid in (getattr(note, "cites", None) or ()))


def _evaluate_selection_pairing(
    members: list[Any], notes: list[Any]
) -> tuple[int, list[str]]:
    """2.6 收口閘（spec 25 v2.0 §3.2）。

    合格配對＝選定區內 1 張問題定義 ＋ 1 張合格選定理由（cites 指向該問題定義；
    理由必須指到 ≥1 條現存準則，見 ``is_qualified_selection_reason``）。
    通過條件（三項同時）：合格配對 ≥1、問題定義 ≤3、無未配對問題定義。
    time_box_forced 理由便條視為合格配對（豁免指準則要求）。
    回 (合格配對數, reasons_zh)。
    """
    ps_notes = [n for n in members if _is_problem_statement(n)]
    ps_ids = {str(getattr(p, "id", "")) for p in ps_notes}
    criteria = criteria_notes(notes)
    non_ps = [n for n in members if str(getattr(n, "id", "")) not in ps_ids]
    reason_notes = [n for n in non_ps if is_qualified_selection_reason(n, criteria)]
    # 只差「指名準則對不上」的理由——單獨給指導語（不是格式錯，是準則名編造/打錯）。
    name_missed = [
        n for n in non_ps
        if n not in reason_notes
        and validate_template(_note_text(n), "selection_reason").passed
    ]

    paired = 0
    unpaired = 0
    for p in ps_notes:
        pid = str(getattr(p, "id", ""))
        if any(pid in (getattr(r, "cites", None) or ()) for r in reason_notes):
            paired += 1
        else:
            unpaired += 1

    reasons: list[str] = []
    if len(ps_notes) > 3:
        reasons.append(
            "選定區裡的問題定義有點多了——先一起收斂到最多三張最值得做的。"
        )
    if unpaired > 0:
        reasons.append(
            f"選定區還有 {unpaired} 張問題定義沒寫「為什麼選它」——"
            "每一張都要配一張選定理由，說清楚它符合我們訂的哪一條準則。"
        )
    if name_missed and unpaired > 0:
        reasons.append(
            "有理由便條寫的準則名稱，跟我們在準則區訂好的對不起來——"
            "把名稱改成準則區真的有的那一條，或貼的時候點選那張準則便條。"
        )
    if paired == 0 and not reasons:
        reasons.append(
            "還沒把談定的問題定義搬進選定區——把最值得做的一到三句搬進去，"
            "每張旁邊配一張「為什麼選它」的便條。"
        )
    return paired, reasons


def _evaluate_hmw_pairing(
    members: list[Any], notes: list[Any]
) -> tuple[int, list[str]]:
    """2.7 配對閘（spec 25 v2.0 §3.3）。

    N＝選定區內問題定義數（2.6 保證 1–3）。每張選定問題定義須配 ≥1 張設計題目
    （hmw 模板），且該設計題目 from（cites）指向這張選定問題定義。
    通過：N ≥1 且每張都有 ≥1 組有效配對。回 (已配對的選定問題定義數, reasons_zh)。
    張數＝選定數，無 ≥3 固定下限。
    """
    selected = [n for n in members if _is_problem_statement(n)]
    hmw_notes = [
        n for n in notes
        if validate_template(
            getattr(n, "text", None) or getattr(n, "content", "") or "", "hmw"
        ).passed
    ]

    paired = 0
    unpaired = 0
    for p in selected:
        pid = str(getattr(p, "id", ""))
        if any(pid in (getattr(h, "cites", None) or ()) for h in hmw_notes):
            paired += 1
        else:
            unpaired += 1

    reasons: list[str] = []
    if not selected:
        reasons.append(
            "還沒有選定的問題定義可以改寫——先回到上一步把要做的問題搬進選定區。"
        )
    elif unpaired > 0:
        reasons.append(
            f"還有 {unpaired} 張選定的問題定義沒有對應的設計題目——"
            "每一張都改寫成一句「我們可以怎麼…？」，寫的時候點選它對應的問題定義。"
        )
    return paired, reasons


async def _evaluate_special_key(
    key: str, project_id: UUID, notes: list[Any]
) -> tuple[int, list[str]]:
    """特殊鍵分派（spec 25 v2.0 §3）。回 (count, reasons_zh)。"""
    members = await _selection_members(project_id, notes)
    if key == "selection_pairing":
        return _evaluate_selection_pairing(members, notes)
    if key == "hmw_pairing":
        return _evaluate_hmw_pairing(members, notes)
    return 0, []


async def check_artifact_gate(
    project_id: UUID,
    sub_phase_id: str,
) -> ArtifactGateResult:
    """Check whether the sub_phase's ``min_artifact_counts`` are satisfied.

    Returns ``passed=True`` when:
    - sub_phase has no min_artifact_counts declared
    - canvas analysis fails (graceful degradation: don't block UX)
    - 所有 requirements（含結構附加條件）都達標
    """
    sp = SUB_PHASES.get(sub_phase_id)
    if sp is None or not sp.min_artifact_counts:
        return ArtifactGateResult(passed=True)

    # spec/16 §2.4: 依該專案 timer config 的 intensity 縮放門檻（地板 1）。
    requirements = dict(sp.min_artifact_counts)
    try:
        from app.timer.service import TimerService
        from app.timer.scaling import effective_min_artifact_counts

        config = await TimerService.get_config(project_id)
        requirements = effective_min_artifact_counts(sp, config)
    except Exception as exc:  # pragma: no cover - graceful degradation
        logger.debug("artifact_gate: intensity scaling skipped (%s)", exc)

    try:
        from app.canvas.analyzer import get_spatial_analyzer

        analyzer = get_spatial_analyzer()
        analysis = await analyzer.analyze(project_id)
        notes = list(analysis.notes)
    except Exception as exc:
        logger.warning(
            "artifact_gate: canvas analysis failed for %s — pass: %s",
            sub_phase_id,
            exc,
        )
        return ArtifactGateResult(
            passed=True,
            requirements=requirements,
        )

    # Aggregate counts（spec 25 v2.0 §2.3）：
    #   - 特殊鍵（selection_pairing / hmw_pairing）→ helper 動態判定（§3）
    #   - 2.1 problem_candidate → 主題群數；2.2 problem_statement → cites≥2 計入
    #   - 牆面計數鍵 → zone+kind；其餘 → 模板分類
    template_counts = _aggregate_template_counts(notes)
    notes_by_id = _notes_by_id(notes)
    counts: dict[str, int] = {}
    special_reasons: list[str] = []
    for key in requirements:
        if key in SPECIAL_KEYS:
            cnt, sp_reasons = await _evaluate_special_key(key, project_id, notes)
            counts[key] = cnt
            special_reasons.extend(sp_reasons)
        elif key == "problem_candidate" and sub_phase_id == "2.1":
            counts[key] = await _count_theme_groups(project_id, notes)
        elif key == "problem_statement" and sub_phase_id == "2.2":
            counts[key] = _count_problem_statements_with_cites(notes, notes_by_id)
        else:
            wall_zone = _WALL_COUNT_KEYS.get(key)
            if wall_zone is not None:
                counts[key] = await _count_wall_notes(project_id, notes, wall_zone)
            else:
                counts[key] = template_counts.get(key, 0)

    missing = {
        key: req - counts.get(key, 0)
        for key, req in requirements.items()
        if counts.get(key, 0) < req
    }

    # 特殊鍵 count≥1 但仍有結構違規（超量／未配對）時 missing 不含它——以 reasons 為準。
    reasons = _structural_reasons(sub_phase_id, notes) + special_reasons

    return ArtifactGateResult(
        passed=not missing and not reasons,
        counts=counts,
        requirements=requirements,
        missing=missing,
        reasons_zh=tuple(reasons),
    )


# spec 25 v2.0 §6 中文標籤表（Phase 42 補正 R2／P1-2＋G11）：一般計數鍵 → 大白話名詞。
# 涵蓋全部模板鍵＋牆面計數鍵；未知鍵一律走 fallback 句、**不得**把鍵名印出來（#29）。
_KEY_LABELS_ZH: dict[str, str] = {
    "stakeholder": "利害關係人便條",
    "pain_point": "痛點便條",
    "problem_candidate": "主題群標籤",
    "problem_statement": "問題定義便條",
    "criteria": "準則便條",
    "hmw": "設計題目便條",
    "selection_reason": "選定理由便條",
}

_UNKNOWN_KEY_FALLBACK_ZH = "這一關需要的便條還不夠。"


def gate_shortfall_lines_zh(result: ArtifactGateResult) -> list[str]:
    """單一素材源（spec 25 v2.0 §6）：三條 formatter 共用的逐條大白話句子。

    一般計數鍵套「{名詞}還不夠：目前 X 張，至少要 Y 張。」；特殊鍵與結構性違規
    直接取 ``reasons_zh``；未知鍵合併為一句 fallback（不印鍵名）。
    """
    lines: list[str] = []
    unknown_hit = False
    for key, shortfall in result.missing.items():
        # 特殊鍵（selection_pairing / hmw_pairing）的失敗一律由 reasons_zh 承載。
        if key in SPECIAL_KEYS:
            continue
        label = _KEY_LABELS_ZH.get(key)
        if label is None:
            tpl = None
            try:
                from app.canvas.text_templates import TEMPLATES

                tpl = TEMPLATES.get(key)
            except Exception:  # pragma: no cover - 標籤查詢失敗走 fallback
                tpl = None
            if tpl is not None:
                label = f"「{tpl.name_zh}」便條"
            else:
                unknown_hit = True
                continue
        have = result.counts.get(key, 0)
        need = result.requirements.get(key, have + shortfall)
        lines.append(f"{label}還不夠：目前 {have} 張，至少要 {need} 張。")
    lines.extend(getattr(result, "reasons_zh", ()) or ())
    if unknown_hit and _UNKNOWN_KEY_FALLBACK_ZH not in lines:
        lines.append(_UNKNOWN_KEY_FALLBACK_ZH)
    return lines


def format_gate_rejection_zh(result: ArtifactGateResult) -> str:
    """組裝大白話拒絕文案（spec 25 v2.0 §6 canonical）。

    給組長代言／watcher 兜底原樣發出用；開頭「還差一點才能往下」、
    不含機制名／規則代號／模板鍵名／英文縮寫。
    """
    lines = gate_shortfall_lines_zh(result)
    if not lines:
        return ""
    return "還差一點才能往下：\n  - " + "\n  - ".join(lines)


__all__ = [
    "ArtifactGateResult",
    "SPECIAL_KEYS",
    "check_artifact_gate",
    "format_gate_rejection_zh",
    "gate_shortfall_lines_zh",
]
