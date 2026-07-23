"""人類輸入實質檢核（Phase 42 A2，spec 20 v2.0 §12）。

回合鎖解鎖判定的第一道把關（§11.4 條件 1）：真人在**群組 chat / 白板**的輸入是否
為「實質參與」。personal chat 不經此檢核（§4 / §12.1）。

分層（§12.1）：
  confirm 語境白名單 → 直接有效
  否則 → tier-1 規則層（≥5 有意義字元、敷衍黑名單、純 emoji/標點=0）
            ├ 不過 → 退回（§12.5）
            └ 過 → tier-2 LLM 語意層（按關判準；不可達→保守放行）
                     ├ 不過 → 退回
                     └ 過 → 有效

confirm 白名單已於 A3 轉正（Phase 42 補正 R5 更正 stale docstring）：
`confirm_context_active(project_id, sub_phase)` 讀 user_task_state——
`action_kind=confirm` 且 sub_phase 相符才放行（任務更換/換關失效，Flow 12），
由 `process_group_input` 接上；參數 `is_confirm_context` 供測試/呼叫端覆寫。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.agents.text_metrics import meaningful_char_count

logger = logging.getLogger(__name__)

_MIN_MEANINGFUL_CHARS = 5
# 便條型輸入的長度地板較低（A2 補強裁定，記於 progress.md）：1.1b 等格的便條
# 規格本就「只寫名字」（如「學生」=2 字），§12.2 的 ≥5 字地板會誤殺；貼便條是
# 刻意動作、敷衍風險低，黑名單與純 emoji/標點=0 照常把關。
_MIN_MEANINGFUL_CHARS_NOTE = 2

# 敷衍黑名單（去空白標點後的有意義字元字串比對）。spec 僅列代表例，完整清單維護於此。
# 註：「對 / 好 / 可以 / 不錯 / 嗯」等多半已被 ≥5 字地板擋下；黑名單補較長的敷衍句。
_BLACKLIST: frozenset[str] = frozenset({
    "對", "對啊", "對對對", "不錯", "嗯", "嗯嗯", "好", "好喔", "好啊", "好的",
    "哈哈", "哈哈哈", "沒意見", "沒有意見", "都可以", "都行", "隨便", "都好",
    "不知道", "沒想法", "沒fu", "ok", "okok", "yes", "no",
})


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    reason_zh: str = ""
    hint_zh: str = ""


def _normalize(text: str) -> str:
    """去掉非有意義字元（空白 / 標點 / emoji），保留 CJK 與英數（轉小寫）。"""
    return "".join(ch for ch in text if ch.isalnum()).lower()


def tier1_pass(
    text: str | None,
    *,
    is_confirm_context: bool = False,
    input_type: str = "chat",
) -> tuple[bool, str]:
    """tier-1 規則層。回 (passed, 內部原因鍵)。confirm 語境直接放行。

    長度地板依 input_type：chat ≥5、note ≥2（便條規格本就精簡，見常數註記）。
    """
    if is_confirm_context:
        return True, "confirm_whitelist"
    if not text:
        return False, "empty"
    meaningful = meaningful_char_count(text)
    if meaningful == 0:
        return False, "emoji_or_punct"
    floor = _MIN_MEANINGFUL_CHARS_NOTE if input_type == "note" else _MIN_MEANINGFUL_CHARS
    if meaningful < floor:
        return False, "too_short"
    normalized = _normalize(text)
    if normalized in _BLACKLIST:
        return False, "perfunctory"
    # 單一重複字元的填充（如「哈哈哈哈哈」「嗯嗯嗯嗯嗯」）視為敷衍。
    # 僅適用 ≥3 字——2 字疊字可能是正當名稱（「媽媽」「爸爸」）；「哈哈」由黑名單擋。
    if meaningful >= 3 and len(set(normalized)) <= 1:
        return False, "perfunctory"
    return True, "ok"


async def tier2_pass(text: str, sub_phase: str, *, llm_ctx) -> bool:
    """tier-2 LLM 語意層。LLM 不可達 / 無 owning user → 保守放行（§12.3）。"""
    owning = getattr(llm_ctx, "owning_user_id", None) if llm_ctx else None
    if owning is None:
        return True
    try:
        from app.agents.prompts.human_input_check import tier2_judge_messages
        from app.llm.factory import LLMProviderFactory
        from app.llm.json_utils import parse_llm_json

        llm = LLMProviderFactory.get_service()
        response = await llm.chat_completion(
            messages=tier2_judge_messages(text, sub_phase),
            temperature=0.1,
            max_tokens=120,
            caller="human_input_check",
            owning_user_id=owning,
            project_id=getattr(llm_ctx, "project_id", None),
        )
        parsed = parse_llm_json(response.content)
        if not isinstance(parsed, dict):
            return True  # 解析失敗 → 保守放行
        return bool(parsed.get("substantive", True))
    except Exception:
        logger.debug("tier2 substantive check failed sub=%s — 保守放行", sub_phase, exc_info=True)
        return True


async def check_human_input(
    text: str | None,
    sub_phase: str,
    *,
    llm_ctx=None,
    is_confirm_context: bool = False,
    input_type: str = "chat",
) -> CheckResult:
    """完整檢核。不過時 reason_zh/hint_zh 為內容層話術（無機制名，§12.5）。"""
    from app.agents.prompts.human_input_check import bounce_text

    t1_ok, _reason = tier1_pass(
        text, is_confirm_context=is_confirm_context, input_type=input_type
    )
    if not t1_ok:
        reason_zh, hint_zh = bounce_text(sub_phase)
        return CheckResult(passed=False, reason_zh=reason_zh, hint_zh=hint_zh)

    if is_confirm_context:
        return CheckResult(passed=True)

    if not await tier2_pass(text or "", sub_phase, llm_ctx=llm_ctx):
        reason_zh, hint_zh = bounce_text(sub_phase)
        return CheckResult(passed=False, reason_zh=reason_zh, hint_zh=hint_zh)

    return CheckResult(passed=True)


async def process_group_input(
    project_id: UUID,
    user_id: UUID,
    text: str | None,
    input_type: str,
    sub_phase: str | None = None,
) -> bool:
    """真人群組輸入的完整流程：檢核 → 過則註冊回合鎖、不過則發 input_bounced。

    chat（ws/chat_ws.py）與 note（projects/router.py human_create_note）共用。
    回傳「本回合是否因此完成（解鎖）」。sub_phase 未給時讀 DB 鮮值；讀不到 / 空
    → 不動作（防空鍵污染）。背景任務呼叫，任何失敗不影響輸入本身的落地。
    """
    try:
        if sub_phase is None:
            from sqlalchemy import select

            from app.db.models.project import Project
            from app.db.session import async_session_factory

            async with async_session_factory() as session:
                row = (
                    await session.execute(
                        select(
                            Project.current_sub_phase, Project.current_stage
                        ).where(Project.id == project_id)
                    )
                ).first()
            if row is None:
                return False
            sub_phase = (row[0] or row[1] or "").strip()
        if not sub_phase:
            return False

        from app.agents import round_lock
        from app.agents.llm_context import LLMCallContext

        is_confirm = await confirm_context_active(project_id, sub_phase)
        llm_ctx = LLMCallContext(
            owning_user_id=user_id, project_id=project_id, caller="human_input_check"
        )
        result = await check_human_input(
            text,
            sub_phase,
            llm_ctx=llm_ctx,
            is_confirm_context=is_confirm,
            input_type=input_type,
        )
        if not result.passed:
            from app.events.bus import event_bus
            from app.events.types import InputBouncedEvent

            await event_bus.publish(
                InputBouncedEvent(
                    project_id=project_id,
                    user_id=str(user_id),
                    reason_zh=result.reason_zh,
                    hint_zh=result.hint_zh,
                )
            )
            return False
        return await round_lock.register_human_input(project_id, sub_phase, input_type)
    except Exception:
        logger.debug(
            "process_group_input failed project=%s type=%s",
            project_id, input_type, exc_info=True,
        )
        return False


async def confirm_context_active(project_id: UUID, sub_phase: str | None = None) -> bool:
    """確認語境白名單（spec 20 §12.4；Phase 42 A3 轉正）。

    讀 user_task_state 最新任務：``action_kind=confirm`` 且任務的 sub_phase 與
    當前一致才生效——任務更換或換關即失效（spec 05 Flow 12 生命週期）。
    讀取失敗 → False（保守：不誤放敷衍）。
    """
    try:
        from app.agents.user_task_state import get_current

        task = await get_current(project_id)
        if not task or task.get("action_kind") != "confirm":
            return False
        if sub_phase and task.get("sub_phase") and task["sub_phase"] != sub_phase:
            return False
        return True
    except Exception:
        logger.debug("confirm_context_active failed project=%s", project_id, exc_info=True)
        return False
