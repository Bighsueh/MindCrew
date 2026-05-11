"""Canvas perception tools for AI agents.

Provides three levels of canvas information:
- get_canvas_summary (~400 tokens) — daily perception
- get_canvas_snapshot (~3600 tokens) — full layout decisions
- get_note_detail (~100 tokens) — single note inspection
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.canvas.analyzer import CanvasAnalysis, get_spatial_analyzer
from app.canvas.spatial import (
    assign_grid_position,
    assign_region,
    detect_overlaps,
    find_neighbors,
)


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
    }


async def get_canvas_snapshot(project_id: UUID) -> dict[str, Any]:
    """Full canvas state (~3600 tokens for 30 notes). Spec §4.3."""
    summary = await get_canvas_summary(project_id)

    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id)

    overlap_ids = _overlap_note_ids(analysis)
    cluster_map = _build_cluster_map(analysis)

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
        })

    return {
        **summary,
        "notes": notes_data,
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

    # 發散/收斂單一真實來源；本 hint 額外保留「重整理」子集（1.3 / 3.2 偏整理而非單純收斂）。
    from app.stages.phase_intent import get_phase_intent
    intent = get_phase_intent(micro_phase)
    _HEAVY_ORGANIZE_PHASES = frozenset(("1.3", "3.2"))

    hints: list[str] = []

    # 1. Overlap — always top priority
    if overlap_count > 0:
        hints.append(f"有 {overlap_count} 處便條紙重疊，影響可讀性，建議用 tidy_area 消除。")

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
                f"建議：先呼叫 get_canvas_snapshot 取得完整資訊，再對每個叢集執行 arrange_notes + label，"
                f"最後用 tidy_area 全局對齊。"
            )
        elif orderliness < 0.5:
            hints.append(
                "目前處於收斂整理階段，白板有序度偏低。"
                "建議做一次系統性整理（arrange_notes + label + tidy_area）。"
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
