"""LLMCallContext — bundle of attribution metadata for every LLM call.

Phase 25.J: every ``LLMService.chat_completion(...)`` requires an owning user
and (where relevant) a project. Agents construct one ``LLMCallContext`` at
BaseAgent init time and pass it through to every sub-engine (think, assess,
evaluator, judge, summarizer, persona) that calls the LLM. Route handlers
construct one inline from ``current_user`` + path params.

Immutable on purpose — once an agent's context is fixed for the lifetime of a
seat, no downstream code should mutate the attribution.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID


@dataclass(frozen=True)
class LLMCallContext:
    owning_user_id: UUID
    project_id: UUID | None = None
    triggered_by_user_id: UUID | None = None
    # Caller is the call-site identifier (e.g. "agent_think", "dt_coach").
    # Each callsite passes its own value; defaulting here would mask bad
    # plumbing, so we require it explicitly at every call.
    caller: str = "unknown"

    def with_caller(self, caller: str) -> "LLMCallContext":
        """Return a copy with a different caller string — useful when one
        agent stage runs multiple LLM subcalls (e.g. think + judge)."""
        return replace(self, caller=caller)

    def with_trigger(self, user_id: UUID | None) -> "LLMCallContext":
        """Return a copy with triggered_by set, e.g. when a chat message
        triggers an agent reasoning loop."""
        return replace(self, triggered_by_user_id=user_id)
