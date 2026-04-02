"""Pure-geometry spatial analysis for canvas notes.

All functions are deterministic, CPU-only, and do NOT call any external API.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

# ── Grid constants (mirror sidecar/src/yjs-utils.ts) ──

GRID_START_X = 80
GRID_START_Y = 80
GRID_COL_WIDTH = 260   # 200px note + 60px gap
GRID_ROW_HEIGHT = 210  # 150px note + 60px gap
GRID_COLS = 5
NOTE_WIDTH = 200
NOTE_HEIGHT = 150
NOTE_GAP = 15

# Board logical dimensions for region assignment
BOARD_WIDTH = GRID_START_X + GRID_COLS * GRID_COL_WIDTH + 200
BOARD_HEIGHT = 2000  # generous default


@dataclass(frozen=True)
class GridConfig:
    """Pixel ↔ grid conversion parameters."""

    start_x: float = GRID_START_X
    start_y: float = GRID_START_Y
    col_width: float = GRID_COL_WIDTH
    row_height: float = GRID_ROW_HEIGHT
    cols: int = GRID_COLS
    note_width: float = NOTE_WIDTH
    note_height: float = NOTE_HEIGHT
    note_gap: float = NOTE_GAP


DEFAULT_GRID = GridConfig()


@dataclass
class SpatialNote:
    """Minimal note representation with geometry."""

    id: str
    text: str
    x: float
    y: float
    width: float
    height: float
    color: str
    author_type: str  # "human" | "ai"
    created_at: str
    group_id: str | None = None
    author_name: str = ""

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2


# ── Overlap Detection ──


def _rects_overlap(a: SpatialNote, b: SpatialNote) -> bool:
    return (
        a.x < b.x + b.width
        and a.x + a.width > b.x
        and a.y < b.y + b.height
        and a.y + a.height > b.y
    )


def detect_overlaps(notes: list[SpatialNote]) -> list[tuple[str, str]]:
    """Return pairs of overlapping note IDs."""
    pairs: list[tuple[str, str]] = []
    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            if _rects_overlap(notes[i], notes[j]):
                pairs.append((notes[i].id, notes[j].id))
    return pairs


# ── Proximity Matrix ──


def compute_proximity_matrix(notes: list[SpatialNote]) -> np.ndarray:
    """NxN Euclidean distance matrix between note centers."""
    n = len(notes)
    if n == 0:
        return np.zeros((0, 0))
    centers = np.array([[note.cx, note.cy] for note in notes])
    diff = centers[:, np.newaxis, :] - centers[np.newaxis, :, :]
    return np.sqrt((diff ** 2).sum(axis=2))


# ── Orderliness Score (spec §6.2) ──


def _alignment_regularity(notes: list[SpatialNote], grid: GridConfig) -> float:
    """How well note positions align to a grid. 1 = perfectly aligned."""
    if len(notes) < 2:
        return 1.0
    xs = np.array([n.x for n in notes])
    ys = np.array([n.y for n in notes])
    # Deviation from nearest grid line
    x_dev = np.abs((xs - grid.start_x) % grid.col_width)
    x_dev = np.minimum(x_dev, grid.col_width - x_dev)
    y_dev = np.abs((ys - grid.start_y) % grid.row_height)
    y_dev = np.minimum(y_dev, grid.row_height - y_dev)
    max_x_dev = grid.col_width / 2
    max_y_dev = grid.row_height / 2
    x_score = 1.0 - float(np.mean(x_dev)) / max_x_dev
    y_score = 1.0 - float(np.mean(y_dev)) / max_y_dev
    return max(0.0, (x_score + y_score) / 2)


def _cluster_separation_clarity(
    notes: list[SpatialNote],
    cluster_labels: dict[str, str] | None = None,
) -> float:
    """Ratio of inter-cluster to intra-cluster distance. Higher = better separation."""
    if cluster_labels is None or len(notes) < 3:
        return 0.5  # neutral when no cluster info

    clusters: dict[str, list[SpatialNote]] = {}
    for n in notes:
        cid = cluster_labels.get(n.id, "__ungrouped__")
        clusters.setdefault(cid, []).append(n)

    if len(clusters) < 2:
        return 0.5

    # Intra-cluster mean distance
    intra_dists: list[float] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                d = math.hypot(members[i].cx - members[j].cx, members[i].cy - members[j].cy)
                intra_dists.append(d)

    # Inter-cluster mean distance (between centroids)
    centroids = []
    for members in clusters.values():
        cx = sum(m.cx for m in members) / len(members)
        cy = sum(m.cy for m in members) / len(members)
        centroids.append((cx, cy))

    inter_dists: list[float] = []
    for i in range(len(centroids)):
        for j in range(i + 1, len(centroids)):
            d = math.hypot(centroids[i][0] - centroids[j][0], centroids[i][1] - centroids[j][1])
            inter_dists.append(d)

    mean_intra = np.mean(intra_dists) if intra_dists else 1.0
    mean_inter = np.mean(inter_dists) if inter_dists else 1.0

    if mean_intra == 0:
        return 1.0
    ratio = float(mean_inter) / float(mean_intra)
    # Normalize: ratio=1 → 0.5, ratio≥3 → ~1.0
    return min(1.0, ratio / 3.0)


def _overlap_ratio(notes: list[SpatialNote]) -> float:
    """Fraction of notes involved in at least one overlap."""
    if len(notes) < 2:
        return 0.0
    overlapping_ids: set[str] = set()
    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            if _rects_overlap(notes[i], notes[j]):
                overlapping_ids.add(notes[i].id)
                overlapping_ids.add(notes[j].id)
    return len(overlapping_ids) / len(notes)


def _spacing_consistency(notes: list[SpatialNote]) -> float:
    """Low coefficient of variation in nearest-neighbor distances → high score."""
    if len(notes) < 2:
        return 1.0
    dist_mat = compute_proximity_matrix(notes)
    np.fill_diagonal(dist_mat, np.inf)
    nn_dists = dist_mat.min(axis=1)
    mean_d = float(np.mean(nn_dists))
    if mean_d == 0:
        return 1.0
    cv = float(np.std(nn_dists)) / mean_d
    # cv=0 → 1.0, cv≥2 → 0.0
    return max(0.0, 1.0 - cv / 2.0)


def compute_orderliness(
    notes: list[SpatialNote],
    cluster_labels: dict[str, str] | None = None,
    grid: GridConfig = DEFAULT_GRID,
) -> float:
    """Spec §6.2 weighted orderliness score (0–1)."""
    if len(notes) < 2:
        return 1.0
    align = _alignment_regularity(notes, grid)
    sep = _cluster_separation_clarity(notes, cluster_labels)
    overlap = _overlap_ratio(notes)
    spacing = _spacing_consistency(notes)
    return 0.3 * align + 0.3 * sep + 0.2 * (1 - overlap) + 0.2 * spacing


# ── Region Assignment ──

_REGION_COLS = 3  # left, center, right
_REGION_ROWS = 2  # top, bottom
_COL_NAMES = ["left", "center", "right"]
_ROW_NAMES = ["top", "bottom"]


def assign_region(x: float, y: float) -> str:
    """Map pixel coords to a human-readable region name like 'top-left'."""
    col_idx = min(int(x / (BOARD_WIDTH / _REGION_COLS)), _REGION_COLS - 1)
    row_idx = min(int(y / (BOARD_HEIGHT / _REGION_ROWS)), _REGION_ROWS - 1)
    col_idx = max(0, col_idx)
    row_idx = max(0, row_idx)
    return f"{_ROW_NAMES[row_idx]}-{_COL_NAMES[col_idx]}"


def assign_grid_position(
    x: float,
    y: float,
    grid: GridConfig = DEFAULT_GRID,
) -> tuple[int, int]:
    """Convert pixel coords to (col, row) grid position."""
    col = max(0, round((x - grid.start_x) / grid.col_width))
    row = max(0, round((y - grid.start_y) / grid.row_height))
    return (col, row)


# ── Free Regions ──


def find_free_regions(notes: list[SpatialNote]) -> list[str]:
    """Return region names that contain no notes."""
    occupied: set[str] = set()
    for n in notes:
        occupied.add(assign_region(n.cx, n.cy))
    all_regions = {
        f"{r}-{c}" for r in _ROW_NAMES for c in _COL_NAMES
    }
    return sorted(all_regions - occupied)


def compute_board_bounds(notes: list[SpatialNote]) -> dict[str, Any]:
    """Compute used area description and free regions."""
    if not notes:
        return {"used_area": "empty", "free_regions": find_free_regions([])}
    min_x = min(n.x for n in notes)
    min_y = min(n.y for n in notes)
    max_x = max(n.x + n.width for n in notes)
    max_y = max(n.y + n.height for n in notes)
    tl = assign_region(min_x, min_y)
    br = assign_region(max_x, max_y)
    return {
        "used_area": f"{tl} to {br}",
        "free_regions": find_free_regions(notes),
    }


# ── Neighbors ──


def find_neighbors(
    note_id: str,
    notes: list[SpatialNote],
    max_distance: float = 400.0,
) -> list[dict[str, Any]]:
    """Find neighboring notes with direction and distance category."""
    target = next((n for n in notes if n.id == note_id), None)
    if target is None:
        return []

    result: list[dict[str, Any]] = []
    for n in notes:
        if n.id == note_id:
            continue
        dist = math.hypot(n.cx - target.cx, n.cy - target.cy)
        if dist > max_distance:
            continue

        # Direction (primary axis)
        dx = n.cx - target.cx
        dy = n.cy - target.cy
        if abs(dx) > abs(dy):
            direction = "right" if dx > 0 else "left"
        else:
            direction = "below" if dy > 0 else "above"

        # Distance category
        if _rects_overlap(target, n):
            distance_cat = "touching"
        elif dist < 300:
            distance_cat = "near"
        else:
            distance_cat = "far"

        result.append({
            "id": n.id,
            "distance": distance_cat,
            "direction": direction,
        })

    result.sort(key=lambda r: {"touching": 0, "near": 1, "far": 2}[r["distance"]])
    return result
