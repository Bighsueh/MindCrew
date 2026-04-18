"""Organization Turn — Supervisor-driven canvas cleanup at phase transitions.

At key phase boundaries (convergence phases, macro transitions), the Supervisor
gets a dedicated turn to organize the whiteboard. This replaces the old
_AUTO_TIDY_PHASES silent system tidy with a visible, agent-driven process.

The Supervisor:
1. Announces in chat that it's organizing
2. Receives a full canvas snapshot (all note_ids, clusters, positions)
3. Gets a focused organization-only prompt
4. Must produce at least one canvas action (validated)
5. Falls back to a deterministic plan if LLM fails 3 times
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.canvas.analyzer import CanvasAnalysis, get_spatial_analyzer
from app.chinese.converter import chinese_converter
from app.config import settings
from app.events.bus import event_bus
from app.events.types import ChatMessageEvent
from app.llm.factory import LLMProviderFactory
from app.llm.json_utils import parse_llm_json
from app.stages.micro_phases import get_micro_phase

logger = logging.getLogger(__name__)

# Phases that trigger an Organization Turn on entry.
_ORGANIZATION_PHASES: frozenset[str] = frozenset({
    "1.3", "2.1", "2.3", "3.1", "3.2", "3.3", "4.1",
})

_CANVAS_ACTION_TYPES: frozenset[str] = frozenset({
    "arrange_notes", "tidy_area", "move_note",
})

_MAX_LLM_RETRIES = 3
_MIN_NOTES_FOR_ORG = 5
_REDIS_LOCK_TTL = 120
_REDIS_COMPLETED_TTL = 300


@dataclass(frozen=True)
class OrganizationResult:
    status: str  # "completed" | "skipped" | "fallback"
    reason: str = ""
    executed_count: int = 0
    used_fallback: bool = False
    retries: int = 0
    pre_orderliness: float = 0.0


# ---------------------------------------------------------------------------
# Gate: should we run?
# ---------------------------------------------------------------------------

async def should_run_organization_turn(
    project_id: UUID,
    to_phase: str,
) -> bool:
    """Decide whether an Organization Turn should run for this transition."""
    if to_phase not in _ORGANIZATION_PHASES:
        return False

    # Check Supervisor seat — skip if a human is sitting there
    if await _is_human_supervisor(project_id):
        logger.info("Skipping Organization Turn: human Supervisor")
        return False

    # Check note count — skip if too few
    try:
        analyzer = get_spatial_analyzer()
        analysis = await analyzer.analyze(project_id)
        if len(analysis.notes) < _MIN_NOTES_FOR_ORG:
            logger.info("Skipping Organization Turn: only %d notes", len(analysis.notes))
            return False
    except Exception:
        logger.warning("Skipping Organization Turn: canvas analysis failed")
        return False

    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_organization_turn(
    project_id: UUID,
    agent_id: str,
    from_phase: str,
    to_phase: str,
) -> OrganizationResult:
    """Execute a Supervisor-driven Organization Turn."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    lock_key = f"project:{project_id}:org_turn_running"

    try:
        acquired = await r.set(lock_key, "1", nx=True, ex=_REDIS_LOCK_TTL)
        if not acquired:
            return OrganizationResult(status="skipped", reason="already_running")

        # 1. Announce in chat
        await _send_chat(project_id, agent_id, "在進入下一步驟之前，我來整理一下白板上的便條紙。")

        # 2. Full canvas analysis (no cap)
        analyzer = get_spatial_analyzer()
        await analyzer.invalidate_full_state_cache(project_id)
        analysis = await analyzer.analyze(project_id)

        if len(analysis.notes) < _MIN_NOTES_FOR_ORG:
            return OrganizationResult(status="skipped", reason="too_few_notes")

        # 3. Build snapshot for prompt
        from app.canvas.tools_perception import get_canvas_snapshot
        snapshot = await get_canvas_snapshot(project_id)

        # 4. Pre-compute fallback plan
        fallback_actions = _build_fallback_plan(analysis)

        # 5. Build organization prompt
        messages = _build_organization_prompt(analysis, snapshot, from_phase, to_phase)

        # 6. LLM call with retries
        final_actions: list[dict] | None = None
        used_fallback = False
        retries = 0

        llm = LLMProviderFactory.get_service()

        for attempt in range(_MAX_LLM_RETRIES):
            try:
                if attempt > 0:
                    messages = _escalate_prompt(messages, attempt, fallback_actions)
                    retries = attempt

                response = await llm.chat_completion(
                    messages=messages,
                    temperature=0.4,
                    max_tokens=settings.LLM_MAX_TOKENS_PER_CALL,
                )

                parsed = parse_llm_json(response.content)
                if parsed is None:
                    continue

                actions = parsed.get("actions", [])
                if not isinstance(actions, list):
                    continue

                filtered, is_valid = _validate_organization_response(actions)
                if is_valid:
                    final_actions = filtered
                    break

            except Exception as exc:
                logger.warning("Organization Turn LLM attempt %d failed: %s", attempt, exc)

        # 7. Fallback if LLM failed
        if final_actions is None:
            final_actions = fallback_actions
            used_fallback = True
            logger.info("Organization Turn using fallback plan")

        # 8. Execute canvas actions with staggered animation
        executed_count = await _execute_staggered(
            project_id, agent_id, final_actions, analysis,
        )

        # 9. Mark completion
        await r.set(
            f"project:{project_id}:org_turn_completed_at",
            str(time.time()),
            ex=_REDIS_COMPLETED_TTL,
        )

        # 10. Completion announcement
        await _send_chat(project_id, agent_id, "白板整理完成，我們繼續下一步驟。")

        return OrganizationResult(
            status="fallback" if used_fallback else "completed",
            executed_count=executed_count,
            used_fallback=used_fallback,
            retries=retries,
            pre_orderliness=analysis.orderliness_score,
        )

    except Exception as exc:
        logger.error("Organization Turn unexpected error: %s", exc)
        return OrganizationResult(status="skipped", reason=str(exc))
    finally:
        await r.delete(lock_key)
        await r.aclose()


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

