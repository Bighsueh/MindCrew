"""Canvas manipulation tools for AI agents.

These tools translate high-level intents into coordinate operations:
  move_note, arrange_notes, create_note, swap_notes, tidy_area, draw_zone

Spec 13 — create_note 整合 zone resolution + content gate + template validation。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.bridge.canvas_ops import canvas_ops
from app.canvas.analyzer import get_spatial_analyzer
from app.canvas.content_gate import check_text, check_text_with_llm
from app.canvas.placement_lock import placement_lock
from app.canvas.layout_engine import (
    SPACING_VALUES,
    CoordinateUpdate,
    get_layout_engine,
)
from app.canvas.spatial import NOTE_HEIGHT, NOTE_WIDTH
from app.canvas.text_templates import validate_template, validate_template_with_canvas
from app.canvas.zone_registry import (
    get_all_zones_for_project,
    get_zone_bounds,
    register_zone,
)
from app.canvas.zones import (
    Bounds,
    Zone,
    ZONES,
    get_active_zones,
    get_zone,
    resolve_zone_by_position,
)
from app.chinese.converter import chinese_converter
from app.stages.sub_phases import SUB_PHASES, get_sub_phase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GateRejection:
    """Represents a rejection from any gate (zone / color / content / template)."""

    reason_zh: str
    rule_module: str
    rule_name: str
    matched_text: str | None = None


@dataclass(frozen=True)
class CreateNoteOutcome:
    """Outcome of a gated create_note call."""

    success: bool
    note_id: str | None = None
    x: float | None = None
    y: float | None = None
    rejection: GateRejection | None = None
    zone_id: str | None = None
    gate_violation_metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Spec 27 (Phase 36) — 接話式（threaded_reveal）helpers
# ---------------------------------------------------------------------------


# 人本暖場：每位作者便條上限（避免單一 agent 在暖場連刷灌牆；聊天不受限）。
# Phase 38 (spec/28 §7)：暖場已升格為 macro stage（0.0a）；group_id strip 與 per-agent
# 便條上限 retarget 1.1a → 0.0a（1.1a 還原為一般 discover 經驗分享步驟）。
# Phase 42 B1 (spec/28 §3.2 v2.0)：衝量模式 cap 2 → 8（去重保留）；組長解禁貼便條
# 但**限示範一張**（內容便條 cap=1，標題 label 不計；§4「嚴禁示範以外灌牆」機制化）。
_WARMUP_SUB_PHASES = frozenset({"0.0a"})
_WARMUP_PER_AGENT_NOTE_CAP = 8
_WARMUP_SUPERVISOR_NOTE_CAP = 1


def _warmup_author_note_count(notes: list[Any], author_tag: str) -> int:
    """該作者（"Name(type)"）在牆上的內容便條數（暖場 per-agent 上限用）。"""
    return sum(
        1 for n in notes
        if getattr(n, "author_name", "") == author_tag
        and getattr(n, "kind", "content") == "content"
    )


def _is_threaded_sub_phase(sub_phase_id: str | None) -> bool:
    """True 若該 sub-phase 使用接話式（threaded_reveal）互動模式。"""
    if not sub_phase_id:
        return False
    try:
        sp = get_sub_phase(sub_phase_id)
    except KeyError:
        return False
    return "threaded_reveal" in sp.comm_modes


def _should_dedupe_sub_phase(sub_phase_id: str | None) -> bool:
    """True 若該 sub-phase 應啟用去重 gate。

    Phase 41：從「僅接話式 threaded_reveal」泛化到**所有發散貼便條階段**（`phase_intent=
    divergent`，如 1.1b / 2.2）。移除沉默後，發散期 AI 可自由貼+講，去重 gate 是防止
    「換句話說重貼 / 洗版」的硬性兜底（取代原 silent_write 的部分作用）。
    Phase 42 B1：暖場（0.0a）明確納入——衝量模式（cap 8）下「同句洗版」風險更高，
    spec 28 §3.2/§6「去重保留」（0.0a 在 phase_intent 屬過渡、原本不在發散集合內）。
    """
    if sub_phase_id in _WARMUP_SUB_PHASES:
        return True
    if _is_threaded_sub_phase(sub_phase_id):
        return True
    try:
        from app.stages.phase_intent import get_phase_intent_by_sub_phase

        return get_phase_intent_by_sub_phase(sub_phase_id) == "divergent"
    except Exception:
        return False


def _normalize_concept(text: str) -> str:
    """正規化概念文字供去重比對：去標點 / 空白、轉小寫。"""
    return re.sub(r"[\s，。、！？!?,.~～「」『』（）()：:；;]+", "", text).lower()


# Spec 27 §4.4 (P4)：同主題群內，CJK 字集 Jaccard 重疊 ≥ 此值 → 視為「換句話說」的
# 重述（含詞序重排 / 大量用字重用）。設得保守（高）以免併掉同對象但實質不同的概念。
_DEDUP_CHARSET_JACCARD = 0.7


def _charset_jaccard(a: str, b: str) -> float:
    """CJK 單字集合 Jaccard，對短概念便條的重述 / 詞序重排偵測較 trigram 穩健。"""
    from app.agents.assess_heuristics import extract_cjk_ngrams

    sa = extract_cjk_ngrams(a, n=1)
    sb = extract_cjk_ngrams(b, n=1)
    if not sa or not sb:
        return 0.0
    union = len(sa | sb)
    return len(sa & sb) / union if union else 0.0


def _is_duplicate_concept(
    text: str, group_id: str | None, notes: list[Any]
) -> str | None:
    """Spec 27 §4.4 + Phase 41：去重 — 牆上若已有「實質相同」的概念便條，回傳其 id。

    判定層級（皆為確定性、無 LLM）：
    - 正規化後**完全相同** → 重複（即使跨群，例：同一句被貼兩次）。
    - 一方包含另一方（重述、長度 ≥6）→ 重複。
    - CJK 字集 Jaccard ≥ ``_DEDUP_CHARSET_JACCARD``（換句話說 / 詞序重排）→ 重複。
    後兩項（近似比對）的適用範圍：接話式（有 group_id）限**同主題群**（避免併掉同對象的不同
    概念）；發散非接話格（``group_id is None``，Phase 41）對**全牆**比對（防發散期換句話說重貼）。
    無相符回傳 None。

    註：純同義且用字幾乎不重疊（如「價格太貴」vs「覺得不划算」）需 LLM 語意層補強，
    屬後續工作；本函式只做不需 LLM 的確定性層，避免誤併同對象的不同概念。
    """
    norm = _normalize_concept(text)
    if not norm:
        return None
    for n in notes:
        other_raw = getattr(n, "text", "") or ""
        other = _normalize_concept(other_raw)
        if not other:
            continue
        if norm == other:
            return n.id
        same_group = bool(group_id) and getattr(n, "concept_group_id", None) == group_id
        # Phase 41：接話式（有 group_id）維持「僅同群」近似比對，避免併掉同對象的不同概念；
        # 發散非接話格（無 group_id）對全牆做近似比對，防「換句話說重貼」。Jaccard 門檻高（0.7）
        # 限制跨主題誤併；發散期本就該抑制近似重複以求廣度。
        if not (same_group or group_id is None):
            continue
        if (norm in other or other in norm) and min(len(norm), len(other)) >= 6:
            return n.id
        if _charset_jaccard(text, other_raw) >= _DEDUP_CHARSET_JACCARD:
            return n.id
    return None


def _pick_target_zone(
    active: list[Zone],
    project_bounds: dict[str, Bounds],
) -> tuple[Zone, Bounds] | None:
    """取第一個有可解析 bounds（registered 優先、否則 default_bounds）的 active zone。

    多 zone phase 時 LLM 通常自帶 position，snap 只當安全網，故取確定性的第一個即可。
    """
    for zone in active:
        bounds = project_bounds.get(zone.id) or zone.default_bounds
        if bounds is not None:
            return zone, bounds
    return None


_ZONE_GROW_MARGIN = 60.0


async def _grow_zone_to_contain(
    project_id: UUID,
    zone_id: str,
    b: Bounds,
    x: float,
    y: float,
) -> None:
    """把 zone bounds 擴張到容納 (x,y) 的便條（含 margin），re-register 供 gate 接受。

    保留原左上原點、往右/下長大（必要時也能往上/左）；不改變的話不寫。
    註：dashed 框 redraw 走 best-effort（`broadcast_zone_drawn` 目前為 no-op），
    對 gate 通過不影響——重點是 registered bounds 變大、落點與 gate 一致。
    """
    m = _ZONE_GROW_MARGIN
    new_x = min(b.x, x - m)
    new_y = min(b.y, y - m)
    right = max(b.x + b.w, x + NOTE_WIDTH + m)
    bottom = max(b.y + b.h, y + NOTE_HEIGHT + m)
    new_w = right - new_x
    new_h = bottom - new_y
    if (new_x, new_y, new_w, new_h) == (b.x, b.y, b.w, b.h):
        return
    try:
        await register_zone(
            project_id, zone_id, Bounds(x=new_x, y=new_y, w=new_w, h=new_h)
        )
    except Exception:
        logger.debug("grow zone failed project=%s zone=%s", project_id, zone_id, exc_info=True)


def _group_anchor_in_bounds(
    group_id: str | None, notes: list[Any], b: Bounds
) -> tuple[float, float] | None:
    """同群且落在 bounds 內的成員左上錨點；無則 None（病根 C-3 群錨 snap 用）。"""
    if not group_id:
        return None
    members = [
        n for n in notes
        if getattr(n, "concept_group_id", None) == group_id
        and getattr(n, "kind", "content") != "label"
        and b.x <= n.x <= b.x + b.w
        and b.y <= n.y <= b.y + b.h
    ]
    if not members:
        return None
    return (min(m.x for m in members), min(m.y for m in members))


async def _snap_into_active_zone(
    x: float,
    y: float,
    sub_phase_id: str,
    project_id: UUID,
    engine: Any,
    notes: list[Any],
    *,
    group_id: str | None = None,
) -> tuple[float, float]:
    """便條落點若不在任一 active zone 內 → 放進 zone 的非重疊空位（保證 gate 通過、不疊）。

    - 已在 zone 內 → 原樣回（保留 Spec 27 concept_group 群聚）。
    - 否則：優先從「同群且在此 zone 內成員」的錨點起算（病根 C-3：保住群聚，不把
      grouped 便條一律丟到 zone 正中心打散）；無同群成員 → **帶內掃空位**
      （RC3：舊「zone 中心種子」讓連續便條堆在同一點；帶掃描與動態 section 走
      同一 `_place_in_section` 演算法，spec 10 §2.3 單一佈局邏輯）。
    - 落點若超出框 → **不 clamp**（clamp 會把便條釘在邊緣互疊），改長大 zone
      去容納（grow-to-contain）。
    - 無任何 bounds（真實設定缺口）→ 原樣回，讓 gate 照常拒絕（不遮蔽真問題）。
    - **落在動態 section 帶內 → 原樣回**（2026-07-13 live 修補，見下）。
    """
    # 2026-07-13 live 揪出（R1-b 最後一層）：本函式只認靜態 zone——落點算在動態
    # section 帶內時仍被「吸」回 active zone。實機：crew 用 `near:<選定區裡的PS>`
    # 貼選定理由，落點正確算在選定區內，卻被扯回問題定義牆（zone=pov_wall）→
    # selection_members 看不到 → 收口閘照樣不過。gate 已接受 section 落點（R1），
    # 落點吸附器也必須對稱地認得 section，否則 R1 的修復被這裡抵銷。
    if await _resolve_dynamic_section(project_id, x, y) is not None:
        return x, y

    project_bounds = await get_all_zones_for_project(project_id)
    if resolve_zone_by_position(x, y, sub_phase_id, project_zone_bounds=project_bounds):
        return x, y

    picked = _pick_target_zone(get_active_zones(sub_phase_id), project_bounds)
    if picked is None:
        return x, y
    zone, b = picked

    seed = _group_anchor_in_bounds(group_id, notes, b)
    if seed is not None:
        nx, ny = engine._find_non_colliding(
            seed[0], seed[1], notes, SPACING_VALUES["default"]
        )
    else:
        nx, ny = engine._place_in_section(
            b, notes, SPACING_VALUES["default"],
            forbidden=await _dynamic_section_bounds(project_id),
        )
    # 非重疊落點可能落在框外 → 長大 zone 容納（取代會造成重疊的 clamp）。
    await _grow_zone_to_contain(project_id, zone.id, b, nx, ny)
    return nx, ny


# AI 落點左上界夾制（RC3：實機曾出現 x=−126.9 漂出畫布左緣被裁切）。
# 只夾 AI/system 計算落點；人類 absolute 精準座標不經此（tldraw 無限畫布，
# 人類有權把便條拖到任何座標）。
_MIN_BOARD_X = 20.0
_MIN_BOARD_Y = 20.0


def _clamp_to_board(x: float, y: float) -> tuple[float, float]:
    return (max(_MIN_BOARD_X, x), max(_MIN_BOARD_Y, y))


async def _default_band_position(
    project_id: UUID,
    sub_phase_id: str | None,
    engine: Any,
    notes: list[Any],
) -> tuple[float, float] | None:
    """Spec 10 v2.0 §5.5「position 省略＝當前作用 section 的空位」。

    過渡期作用 section＝當前 sub_phase 的 active zone 帶（spec 10 §2.3），
    帶內掃空位（與動態 section 同一 ``_place_in_section`` 演算法）。
    無可用帶 → None（呼叫端退 legacy region:center 解析）。
    """
    if sub_phase_id is None:
        return None
    project_bounds = await get_all_zones_for_project(project_id)
    picked = _pick_target_zone(get_active_zones(sub_phase_id), project_bounds)
    if picked is None:
        return None
    _zone, band = picked
    return engine._place_in_section(
        band, notes, SPACING_VALUES["default"],
        forbidden=await _dynamic_section_bounds(project_id),
    )


async def _dynamic_section_bounds(project_id: UUID) -> tuple[Bounds, ...]:
    """動態 section（選定區）bounds——zone 帶落點的禁入區（防幽靈入選）。"""
    from app.canvas.sections import get_section_bounds_map

    try:
        return tuple((await get_section_bounds_map(project_id)).values())
    except Exception:  # pragma: no cover - sections 不可達退空
        return ()


async def _resolve_concept_position(
    position: str,
    group_id: str | None,
    is_threaded: bool,
    engine: Any,
    analysis: Any,
    *,
    project_id: UUID,
    sub_phase_id: str | None,
    author_type: str = "ai",
) -> tuple[float, float]:
    """Spec 27 §4.2 / §5：接話式落點 — 同主題群靠一起 + organic。

    - 人類指定絕對座標 → 尊重（不 snap）。
    - 接話式且該主題群已有成員 → 靠該群旁開新欄（同對象聚一起）。
    - position 省略（""）→ 當前作用帶的空位（spec 10 §5.5；RC3：取代舊預設
      region:center 造成的板中心堆積）。
    - 其餘維持呼叫端 position（near / cluster…），由 organic jitter 避免格子感。
    - 最後：若落點不在 active zone 內 → snap 進 zone（避免 no_active_zone 硬拒絕造成
      白板長期空白；見 plan「no_active_zone 100% 拒絕」）。
    """
    notes = analysis.notes
    clusters = analysis.cluster_state.clusters

    # R1b-re：`near:<id>` 的錨點 id 同受 LLM 剝前綴竄改——錨點對不上會靜默
    # 落回自動格位，等同沒填 position。對齊回實存 id。
    if position.startswith("near:"):
        position = f"near:{_normalize_note_id(position.split(':', 1)[1], notes)}"
    is_absolute = isinstance(position, str) and position.startswith("absolute:")
    if is_absolute and author_type == "human":
        ax, ay = engine.resolve_position(to=position, notes=notes, clusters=clusters)
        # Spec 27 §7 鐵律：發散期人類手貼也「只動這一張、不碰既有」。點擊處沒重疊 → 精確
        # 尊重（不 jitter、不 snap，維持 Spec 13 精準落點）；有重疊才以點擊處為種子做 per-note
        # 避讓（_find_non_colliding 唯讀既有便條，既有便條永不被移動）。
        if engine._has_collision(ax, ay, NOTE_WIDTH, NOTE_HEIGHT, notes):
            return engine._find_non_colliding(
                ax, ay, notes, SPACING_VALUES["default"]
            )
        return ax, ay

    # Spec 10 v2.0 §5.1/§5.3：LLM 永不給座標——AI 的 absolute: / grid: / region:
    # 逃生口一律忽略，改走「省略」語意（當前作用帶的空位）。
    if author_type != "human" and isinstance(position, str) and (
        is_absolute
        or position.startswith("grid:")
        or position.startswith("region:")
    ):
        logger.info(
            "AI position %r ignored（LLM 永不給座標/全板區域）→ 帶內落點", position,
        )
        position = ""

    # Phase 42 C0 (spec 10 §5.5)：position="section:<id>" → 帶內空位、避撞限本帶；
    # 不做 zone-snap（snap 會把便條拉回靜態 zone，毀掉動態 section 落點）。
    if isinstance(position, str) and position.startswith("section:"):
        from app.canvas.sections import get_section_bounds_map

        sections = await get_section_bounds_map(project_id)
        resolved = await resolve_section_target(project_id, position, sections)
        if resolved is not None:
            return engine.resolve_position(
                to=resolved, notes=notes, clusters=clusters, sections=sections,
            )

    if is_threaded and group_id and any(
        getattr(n, "concept_group_id", None) == group_id for n in notes
    ):
        x, y = engine.resolve_position(
            to=f"concept_group:{group_id}", notes=notes, clusters=clusters,
        )
    elif not position:
        # Spec 10 §5.5：省略＝當前作用帶的空位；無帶可用退 legacy region:center。
        band_pos = await _default_band_position(
            project_id, sub_phase_id, engine, notes
        )
        if band_pos is not None:
            x, y = band_pos
        else:
            x, y = engine.resolve_position(
                to="region:center", notes=notes, clusters=clusters,
            )
    else:
        x, y = engine.resolve_position(to=position, notes=notes, clusters=clusters)

    if sub_phase_id is not None:
        x, y = await _snap_into_active_zone(
            x, y, sub_phase_id, project_id, engine, notes, group_id=group_id,
        )
    return x, y


async def tool_move_note(
    project_id: UUID,
    note_id: str,
    to: str,
    direction: str | None = None,
    spacing: str = "default",
    group_id: str | None = None,
    moved_by: str | None = None,
) -> dict[str, Any]:
    """Move a single note to a semantic destination.

    moved_by: move-delta 事件歸因（spec 10 v2.0 §4.7；act 層帶作者 tag）。

    group_id: if provided, also updates the note's semantic concept_group_id
    (事後歸群 — 便條搬到哪群就屬於哪群，LLM context 下次即可讀到）。
    """
    analyzer = get_spatial_analyzer()
    engine = get_layout_engine()

    # Phase 42 C0 (spec 10 §5.3)：to="section:<id>" → 載入動態 section registry
    sections = None
    if to.startswith("section:"):
        from app.canvas.sections import get_section_bounds_map

        sections = await get_section_bounds_map(project_id)
        # 2026-07-13：LLM 幻覺 section id 的容錯（標題比對／唯一區）＋失敗時 WARNING。
        resolved = await resolve_section_target(project_id, to, sections)
        if resolved is None:
            # R1b-re：解析失敗不再落回 `_auto_grid_position` 靜默瞬移——move 無
            # gate 兜底，靜默＝可把便條（含選定 PS）移到任意格位而零訊號。拒絕
            # 並回報，LLM 下一輪改用【白板動態區】列的真 id。
            return {
                "success": False,
                "note_id": note_id,
                "error": "section_not_found: 找不到這個區 id——"
                "請改用【白板動態區】列出的實際區 id（sec_ 開頭）",
            }
        to = resolved

    # RC3：與 create 同一放置鎖＋寫後一致新鮮讀，避免併發移動/新增互撞。
    async with placement_lock(project_id):
        analysis = await analyzer.analyze(project_id, fresh=True)
        note_id = _normalize_note_id(note_id, analysis.notes)  # R1b-re：剝前綴容錯
        if to.startswith("near:"):  # R1b-re：near 錨點 id 同步容錯
            to = f"near:{_normalize_note_id(to.split(':', 1)[1], analysis.notes)}"
        x, y = engine.resolve_position(
            to=to,
            notes=analysis.notes,
            clusters=analysis.cluster_state.clusters,
            direction=direction,
            spacing=spacing,
            sections=sections,
        )
        x, y = _clamp_to_board(x, y)

        ok = await canvas_ops.batch_update_coordinates(
            project_id,
            [{"id": note_id, "x": x, "y": y}],
            moved_by=moved_by,
        )

    if ok and group_id is not None:
        await canvas_ops.update_note_group_id(project_id, note_id, group_id)

    return {"success": ok, "note_id": note_id, "x": x, "y": y, "group_id": group_id}


def _normalize_note_id(note_id: str, notes: list[Any]) -> str:
    """LLM 常把 `shape:note_…` 抄成 `note_…`（剝前綴）——對齊回實存 id。

    R1b-re live 實證（房 ff8ad088）：serializer 給的是全 id `[shape:note_…]`，
    gemma 回吐時剝掉 `shape:`，move 拿裸 id 打 sidecar → ok=False → 選定 PS 進
    不了選定區、2.6 有機路徑只能靠 time_box 兜底。與 section id 幻覺同類的
    id 竄改，工具層必須同等容錯。全不中 → 原樣回（下游照常回報失敗）。
    """
    if any(getattr(n, "id", None) == note_id for n in notes):
        return note_id
    prefixed = f"shape:{note_id}"
    if any(getattr(n, "id", None) == prefixed for n in notes):
        logger.info("note id 容錯：'%s' → '%s'（補 shape: 前綴）", note_id, prefixed)
        return prefixed
    return note_id


async def _section_pinned_ids(project_id: UUID, notes: list[Any]) -> set[str]:
    """目前落在任一動態 section 帶內的便條 id——版面工具不得把它們搬離其帶（spec 27 §7
    鐵律、canvas-DRAFT §1/§2「限本 section 水平帶內」）。

    與 gate/closing/perception 同一 ``sections.selection_members`` 界定（純由位置衍生：
    人類刻意把便條拖出帶外即自動解除、可正常退選），故 layout 存活的成員＝closing 仍認的
    選定成員，不會兩處分歧。section 不可達→空集（best-effort、不擋整理）。
    """
    from app.canvas.sections import selection_members

    try:
        members = await selection_members(project_id, notes)
    except Exception:  # pragma: no cover - sections 不可達退空
        return set()
    return {str(getattr(n, "id", "")) for n in members}


async def tool_arrange_notes(
    project_id: UUID,
    note_ids: list[str],
    layout: str,
    target_region: str,
    columns: int | None = None,
    spacing: str = "default",
    label: str | None = None,
    group_id: str | None = None,
    moved_by: str | None = None,
) -> dict[str, Any]:
    """Batch-arrange notes in a layout pattern.

    Spec 27 §6 / 病根 A：若帶 ``label``，自動建立的標題便條必須以 ``kind="label"``
    （與該群 ``group_id``）寫入，才會被辨識為分類便條、序列化給 LLM、畫面上可區別。
    """
    analyzer = get_spatial_analyzer()
    engine = get_layout_engine()

    # RC3：與 create/move 同一放置鎖＋fresh 讀（review 確認的無鎖寫路徑漏洞）。
    async with placement_lock(project_id):
        analysis = await analyzer.analyze(project_id, fresh=True)

        # R1b-re：剝前綴容錯要在 pinned 過濾前——裸 id 對不上 pinned 集會漏擋。
        note_ids = [_normalize_note_id(nid, analysis.notes) for nid in note_ids]

        # WS4：選定區/動態 section 成員不被版面工具搬離其帶（spec 27 §7、canvas-DRAFT §1/§2）。
        pinned_ids = await _section_pinned_ids(project_id, analysis.notes)
        pinned_skipped = sum(1 for nid in note_ids if nid in pinned_ids)
        if pinned_ids:
            note_ids = [nid for nid in note_ids if nid not in pinned_ids]

        # R1b-re：排列尾端不得延伸進動態 section 帶（非成員便條「位置入選」）。
        from app.canvas.sections import get_section_bounds_map

        try:
            section_bounds = tuple((await get_section_bounds_map(project_id)).values())
        except Exception:  # pragma: no cover - sections 不可達退空
            section_bounds = ()

        updates = engine.compute_arrangement(
            note_ids=note_ids,
            layout=layout,
            target_region=target_region,
            notes=analysis.notes,
            columns=columns,
            spacing=spacing,
            forbidden=section_bounds,
        )

        ok = await canvas_ops.batch_update_coordinates(
            project_id,
            [{"id": u.id, "x": u.x, "y": u.y} for u in updates],
            moved_by=moved_by,
        )

    result: dict[str, Any] = {
        "success": ok,
        "arranged_count": len(updates),
        "pinned_skipped": pinned_skipped,
        "layout": layout,
    }

    # Create a label note above the arrangement if requested
    if label and ok and updates:
        converted_label = chinese_converter.convert(label)
        min_x = min(u.x for u in updates)
        min_y = min(u.y for u in updates)
        label_note_id = await canvas_ops.add_note(
            project_id=project_id,
            content=converted_label,
            position={"x": min_x, "y": min_y - 160},
            color="blue",
            author_id="system",
            author_name="System",
            author_type="ai",
            kind="label",
            group_id=group_id,
        )
        result["label_note_id"] = label_note_id
        await analyzer.invalidate_semantic_cache(project_id)

    return result


async def tool_create_note(
    project_id: UUID,
    text: str,
    color: str = "yellow",
    position: str = "",
    author_id: str = "system",
    author_name: str = "System",
    author_type: str = "ai",
    sub_phase_id: str | None = None,
    force_publish: bool = False,
    *,
    kind: str = "content",
    group_id: str | None = None,
    owning_user_id: UUID | None = None,
    seat_role: str | None = None,
    cites: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new note at a semantic position with Spec 13 zone + gate checks.

    Args:
      position: 語意落點字串；**省略（""）＝當前作用帶的空位**（spec 10 §5.5）。
      sub_phase_id: 當前 sub-phase。若 None 則跳過所有 zone/gate 檢查（向下相容）
      force_publish: 人類使用者強制送出（違反 gate 但仍 publish，標記 gate_violation）。
        AI agent 不應啟用此 flag。
      kind: "content"（概念便條）/ "label"（分類標籤便條，Spec 27 §6，跳過 content/template gate）
      group_id: 接話式主題群（顧客 / 店員…）；同對象聚一起的依據，未提供則 None。
      seat_role: 發話席位（act 層帶入；Phase 42 B1 暖場「組長限示範一張」判定用）。
      cites: 引用鏈（被引用便條 id；Spec 06 v4.25 / Phase 42 C0，sidecar 過濾不存在 id）。

    Returns dict with: success, note_id, x, y, kind, group_id, [rejection], [zone_id], [gate_violation]
    """
    converted_text = chinese_converter.convert(text)

    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id)
    engine = get_layout_engine()

    is_threaded = _is_threaded_sub_phase(sub_phase_id)

    # 人本暖場：發散不分群 —— 即使 LLM 自願帶 group_id 也強制拿掉，保證暖場便條不分群。
    # （只移除系統強制還不夠：LLM 偶爾會自己塞 group_id，仍會造成發散期碎裂。）
    if sub_phase_id in _WARMUP_SUB_PHASES:
        group_id = None

    # 人本暖場：每位作者便條上限——超過就軟拒（聊天不受限），避免單一 agent 連刷灌牆。
    # Phase 42 B1（spec 28 §3.2/§4 v2.0）：衝量模式 cap 8；組長解禁但限示範一張
    # （標題 label 不計入——cap 只數 kind=content）。
    if sub_phase_id in _WARMUP_SUB_PHASES and kind == "content":
        is_supervisor = bool(seat_role and "supervisor" in seat_role.lower())
        cap = _WARMUP_SUPERVISOR_NOTE_CAP if is_supervisor else _WARMUP_PER_AGENT_NOTE_CAP
        author_tag = f"{author_name}({author_type})"
        if _warmup_author_note_count(analysis.notes, author_tag) >= cap:
            reason = (
                "示範便條貼一張就好——剩下的點子留給大家貼，你用聊天帶氣氛。"
                if is_supervisor
                else "暖場你已經貼了幾張了，先把空間留給其他人衝、改用聊天接話。"
            )
            return {
                "success": False,
                "rejection": {
                    "reason_zh": reason,
                    "rule_module": "warmup_pacing",
                    "rule_name": "warmup_per_agent_note_cap",
                    "matched_text": None,
                },
            }

    # 病根 B（基石）：接話式內容便條若 LLM 漏帶 group_id → 從既有主題群確定性兜底
    # （不依賴 LLM）。先補群再去重 / 落點，讓「同對象同群 / 靠群聚」即使 LLM 漏帶也成立。
    if is_threaded and kind == "content" and not group_id:
        from app.canvas.group_assignment import assign_group_id

        backfilled = assign_group_id(converted_text, analysis.notes)
        if backfilled:
            group_id = backfilled
            logger.info(
                "create_note group_id 兜底：'%s…' → 群 %s",
                converted_text[:16], backfilled,
            )

    # Spec 27 §4.4 + Phase 41：去重 — 同一個概念不重貼（含「換句話說」重述）。
    # 觸發由「僅接話式」泛化到「接話式 OR 發散階段」（防發散期 AI 洗版重貼）。
    # Phase 42 補正 R4（spec 27 v3.3 §4.4）：真人 force_publish＝明知重複仍要貼的
    # 最終決定權，不受貼上去重擋（gate 違規仍照常標 metadata）；AI 照常 dedup。
    if (
        _should_dedupe_sub_phase(sub_phase_id)
        and kind == "content"
        and not (author_type == "human" and force_publish)
    ):
        dup_id = _is_duplicate_concept(converted_text, group_id, analysis.notes)
        if dup_id:
            logger.info(
                "create_note dedup: '%s…' 與既有概念 %s 實質重複，跳過",
                converted_text[:16], dup_id,
            )
            return {
                "success": False,
                "deduped": True,
                "duplicate_of": dup_id,
                "rejection": {
                    "reason_zh": "這個概念牆上已經有了（或只是換句話說），就不重複貼了。",
                    "rule_module": "must_be_concept",
                    "rule_name": "duplicate_concept",
                    "matched_text": None,
                },
            }

    # Spec 27 §4.2 / §5：接話式同主題群靠一起 + organic 落點（非格子）。
    x, y = await _resolve_concept_position(
        position=position,
        group_id=group_id,
        is_threaded=is_threaded,
        engine=engine,
        analysis=analysis,
        project_id=project_id,
        sub_phase_id=sub_phase_id,
        author_type=author_type,
    )

    # Phase 22：席位鎖定色覆蓋（system author 不 override）；先算出實際會貼上的顏色，
    # 讓 gate 對「真正會用的色」檢查、並在不合 zone 時 coerce（而非硬拒）。
    from app.seats.colors import lookup_color_for_author
    seat_color = await lookup_color_for_author(project_id, author_id, author_type)
    base_color = seat_color or color

    # 若 sub_phase 提供 → 跑 Spec 13 gates（接話式加掛 must_be_concept；label 跳過 content/template）
    outcome = await _evaluate_create_gates(
        project_id=project_id,
        text=converted_text,
        color=base_color,
        x=x,
        y=y,
        sub_phase_id=sub_phase_id,
        author_type=author_type,
        force_publish=force_publish,
        is_threaded=is_threaded,
        kind=kind,
        owning_user_id=owning_user_id,
        agent_id=author_id,
    )
    if outcome.rejection is not None and not outcome.gate_violation_metadata:
        # Hard reject
        return {
            "success": False,
            "rejection": {
                "reason_zh": outcome.rejection.reason_zh,
                "rule_module": outcome.rejection.rule_module,
                "rule_name": outcome.rejection.rule_name,
                "matched_text": outcome.rejection.matched_text,
            },
        }

    # 作者身分色永遠勝出：便條色 = 作者席位色（system author 則沿用呼叫端傳入色）。
    # 不再依 zone allowed_colors 改色（取消 Spec 27 區域語意上色，見 progress.md 規格偏離記錄）。
    effective_color = base_color

    # Phase 24.A：寫入 ISO Z 時間戳供 Activity Highlight 配對（同作者 + 30s 視窗）。
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # RC3：實際落點在 per-project 放置鎖內、以「寫後一致」新鮮狀態重算後寫入——
    # 併發 create 彼此可見，不再因共用 3s 快照挑到同一空位互疊。
    # （gate 已用暫定落點驗過 zone；重算走同一 band/snap 邏輯，仍落同一 active zone。）
    async with placement_lock(project_id):
        fresh_analysis = await analyzer.analyze(project_id, fresh=True)
        x, y = await _resolve_concept_position(
            position=position,
            group_id=group_id,
            is_threaded=is_threaded,
            engine=engine,
            analysis=fresh_analysis,
            project_id=project_id,
            sub_phase_id=sub_phase_id,
            author_type=author_type,
        )
        if author_type != "human":
            x, y = _clamp_to_board(x, y)
        # R1b-re：cites 同樣受 LLM 剝前綴竄改——sidecar 對不存在的 cite id 是
        # **靜默過濾**（canvas_ops docstring），2.6 配對閘依賴 cites，剝壞＝有機
        # 配對無聲失敗。寫入前對齊回實存 id。
        if cites:
            cites = [_normalize_note_id(c, fresh_analysis.notes) for c in cites]
        note_id = await canvas_ops.add_note(
            project_id=project_id,
            content=converted_text,
            position={"x": x, "y": y},
            color=effective_color,
            author_id=author_id,
            author_name=author_name,
            author_type=author_type,
            created_at=created_at,
            kind=kind,
            group_id=group_id,
            cites=cites,
        )

    # 紀錄 gate_violation metadata（人類強制送出時）。
    # Phase 42 補正 R3（§4.4）：canvas_ops.set_note_metadata 早已實作，
    # 舊 AttributeError 防禦分支永不觸發＝死碼，移除。
    if outcome.gate_violation_metadata:
        await canvas_ops.set_note_metadata(
            project_id=project_id,
            note_id=note_id,
            metadata={"gate_violation": outcome.gate_violation_metadata},
        )

    await analyzer.invalidate_semantic_cache(project_id)

    result: dict[str, Any] = {
        "success": True,
        "note_id": note_id,
        "x": x,
        "y": y,
        # Spec 27 便條欄位回傳（供 act layer / trace）
        "kind": kind,
        "group_id": group_id,
    }
    if outcome.zone_id:
        result["zone_id"] = outcome.zone_id
    if outcome.gate_violation_metadata:
        result["gate_violation"] = outcome.gate_violation_metadata
    return result


