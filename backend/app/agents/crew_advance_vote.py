"""Crew advance vote — Spec 14 N2 / Phase 18 Stream D.

當 timer ≥90% / supervisor idle 60s / 人類觸發時開啟「推進投票」session。
4 個 crew 各擲一票（同意 / 反對 / 棄權），30 秒內：
  - 同意 ≥ 3 → 自動 advance_sub_phase
  - 反對 ≥ 2 → vote 結束，繼續當前 sub_phase
  - 未達 quorum → vote 結束，靜默繼續
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.config import settings

logger = logging.getLogger(__name__)

VoteChoice = Literal["approve", "reject", "abstain"]

VOTE_DURATION_SECONDS = 30
APPROVE_THRESHOLD = 3
REJECT_THRESHOLD = 2


@dataclass(frozen=True)
class AdvanceVoteResult:
    outcome: Literal["approved", "rejected", "no_quorum", "cancelled", "still_open"]
    session_id: str
    approve_count: int = 0
    reject_count: int = 0
    abstain_count: int = 0
    voters: list[dict[str, str]] = None  # type: ignore[assignment]


async def _get_redis() -> Any:
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def _session_key(project_id: UUID) -> str:
    return f"advance_vote:{project_id}"


# ---------------------------------------------------------------------------
# Open / Cast / Close
# ---------------------------------------------------------------------------

async def open_advance_vote(
    project_id: UUID,
    current_sub_phase: str,
    triggered_by: str,
    trigger_reason: str,
) -> AdvanceVoteResult | None:
    """Open a new advance vote session. Returns None if one already open."""
    r = await _get_redis()
    try:
        existing = await r.get(_session_key(project_id))
        if existing:
            logger.info(
                "advance_vote already open for project=%s — skip",
                project_id,
            )
            return None

        session_id = f"av-{project_id}-{int(time.time())}"
        payload = {
            "session_id": session_id,
            "sub_phase": current_sub_phase,
            "triggered_by": triggered_by,
            "trigger_reason": trigger_reason,
            "opened_at": time.time(),
            "expires_at": time.time() + VOTE_DURATION_SECONDS,
            "voters": [],
        }
        await r.set(
            _session_key(project_id),
            json.dumps(payload),
            ex=VOTE_DURATION_SECONDS + 60,
        )
    finally:
        await r.aclose()

    logger.info(
        "advance_vote opened project=%s session=%s sub_phase=%s reason=%s",
        project_id, session_id, current_sub_phase, trigger_reason,
    )

    # Broadcast event for frontend banner
    await _broadcast_vote_event(project_id, session_id, "opened", trigger_reason)

    return AdvanceVoteResult(outcome="still_open", session_id=session_id)


async def cast_vote(
    project_id: UUID,
    voter_id: str,
    voter_name: str,
    choice: VoteChoice,
) -> AdvanceVoteResult | None:
    """Cast a vote. Returns updated result, or None if no open session."""
    r = await _get_redis()
    try:
        raw = await r.get(_session_key(project_id))
        if not raw:
            return None
        session = json.loads(raw)
        voters: list[dict[str, str]] = session.get("voters", [])

        # Replace existing vote from same voter
        voters = [v for v in voters if v.get("voter_id") != voter_id]
        voters.append({
            "voter_id": voter_id,
            "voter_name": voter_name,
            "choice": choice,
            "cast_at": str(time.time()),
        })
        session["voters"] = voters
        await r.set(
            _session_key(project_id),
            json.dumps(session),
            ex=VOTE_DURATION_SECONDS + 60,
        )
    finally:
        await r.aclose()

    result = _tally(session)
    logger.info(
        "advance_vote project=%s voter=%s choice=%s tally=%d/%d/%d",
        project_id, voter_id, choice,
        result.approve_count, result.reject_count, result.abstain_count,
    )

    # Auto-close if quorum reached
    if result.approve_count >= APPROVE_THRESHOLD:
        await _close_and_advance(project_id, session, "approved")
        return AdvanceVoteResult(
            outcome="approved",
            session_id=session["session_id"],
            approve_count=result.approve_count,
            reject_count=result.reject_count,
            abstain_count=result.abstain_count,
            voters=voters,
        )
    if result.reject_count >= REJECT_THRESHOLD:
        await _close(project_id, session, "rejected")
        return AdvanceVoteResult(
            outcome="rejected",
            session_id=session["session_id"],
            approve_count=result.approve_count,
            reject_count=result.reject_count,
            abstain_count=result.abstain_count,
            voters=voters,
        )

    return result


async def cancel_vote(project_id: UUID, cancelled_by: str) -> bool:
    """Teacher cancels an open vote."""
    r = await _get_redis()
    try:
        raw = await r.get(_session_key(project_id))
        if not raw:
            return False
        session = json.loads(raw)
        await r.delete(_session_key(project_id))
    finally:
        await r.aclose()

    await _broadcast_vote_event(
        project_id, session["session_id"], "cancelled", f"by:{cancelled_by}",
    )
    logger.info("advance_vote cancelled project=%s by=%s", project_id, cancelled_by)
    return True


async def get_open_session(project_id: UUID) -> dict | None:
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


async def check_expiry(project_id: UUID) -> AdvanceVoteResult | None:
    """Called by background task — close expired vote sessions."""
    session = await get_open_session(project_id)
    if not session:
        return None
    if time.time() < session.get("expires_at", 0):
        return None
    # Expired — tally final result
    result = _tally(session)
    if result.approve_count >= APPROVE_THRESHOLD:
        await _close_and_advance(project_id, session, "approved")
        return AdvanceVoteResult(
            outcome="approved",
            session_id=session["session_id"],
            approve_count=result.approve_count,
            reject_count=result.reject_count,
            abstain_count=result.abstain_count,
        )
    else:
        await _close(project_id, session, "no_quorum")
        return AdvanceVoteResult(
            outcome="no_quorum",
            session_id=session["session_id"],
            approve_count=result.approve_count,
            reject_count=result.reject_count,
            abstain_count=result.abstain_count,
        )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _tally(session: dict) -> AdvanceVoteResult:
    voters = session.get("voters", [])
    approve = sum(1 for v in voters if v.get("choice") == "approve")
    reject = sum(1 for v in voters if v.get("choice") == "reject")
    abstain = sum(1 for v in voters if v.get("choice") == "abstain")
    return AdvanceVoteResult(
        outcome="still_open",
        session_id=session.get("session_id", ""),
        approve_count=approve,
        reject_count=reject,
        abstain_count=abstain,
        voters=voters,
    )


async def _close(project_id: UUID, session: dict, outcome: str) -> None:
    r = await _get_redis()
    try:
        await r.delete(_session_key(project_id))
    finally:
        await r.aclose()
    await _broadcast_vote_event(project_id, session["session_id"], outcome, "")


async def _close_and_advance(project_id: UUID, session: dict, outcome: str) -> None:
    await _close(project_id, session, outcome)
    # Trigger advance
    try:
        from app.agents.stage_advancement import advance_sub_phase
        from app.stages.sub_phases import get_next_sub_phase

        sub_phase = session.get("sub_phase", "")
        next_id = get_next_sub_phase(sub_phase)
        if next_id:
            result = await advance_sub_phase(
                project_id=project_id,
                agent_id="system_crew_vote",
                from_sub_phase=sub_phase,
                to_sub_phase=next_id,
                skip_deliverable_check=False,
            )
            logger.info("crew_vote auto-advance: %s", result)
    except Exception:
        logger.exception("crew_vote auto-advance failed")


async def _broadcast_vote_event(
    project_id: UUID,
    session_id: str,
    outcome: str,
    detail: str,
) -> None:
    try:
        from app.events.bus import event_bus
        # Use generic publish — WS layer subscribes by project_id
        await event_bus.publish({  # type: ignore[arg-type]
            "type": f"advance_vote:{outcome}",
            "project_id": str(project_id),
            "session_id": session_id,
            "detail": detail,
        })
    except Exception:
        logger.debug("advance_vote event broadcast failed", exc_info=True)
