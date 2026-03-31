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
_RE_GRID = re.compile(r"^grid:(\d+),(\d+)$")
_RE_REGION = re.compile(r"^region:(.+)$")
_RE_CLUSTER = re.compile(r"^cluster:(.+)$")
_RE_ABOVE_CLUSTER = re.compile(r"^above_cluster:(.+)$")


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
    ) -> tuple[float, float]:
        """Parse a `to` string and return target (x, y) pixel coordinates.

        Supported formats:
          - "near:<note_id>"
          - "grid:<col>,<row>"
          - "region:<name>"
          - "cluster:<cluster_id>"
          - "above_cluster:<cluster_id>"
        """
        gap = SPACING_VALUES.get(spacing, SPACING_VALUES["default"])
        notes_map = {n.id: n for n in notes}

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

        # Fallback
        return self._auto_grid_position(notes)

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
        """Find the next available grid slot."""
        occupied_slots: set[tuple[int, int]] = set()
        for n in notes:
            col = round((n.x - self._grid.start_x) / self._grid.col_width)
            row = round((n.y - self._grid.start_y) / self._grid.row_height)
            occupied_slots.add((max(0, col), max(0, row)))

        for slot_idx in range(200):
            col = slot_idx % self._grid.cols
            row = slot_idx // self._grid.cols
            if (col, row) not in occupied_slots:
                return self._grid_to_pixel(col, row)

        return self._grid_to_pixel(0, len(notes) // self._grid.cols + 1)

    # ── Arrangement ──

    def compute_arrangement(
        self,
        note_ids: list[str],
        layout: str,
        target_region: str,
        notes: list[SpatialNote],
        columns: int | None = None,
        spacing: str = "default",
    ) -> list[CoordinateUpdate]:
        """Compute target coordinates for a batch arrangement."""
        gap = SPACING_VALUES.get(spacing, SPACING_VALUES["default"])
        origin = _REGION_CENTERS.get(target_region, _REGION_CENTERS["top-left"])
        # Start from top-left of region, not center
        start_x = origin[0] - (NOTE_WIDTH + gap) * 1.5
        start_y = origin[1] - (NOTE_HEIGHT + gap) * 1.5
        start_x = max(GRID_START_X, start_x)
        start_y = max(GRID_START_Y, start_y)

        if layout == "horizontal":
            return self._layout_horizontal(note_ids, start_x, start_y, gap)
        elif layout == "vertical":
            return self._layout_vertical(note_ids, start_x, start_y, gap)
        elif layout == "circular":
            return self._layout_circular(note_ids, origin[0], origin[1])
        else:  # grid (default)
            cols = columns or max(2, math.ceil(math.sqrt(len(note_ids))))
            return self._layout_grid(note_ids, start_x, start_y, cols, gap)

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

    def compute_tidy(
        self,
        scope: str,
        target: str | None,
        strategy: str,
        notes: list[SpatialNote],
        clusters: list[ClusterResult] | None = None,
    ) -> list[CoordinateUpdate]:
        """Compute tidy coordinates for a scope of notes."""
        target_notes = self._resolve_tidy_scope(scope, target, notes, clusters)
        if not target_notes:
            return []

        gap = SPACING_VALUES["default"]

        if strategy == "compact":
            gap = SPACING_VALUES["compact"]
            cols = max(2, math.ceil(math.sqrt(len(target_notes))))
        elif strategy == "spread_even":
            gap = SPACING_VALUES["spacious"]
            cols = max(3, math.ceil(math.sqrt(len(target_notes)) * 1.2))
        else:  # align_grid
            cols = self._grid.cols

        # Find starting position: below existing non-target notes
        other_notes = [n for n in notes if n.id not in {tn.id for tn in target_notes}]
        if other_notes:
            max_y = max(n.y + n.height for n in other_notes) + 40
        else:
            max_y = GRID_START_Y

        start_x = GRID_START_X

        return [
            CoordinateUpdate(
                id=target_notes[i].id,
                x=start_x + (i % cols) * (NOTE_WIDTH + gap),
                y=max_y + (i // cols) * (NOTE_HEIGHT + gap),
            )
            for i in range(len(target_notes))
        ]

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

        return list(notes)

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
        """Spiral outward from (x, y) until a non-colliding position is found."""
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

        return (x + NOTE_WIDTH + gap, y)


# Module-level singleton
_engine: LayoutEngine | None = None


def get_layout_engine() -> LayoutEngine:
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = LayoutEngine()
    return _engine