# spec 23 v2.1 §4.1.1 選定區列：動態 section 內新建內容便條的接受清單（match 任一）。
_SECTION_ACCEPTED_TEMPLATES: tuple[str, ...] = (
    "problem_statement",
    "selection_reason",
    "hmw",
)
# 全不中時用哪顆模板的指導語回覆（2.7 教設計題目句型；其餘教選定理由）。
_SECTION_PRIMARY_TEMPLATE: dict[str, str] = {"2.7": "hmw"}
_SECTION_PRIMARY_DEFAULT = "selection_reason"


async def resolve_section_target(
    project_id: UUID, target: str, sections: dict[str, Any]
) -> str | None:
    """把 LLM 給的 ``section:<X>`` 解析成真實的 ``section:<sec_id>``（不合法回 None）。

    2026-07-13 live 根因修補：LLM 常給幻覺 id（抄 few-shot 的 `s1`、或拿區的中文
    標題「選定區」當 id）。修復前這種目標**靜默**解析失敗 → 落回靜態 zone snap →
    選定理由便條落到問題定義牆、收口閘永遠看不到（無任何錯誤訊息）。

    解析順序：① 真 id 命中 ② 標題容錯（雙向子字串，如「選定區」→「選定區｜要往下
    做的問題」）③ 全場只有一條 section 時，任何 `section:` 目標都指它（第一鑽石只有
    選定區一條動態帶——spec 27 §14 的 C0 設計）。全不中 → 回 None ＋ WARNING。
    """
    raw = target.split(":", 1)[1].strip() if ":" in target else ""
    if raw in sections:
        return f"section:{raw}"

    titles: dict[str, str] = {}
    try:
        from app.canvas.sections import list_sections

        titles = {
            s["id"]: (s.get("title") or "")
            for s in await list_sections(project_id)
            if s.get("id") in sections
        }
    except Exception:
        logger.debug("resolve_section_target: list_sections failed", exc_info=True)

    if raw:
        for sid, title in titles.items():
            t = title.strip()
            if t and (raw in t or t in raw):
                logger.info(
                    "section target 容錯：'%s' → %s（標題比對「%s」）", raw, sid, title
                )
                return f"section:{sid}"

    if len(sections) == 1:
        only = next(iter(sections))
        # R1b-re：升 WARNING——這條兜底吃掉的是「LLM 沒用【白板動態區】列的真 id」
        # （照抄 few-shot 佔位符／幻覺 id），INFO 級等於把主路徑回歸藏起來：
        # serializer 若再度沒餵 id，單 section 場景照樣全綠、零訊號。
        logger.warning("section target 容錯：'%s' → %s（全場唯一動態區兜底）", raw, only)
        return f"section:{only}"

    logger.warning(
        "section target 解析失敗 project=%s target=%r（現存區：%s）——"
        "便條/搬動將落回靜態牆面，收口閘看不到它",
        project_id, target, list(sections),
    )
    return None


