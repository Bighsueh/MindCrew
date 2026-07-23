"""Canvas perception tools for AI agents.

Provides three levels of canvas information:
- get_canvas_summary (~400 tokens) — daily perception
- get_canvas_snapshot (~3600 tokens) — full layout decisions
- get_note_detail (~100 tokens) — single note inspection
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.canvas.analyzer import CanvasAnalysis, get_spatial_analyzer
from app.canvas.sections import list_sections, selection_members
from app.canvas.spatial import (
    assign_grid_position,
    assign_region,
    detect_overlaps,
    find_neighbors,
)
from app.canvas.text_templates import validate_template

logger = logging.getLogger(__name__)


async def get_canvas_summary(
    project_id: UUID,
    micro_phase: str | None = None,
) -> dict[str, Any]:
    """Lightweight canvas overview (~400 tokens). Spec §4.2."""
    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id)

    overlap_ids = _overlap_note_ids(analysis)

    clusters_data = []
    for c in analysis.cluster_state.clusters:
        members = [n for n in analysis.notes if n.id in c.note_ids]
        region = _dominant_region(members) if members else "center"
        density = "dense" if len(members) >= 5 else "sparse"
        has_overlaps = any(nid in overlap_ids for nid in c.note_ids)

        clusters_data.append({
            "cluster_id": c.cluster_id,
            "suggested_label": analysis.cluster_labels.get(c.cluster_id, ""),
            "note_count": len(c.note_ids),
            "region": region,
            "density": density,
            "has_overlaps": has_overlaps,
            "coherence_score": c.coherence_score,
        })

    ungrouped_data = _build_ungrouped_summary(analysis)

    # Spec 27 §6：分類/標示便條（kind=label）— 餵進 agent context 使其 follow。
    label_notes = [
        {
            "id": n.id,
            "text": n.text,
            "region": assign_region(n.cx, n.cy),
            "group_id": getattr(n, "concept_group_id", None),
        }
        for n in analysis.notes
        if getattr(n, "kind", "content") == "label"
    ]

    # Spec 27 §6/§7：明顯錯置偵測（供 Supervisor 介入糾正）。
    from app.canvas.misplacement_detector import detect_misplaced_notes
    misplaced = detect_misplaced_notes(analysis.notes)

    return {
        "summary": {
            "total_notes": len(analysis.notes),
            "board_bounds": analysis.board_bounds,
            "orderliness_score": analysis.orderliness_score,
            "overlap_count": len(analysis.overlap_pairs),
            "cluster_count": len(analysis.cluster_state.clusters),
            "ungrouped_count": len(analysis.cluster_state.ungrouped_note_ids),
            "largest_cluster_ratio": analysis.largest_cluster_ratio,
            "cross_cluster_max_similarity": analysis.cross_cluster_max_similarity,
        },
        "clusters": clusters_data,
        "ungrouped_notes": ungrouped_data,
        "organization_hint": _generate_organization_hint(analysis, micro_phase),
        # Spec 27
        "label_notes": label_notes,
        "misplaced_notes": misplaced,
    }


async def get_canvas_snapshot(project_id: UUID) -> dict[str, Any]:
    """Full canvas state (~3600 tokens for 30 notes). Spec §4.3."""
    summary = await get_canvas_summary(project_id)

    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id)

    overlap_ids = _overlap_note_ids(analysis)
    cluster_map = _build_cluster_map(analysis)

    # Phase 42 D1c-前導：把選定 section 內的問題定義投影進感知（衍生投影，非可寫
    # is_chosen，守住無投票模型）。與 first_diamond_closing 同一界定（section 成員＋
    # problem_statement 模板），避免「哪張被選中」在感知與結業分叉。
    members = await selection_members(project_id, analysis.notes)
    selected_ps_ids = {
        str(getattr(n, "id", ""))
        for n in members
        # 文字抽取與 artifact_gate._is_problem_statement 逐字一致（text→content→""），
        # 鎖死「選定」在感知與結業的同義界定，未來若有便條來源帶 content 也不分叉。
        if validate_template(
            getattr(n, "text", None) or getattr(n, "content", "") or "",
            "problem_statement",
        ).passed
    }

    # R1b-re：section 成員（含理由便條、標籤）也要投影旗標——section 帶開在全板
    # 最底、grid row 常 ≥21，`_normalize_canvas` 封存過濾原本只豁免 selected_ps →
    # 隊友剛貼的選定理由對 agent 隱形（live 房 3d1eb306 實證：supervisor 在 crew_1
    # 貼完理由 1 分鐘後又貼一張）。與 gate/closing 同一 selection_members 界定。
    member_ids = {str(getattr(n, "id", "")) for n in members}

    notes_data = []
    for n in analysis.notes:
        overlaps_with = [
            other for a, b in analysis.overlap_pairs
            for other in [b if a == n.id else a if b == n.id else None]
            if other is not None
        ]
        grid_pos = assign_grid_position(n.x, n.y)
        is_isolated = (
            n.id not in cluster_map
            and n.id not in overlap_ids
            and not any(
                other.id != n.id
                for other in analysis.notes
                if abs(other.cx - n.cx) < 400 and abs(other.cy - n.cy) < 400
            )
        )

        notes_data.append({
            "id": n.id,
            "text": n.text,
            "text_length": len(n.text),
            "color": n.color,
            "author_type": n.author_type,
            "author_name": n.author_name,
            "region": assign_region(n.cx, n.cy),
            "grid_position": list(grid_pos),
            "cluster_id": cluster_map.get(n.id),
            "overlaps_with": overlaps_with,
            "is_isolated": is_isolated,
            # Spec 27：便條欄位
            "kind": getattr(n, "kind", "content"),
            "concept_group_id": getattr(n, "concept_group_id", None),
            # Phase 42 D1c-前導：引用關聯（2.2/2.6/2.7 寫 cites 需看到既有 id）＋選定旗標。
            "cites": list(getattr(n, "cites", None) or []),
            "selected_ps": str(getattr(n, "id", "")) in selected_ps_ids,
            "in_section": str(getattr(n, "id", "")) in member_ids,
        })

    # 2026-07-13 live 揪出：agent 看不到動態 section 的真實 id（prompt 只有 few-shot
    # 的 `section:s1`）→ crew 一律幻覺 id（抄 s1／拿中文標題）→ `section:` 解析不到 →
    # 靜默 snap 回靜態 zone → 選定理由落到問題定義牆 → 2.6 收口閘有機永遠不過。
    # 修法：把現存 section（真 id＋標題）投影進感知，序列化層據此教 LLM 用實際 id。
    try:
        sections = [
            {"id": s["id"], "title": s.get("title", "")}
            for s in await list_sections(project_id)
        ]
    except Exception:
        # R1b-re：退空但必留 WARNING——原本零 log，sections 供應斷掉時 crew 直接
        # 回到幻覺 id 狀態且無任何診斷線索。
        logger.warning(
            "get_canvas_snapshot: list_sections 失敗，sections 退空 project=%s",
            project_id, exc_info=True,
        )
        sections = []

    return {
        **summary,
        "notes": notes_data,
        "sections": sections,
    }


async def get_note_detail(project_id: UUID, note_id: str) -> dict[str, Any] | None:
    """Single note details (~100 tokens). Spec §4.4."""
    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id)

    target = next((n for n in analysis.notes if n.id == note_id), None)
    if target is None:
        return None

    cluster_map = _build_cluster_map(analysis)
    overlaps_with = [
        other for a, b in analysis.overlap_pairs
        for other in [b if a == note_id else a if b == note_id else None]
        if other is not None
    ]
    neighbors = find_neighbors(note_id, analysis.notes)
    grid_pos = assign_grid_position(target.x, target.y)

    return {
        "id": target.id,
        "text": target.text,
        "text_length": len(target.text),
        "color": target.color,
        "author_type": target.author_type,
        "author_name": "",  # Not tracked at spatial level
        "created_at": target.created_at,
        "grid_position": list(grid_pos),
        "pixel_position": {"x": target.x, "y": target.y},
        "size": {"width": target.width, "height": target.height},
        "overlaps_with": overlaps_with,
        "cluster_id": cluster_map.get(target.id),
        "neighbors": neighbors,
        # Phase 42 D1c-前導：與 snapshot 一致暴露引用關聯（避免 detail 看不到 cites）。
        "cites": list(getattr(target, "cites", None) or []),
    }


# ── Organization Hint (Phase 15) ──


def _generate_organization_hint(
    analysis: CanvasAnalysis,
    micro_phase: str | None,
) -> str:
    """Produce phase-aware organization hint. Pure rules, no LLM, zero cost."""
    total = len(analysis.notes)
    if total == 0:
        return "白板是空的，無需整理。"

    orderliness = analysis.orderliness_score
    overlap_count = len(analysis.overlap_pairs)
    ungrouped_count = len(analysis.cluster_state.ungrouped_note_ids)
    cluster_count = len(analysis.cluster_state.clusters)
    ungrouped_ratio = ungrouped_count / total

    # 發散/收斂單一真實來源；「重整理」子集＝重歸類的收斂桶
    # （Phase 42 C1：舊 1.3 Persona 移除；2.1 痛點歸類＝按主題橫切重組群，屬重整理）。
    from app.stages.phase_intent import get_phase_intent
    intent = get_phase_intent(micro_phase)
    _HEAVY_ORGANIZE_PHASES = frozenset(("2.1",))

    hints: list[str] = []

    # 1. Overlap — always top priority
    if overlap_count > 0:
        hints.append(
            f"有 {overlap_count} 處便條紙重疊，影響可讀性，"
            f"建議對重疊所在的那一群用 tidy_area(scope=\"group\", target=\"群名\") 收攏。"
        )

    # 2. Phase-aware strategy
    if intent == "divergent":
        if orderliness < 0.25 and total > 12:
            hints.append(
                "目前處於發散階段，白板非常混亂。"
                "建議僅消除重疊和嚴重擁擠，不做語意分群——過早整理會抑制創意。"
            )
        else:
            hints.append("目前處於發散階段，保持便條紙自然散佈即可，不需整理。")
    elif micro_phase in _HEAVY_ORGANIZE_PHASES:
        if ungrouped_ratio > 0.4 and cluster_count >= 2:
            hints.append(
                f"目前處於收斂整理階段，有 {ungrouped_count} 張未分群便條紙（佔 {ungrouped_ratio:.0%}）。"
                f"建議：先呼叫 get_canvas_snapshot 取得完整資訊，一次挑幾張同類的用 arrange_notes + label 併成一群，"
                f"再對排最亂的那一群 tidy_area(scope=\"group\", target=\"群名\") 收攏（逐撮進行，不要整面重排）。"
            )
        elif orderliness < 0.5:
            hints.append(
                "目前處於收斂整理階段，白板有序度偏低。"
                "建議逐撮整理：每輪挑一群（arrange_notes 併群 + label，或 tidy_area scope=\"group\" 收攏），不要一次動全板。"
            )
        else:
            hints.append("目前處於收斂整理階段，白板結構尚可。可視需要微調。")
    elif intent == "convergent":
        if orderliness < 0.45:
            hints.append("目前處於收斂階段，白板偏亂。建議整理後再進行討論。")
    else:
        # Other phases or None: standard judgment
        if orderliness < 0.4 and total > 8:
            hints.append("白板有序度低，建議適時整理。")

    # 3. Structural quality
    if analysis.largest_cluster_ratio > 0.40 and cluster_count >= 2:
        biggest = max(analysis.cluster_state.clusters, key=lambda c: len(c.note_ids))
        label = analysis.cluster_labels.get(biggest.cluster_id, biggest.cluster_id)
        hints.append(f"叢集「{label}」佔比 {analysis.largest_cluster_ratio:.0%}，可能需要拆分為更細的子群組。")

    if analysis.cross_cluster_max_similarity > 0.75 and cluster_count >= 2:
        hints.append("有兩個叢集的語意高度相似，可能可以合併。")

    if not hints:
        return "白板狀態正常，無需特別整理。"

    return " ".join(hints)


# ── Helpers ──


def _overlap_note_ids(analysis: CanvasAnalysis) -> set[str]:
    ids: set[str] = set()
    for a, b in analysis.overlap_pairs:
        ids.add(a)
        ids.add(b)
    return ids


def _dominant_region(notes: list[Any]) -> str:
    """Most common region among notes."""
    from collections import Counter
    regions = [assign_region(n.cx, n.cy) for n in notes]
    if not regions:
        return "center"
    return Counter(regions).most_common(1)[0][0]


def _build_cluster_map(analysis: CanvasAnalysis) -> dict[str, str]:
    """Map note_id → cluster_id."""
    m: dict[str, str] = {}
    for c in analysis.cluster_state.clusters:
        for nid in c.note_ids:
            m[nid] = c.cluster_id
    return m


def _build_ungrouped_summary(analysis: CanvasAnalysis) -> list[dict[str, Any]]:
    """Build ungrouped notes summary with nearest cluster info (spatial proximity)."""
    ungrouped_ids = set(analysis.cluster_state.ungrouped_note_ids)
    notes_by_id = {n.id: n for n in analysis.notes}
    result = []

    for nid in analysis.cluster_state.ungrouped_note_ids:
        note = notes_by_id.get(nid)
        if note is None:
            continue

        nearest_cluster = None
        similarity = 0.0

        # Spatial proximity to clusters (inverse distance as similarity proxy)
        import math
        for c in analysis.cluster_state.clusters:
            members = [notes_by_id[mid] for mid in c.note_ids if mid in notes_by_id]
            if members:
                cx = sum(m.cx for m in members) / len(members)
                cy = sum(m.cy for m in members) / len(members)
                dist = math.hypot(note.cx - cx, note.cy - cy)
                # Use inverse distance as a rough similarity proxy
                sim = max(0.0, 1.0 - dist / 1000.0)
                if sim > similarity:
                    similarity = sim
                    nearest_cluster = c.cluster_id

        preview = note.text[:20] + "..." if len(note.text) > 20 else note.text
        result.append({
            "id": nid,
            "text_preview": preview,
            "region": assign_region(note.cx, note.cy),
            "nearest_cluster": nearest_cluster,
            "similarity_to_nearest": round(similarity, 2),
        })

    return result
