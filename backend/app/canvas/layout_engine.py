"""Layout Engine: translate semantic movement intents into pixel coordinates.

Replaces sidecar's auto-layout logic. All layout computation happens here;
the sidecar only receives final coordinate updates.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from app.canvas.clustering import ClusterResult
from app.canvas.spatial import (
    BOARD_HEIGHT,
    BOARD_WIDTH,
    DEFAULT_GRID,
    GRID_START_X,
    GRID_START_Y,
    NOTE_HEIGHT,
    NOTE_WIDTH,
    GridConfig,
    SpatialNote,
    assign_region,
)

# ── Spacing Presets ──

SPACING_VALUES = {
    "compact": 10,
    "default": 15,
    "spacious": 30,
}


# ── Region Center Coordinates ──

_REGION_CENTERS: dict[str, tuple[float, float]] = {
    "top-left": (BOARD_WIDTH * 0.17, BOARD_HEIGHT * 0.25),
    "top-center": (BOARD_WIDTH * 0.50, BOARD_HEIGHT * 0.25),
    "top-right": (BOARD_WIDTH * 0.83, BOARD_HEIGHT * 0.25),
    "bottom-left": (BOARD_WIDTH * 0.17, BOARD_HEIGHT * 0.75),
    "bottom-center": (BOARD_WIDTH * 0.50, BOARD_HEIGHT * 0.75),
    "bottom-right": (BOARD_WIDTH * 0.83, BOARD_HEIGHT * 0.75),
    "center": (BOARD_WIDTH * 0.50, BOARD_HEIGHT * 0.50),
}

# ── Regex patterns for `to` string parsing ──

_RE_NEAR = re.compile(r"^near:(.+)$")
_RE_ABSOLUTE = re.compile(r"^absolute:(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$")
_RE_GRID = re.compile(r"^grid:(\d+),(\d+)$")
_RE_REGION = re.compile(r"^region:(.+)$")
_RE_CLUSTER = re.compile(r"^cluster:(.+)$")
_RE_ABOVE_CLUSTER = re.compile(r"^above_cluster:(.+)$")
# Spec 27 (Phase 36)：依語意主題群落點（同對象聚一起）
_RE_CONCEPT_GROUP = re.compile(r"^concept_group:(.+)$")
# Spec 10 v2.0 §5.5：`group:<group_id>` 為對外正式語彙（≡ concept_group:）
_RE_GROUP = re.compile(r"^group:(.+)$")
# Spec 10 v2.0 §5.3 (Phase 42 C0)：移到某條動態 section 帶（帶內空位）
_RE_SECTION = re.compile(r"^section:(.+)$")


# Spec 27：organic 落點 jitter — 取代整齊網格，讓擺放「像人」。
_ORGANIC_JITTER_PX = 22.0


def _organic_jitter(seed: int) -> tuple[float, float]:
    """Deterministic pseudo-random jitter in [-J, J]（避免機械對齊但可重現）。"""
    h = (seed * 2654435761 + 1013904223) & 0xFFFFFFFF
    jx = ((h & 0x3FF) / 0x3FF - 0.5) * 2 * _ORGANIC_JITTER_PX
    jy = (((h >> 11) & 0x3FF) / 0x3FF - 0.5) * 2 * _ORGANIC_JITTER_PX
    return jx, jy


@dataclass(frozen=True)
class CoordinateUpdate:
    """A single coordinate update to send to sidecar."""

    id: str
    x: float
    y: float


class LayoutEngine:
    """Translate high-level placement intents into pixel coordinates."""

    def __init__(self, grid: GridConfig = DEFAULT_GRID) -> None:
        self._grid = grid

    # ── Position Resolution ──

    def resolve_position(
        self,
        to: str,
        notes: list[SpatialNote],
        clusters: list[ClusterResult] | None = None,
        direction: str | None = None,
        spacing: str = "default",
        sections: dict[str, Any] | None = None,
    ) -> tuple[float, float]:
        """Parse a `to` string and return target (x, y) pixel coordinates.

        Supported formats:
          - "near:<note_id>"
          - "grid:<col>,<row>"
          - "region:<name>"
          - "cluster:<cluster_id>"
          - "above_cluster:<cluster_id>"
          - "section:<section_id>"（Phase 42 C0；sections={id: Bounds-like}，
            呼叫端自 sections registry 載入）
        """
        gap = SPACING_VALUES.get(spacing, SPACING_VALUES["default"])
        notes_map = {n.id: n for n in notes}

        # absolute:<x>,<y>  (Spec 13 — human drops at exact coord)
        m = _RE_ABSOLUTE.match(to)
        if m:
            return float(m.group(1)), float(m.group(2))

        # near:<note_id>
        m = _RE_NEAR.match(to)
        if m:
            ref_id = m.group(1)
            ref = notes_map.get(ref_id)
            if ref:
                return self._place_near(ref, notes, direction, gap)
            # Fallback: auto-grid
            return self._auto_grid_position(notes)

        # grid:<col>,<row>
        m = _RE_GRID.match(to)
        if m:
            col, row = int(m.group(1)), int(m.group(2))
            return self._grid_to_pixel(col, row)

        # region:<name>
        m = _RE_REGION.match(to)
        if m:
            region_name = m.group(1)
            return self._place_in_region(region_name, notes, gap)

        # cluster:<cluster_id>
        m = _RE_CLUSTER.match(to)
        if m:
            cluster_id = m.group(1)
            return self._place_in_cluster(cluster_id, notes, clusters, gap)

        # above_cluster:<cluster_id>
        m = _RE_ABOVE_CLUSTER.match(to)
        if m:
            cluster_id = m.group(1)
            return self._place_above_cluster(cluster_id, notes, clusters)

        # concept_group:<group_id> / group:<group_id>  (Spec 27 — 同主題群聚一起；
        # group: 為 spec 10 v2.0 §5.5 對外正式語彙)
        m = _RE_CONCEPT_GROUP.match(to) or _RE_GROUP.match(to)
        if m:
            return self._place_in_concept_group(m.group(1), notes, gap)

        # section:<section_id>  (Spec 10 v2.0 §5.3 — 動態 section 帶內空位)
        m = _RE_SECTION.match(to)
        if m and sections:
            band = sections.get(m.group(1))
            if band is not None:
                return self._place_in_section(band, notes, gap)

        # Fallback — Spec 27 organic 落點（取代整齊網格）
        return self._auto_grid_position(notes)

    def _place_in_section(
        self,
        band: Any,
        notes: list[SpatialNote],
        gap: float,
        forbidden: tuple[Any, ...] = (),
    ) -> tuple[float, float]:
        """Spec 10 v2.0 §5.3/§5.8：在 section 水平帶內找空位（避撞限本帶）。

        帶頭第一列留給標題便條（label band），內容從第二列起逐列由左而右掃描；
        本帶標稱高度掃滿仍無空位 → 繼續往帶下方延伸掃描（新帶開在最下方、其下
        為空白，視為帶的自然生長，不會侵入其他 phase 的帶）。

        forbidden：禁入矩形（有 x/y/w/h 的 Bounds-like）。zone 帶延伸時傳入動態
        section bounds，確保延伸格位永不落進選定區（防「幽靈入選」，spec 27 §14
        成員資格純由位置衍生）。

        Spec 27 §5.3 有機落點：選中的空格會嘗試套確定性 jitter（仍驗證不碰撞、
        不出帶、不入禁區），避免「回退整齊網格」（§12.6 硬驗收）。
        """
        bx = float(band.x)
        by = float(band.y)
        bw = float(band.w)
        bh = float(band.h)

        col_w = NOTE_WIDTH + gap
        row_h = NOTE_HEIGHT + gap
        cols = max(1, int((bw - 2 * gap) // col_w))
        content_top = by + NOTE_HEIGHT + 2 * gap  # 第一列＝標題帶
        nominal_rows = max(1, int((bh - (content_top - by)) // row_h))

        def _in_forbidden(x: float, y: float) -> bool:
            for f in forbidden:
                if (
                    x < f.x + f.w and x + NOTE_WIDTH > f.x
                    and y < f.y + f.h and y + NOTE_HEIGHT > f.y
                ):
                    return True
            return False

        for row in range(nominal_rows + 12):  # 標稱列數掃滿 → 往下延伸（帶的生長）
            for col in range(cols):
                x = bx + gap + col * col_w
                y = content_top + row * row_h
                if _in_forbidden(x, y):
                    continue
                if not self._has_collision(x, y, NOTE_WIDTH, NOTE_HEIGHT, notes):
                    # 有機 jitter（確定性）：不撞、不出帶左緣、不入禁區才採用。
                    jx, jy = _organic_jitter(row * cols + col)
                    nx, ny = x + jx, max(content_top, y + jy)
                    if (
                        nx >= bx
                        and nx + NOTE_WIDTH <= bx + bw
                        and not _in_forbidden(nx, ny)
                        and not self._has_collision(
                            nx, ny, NOTE_WIDTH, NOTE_HEIGHT, notes
                        )
                    ):
                        return (nx, ny)
                    return (x, y)

        # 掃盡（極端滿載）：放到全部便條下緣之下（垂直必不重疊，病根 C-2 原則：
        # 不得回傳保證重疊的座標）。
        if notes:
            floor_y = max(n.y + n.height for n in notes) + gap
            return (bx + gap, floor_y)
        return (bx + gap, content_top)

    # 病根 C-1：每群一欄最多堆幾張，滿了往右開新欄（避免無限右移把群抹開）。
    _GROUP_MAX_ROWS = 6
    _GROUP_MAX_COLS = 16

    def _place_in_concept_group(
        self,
        group_id: str,
        notes: list[SpatialNote],
        gap: float,
    ) -> tuple[float, float]:
        """Spec 27 §4.2：把新概念落在同主題群（concept_group_id）旁，形成緊湊欄。

        病根 C-1：以該群既有成員的**穩定左上錨點**為原點，逐欄由上往下密堆、欄滿往右
        開新欄（取代用散落成員 max_x/min_y 當原點——那會隨每次新增無限右移、把群抹開）。
        每個落點都通過碰撞避讓，保證不疊；同一群成員集合下為確定性（可重現、不閃動）。
        """
        members = [
            n for n in notes
            if getattr(n, "concept_group_id", None) == group_id
            and getattr(n, "kind", "content") != "label"  # 標籤在欄頂，不算錨點
        ]
        if not members:
            return self._auto_grid_position(notes)

        anchor_x = min(m.x for m in members)
        anchor_y = min(m.y for m in members)
        col_w = NOTE_WIDTH + gap
        row_h = NOTE_HEIGHT + gap
        for col in range(self._GROUP_MAX_COLS):
            for row in range(self._GROUP_MAX_ROWS):
                x = anchor_x + col * col_w
                y = anchor_y + row * row_h
                if not self._has_collision(x, y, NOTE_WIDTH, NOTE_HEIGHT, notes):
                    return (x, y)
        # 群區整片滿了 → 退回避讓（仍從群錨點起算，保住群聚）。
        return self._find_non_colliding(anchor_x, anchor_y, notes, gap)

    def _place_near(
        self,
        ref: SpatialNote,
        notes: list[SpatialNote],
        direction: str | None,
        gap: float,
    ) -> tuple[float, float]:
        """Place adjacent to a reference note, avoiding collisions."""
        offsets = {
            "right": (ref.width + gap, 0),
            "left": (-(NOTE_WIDTH + gap), 0),
            "below": (0, ref.height + gap),
            "above": (0, -(NOTE_HEIGHT + gap)),
        }

        if direction and direction in offsets:
            dx, dy = offsets[direction]
            x, y = ref.x + dx, ref.y + dy
            if not self._has_collision(x, y, NOTE_WIDTH, NOTE_HEIGHT, notes, exclude_id=None):
                return (x, y)

        # Try all four directions
        for d in ["right", "below", "left", "above"]:
            dx, dy = offsets[d]
            x, y = ref.x + dx, ref.y + dy
            if not self._has_collision(x, y, NOTE_WIDTH, NOTE_HEIGHT, notes, exclude_id=None):
                return (x, y)

        # Last resort: offset with jitter
        return (ref.x + ref.width + gap, ref.y + gap)

    def _place_in_region(
        self,
        region_name: str,
        notes: list[SpatialNote],
        gap: float,
    ) -> tuple[float, float]:
        """Find free space in a named region."""
        center = _REGION_CENTERS.get(region_name, _REGION_CENTERS["center"])
        return self._find_non_colliding(center[0], center[1], notes, gap)

    def _place_in_cluster(
        self,
        cluster_id: str,
        notes: list[SpatialNote],
        clusters: list[ClusterResult] | None,
        gap: float,
    ) -> tuple[float, float]:
        """Place near the centroid of a cluster."""
        if clusters:
            for c in clusters:
                if c.cluster_id == cluster_id:
                    # Compute spatial centroid from member notes
                    members = [n for n in notes if n.id in c.note_ids]
                    if members:
                        cx = sum(m.cx for m in members) / len(members)
                        cy = sum(m.cy for m in members) / len(members)
                        return self._find_non_colliding(cx, cy, notes, gap)
        return self._auto_grid_position(notes)

    def _place_above_cluster(
        self,
        cluster_id: str,
        notes: list[SpatialNote],
        clusters: list[ClusterResult] | None,
    ) -> tuple[float, float]:
        """Place above a cluster (for title labels)."""
        if clusters:
            for c in clusters:
                if c.cluster_id == cluster_id:
                    members = [n for n in notes if n.id in c.note_ids]
                    if members:
                        min_x = min(m.x for m in members)
                        min_y = min(m.y for m in members)
                        return (min_x, min_y - NOTE_HEIGHT - 10)
        return self._auto_grid_position(notes)

    def _grid_to_pixel(self, col: int, row: int) -> tuple[float, float]:
        return (
            self._grid.start_x + col * self._grid.col_width,
            self._grid.start_y + row * self._grid.row_height,
        )

    def _auto_grid_position(self, notes: list[SpatialNote]) -> tuple[float, float]:
        """Spec 27：organic 落點 — 以鬆散網格為骨架但每格帶自然 jitter（取代整齊網格），
        再做像素級避讓碰撞。讓 AI 擺放「像人」而非機械對齊。"""
        n = len(notes)
        # 從第 n 格開始往後找：骨架格 + jitter，避讓碰撞
        for slot_idx in range(n, n + 240):
            col = slot_idx % self._grid.cols
            row = slot_idx // self._grid.cols
            base_x, base_y = self._grid_to_pixel(col, row)
            jx, jy = _organic_jitter(slot_idx)
            x, y = base_x + jx, base_y + jy
            if x < self._grid.start_x - _ORGANIC_JITTER_PX or y < self._grid.start_y - _ORGANIC_JITTER_PX:
                continue
            if not self._has_collision(x, y, NOTE_WIDTH, NOTE_HEIGHT, notes, exclude_id=None):
                return (x, y)

        # 最後手段：下一列起點
        return self._grid_to_pixel(0, n // self._grid.cols + 1)

    # ── Arrangement ──

    def compute_arrangement(
        self,
        note_ids: list[str],
        layout: str,
        target_region: str,
        notes: list[SpatialNote],
        columns: int | None = None,
        spacing: str = "default",
        forbidden: tuple[Any, ...] = (),
    ) -> list[CoordinateUpdate]:
        """Compute target coordinates for a batch arrangement.

        target_region 省略（""，spec 10 v2.0 §5.4 移除區域參數）→ **就地錨定**：
        以被排列便條的左上錨點為原點併群，不跳到全板 top-left（避免把別帶的
        便條拉出自己的水平帶，spec 27 §12.14 不跨帶污染）。

        forbidden：動態 section 帶（Bounds）。排列尾端若延伸進帶內＝非成員便條
        「位置入選」（成員資格純由位置衍生），整塊下移讓開。
        """
        gap = SPACING_VALUES.get(spacing, SPACING_VALUES["default"])
        if target_region:
            origin = _REGION_CENTERS.get(target_region, _REGION_CENTERS["top-left"])
            # Start from top-left of region, not center
            start_x = origin[0] - (NOTE_WIDTH + gap) * 1.5
            start_y = origin[1] - (NOTE_HEIGHT + gap) * 1.5
            start_x = max(GRID_START_X, start_x)
            start_y = max(GRID_START_Y, start_y)
        else:
            ids = set(note_ids)
            members = [n for n in notes if n.id in ids]
            if members:
                start_x = min(m.x for m in members)
                start_y = min(m.y for m in members)
            else:
                start_x, start_y = GRID_START_X, GRID_START_Y

        if layout == "horizontal":
            updates = self._layout_horizontal(note_ids, start_x, start_y, gap)
        elif layout == "vertical":
            updates = self._layout_vertical(note_ids, start_x, start_y, gap)
        elif layout == "circular":
            updates = self._layout_circular(note_ids, origin[0], origin[1])
        else:  # grid (default)
            cols = columns or max(2, math.ceil(math.sqrt(len(note_ids))))
            updates = self._layout_grid(note_ids, start_x, start_y, cols, gap)

        if forbidden and updates:
            dy = self._clear_forbidden_dy(
                top=min(u.y for u in updates),
                bottom=max(u.y for u in updates) + NOTE_HEIGHT,
                left=min(u.x for u in updates),
                right=max(u.x for u in updates) + NOTE_WIDTH,
                forbidden=forbidden,
            )
            if dy > 0:
                updates = [
                    CoordinateUpdate(id=u.id, x=u.x, y=u.y + dy) for u in updates
                ]
        return updates

    @staticmethod
    def _clear_forbidden_dy(
        top: float,
        bottom: float,
        left: float,
        right: float,
        forbidden: tuple[Any, ...],
    ) -> float:
        """讓 [left,right]×[top,bottom] 區塊完全讓開所有禁區帶所需的整體下移量。

        帶是全寬水平帶（section），垂直讓開即可；整塊平移保住排列的相對幾何。
        每輪移到「命中帶」下緣＋40，最多帶數＋1 輪必收斂（dy 單調遞增）。
        """
        dy = 0.0
        for _ in range(len(forbidden) + 1):
            hit = next(
                (
                    b for b in forbidden
                    if left < b.x + b.w and right > b.x
                    and top + dy < b.y + b.h and bottom + dy > b.y
                ),
                None,
            )
            if hit is None:
                break
            dy = hit.y + hit.h + 40.0 - top
        return dy

    def _layout_grid(
        self,
        ids: list[str],
        start_x: float,
        start_y: float,
        cols: int,
        gap: float,
    ) -> list[CoordinateUpdate]:
        updates = []
        for i, nid in enumerate(ids):
            col = i % cols
            row = i // cols
            updates.append(CoordinateUpdate(
                id=nid,
                x=start_x + col * (NOTE_WIDTH + gap),
                y=start_y + row * (NOTE_HEIGHT + gap),
            ))
        return updates

    def _layout_horizontal(
        self,
        ids: list[str],
        start_x: float,
        start_y: float,
        gap: float,
    ) -> list[CoordinateUpdate]:
        return [
            CoordinateUpdate(
                id=nid,
                x=start_x + i * (NOTE_WIDTH + gap),
                y=start_y,
            )
            for i, nid in enumerate(ids)
        ]

    def _layout_vertical(
        self,
        ids: list[str],
        start_x: float,
        start_y: float,
        gap: float,
    ) -> list[CoordinateUpdate]:
        return [
            CoordinateUpdate(
                id=nid,
                x=start_x,
                y=start_y + i * (NOTE_HEIGHT + gap),
            )
            for i, nid in enumerate(ids)
        ]

    def _layout_circular(
        self,
        ids: list[str],
        cx: float,
        cy: float,
    ) -> list[CoordinateUpdate]:
        n = len(ids)
        radius = max(150, n * 30)
        updates = []
        for i, nid in enumerate(ids):
            angle = 2 * math.pi * i / n - math.pi / 2
            x = cx + radius * math.cos(angle) - NOTE_WIDTH / 2
            y = cy + radius * math.sin(angle) - NOTE_HEIGHT / 2
            updates.append(CoordinateUpdate(id=nid, x=x, y=y))
        return updates

    # ── Tidy ──

    # 病根 E：整理時每群一欄最多堆幾張、上方留標題位（與 C-1 同精神）。
    _TIDY_MAX_ROWS = 6
    _TIDY_LABEL_BAND = NOTE_HEIGHT  # 內容上方預留給分類標籤的高度

    def compute_tidy(
        self,
        scope: str,
        target: str | None,
        strategy: str,
        notes: list[SpatialNote],
        clusters: list[ClusterResult] | None = None,
        pinned_ids: frozenset[str] | set[str] = frozenset(),
        forbidden: tuple[Any, ...] = (),
    ) -> list[CoordinateUpdate]:
        """Compute tidy coordinates — 病根 E：依 concept_group_id 排成「有標題位的欄」。

        取代舊「一律重排成單一格子」（theme-blind）。同群便條聚成相鄰欄、群與群分開、
        內容上方留標題帶；確定性排序（群名、id）→ **冪等**（重跑同集合得同座標，
        不經 Yjs 動畫造成閃動）。label 便條由 ``compute_group_label_anchors`` 另排。

        ``scope="group"``（spec 10 v2.0 §5.7）：就地收攏單一群（錨在群自己的左上角、
        不動其他群、只送差異）——auto_reflow 保底與 LLM 皆可用。
        """
        if scope == "group" and target:
            from app.canvas.tidy_group import compute_group_tidy

            gap = self._tidy_gap(strategy)
            return [
                CoordinateUpdate(id=nid, x=x, y=y)
                for nid, x, y in compute_group_tidy(
                    target, notes, gap,
                    pinned_ids=pinned_ids, forbidden=forbidden,
                )
            ]
        content, _labels = self._grouped_tidy(
            scope, target, strategy, notes, clusters, forbidden=forbidden,
        )
        return content

    @staticmethod
    def _tidy_gap(strategy: str) -> float:
        if strategy == "compact":
            return SPACING_VALUES["compact"]
        if strategy == "spread_even":
            return SPACING_VALUES["spacious"]
        return SPACING_VALUES["default"]

    def compute_group_label_anchors(
        self,
        scope: str,
        target: str | None,
        strategy: str,
        notes: list[SpatialNote],
        clusters: list[ClusterResult] | None = None,
        forbidden: tuple[Any, ...] = (),
    ) -> dict[str, tuple[float, float]]:
        """每個（非空）主題群的分類標籤應落點（其欄頂、內容上方標題帶）。

        forbidden 必須與 compute_tidy 帶同一組值——標籤落點由同一次
        ``_grouped_tidy`` 幾何推出，兩邊禁區不一致標籤會跟內容脫節。
        """
        if scope == "group" and target:
            from app.canvas.tidy_group import group_label_anchor

            anchor = group_label_anchor(target, notes)
            return {target: anchor} if anchor else {}
        _content, labels = self._grouped_tidy(
            scope, target, strategy, notes, clusters, forbidden=forbidden,
        )
        return labels

    def _grouped_tidy(
        self,
        scope: str,
        target: str | None,
        strategy: str,
        notes: list[SpatialNote],
        clusters: list[ClusterResult] | None,
        forbidden: tuple[Any, ...] = (),
    ) -> tuple[list[CoordinateUpdate], dict[str, tuple[float, float]]]:
        """共用核心：回傳 (內容便條座標更新, {group_id: 標籤落點})。

        forbidden：動態 section 帶。start_y＝全板既有內容最底＋40，而 section
        成員就在最底（帶高 700）→ 排格區塊會直接排進帶內＝整撮被整理的便條
        「位置入選」污染 gate/closing/感知。區塊與帶相交時整體下移讓開
        （scope="group" 路徑由 compute_group_tidy 自帶 forbidden，不經此處）。
        """
        target_notes = self._resolve_tidy_scope(scope, target, notes, clusters)
        if not target_notes:
            return [], {}

        gap = self._tidy_gap(strategy)

        # 起始 y：在既有非 target 便條下方（沿用原行為，避免蓋住別區）。
        other_notes = [n for n in notes if n.id not in {tn.id for tn in target_notes}]
        start_y = (
            max(n.y + n.height for n in other_notes) + 40
            if other_notes else GRID_START_Y
        )
        start_x = GRID_START_X

        # 依 concept_group_id 分桶（label 不參與內容欄；無群 → "" 桶最後）。
        buckets: dict[str, list[SpatialNote]] = {}
        for n in target_notes:
            if getattr(n, "kind", "content") == "label":
                continue
            gid = getattr(n, "concept_group_id", None) or ""
            buckets.setdefault(gid, []).append(n)

        # 確定性順序：有群名者依名排序在前、無群("")最後 → 冪等。
        ordered = sorted(buckets.keys(), key=lambda k: (k == "", k))

        col_w = NOTE_WIDTH + gap
        row_h = NOTE_HEIGHT + gap
        content_y = start_y + self._TIDY_LABEL_BAND
        cursor_x = start_x
        updates: list[CoordinateUpdate] = []
        label_anchors: dict[str, tuple[float, float]] = {}

        for gid in ordered:
            members = sorted(buckets[gid], key=lambda n: n.id)  # 確定性
            cols_used = 1
            for i, n in enumerate(members):
                col = i // self._TIDY_MAX_ROWS
                row = i % self._TIDY_MAX_ROWS
                cols_used = max(cols_used, col + 1)
                updates.append(CoordinateUpdate(
                    id=n.id,
                    x=cursor_x + col * col_w,
                    y=content_y + row * row_h,
                ))
            if gid:  # 非空群 → 標籤落在欄頂（內容上方標題帶）
                label_anchors[gid] = (cursor_x, start_y)
            cursor_x += cols_used * col_w + gap * 2  # 群間距

        if forbidden and updates:
            dy = self._clear_forbidden_dy(
                top=start_y,  # 含標籤帶
                bottom=max(u.y for u in updates) + NOTE_HEIGHT,
                left=start_x,
                right=cursor_x,
                forbidden=forbidden,
            )
            if dy > 0:
                updates = [
                    CoordinateUpdate(id=u.id, x=u.x, y=u.y + dy) for u in updates
                ]
                label_anchors = {
                    g: (x, y + dy) for g, (x, y) in label_anchors.items()
                }

        return updates, label_anchors

    def _resolve_tidy_scope(
        self,
        scope: str,
        target: str | None,
        notes: list[SpatialNote],
        clusters: list[ClusterResult] | None,
    ) -> list[SpatialNote]:
        """Resolve which notes are in the tidy scope."""
        if scope == "all":
            return list(notes)

        if scope == "cluster" and target and clusters:
            for c in clusters:
                if c.cluster_id == target:
                    return [n for n in notes if n.id in c.note_ids]
            return []

        if scope == "region" and target:
            return [n for n in notes if assign_region(n.cx, n.cy) == target]

        # 未知 scope／缺 target（含 scope="group" 無 target）→ 空集。
        # 舊行為「fallthrough 到全板」等同整面重排逃生口，違反 spec 27 §7 鐵律。
        return []

    # ── Collision Detection ──

    def _has_collision(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        notes: list[SpatialNote],
        exclude_id: str | None = None,
    ) -> bool:
        for n in notes:
            if n.id == exclude_id:
                continue
            if x < n.x + n.width and x + w > n.x and y < n.y + n.height and y + h > n.y:
                return True
        return False

    def _find_non_colliding(
        self,
        x: float,
        y: float,
        notes: list[SpatialNote],
        gap: float,
    ) -> tuple[float, float]:
        """Spiral outward from (x, y) until a non-colliding position is found.

        Spec 27 §5.2：對種子座標套一次 organic jitter（取代機械對齊），讓「靠群/靠區」
        落點像人；之後的螺旋避讓仍保證最終座標不碰撞。涵蓋 region/concept_group/cluster
        等所有經本函式的主路徑（_place_near 的精確方向放置不走這裡，維持精準）。
        """
        jx, jy = _organic_jitter(len(notes))
        x, y = x + jx, y + jy
        if not self._has_collision(x, y, NOTE_WIDTH, NOTE_HEIGHT, notes):
            return (x, y)

        for radius in range(1, 20):
            step = NOTE_WIDTH + gap
            for dx, dy in [
                (step * radius, 0),
                (-step * radius, 0),
                (0, (NOTE_HEIGHT + gap) * radius),
                (0, -(NOTE_HEIGHT + gap) * radius),
                (step * radius, (NOTE_HEIGHT + gap) * radius),
                (-step * radius, (NOTE_HEIGHT + gap) * radius),
            ]:
                nx, ny = x + dx, y + dy
                if not self._has_collision(nx, ny, NOTE_WIDTH, NOTE_HEIGHT, notes):
                    return (nx, ny)

        # 病根 C-2：螺旋耗盡仍碰撞 → 不得回傳「保證重疊」的座標。改放到所有便條下緣
        # 之下（新便條 top 低於全部既有 bottom → AABB 垂直不重疊 → 必不碰撞），保證收斂。
        if notes:
            floor_y = max(n.y + n.height for n in notes) + gap
            return (max(GRID_START_X, x), floor_y)
        return (x, y)


# Module-level singleton
_engine: LayoutEngine | None = None


def get_layout_engine() -> LayoutEngine:
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = LayoutEngine()
    return _engine