async def _resolve_dynamic_section(
    project_id: UUID, x: float, y: float
) -> dict[str, Any] | None:
    """(x, y) 落在哪條動態 section 帶（spec 27 v3.2 §14.8 合法落點判定用）。

    sections 不可達 → None（維持舊 no_active_zone 拒絕路徑，fail-closed 不遮蔽故障）。
    """
    from app.canvas.sections import list_sections, resolve_section_by_position

    try:
        return resolve_section_by_position(await list_sections(project_id), x, y)
    except Exception:
        logger.warning(
            "resolve_dynamic_section failed project=%s", project_id, exc_info=True
        )
        return None


async def _evaluate_section_create_gates(
    project_id: UUID,
    text: str,
    sub_phase_id: str,
    sub_phase: Any,
    section: dict[str, Any],
    author_type: str,
    force_publish: bool,
    is_threaded: bool,
    kind: str,
    owning_user_id: UUID | None,
    agent_id: str | None,
) -> CreateNoteOutcome:
    """動態 section 帶內的 create gate（spec 27 v3.2 §14.8／spec 23 v2.1 §4.1.1）。

    P0-1 修復：舊 code 對 section 零感知，`position="section:<id>"`（assembler
    few-shot 明教的路）必然 no_active_zone 硬拒——2.6 合格選定理由的有機路徑被
    結構性封死，只剩 forced_closure 兜底。本函式把 section 帶視為合法落點：
    content gate 照 sub_phase 規則跑、模板依選定區接受清單 match 任一。
    """
    zone_ref = f"section:{section.get('id', '')}"

    # kind=label（如 section 標題便條）跳過 content / template gate（spec 27 §6）。
    if kind == "label":
        return CreateNoteOutcome(success=True, zone_id=zone_ref)

    # Content gate：section 無 zone 層模組，套 sub_phase 規則（+接話式 must_be_concept）。
    module_set = set(sub_phase.gate_modules)
    if is_threaded:
        module_set.add("must_be_concept")
    gate_result = await check_text_with_llm(
        text,
        tuple(module_set),
        context={"sub_phase": sub_phase_id, "zone": zone_ref},
        project_id=project_id,
        agent_id=agent_id,
        owning_user_id=owning_user_id,
    )
    if not gate_result.passed:
        violation_metadata = None
        if author_type == "human" and force_publish:
            violation_metadata = {
                "phase": sub_phase_id,
                "zone_id": zone_ref,
                "rule": gate_result.violated_rule,
                "module": gate_result.violated_module,
                "matched_text": gate_result.matched_text,
            }
        return CreateNoteOutcome(
            success=False,
            zone_id=zone_ref,
            rejection=GateRejection(
                reason_zh=gate_result.message_zh or "違反語言規則",
                rule_module=gate_result.violated_module or "unknown",
                rule_name=gate_result.violated_rule or "unknown",
                matched_text=gate_result.matched_text,
            ),
            gate_violation_metadata=violation_metadata,
        )

    # 模板：接受清單 match 任一即過（spec 23 §4.1.1 選定區列）。
    results: dict[str, Any] = {}
    for template_id in _SECTION_ACCEPTED_TEMPLATES:
        tpl_result = await validate_template_with_canvas(text, template_id, project_id)
        if tpl_result.passed:
            return CreateNoteOutcome(success=True, zone_id=zone_ref)
        results[template_id] = tpl_result

    primary_id = _SECTION_PRIMARY_TEMPLATE.get(sub_phase_id, _SECTION_PRIMARY_DEFAULT)
    primary_result = results[primary_id]
    violation_metadata = None
    if author_type == "human" and force_publish:
        violation_metadata = {
            "phase": sub_phase_id,
            "zone_id": zone_ref,
            "rule": "template_mismatch",
            "module": f"template:{primary_id}",
            "matched_text": None,
        }
    return CreateNoteOutcome(
        success=False,
        zone_id=zone_ref,
        rejection=GateRejection(
            reason_zh=primary_result.reason_zh or "格式不符",
            rule_module=f"template:{primary_id}",
            rule_name="template_mismatch",
        ),
        gate_violation_metadata=violation_metadata,
    )


