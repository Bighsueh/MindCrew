"""caller → capability_class routing policy (Phase 37).

The ``capability_class`` axis is orthogonal to provider ``tier`` (fault-tolerance
order). It routes each LLM call to a quality pool based on task difficulty:

  * ``quality``  — strong-but-slow model (e.g. gemma). For quality-critical,
                   latency-tolerant tasks (persona generation, qualitative
                   evaluation, closing ritual).
  * ``standard`` — fast default model (e.g. gpt-oss). For latency-sensitive,
                   high-frequency, or low-quality-sensitivity tasks.

The routing key is the ``caller`` string every call site already passes. Any
caller not listed here resolves to ``standard`` (fast/cheap is the safe default;
quality is opt-in).

Decision basis: DB latency analysis in
``_discussion/docs/llm-tiering-and-agent-think-optimization.md`` and spec v4.17
(``specs/03 §4.1.2``, ``specs/06 §1.10``, ``specs/02 §6``).
"""
from __future__ import annotations

QUALITY = "quality"
STANDARD = "standard"

#: Callers routed to the QUALITY pool. Everything else defaults to STANDARD.
_QUALITY_CALLERS: frozenset[str] = frozenset(
    {
        "evaluator_qualitative",
        "persona_generation",
        "persona_stream",
        "persona_from_stakeholders",
        "stakeholder_suggestion",
        "first_diamond_closing",
    }
)


def resolve_class(caller: str | None) -> str:
    """Map a ``caller`` string to its required capability_class.

    Unknown / missing callers fall back to ``standard`` (fast default).
    """
    if caller and caller in _QUALITY_CALLERS:
        return QUALITY
    return STANDARD