_TRANSITION_INSTRUCTIONS: dict[str, str] = {
    "1.3": "整理目標：將觀察便條紙分群 + 加標題。對每個語意叢集執行 arrange_notes，加上描述性標題。未分群的保留原位。最後 tidy_area 全局對齊。",
    "2.1": "整理目標：突顯 Persona + 歸檔觀察。確保每個 Persona 群組清晰標記。將散落的觀察便條紙歸整到對應叢集。",
    "2.3": "整理目標：突顯 HMW 問題。將 HMW 便條紙（綠色 or 含「如何能」）排列在顯眼位置。整理 insight 便條紙到叢集。",
    "3.1": "整理目標：淨空白板。將前一階段的便條紙整理到叢集，為大量方案發想清出空間。",
    "3.2": "整理目標：方案分群。將散落的方案便條紙按主題分群 + 加標題。",
    "3.3": "整理目標：標記重點方案。將方案按優先度整理，重點方案放在顯眼位置。",
    "4.1": "整理目標：方案整理。確保選定方案清晰標記，為原型設計清出工作區。",
}


def _build_organization_prompt(
    analysis: CanvasAnalysis,
    snapshot: dict[str, Any],
    from_phase: str,
    to_phase: str,
) -> list[dict]:
    """Build a focused 2-message prompt for organization."""
    try:
        mp = get_micro_phase(to_phase)
        to_name = mp.name_zh
    except KeyError:
        to_name = to_phase

    transition_instr = _TRANSITION_INSTRUCTIONS.get(to_phase, "整理白板，讓便條紙分群清晰。")

    system_msg = (
        f"你是工作坊的引導者。團隊即將進入「{to_name}」（{to_phase}）。\n"
        "在繼續之前，你要先整理白板，讓大家清楚看到目前的成果。\n\n"
        f"【整理指引】\n{transition_instr}\n\n"
        "【回應格式】\n"
        "以 JSON 回應，格式如下：\n"
        '{"reasoning": "...", "actions": [...]}\n\n'
        "actions 中：\n"
        "- 必須包含至少一個 arrange_notes 或 tidy_area\n"
        "- 可以有一個 chat_message 宣告你在做什麼\n"
        "- arrange_notes 參數：note_ids (list), layout (\"grid\"), target_region (str), label (str)\n"
        "- tidy_area 參數：scope (\"all\"), strategy (\"align_grid\")\n"
        "- move_note 參數：note_id (str), to (\"cluster:xxx\" 或 \"region:xxx\")\n\n"
        "你必須使用白板操作工具。只發 chat_message 不整理白板是不可接受的。\n"
        "只回應 JSON，不要包含任何其他文字。"
    )

    user_msg = _format_canvas_for_prompt(analysis, snapshot)

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _format_canvas_for_prompt(
    analysis: CanvasAnalysis,
    snapshot: dict[str, Any],
) -> str:
    """Format full canvas state as user message with concrete examples."""
    parts: list[str] = []
    total = len(analysis.notes)
    cluster_count = len(analysis.cluster_state.clusters)
    ungrouped_count = len(analysis.cluster_state.ungrouped_note_ids)

    parts.append(f"【白板】共 {total} 張便條紙，{cluster_count} 個語意叢集，{ungrouped_count} 張未分群\n")

    # Clusters with note_ids
    for c in analysis.cluster_state.clusters:
        label = analysis.cluster_labels.get(c.cluster_id, "未命名")
        members = [n for n in analysis.notes if n.id in c.note_ids]
        parts.append(f"叢集「{label}」({len(members)} 張)：")
        for n in members[:10]:  # Cap per cluster to save tokens
            text_preview = n.text[:30] if n.text else ""
            parts.append(f"  - {n.id}: {text_preview} [{n.color}]")
        if len(members) > 10:
            parts.append(f"  ... 還有 {len(members) - 10} 張")
        parts.append("")

    # Ungrouped notes
    if analysis.cluster_state.ungrouped_note_ids:
        ungrouped_notes = [
            n for n in analysis.notes
            if n.id in analysis.cluster_state.ungrouped_note_ids
        ]
        parts.append(f"未分群 ({len(ungrouped_notes)} 張)：")
        for n in ungrouped_notes[:8]:
            text_preview = n.text[:30] if n.text else ""
            parts.append(f"  - {n.id}: {text_preview} [{n.color}]")
        if len(ungrouped_notes) > 8:
            parts.append(f"  ... 還有 {len(ungrouped_notes) - 8} 張")
        parts.append("")

    # Concrete examples using REAL note_ids
    parts.append("【操作範例】根據目前白板，你可以這樣做：")
    if analysis.cluster_state.clusters:
        first_cluster = analysis.cluster_state.clusters[0]
        first_label = analysis.cluster_labels.get(first_cluster.cluster_id, "主題")
        example_ids = first_cluster.note_ids[:5]
        ids_str = ", ".join(f'"{nid}"' for nid in example_ids)
        parts.append(
            f'- {{"type": "arrange_notes", "note_ids": [{ids_str}], '
            f'"layout": "grid", "target_region": "top-left", "label": "{first_label}"}}'
        )
    parts.append('- {"type": "tidy_area", "scope": "all", "strategy": "align_grid"}')

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_organization_response(
    actions: list[dict],
) -> tuple[list[dict], bool]:
    """Validate that response contains canvas actions.

    Returns (filtered_actions, is_valid).
    """
    filtered: list[dict] = []
    chat_count = 0
    has_canvas = False

    for action in actions:
        action_type = action.get("type", "")
        if action_type == "chat_message":
            if chat_count < 1:  # Allow one announcement
                filtered.append(action)
                chat_count += 1
        elif action_type in _CANVAS_ACTION_TYPES:
            filtered.append(action)
            has_canvas = True
        # Silently drop other types (no_action, set_directive, etc.)

    return filtered, has_canvas


