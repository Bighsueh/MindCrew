from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.db.models.agent_decision_trace import AgentDecisionTrace
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


class TraceService:
    """Write agent decision traces to the agent_decision_trace table.

    This service provides a clean interface for saving full Decision Trace
    records that include Observe → Assess → Think → Act results.
    """

    async def save_trace(
        self,
        project_id: UUID,
        agent_id: str,
        stage: str,
        assess_result: Any | None,
        think_result: Any | None,
        act_result: Any | None,
    ) -> None:
        """Persist one complete decision cycle trace to the database.

        Args:
            project_id: UUID of the project this agent belongs to.
            agent_id: Identifier of the agent (e.g. "agent_supervisor").
            stage: Current Design Thinking stage name (warmup/discover/define/completed).
            assess_result: AssessResult dataclass instance (or None if assess was skipped).
            think_result: ThinkResult dataclass instance (or None if think was skipped).
            act_result: ActResult dataclass instance (or None if act was skipped).
        """
        try:
            async with async_session_factory() as session:
                trace = AgentDecisionTrace(
                    project_id=project_id,
                    agent_id=agent_id,
                    stage=stage,
                    # Assess fields
                    assess_result=getattr(assess_result, "decision", "unknown"),
                    assess_rule=getattr(assess_result, "rule", None),
                    assess_details=getattr(assess_result, "details", None),
                    # Think fields
                    prompt_text=getattr(think_result, "prompt_text", None),
                    llm_response=getattr(think_result, "raw_response", None),
                    llm_model=getattr(think_result, "model", None),
                    llm_tokens_in=getattr(think_result, "tokens_in", None),
                    llm_tokens_out=getattr(think_result, "tokens_out", None),
                    llm_latency_ms=getattr(think_result, "latency_ms", None),
                    # Act fields
                    action_type=self._extract_action_type(act_result),
                    action_details=self._extract_action_details(act_result),
                    action_result="success" if self._is_success(act_result) else "error",
                )
                session.add(trace)
                await session.commit()
                logger.debug(
                    "Trace saved: project=%s agent=%s stage=%s assess=%s",
                    project_id,
                    agent_id,
                    stage,
                    trace.assess_result,
                )
        except Exception as exc:
            logger.error(
                "Failed to save trace for agent=%s project=%s: %s",
                agent_id,
                project_id,
                exc,
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_action_type(self, act_result: Any | None) -> str | None:
        if act_result is None:
            return None
        executed: list[dict] = getattr(act_result, "executed_actions", [])
        if executed:
            return executed[0].get("type")
        return "no_action"

    def _extract_action_details(self, act_result: Any | None) -> dict | None:
        if act_result is None:
            return None
        return {
            "executed": getattr(act_result, "executed_actions", []),
            "skipped": getattr(act_result, "skipped_actions", []),
            "errors": getattr(act_result, "errors", []),
        }

    def _is_success(self, act_result: Any | None) -> bool:
        if act_result is None:
            return True  # No act = no failure
        return getattr(act_result, "success", True)


# Module-level singleton
trace_service = TraceService()
