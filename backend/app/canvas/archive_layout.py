"""Canvas archive layout — compact positioning for archived phase notes.

Provides spatial zones below the active viewport (y > 4500) where
notes from completed phases are stored in a compact grid layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.canvas.spatial import SpatialNote

# Archive zone y-offsets for each completed macro stage.
ARCHIVE_ZONES: dict[str, tuple[int, int]] = {
    "discover": (5000, 80),   # (y_start, x_start)
    "define": (7000, 80),
    "develop": (9000, 80),
}

# Active zone upper boundary — notes below this are considered archived.
ACTIVE_ZONE_MAX_Y = 4500

# Grid parameters for archive layout.
_ARCHIVE_COL_WIDTH = 220  # note width (200) + gap (20) — compact
_ARCHIVE_ROW_HEIGHT = 170  # note height (150) + gap (20) — compact
_ARCHIVE_COLUMNS = 6


@dataclass(frozen=True)
class CoordinateUpdate:
    id: str
    x: float
    y: float


def compute_archive_positions(
    notes: list[SpatialNote],
    zone: str,
    columns: int = _ARCHIVE_COLUMNS,
) -> list[CoordinateUpdate]:
    """Compute compact grid positions in the archive zone.

    Args:
        notes: Notes to archive.
        zone: One of "discover", "define", "develop".
        columns: Number of columns in the archive grid.

    Returns:
        List of coordinate updates to apply.
    """
    if not notes or zone not in ARCHIVE_ZONES:
        return []

    y_start, x_start = ARCHIVE_ZONES[zone]
    updates: list[CoordinateUpdate] = []

    for i, note in enumerate(notes):
        col = i % columns
        row = i // columns
        x = x_start + col * _ARCHIVE_COL_WIDTH
        y = y_start + row * _ARCHIVE_ROW_HEIGHT
        updates.append(CoordinateUpdate(id=note.id, x=x, y=y))

    return updates


def is_archived(note: SpatialNote) -> bool:
    """Check whether a note is in the archive zone."""
    return note.y >= ACTIVE_ZONE_MAX_Y