# ---------------------------------------------------------------------------
# Fallback plan
# ---------------------------------------------------------------------------

def _build_fallback_plan(analysis: CanvasAnalysis) -> list[dict]:
    """Deterministic fallback actions from cluster analysis."""
    actions: list[dict] = []

    regions = ["top-left", "top-center", "top-right", "center-left", "center", "center-right"]

    for i, cluster in enumerate(analysis.cluster_state.clusters):
        label = analysis.cluster_labels.get(cluster.cluster_id, f"群組{i + 1}")
        region = regions[i % len(regions)]
        actions.append({
            "type": "arrange_notes",
            "note_ids": cluster.note_ids,
            "layout": "grid",
            "target_region": region,
            "label": chinese_converter.convert(label),
        })

    # Always tidy at the end
    actions.append({
        "type": "tidy_area",
        "scope": "all",
        "strategy": "align_grid",
    })

    return actions


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------

def _escalate_prompt(
    messages: list[dict],
    attempt: int,
    fallback_actions: list[dict],
) -> list[dict]:
    """Add escalating specificity on retry."""
    import json

    escalation = ""
    if attempt == 1:
        escalation = (
            "\n\n⚠️ 你的上次回應沒有包含任何白板操作。"
            "你必須在 actions 中包含至少一個 arrange_notes 或 tidy_area。"
        )
    elif attempt >= 2:
        plan_json = json.dumps(fallback_actions, ensure_ascii=False, indent=2)
        escalation = (
            "\n\n⚠️ 你已經兩次未能提供白板操作。"
            "以下是一個可行的整理方案，你可以直接採用或改進：\n"
            f"```json\n{plan_json}\n```"
        )

    if not messages:
        return messages

    updated = list(messages)
    updated[-1] = {
        "role": updated[-1]["role"],
        "content": updated[-1]["content"] + escalation,
    }
    return updated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _is_human_supervisor(project_id: UUID) -> bool:
    """Check if the Supervisor seat is occupied by a human."""
    try:
        from app.db.session import async_session_factory
        from sqlalchemy import select
        from app.db.models.seat import Seat

        async with async_session_factory() as session:
            result = await session.execute(
                select(Seat).where(
                    Seat.project_id == project_id,
                    Seat.seat_role == "supervisor",
                    Seat.occupant_type == "human",
                )
            )
            return result.scalar_one_or_none() is not None
    except Exception:
        return False