async def _evaluate_create_gates(
    project_id: UUID,
    text: str,
    color: str,
    x: float,
    y: float,
    sub_phase_id: str | None,
    author_type: str,
    force_publish: bool,
    is_threaded: bool = False,
    kind: str = "content",
    owning_user_id: UUID | None = None,
    agent_id: str | None = None,
) -> CreateNoteOutcome:
    """Run zone / color / content gate / template checks.

    AI 違規 → hard reject（gate_violation_metadata = None, rejection 有值）
    人類 + force_publish=True → publish but 標記 gate_violation
    人類 + force_publish=False → hard reject
    sub_phase_id=None → 直接 pass（向下相容）

    Spec 27：
      - is_threaded=True → content gate 加掛 must_be_concept（接話便條須為概念非對白）。
      - kind="label" → 分類標籤便條跳過 content / template gate（標籤非想法）。
    """
    if sub_phase_id is None:
        return CreateNoteOutcome(success=True)

    try:
        sub_phase = get_sub_phase(sub_phase_id)
    except KeyError:
        logger.warning("Unknown sub_phase %s in create_note; skip gates", sub_phase_id)
        return CreateNoteOutcome(success=True)

    # Step 1: Resolve zone —— 靜態 zone 查無 → 查動態 section 帶（spec 27 v3.2
    # §14.8：section 帶內＝合法落點；P0-1 修復，見 _evaluate_section_create_gates）。
    project_bounds = await get_all_zones_for_project(project_id)
    zone = resolve_zone_by_position(x, y, sub_phase_id, project_zone_bounds=project_bounds)
    if zone is None:
        section = await _resolve_dynamic_section(project_id, x, y)
        if section is not None:
            return await _evaluate_section_create_gates(
                project_id=project_id,
                text=text,
                sub_phase_id=sub_phase_id,
                sub_phase=sub_phase,
                section=section,
                author_type=author_type,
                force_publish=force_publish,
                is_threaded=is_threaded,
                kind=kind,
                owning_user_id=owning_user_id,
                agent_id=agent_id,
            )
        return CreateNoteOutcome(
            success=False,
            rejection=GateRejection(
                reason_zh="這個位置沒有落在框起來的區域裡，請把便條貼到畫面上框起來的區域內。",
                rule_module="zone_resolution",
                rule_name="no_active_zone",
            ),
        )

    # Step 2: phase_visible 已由 get_active_zones 過濾，再次確認
    if sub_phase_id not in zone.phase_visible:
        return CreateNoteOutcome(
            success=False,
            rejection=GateRejection(
                reason_zh=f"區域「{zone.id}」於本階段不開放寫入。",
                rule_module="zone_resolution",
                rule_name="zone_not_visible",
            ),
        )

    # Step 3: 顏色不再由 zone 強制。作者身分色永遠勝出，故此處不做 color coerce。
    # （zone.allowed_colors 保留於 zones.py 供其他用途；不影響便條上色。）

    # Spec 27：分類標籤便條（kind=label）非想法 → 跳過 content + template gate。
    if kind == "label":
        return CreateNoteOutcome(success=True, zone_id=zone.id)

    # Step 4: Content gate — 套用 zone + sub_phase 合併規則
    module_set = set(zone.gate_modules) | set(sub_phase.gate_modules)
    # Spec 27：接話式（threaded_reveal）加掛 must_be_concept（便條須是沉澱概念非對白/問句）
    if is_threaded:
        module_set.add("must_be_concept")
    all_modules = tuple(module_set)
    # Spec 14: 使用 LLM-judged 兩層評估（regex 預過濾 + LLM 確認，能識別引述/否定/Meta）
    gate_result = await check_text_with_llm(
        text,
        all_modules,
        context={"sub_phase": sub_phase_id, "zone": zone.id},
        project_id=project_id,
        agent_id=agent_id,
        owning_user_id=owning_user_id,
    )
    if not gate_result.passed:
        violation_metadata = None
        if author_type == "human" and force_publish:
            # Human override allowed
            violation_metadata = {
                "phase": sub_phase_id,
                "zone_id": zone.id,
                "rule": gate_result.violated_rule,
                "module": gate_result.violated_module,
                "matched_text": gate_result.matched_text,
            }
        return CreateNoteOutcome(
            success=False,
            zone_id=zone.id,
            rejection=GateRejection(
                reason_zh=gate_result.message_zh or "違反語言規則",
                rule_module=gate_result.violated_module or "unknown",
                rule_name=gate_result.violated_rule or "unknown",
                matched_text=gate_result.matched_text,
            ),
            gate_violation_metadata=violation_metadata,
        )

    # Step 5: Template check —— templates＝接受清單，只在強制 sub_phase 比對且
    # match **任一**即過（spec 23 v2.1 §4.1.1；P0-2 修復：舊語意「全部強制」把
    # 1.2 >15 字痛點便條、2.3 根源概念自由文字全誤殺）。
    if zone.templates and sub_phase_id in zone.template_required_sub_phases:
        tpl_results: dict[str, Any] = {}
        for template_id in zone.templates:
            # Spec 14 N4: 使用 canvas-aware 版本驗證 cite id 存在性
            tpl_result = await validate_template_with_canvas(text, template_id, project_id)
            if tpl_result.passed:
                return CreateNoteOutcome(success=True, zone_id=zone.id)
            tpl_results[template_id] = tpl_result

        primary_id = zone.templates[0]
        primary_result = tpl_results[primary_id]
        violation_metadata = None
        if author_type == "human" and force_publish:
            violation_metadata = {
                "phase": sub_phase_id,
                "zone_id": zone.id,
                "rule": "template_mismatch",
                "module": f"template:{primary_id}",
                "matched_text": None,
            }
        return CreateNoteOutcome(
            success=False,
            zone_id=zone.id,
            rejection=GateRejection(
                reason_zh=primary_result.reason_zh or "格式不符",
                rule_module=f"template:{primary_id}",
                rule_name="template_mismatch",
            ),
            gate_violation_metadata=violation_metadata,
        )

    return CreateNoteOutcome(success=True, zone_id=zone.id)


