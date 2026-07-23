"""Group-scope tidy — spec 10 v2.0 §5.7 ``scope="group"``：就地收攏單一群。

與 ``_grouped_tidy``（scope=all/cluster/region，把 target 排到全板最下方）不同，
本模組**錨在該群自己的左上角**收攏成欄——不搬離原地、不動其他群、只送有變化
的差異（冪等，重跑同集合零更新）。這是 auto_reflow（RC4 保底）的整理原語，
符合 spec 27 §7 鐵律「每次只動少數便條、永不整面重排」。

獨立成檔以維持 layout_engine.py 檔案行數上限（≤500 行原則；該檔已超限，
不再增肥）。
"""

from __future__ import annotations

from typing import Any

from app.canvas.spatial import NOTE_HEIGHT, NOTE_WIDTH

# 與 layout_engine._GROUP_MAX_ROWS/_GROUP_MAX_COLS 同精神：每欄最多堆幾張、
# 欄滿往右開新欄（病根 C-1 的欄式群聚）。
_MAX_ROWS = 6
_MAX_COLS = 16
_LABEL_GAP = 10.0


def group_members(group_id: str, notes: list[Any]) -> list[Any]:
    """該群內容便條，依 created_at（後備 id）確定性排序。"""
    return sorted(
        (
            n for n in notes
            if getattr(n, "concept_group_id", None) == group_id
            and getattr(n, "kind", "content") != "label"
        ),
        key=lambda n: (getattr(n, "created_at", "") or "", n.id),
    )


def group_anchor(group_id: str, notes: list[Any]) -> tuple[float, float] | None:
    """群成員的穩定左上錨點（min x, min y）；空群回 None。"""
    members = group_members(group_id, notes)
    if not members:
        return None
    return (min(m.x for m in members), min(m.y for m in members))


def group_label_anchor(group_id: str, notes: list[Any]) -> tuple[float, float] | None:
    """群標籤落點＝錨點正上方一張便條的高度（同 above_cluster 慣例）。"""
    anchor = group_anchor(group_id, notes)
    if anchor is None:
        return None
    return (anchor[0], anchor[1] - NOTE_HEIGHT - _LABEL_GAP)


def _overlaps(x: float, y: float, ox: float, oy: float, ow: float, oh: float) -> bool:
    return (
        x < ox + ow and x + NOTE_WIDTH > ox and y < oy + oh and y + NOTE_HEIGHT > oy
    )


def compute_group_tidy(
    group_id: str,
    notes: list[Any],
    gap: float,
    pinned_ids: frozenset[str] | set[str] = frozenset(),
    forbidden: tuple[Any, ...] = (),
) -> list[tuple[str, float, float]]:
    """就地收攏一個群：以群錨點為原點逐欄由上往下排格。

    - 障礙物＝所有非本群便條（含標籤）＋**pinned 成員**（動態 section 帶內的
      選定成員以「實際位置」佔位、永不被排格——避免其他成員的計畫格位疊上它）。
    - forbidden：禁入矩形（動態 section bounds）——格位永不落進選定區
      （防幽靈入選，spec 27 §14 成員資格純由位置衍生）。
    - 成員依 created_at 排序逐一取「第一個空格」；已在目標位者不產生更新。
    - 回傳 (note_id, x, y) 差異清單（座標型別交由呼叫端包裝）。
    """
    members = [
        m for m in group_members(group_id, notes) if m.id not in pinned_ids
    ]
    if not members:
        return []

    anchor_x = min(m.x for m in members)
    anchor_y = min(m.y for m in members)
    member_ids = {m.id for m in members}
    obstacles = [n for n in notes if n.id not in member_ids]

    col_w = NOTE_WIDTH + gap
    row_h = NOTE_HEIGHT + gap

    claimed: list[tuple[float, float]] = []

    def _slot_free(x: float, y: float) -> bool:
        for f in forbidden:
            if _overlaps(x, y, f.x, f.y, f.w, f.h):
                return False
        for cx, cy in claimed:
            if _overlaps(x, y, cx, cy, NOTE_WIDTH, NOTE_HEIGHT):
                return False
        for o in obstacles:
            if _overlaps(x, y, o.x, o.y, o.width, o.height):
                return False
        return True

    updates: list[tuple[str, float, float]] = []
    for m in members:
        target: tuple[float, float] | None = None
        for col in range(_MAX_COLS):
            for row in range(_MAX_ROWS):
                x = anchor_x + col * col_w
                y = anchor_y + row * row_h
                if _slot_free(x, y):
                    target = (x, y)
                    break
            if target:
                break
        if target is None:
            # 格盤滿（極端）：從已認領格最下緣往下逐列找，保證收斂且不疊。
            y = max((cy for _, cy in claimed), default=anchor_y) + row_h
            while not _slot_free(anchor_x, y):
                y += row_h
            target = (anchor_x, y)
        claimed.append(target)
        if (m.x, m.y) != target:
            updates.append((m.id, target[0], target[1]))
    return updates
