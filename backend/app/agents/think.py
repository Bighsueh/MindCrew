from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from app.agents.llm_context import LLMCallContext
from app.agents.prompts.assembler import PromptAssembler
from app.chinese.converter import chinese_converter
from app.config import settings
from app.llm.factory import LLMProviderFactory
from app.llm.json_utils import parse_llm_json

logger = logging.getLogger(__name__)

_VALID_ACTION_TYPES = {
    "chat_message",
    "create_note",
    "move_note",
    "edit_note",
    "delete_note",
    "arrange_notes",
    "swap_notes",
    "tidy_area",
    "set_directive",
    "no_action",
    # Spec 13 — Supervisor only（draw_template 已移除，Phase 42 補正 R3／P1-4）
    "draw_zone",
    # Phase 42 C0 (spec 10 v2.0 §5.9) — Supervisor only：動態往下開新 section
    "open_section",
    # Phase 42 A1 (spec 04-06 §5.8) — Supervisor only：組長宣布推進
    "advance_sub_phase",
    # Phase 42 A3 (spec 04-03 §2.3.2.1 守則 8 / §3.0.7) — Supervisor only：
    # 任務提示與便條指認高亮
    "set_user_task",
    "note_highlight",
    # Phase 42 C2：投票相關 action 隨無投票收斂全面移除（spec 27 §14）；
    # 2.6 改 open_section ＋搬便條進選定區＋配選定理由。
}

# Text fields that must be converted to Traditional Chinese
_TEXT_FIELDS = {
    "content", "new_content", "group_name", "reason",
    "instruction", "focus_topic", "text", "label",
}


@dataclass
class ThinkResult:
    reasoning: str
    actions: list[dict]
    raw_response: str
    prompt_text: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    parse_failed: bool = False


def _apply_chinese_conversion(action: dict) -> dict:
    """Return a copy of the action with all text fields converted to Traditional Chinese."""
    converted = dict(action)
    for key in _TEXT_FIELDS:
        if key in converted and isinstance(converted[key], str):
            converted[key] = chinese_converter.convert(converted[key])
    return converted


def _parse_llm_response(raw: str) -> tuple[str, list[dict], bool]:
    """Parse the LLM JSON response.

    Returns (reasoning, actions, parse_failed).
    Uses robust JSON parsing with regex fallback and truncation repair.
    On any failure, returns a no_action fallback.
    """
    data = parse_llm_json(raw)
    if data is None:
        logger.warning("LLM response JSON parse failed | raw=%r", raw[:300])
        return "", [{"type": "no_action", "reason": "JSON 解析失敗"}], True

    reasoning = data.get("reasoning", "")
    actions_raw: list[dict] = data.get("actions", [])

    if not isinstance(actions_raw, list):
        return reasoning, [{"type": "no_action", "reason": "actions 欄位格式錯誤"}], True

    validated: list[dict] = []
    for act in actions_raw:
        if not isinstance(act, dict):
            continue
        action_type = act.get("type", "")
        if action_type not in _VALID_ACTION_TYPES:
            logger.warning("Unknown action type skipped: %r", action_type)
            continue
        validated.append(act)

    if not validated:
        validated = [{"type": "no_action", "reason": "沒有有效的 action"}]

    action_types = [a.get("type") for a in validated]
    logger.info("Parsed LLM actions: %s", action_types)

    return reasoning, validated, False


class ThinkEngine:
    """Generate actions by calling the LLM with a 4-layer assembled prompt."""

    def __init__(self) -> None:
        self._assembler = PromptAssembler()
        self._llm_service = LLMProviderFactory.get_service()

    async def generate_actions(
        self, context: dict, *, llm_ctx: LLMCallContext
    ) -> ThinkResult:
        """Call the LLM and parse the response into structured actions.

        All text content fields are post-processed through OpenCC.
        On JSON parse failure, falls back to no_action.
        """
        messages = self._assembler.assemble(context)

        # Guard: truncate user message if total prompt is too long for model
        # Rough estimate: 1 CJK char ≈ 2 tokens, 1 ASCII word ≈ 1.3 tokens
        _MAX_PROMPT_CHARS = 12000  # ~24K tokens, leaves room for max_tokens output
        total_chars = sum(len(m.get("content", "")) for m in messages)
        if total_chars > _MAX_PROMPT_CHARS and len(messages) >= 2:
            excess = total_chars - _MAX_PROMPT_CHARS
            user_msg = messages[-1]
            content = user_msg.get("content", "")
            if len(content) > excess + 200:
                messages[-1] = {
                    **user_msg,
                    "content": content[: len(content) - excess - 100] + "\n\n（上下文已截短以符合模型限制）",
                }
                logger.info("Prompt truncated: removed %d chars from user message", excess + 100)

        prompt_text = json.dumps(messages, ensure_ascii=False)

        start_ms = int(time.time() * 1000)
        try:
            response = await self._llm_service.chat_completion(
                messages=messages,
                temperature=0.7,
                # Phase 37: cap THINK output — p90≈986/p99≈1024 in production, so
                # 1024 doesn't truncate normal output but cuts the long tail that
                # dominates latency (output length linearly drives decode time).
                # settings.LLM_MAX_TOKENS_PER_CALL is used only here, so this is safe.
                max_tokens=min(settings.LLM_MAX_TOKENS_PER_CALL, 1024),
                caller=llm_ctx.caller or "agent_think",
                owning_user_id=llm_ctx.owning_user_id,
                triggered_by_user_id=llm_ctx.triggered_by_user_id,
                project_id=llm_ctx.project_id,
            )
        except Exception as exc:
            logger.error("LLM call failed in ThinkEngine: %s", exc)
            end_ms = int(time.time() * 1000)
            return ThinkResult(
                reasoning="LLM 呼叫失敗",
                actions=[{"type": "no_action", "reason": f"LLM 錯誤：{exc}"}],
                raw_response="",
                prompt_text=prompt_text,
                model="unknown",
                tokens_in=0,
                tokens_out=0,
                latency_ms=end_ms - start_ms,
                parse_failed=True,
            )

        end_ms = int(time.time() * 1000)
        latency_ms = end_ms - start_ms

        raw_content = response.content
        reasoning, actions, parse_failed = _parse_llm_response(raw_content)

        # Apply Traditional Chinese conversion to all text fields
        actions = [_apply_chinese_conversion(a) for a in actions]
        if reasoning:
            reasoning = chinese_converter.convert(reasoning)

        return ThinkResult(
            reasoning=reasoning,
            actions=actions,
            raw_response=raw_content,
            prompt_text=prompt_text,
            model=response.model,
            tokens_in=response.usage.prompt_tokens,
            tokens_out=response.usage.completion_tokens,
            latency_ms=latency_ms,
            parse_failed=parse_failed,
        )