async def tool_swap_notes(
    project_id: UUID,
    note_id_a: str,
    note_id_b: str,
    moved_by: str | None = None,
) -> dict[str, Any]:
    """Swap the positions of two notes."""
    analyzer = get_spatial_analyzer()

    # RC3：與 create/move 同一放置鎖＋fresh 讀（review 確認的無鎖寫路徑漏洞）。
    async with placement_lock(project_id):
        analysis = await analyzer.analyze(project_id, fresh=True)

        note_id_a = _normalize_note_id(note_id_a, analysis.notes)  # R1b-re
        note_id_b = _normalize_note_id(note_id_b, analysis.notes)
        note_a = next((n for n in analysis.notes if n.id == note_id_a), None)
        note_b = next((n for n in analysis.notes if n.id == note_id_b), None)

        if not note_a or not note_b:
            return {"success": False, "error": "One or both notes not found"}

        # R1b-re：swap 是唯一漏掉 section 防護的座標寫路徑——成員資格純由位置
        # 衍生，帶內便條被換出＝靜默退選、帶外便條被換入＝幽靈入選，gate/closing/
        # 感知三方同時被污染。任一端是 section 成員即拒絕（與 arrange/tidy 的
        # pinned 語意對齊）。
        pinned_ids = await _section_pinned_ids(project_id, analysis.notes)
        if note_id_a in pinned_ids or note_id_b in pinned_ids:
            return {
                "success": False,
                "error": "section_pinned: 選定區內的便條不能交換位置"
                "（會改變入選狀態）；要調整請先把它搬出選定區",
            }

        ok = await canvas_ops.batch_update_coordinates(
            project_id,
            [
                {"id": note_id_a, "x": note_b.x, "y": note_b.y},
                {"id": note_id_b, "x": note_a.x, "y": note_a.y},
            ],
            moved_by=moved_by,
        )

    return {"success": ok, "swapped": [note_id_a, note_id_b]}


