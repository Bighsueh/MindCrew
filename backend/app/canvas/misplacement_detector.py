"""明顯錯置偵測 — Spec 27 (Phase 36) §6 / §7。

Supervisor 只在便條「明顯、嚴重錯置」時出手糾正（不一直挑剔，呼應「不要太吵」）。
本模組提供**保守、確定性**的偵測：只標出強訊號的錯置，避免假陽性洗版。

判定（content 便條、且有 concept_group_id）：
  一張便條 n（屬群 g）被視為明顯錯置進 g2，需同時滿足：
    1. n 離自己群 g 的重心很遠（> min_separation）。
    2. n 離另一群 g2 的重心明顯更近（近 min_separation 以上的差距）。
    3. n 的 k 個最近鄰**全部**屬於 g2（被別群包圍）。
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def detect_misplaced_notes(
    notes: list[Any],
    *,
    min_separation: float = 450.0,
    neighbor_k: int = 3,
    max_flags: int = 5,
) -> list[dict[str, Any]]:
    """回傳明顯錯置的 content 便條清單（保守）。

    每筆：{note_id, text, current_group, near_group}
    notes 需具備 .id/.cx/.cy/.kind/.concept_group_id/.text（SpatialNote）。
    """
    content = [
        n for n in notes
        if getattr(n, "kind", "content") != "label"
        and getattr(n, "concept_group_id", None)
    ]
    by_group: dict[str, list[Any]] = defaultdict(list)
    for n in content:
        by_group[n.concept_group_id].append(n)

    if len(by_group) < 2:
        return []

    centroids: dict[str, tuple[float, float]] = {}
    for g, members in by_group.items():
        cx = sum(m.cx for m in members) / len(members)
        cy = sum(m.cy for m in members) / len(members)
        centroids[g] = (cx, cy)

    flagged: list[dict[str, Any]] = []
    for n in content:
        g = n.concept_group_id
        own_cx, own_cy = centroids[g]
        own_dist = _dist(n.cx, n.cy, own_cx, own_cy)

        others = [
            (g2, _dist(n.cx, n.cy, c2[0], c2[1]))
            for g2, c2 in centroids.items()
            if g2 != g
        ]
        if not others:
            continue
        g2, near_dist = min(others, key=lambda t: t[1])

        if own_dist <= min_separation:
            continue
        if near_dist + min_separation > own_dist:
            continue

        neighbors = sorted(
            (m for m in content if m.id != n.id),
            key=lambda m: _dist(n.cx, n.cy, m.cx, m.cy),
        )[:neighbor_k]
        if not neighbors:
            continue
        if all(m.concept_group_id == g2 for m in neighbors):
            flagged.append({
                "note_id": n.id,
                "text": (n.text or "")[:30],
                "current_group": g,
                "near_group": g2,
            })
        if len(flagged) >= max_flags:
            break

    return flagged
