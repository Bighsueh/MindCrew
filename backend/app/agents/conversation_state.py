"""Conversation thread tracking for multi-turn AI dialogue.

Tracks the active conversation thread per project in Redis.
Uses n-gram heuristics (no LLM calls) to detect topic shifts and
addressee patterns in messages.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from uuid import UUID

logger = logging.getLogger(__name__)

# Redis key for the active thread per project
_KEY_THREAD = "project:{project_id}:active_thread"

# Thread closes after this many turns
_MAX_THREAD_TURNS = 7

# Minimum n-gram overlap ratio to consider same topic
_TOPIC_CONTINUITY_THRESHOLD = 0.3

# N-gram size for topic comparison
_NGRAM_SIZE = 3


@dataclass
class ConversationThread:
    topic_summary: str
    topic_ngrams: list[str]
    participants: list[str]
    turn_count: int
    last_speaker: str
    addressed_to: str | None
    started_at: float
    pending_addressee: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ConversationThread:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _extract_cjk_ngrams(text: str, n: int = _NGRAM_SIZE) -> set[str]:
    """Extract character n-grams from CJK text."""
    cjk = "".join(c for c in text if "\u4e00" <= c <= "\u9fff")
    if len(cjk) < n:
        return {cjk} if cjk else set()
    return {cjk[i : i + n] for i in range(len(cjk) - n + 1)}


def _compute_topic_overlap(ngrams_a: set[str], ngrams_b: set[str]) -> float:
    """Compute Jaccard-like overlap between two n-gram sets."""
    if not ngrams_a or not ngrams_b:
        return 0.0
    intersection = ngrams_a & ngrams_b
    smaller = min(len(ngrams_a), len(ngrams_b))
    return len(intersection) / smaller if smaller > 0 else 0.0


def _detect_addressee(content: str, all_seats: list[str]) -> str | None:
    """Detect if a message addresses a specific agent.

    Patterns: "XX 你怎麼看？", "@crew_2", "XX，", "請問 XX"
    """
    content_lower = content.lower()

    # Check @mentions
    for seat in all_seats:
        if f"@{seat.lower()}" in content_lower:
            return seat

    # Check name patterns: "XX 你怎麼看", "XX，你覺得", "請問 XX"
    # Seat names in Chinese chat often appear as "AI 成員 1", "成員 2", etc.
    for seat in all_seats:
        # Match common addressing patterns
        seat_lower = seat.lower()
        patterns = [
            f"{seat_lower}，",
            f"{seat_lower} 你",
            f"{seat_lower}你",
            f"請問 {seat_lower}",
            f"請問{seat_lower}",
        ]
        if any(p in content_lower for p in patterns):
            return seat

    # Check question directed at someone mentioned by name
    question_marks = content.count("？") + content.count("?")
    if question_marks > 0:
        for seat in all_seats:
            if seat.lower() in content_lower:
                return seat

    return None


def _extract_topic_summary(content: str, max_len: int = 20) -> str:
    """Extract a short topic summary from message content."""
    # Remove common filler phrases
    cleaned = re.sub(r"^(我同意|延伸|針對|關於|我覺得|我想|大家)", "", content)
    cleaned = cleaned.strip("，。、：")
    if len(cleaned) > max_len:
        return cleaned[:max_len] + "…"
    return cleaned or content[:max_len]


class ConversationStateTracker:
    """Track conversation threads per project using Redis."""

    def __init__(self, project_id: UUID) -> None:
        self._project_id = project_id
        self._redis = None

    async def _get_redis(self):  # type: ignore[return]
        if self._redis is None:
            import redis.asyncio as aioredis
            from app.config import settings

            self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    async def get_active_thread(self) -> ConversationThread | None:
        """Get the current active thread, or None."""
        r = await self._get_redis()
        key = _KEY_THREAD.format(project_id=self._project_id)
        raw = await r.get(key)
        if not raw:
            return None
        try:
            return ConversationThread.from_dict(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            return None

    async def update_on_message(
        self,
        sender: str,
        content: str,
        all_seats: list[str],
    ) -> ConversationThread:
        """Update thread state when a new message arrives. Returns the updated thread."""
        r = await self._get_redis()
        key = _KEY_THREAD.format(project_id=self._project_id)
        current = await self.get_active_thread()

        new_ngrams = _extract_cjk_ngrams(content)
        addressee = _detect_addressee(content, all_seats)

        if current is None:
            # Start new thread
            thread = ConversationThread(
                topic_summary=_extract_topic_summary(content),
                topic_ngrams=list(new_ngrams),
                participants=[sender],
                turn_count=1,
                last_speaker=sender,
                addressed_to=addressee,
                started_at=time.time(),
                pending_addressee=addressee,
            )
        else:
            # Check if this is a topic shift
            current_ngrams = set(current.topic_ngrams)
            overlap = _compute_topic_overlap(current_ngrams, new_ngrams)
            is_continuation = overlap >= _TOPIC_CONTINUITY_THRESHOLD

            if is_continuation and current.turn_count < _MAX_THREAD_TURNS:
                # Continue existing thread
                participants = list(current.participants)
                if sender not in participants:
                    participants.append(sender)
                # Merge n-grams (keep recent bias)
                merged = list(new_ngrams | current_ngrams)[-50:]

                # Resolve pending_addressee: clear if the addressed agent has spoken
                pending = current.pending_addressee
                if pending and sender.lower() in pending.lower():
                    pending = None  # addressed agent responded
                # New addressee in this message overrides the pending one
                if addressee:
                    pending = addressee

                thread = ConversationThread(
                    topic_summary=current.topic_summary,
                    topic_ngrams=merged,
                    participants=participants,
                    turn_count=current.turn_count + 1,
                    last_speaker=sender,
                    addressed_to=addressee,
                    started_at=current.started_at,
                    pending_addressee=pending,
                )
            else:
                # Topic shift or thread expired → start new thread
                thread = ConversationThread(
                    topic_summary=_extract_topic_summary(content),
                    topic_ngrams=list(new_ngrams),
                    participants=[sender],
                    turn_count=1,
                    last_speaker=sender,
                    addressed_to=addressee,
                    started_at=time.time(),
                    pending_addressee=addressee,
                )

        await r.set(key, json.dumps(thread.to_dict()), ex=600)  # TTL 10 min
        return thread

    async def get_thread_context(self) -> dict | None:
        """Get thread info formatted for injection into agent context."""
        thread = await self.get_active_thread()
        if thread is None:
            return None
        return {
            "topic_summary": thread.topic_summary,
            "participants": thread.participants,
            "turn_count": thread.turn_count,
            "last_speaker": thread.last_speaker,
            "addressed_to": thread.addressed_to,
            "pending_addressee": thread.pending_addressee,
        }
