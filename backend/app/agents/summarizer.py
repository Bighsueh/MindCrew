"""Supervisor Summarizer — 定期摘要機制（取代 Orchestrator 的 transition 步驟）。

僅在 comm_strategy == "simultaneous_summarizer" 時啟用。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SUMMARIZER_PROMPT: str = """\
請根據最近的討論做一個簡短摘要。摘要格式：

1. 亮點（1~2 個）：「{speaker} 提到的 X 很有意思，特別是 {延伸點}...」
2. 連結：「{speaker_a} 的 X 和 {speaker_b} 的 Y 之間好像有個有趣的關係...」
3. 盲區提問：「我們目前好像還沒有從 {某個角度} 來看這個問題，有人想試試嗎？」

注意：
- 不要列清單，用自然的對話語氣
- 不要評價誰的觀點好或壞
- 盲區提問要具體，不要說「還有沒有其他想法」這種空泛問題\
"""


_SUMMARY_MARKER = "【摘要】"


def should_summarize(context: dict, interval: int) -> bool:
    """判斷是否該做摘要。

    計算自上次 Supervisor 摘要後的新訊息數，達到 interval 則觸發。
    """
    if interval <= 0:
        return False
    recent_chat: list[dict] = context.get("recent_chat", [])
    msgs_since_last_summary = 0
    for msg in reversed(recent_chat):
        sender = msg.get("sender", "")
        content = msg.get("content", "")
        # 用摘要標記或角色名稱識別上一次摘要
        if "supervisor" in sender.lower() and _SUMMARY_MARKER in content:
            break
        msgs_since_last_summary += 1
    return msgs_since_last_summary >= interval


async def do_summarize(context: dict, llm_service: object) -> str | None:
    """使用 SUMMARIZER_PROMPT 呼叫 LLM 產出摘要文字。

    Returns the summary text, or None on failure.
    """
    recent_chat: list[dict] = context.get("recent_chat", [])
    if not recent_chat:
        return None

    # 組裝最近的討論內容供 LLM 摘要
    chat_text = "\n".join(
        f"{m.get('sender', '?')}：{m.get('content', '')}"
        for m in recent_chat[-10:]
    )
    messages = [
        {"role": "system", "content": SUMMARIZER_PROMPT},
        {"role": "user", "content": f"以下是最近的討論內容，請做摘要：\n\n{chat_text}"},
    ]
    try:
        response = await llm_service.chat_completion(messages=messages)  # type: ignore[attr-defined]
        # LLMResponse dataclass has .content attribute
        if hasattr(response, "content"):
            return response.content
        if isinstance(response, dict):
            return response.get("content", "")
        return str(response)
    except Exception:
        logger.warning("Summarizer LLM call failed", exc_info=True)
        return None
