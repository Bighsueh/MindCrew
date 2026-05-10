"""Voting tool — Spec 13 §5 criteria-gated dot voting.

兩個收斂點：2-6 與 4-1c。
開投票條件：
  - current sub_phase ∈ {2.6, 4.1c}
  - 對應 criteria zone 有 ≥ 1 張 Green 便條
  - target zone 有 ≥ 3 張候選

投票方式：在候選便條右上角 create 一張極小的 Green 便條。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.bridge.canvas_ops import canvas_ops
from app.canvas.analyzer import get_spatial_analyzer
from app.canvas.zone_registry import get_all_zones_for_project
from app.canvas.zones import resolve_zone_by_position
from app.config import settings

logger = logging.getLogger(__name__)

# Vote-eligible sub-phases
VOTE_SUB_PHASES: frozenset[str] = frozenset({"2.6", "4.1c"})

# Criteria zone per vote sub-phase
_CRITERIA_ZONE_FOR_PHASE: dict[str, str] = {
    "2.6": "define_criteria_sidebar",
    "4.1c": "deliver_criteria_sidebar",
}

# Target candidate zone per vote sub-phase
_CANDIDATE_ZONE_FOR_PHASE: dict[str, str] = {
    "2.6": "pov_wall",
    "4.1c": "idea_pool",
}

MIN_CANDIDATES = 3
DOT_SIZE = 24  # pixels — small visual dot


@dataclass(frozen=True)
class VoteOpenResult:
    success: bool
    session_id: str | None = None
    error_zh: str | None = None
    criteria_count: int = 0
    candidate_count: int = 0


@dataclass(frozen=True)
class VoteResult:
    success: bool
    error_zh: str | None = None
    note_id: str | None = None


@dataclass(frozen=True)
class TallyEntry:
    note_id: str
    count: int


@dataclass(frozen=True)
class TallyResult:
    success: bool
    entries: tuple[TallyEntry, ...] = ()
    total_votes: int = 0
    error_zh: str | None = None


async def _get_redis() -> Any:
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def _session_key(project_id: UUID) -> str:
    return f"vote_session:{project_id}"


def _tally_key(project_id: UUID) -> str:
    return f"vote_tally:{project_id}"


# ---------------------------------------------------------------------------
# open / close / cast / tally
# ---------------------------------------------------------------------------

async def open_vote(
    project_id: UUID,
    current_sub_phase: str,
    opened_by: str,
) -> VoteOpenResult:
    """Open a vote session if criteria are met."""
    if current_sub_phase not in VOTE_SUB_PHASES:
        return VoteOpenResult(
            success=False,
            error_zh=f"投票只能在 sub-phase 2.6 或 4.1c 開啟（目前 {current_sub_phase}）",
        )

    criteria_zone_id = _CRITERIA_ZONE_FOR_PHASE[current_sub_phase]
    candidate_zone_id = _CANDIDATE_ZONE_FOR_PHASE[current_sub_phase]

    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id)
    project_bounds = await get_all_zones_for_project(project_id)

    # Count green criteria
    criteria_count = 0
    candidate_count = 0
    candidate_ids: list[str] = []

    for note in analysis.notes:
        zone = resolve_zone_by_position(
            note.x, note.y, current_sub_phase,
            project_zone_bounds=project_bounds,
        )
        if zone is None:
            continue
        color = getattr(note, "color", None) or ""
        if zone.id == criteria_zone_id and color == "green":
            criteria_count += 1
        elif zone.id == candidate_zone_id and color != "green":
            candidate_count += 1
            candidate_ids.append(note.id)

    if criteria_count < 1:
        return VoteOpenResult(
            success=False,
            error_zh="開投票前需先建立 ≥ 1 張 Green 收斂準則便條",
            criteria_count=criteria_count,
            candidate_count=candidate_count,
        )
    if candidate_count < MIN_CANDIDATES:
        return VoteOpenResult(
            success=False,
            error_zh=f"候選便條不足（需要 ≥ {MIN_CANDIDATES}，目前 {candidate_count}）",
            criteria_count=criteria_count,
            candidate_count=candidate_count,
        )

    session_id = f"{project_id}:{int(time.time())}"
    session_payload = {
        "session_id": session_id,
        "sub_phase": current_sub_phase,
        "candidate_zone": candidate_zone_id,
        "criteria_zone": criteria_zone_id,
        "candidate_ids": candidate_ids,
        "opened_by": opened_by,
        "opened_at": time.time(),
    }

    r = await _get_redis()
    try:
        await r.set(_session_key(project_id), json.dumps(session_payload), ex=3600)
        # Reset tally
        await r.delete(_tally_key(project_id))
    finally:
        await r.aclose()

    logger.info(
        "Vote opened project=%s session=%s candidates=%d criteria=%d",
        project_id, session_id, candidate_count, criteria_count,
    )
    return VoteOpenResult(
        success=True,
        session_id=session_id,
        criteria_count=criteria_count,
        candidate_count=candidate_count,
    )


async def cast_vote(
    project_id: UUID,
    target_note_id: str,
    voter_id: str,
    voter_name: str,
) -> VoteResult:
    """Cast a single vote: create a tiny green dot near target + increment tally."""
    r = await _get_redis()
    try:
        raw = await r.get(_session_key(project_id))
    finally:
        await r.aclose()

    if not raw:
        return VoteResult(success=False, error_zh="目前沒有開啟中的投票")

    try:
        session = json.loads(raw)
    except json.JSONDecodeError:
        return VoteResult(success=False, error_zh="投票 session 格式錯誤")

    if target_note_id not in session.get("candidate_ids", []):
        return VoteResult(
            success=False,
            error_zh="此便條不在投票候選範圍內",
        )

    # Locate target for dot position
    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id)
    target = next((n for n in analysis.notes if n.id == target_note_id), None)
    if target is None:
        return VoteResult(success=False, error_zh="找不到目標便條")

    # Place dot at top-right of target
    dot_x = target.x + getattr(target, "w", 160) - DOT_SIZE
    dot_y = target.y - DOT_SIZE // 2

    dot_id = await canvas_ops.add_note(
        project_id=project_id,
        content="●",
        position={"x": dot_x, "y": dot_y},
        color="green",
        author_id=voter_id,
        author_name=voter_name,
        author_type="ai" if voter_id.startswith("agent_") else "human",
    )

    # Increment tally
    r = await _get_redis()
    try:
        await r.hincrby(_tally_key(project_id), target_note_id, 1)
    finally:
        await r.aclose()

    logger.info(
        "Vote cast project=%s voter=%s target=%s dot=%s",
        project_id, voter_id, target_note_id, dot_id,
    )
    return VoteResult(success=True, note_id=dot_id)


async def tally(project_id: UUID) -> TallyResult:
    """Return current vote tally sorted by count desc."""
    r = await _get_redis()
    try:
        raw_session = await r.get(_session_key(project_id))
        raw_tally = await r.hgetall(_tally_key(project_id))
    finally:
        await r.aclose()

    if not raw_session:
        return TallyResult(success=False, error_zh="沒有開啟中的投票")

    counts: list[TallyEntry] = []
    total = 0
    for note_id, count_str in raw_tally.items():
        try:
            cnt = int(count_str)
        except ValueError:
            cnt = 0
        counts.append(TallyEntry(note_id=note_id, count=cnt))
        total += cnt

    counts.sort(key=lambda e: e.count, reverse=True)
    return TallyResult(success=True, entries=tuple(counts), total_votes=total)


async def close_vote(project_id: UUID, closed_by: str) -> TallyResult:
    """Close the current vote session, return tally, clear session."""
    result = await tally(project_id)
    if not result.success:
        return result

    r = await _get_redis()
    try:
        await r.delete(_session_key(project_id))
        # Keep tally for record? — clear for cleanliness
        await r.delete(_tally_key(project_id))
    finally:
        await r.aclose()

    logger.info(
        "Vote closed project=%s by=%s total_votes=%d",
        project_id, closed_by, result.total_votes,
    )
    return result


async def get_open_session(project_id: UUID) -> dict[str, Any] | None:
    r = await _get_redis()
    try:
        raw = await r.get(_session_key(project_id))
    finally:
        await r.aclose()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