async def tool_tidy_area(
    project_id: UUID,
    scope: str,
    target: str | None = None,
    strategy: str = "align_grid",
    moved_by: str | None = None,
) -> dict[str, Any]:
    """Tidy a scope of the canvas.

    病根 E：整理改為依 ``concept_group_id`` 排成有標題位的欄（見 compute_tidy），並把分類
    標籤排到各群欄頂；缺標籤且該群 ≥3 張內容便條 → 自動補一張 ``kind="label"``（Spec 27 §6）。
    確定性 / 冪等：重跑同集合得同座標、不重複建標籤。

    RC3：整段「讀-算-寫」持 per-project 放置鎖（asyncio.Lock 不可重入——
    auto_reflow 在自己的鎖區塊外呼叫本工具，勿改）。
    """
    async with placement_lock(project_id):
        return await _tool_tidy_area_locked(
            project_id, scope, target, strategy, moved_by
        )


async def _tool_tidy_area_locked(
    project_id: UUID,
    scope: str,
    target: str | None,
    strategy: str,
    moved_by: str | None,
) -> dict[str, Any]:
    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id, fresh=True)
    engine = get_layout_engine()

    # WS4：選定區/動態 section 成員不被版面工具搬離其帶（spec 27 §7 鐵律、canvas-DRAFT §1/§2）。
    # 先取 pinned＋section bounds 供 compute 排格時「以實位佔位＋禁入選定帶」
    # （事後過濾保留為第二道保險）。
    pinned_ids = await _section_pinned_ids(project_id, analysis.notes)
    from app.canvas.sections import get_section_bounds_map

    try:
        section_bounds = tuple((await get_section_bounds_map(project_id)).values())
    except Exception:  # pragma: no cover - sections 不可達退空
        section_bounds = ()

    updates = engine.compute_tidy(
        scope=scope,
        target=target,
        strategy=strategy,
        notes=analysis.notes,
        clusters=analysis.cluster_state.clusters,
        pinned_ids=pinned_ids,
        forbidden=section_bounds,
    )

    pinned_skipped = sum(1 for u in updates if u.id in pinned_ids)
    if pinned_ids:
        updates = [u for u in updates if u.id not in pinned_ids]

    if not updates:
        return {"success": True, "tidied_count": 0, "pinned_skipped": pinned_skipped}

    label_anchors = engine.compute_group_label_anchors(
        scope=scope,
        target=target,
        strategy=strategy,
        notes=analysis.notes,
        clusters=analysis.cluster_state.clusters,
        forbidden=section_bounds,  # 與 compute_tidy 同組禁區，標籤才跟得上內容位移
    )

    coord_updates = [{"id": u.id, "x": u.x, "y": u.y} for u in updates]

    # 各群既有標籤 / 內容張數（用於「補標籤」與「重定位標籤」）。
    existing_label_by_group: dict[str, str] = {}
    content_count: dict[str, int] = {}
    for n in analysis.notes:
        gid = getattr(n, "concept_group_id", None)
        if not gid:
            continue
        if getattr(n, "kind", "content") == "label":
            existing_label_by_group.setdefault(gid, n.id)
        else:
            content_count[gid] = content_count.get(gid, 0) + 1

    created_labels = 0
    for gid, (raw_lx, raw_ly) in label_anchors.items():
        # 標籤落點夾左上界（帶頂群的標籤位在錨點上方，可能為負/咬進上一帶）。
        lx, ly = _clamp_to_board(raw_lx, raw_ly)
        if gid in existing_label_by_group:
            lbl_id = existing_label_by_group[gid]
            if lbl_id in pinned_ids:
                continue  # WS4：選定區內的標籤也不搬離
            # 既有標籤 → 重定位到欄頂（隨內容一起 batch 更新）。
            coord_updates.append({"id": lbl_id, "x": lx, "y": ly})
        elif content_count.get(gid, 0) >= 3:
            # Spec 27 §6：群已成形（≥3 張）卻無標籤 → 補一張分類標籤便條。
            await canvas_ops.add_note(
                project_id=project_id,
                content=chinese_converter.convert(gid),
                position={"x": lx, "y": ly},
                color="blue",
                author_id="system",
                author_name="System",
                author_type="ai",
                kind="label",
                group_id=gid,
            )
            created_labels += 1

    ok = await canvas_ops.batch_update_coordinates(
        project_id, coord_updates, moved_by=moved_by,
    )
    if created_labels:
        await analyzer.invalidate_semantic_cache(project_id)

    return {
        "success": ok,
        "tidied_count": len(updates),
        "pinned_skipped": pinned_skipped,
        "labels_created": created_labels,
        "strategy": strategy,
    }


# Spec 13: zone drawing tools now live in `app.canvas.tools_zones`
# Phase 42 C0: open_section（spec 10 v2.0 §5.9）同住 tools_zones
from app.canvas.tools_zones import (  # noqa: E402, F401
    tool_draw_zone,
    tool_open_section,
)


# ── Phase 2 Stubs ──


async def tool_create_arrow(
    project_id: UUID,
    from_note_id: str,
    to_note_id: str,
    label: str | None = None,
) -> dict[str, Any]:
    """Phase 2: Create an arrow between two notes."""
    raise NotImplementedError("Phase 2: create_arrow not yet implemented")


async def tool_create_frame(
    project_id: UUID,
    note_ids: list[str],
    title: str | None = None,
) -> dict[str, Any]:
    """Phase 2: Create a frame grouping notes."""
    raise NotImplementedError("Phase 2: create_frame not yet implemented")