async def _execute_staggered(
    project_id: UUID,
    agent_id: str,
    actions: list[dict],
    analysis: CanvasAnalysis,
) -> int:
    """Execute canvas actions with staggered cluster-by-cluster animation.

    For arrange_notes: compute target positions, then send to sidecar as
    staggered updates (one note at a time, 150ms apart). Between clusters,
    add a 500ms pause. Labels appear before their cluster's notes.

    For tidy_area and other ops: execute normally (instant).
    """
    import asyncio

    from app.bridge.canvas_ops import canvas_ops
    from app.canvas.analyzer import get_spatial_analyzer
    from app.canvas.layout_engine import get_layout_engine

    _NOTE_STAGGER_MS = 400
    _CLUSTER_PAUSE_S = 0.8
    _LABEL_DELAY_S = 0.3

    executed = 0
    analyzer = get_spatial_analyzer()

    for action in actions:
        action_type = action.get("type", "")

        if action_type == "arrange_notes":
            note_ids = action.get("note_ids", [])
            layout = action.get("layout", "grid")
            target_region = action.get("target_region", "center")
            columns = action.get("columns")
            spacing = action.get("spacing", "default")
            label = action.get("label")

            if not note_ids:
                continue

            # Compute target positions
            current = await analyzer.analyze(project_id)
            engine = get_layout_engine()
            updates = engine.compute_arrangement(
                note_ids=note_ids,
                layout=layout,
                target_region=target_region,
                notes=current.notes,
                columns=columns,
                spacing=spacing,
            )

            if not updates:
                continue

            # Create label note first (if any)
            if label:
                converted_label = chinese_converter.convert(label)
                min_x = min(u.x for u in updates)
                min_y = min(u.y for u in updates)
                try:
                    await canvas_ops.add_note(
                        project_id=project_id,
                        content=converted_label,
                        position={"x": min_x, "y": min_y - 160},
                        color="blue",
                        author_id=agent_id,
                        author_name="Supervisor",
                        author_type="ai",
                    )
                except Exception as exc:
                    logger.warning("Staggered label creation failed: %s", exc)

                await asyncio.sleep(_LABEL_DELAY_S)

            # Send staggered coordinate updates
            stagger_updates = [
                {"id": u.id, "x": u.x, "y": u.y} for u in updates
            ]
            await canvas_ops.staggered_update_coordinates(
                project_id, stagger_updates,
                stagger_ms=_NOTE_STAGGER_MS,
                moving_by="AI 引導者",
            )

            # Wait for all staggered updates to complete on the sidecar
            total_wait = len(stagger_updates) * _NOTE_STAGGER_MS / 1000.0
            await asyncio.sleep(total_wait + 0.1)

            executed += 1

            # Pause between clusters
            await asyncio.sleep(_CLUSTER_PAUSE_S)

        elif action_type == "tidy_area":
            try:
                from app.agents.act_canvas import execute_canvas_tool
                await execute_canvas_tool(
                    op_type="tidy_area",
                    action=action,
                    project_id=project_id,
                    agent_id=agent_id,
                    agent_name="Supervisor",
                )
                executed += 1
            except Exception as exc:
                logger.warning("Staggered tidy_area failed: %s", exc)

        elif action_type == "move_note":
            try:
                from app.agents.act_canvas import execute_canvas_tool
                await execute_canvas_tool(
                    op_type="move_note",
                    action=action,
                    project_id=project_id,
                    agent_id=agent_id,
                    agent_name="Supervisor",
                )
                executed += 1
                await asyncio.sleep(_NOTE_STAGGER_MS / 1000.0)
            except Exception as exc:
                logger.warning("Staggered move_note failed: %s", exc)

    return executed


async def _send_chat(project_id: UUID, agent_id: str, text: str) -> None:
    """Send a chat message as the Supervisor."""
    try:
        content = chinese_converter.convert(text)
        event = ChatMessageEvent(
            project_id=project_id,
            sender_id=agent_id,
            sender_type="ai",
            sender_name="Supervisor",
            content=content,
        )
        await event_bus.publish(event)
    except Exception as exc:
        logger.warning("Organization Turn chat send failed: %s", exc)
