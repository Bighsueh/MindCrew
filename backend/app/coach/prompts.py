"""DT 教練 prompt 模板與 messages 組合（Phase 20 重寫）。

依 specs/13-personal-chat.md §7.4：
  - system prompt 透過 ``group_summary_text`` 插入「團隊群組摘要」，
    **不可** 餵 group raw messages（避免 Coach 引用具體話打破 RBAC）。
  - ``conversation_history`` 為個人聊天最近 N 輪，以 user/assistant 交錯放進
    messages list（不是塞進 system prompt）。
  - 教練只跟單一使用者一對一對話，不持久化 Canvas、不參與群聊。
"""

from __future__ import annotations

from typing import Iterable

from app.db.models.message import Message


# spec §7.4：system prompt 模板。
DT_COACH_SYSTEM_PROMPT = """\
你是設計思考（Design Thinking）私人教練「DT 教練」，正在一對一陪伴使用者「{user_display_name}」。

目前情境：
- 階段：{stage}（micro phase {micro_phase}）
- 團隊群組摘要（最近活動，僅供你了解大方向，**不要假裝看到群組的具體訊息**）：
  {group_summary_text}

教練守則：
1. 角色：你只跟這位使用者一對一對話。你不會看到團隊群組的逐字訊息，也不參與 Canvas 操作。
   - 不要假裝看到群組的逐字訊息或 Canvas 上的便條紙。
   - 不要主動代寫使用者的作品；你引導他自己想。
2. 語氣：繁體中文（台灣用語），口語、簡短、像隨身教練；避免說教與條列式公文。
3. 內容：聚焦在這個 micro phase 該做什麼、卡點怎麼破、可以問自己哪些好問題。
4. 長度：**單則回應上限 150 字**；需要展開時用反問引導，不一次倒完。
5. 不確定時直接說「我不確定」，鼓勵使用者去團隊群組討論。
6. **絕不**輸出 JSON / 工具呼叫 / 結構化指令——你只發純文字訊息。
"""


def _role_for(message: Message) -> str:
    """把 Message.sender_type 映射成 OpenAI chat role。

    - ``human`` → ``user``
    - 其他（``ai`` / ``system`` ...）→ ``assistant``（DT 教練自己過去的回覆）

    spec §7.2：personal channel 僅有 user 與 DT 教練兩種發言者，因此用
    二分映射即可。``system`` 錯誤訊息（spec §7.3 失敗 fallback）也歸到
    assistant role，讓 LLM 知道上一輪 Coach 失敗，避免重複錯誤。
    """
    if message.sender_type == "human":
        return "user"
    return "assistant"


def build_messages(
    *,
    stage: str,
    micro_phase: str,
    user_display_name: str,
    group_summary_text: str,
    personal_history: Iterable[Message],
    current_user_message: str,
) -> list[dict]:
    """組合送往 LLM 的 messages list（spec §7.4）。

    結構：
      1. system：DT 教練守則 + group_summary_text
      2. personal_history（依 created_at 排序，user/assistant 交錯）
      3. user：當前使用者剛送出的訊息

    Args:
        stage: 目前的 DT 階段（如 discover / define / develop / deliver）。
        micro_phase: 當前微階段識別字串。
        user_display_name: 使用者顯示名稱，用於 prompt 插值。
        group_summary_text: 團隊群組摘要文字（200 字以內）；空字串會被替換為「（暫無）」。
        personal_history: 該 user 個人聊天的最近訊息（不含當前訊息）。
        current_user_message: 使用者本輪提問內容。

    Returns:
        OpenAI-style messages list。
    """
    summary = group_summary_text.strip() if group_summary_text else ""
    system_content = DT_COACH_SYSTEM_PROMPT.format(
        stage=stage,
        micro_phase=micro_phase,
        user_display_name=user_display_name,
        group_summary_text=summary or "（暫無）",
    )

    messages: list[dict] = [{"role": "system", "content": system_content}]

    # 依 created_at 由舊到新排序；對齊 ``MessageRepository.list_personal`` 的回傳排序。
    sorted_history = sorted(
        personal_history,
        key=lambda m: m.created_at,
    )
    for msg in sorted_history:
        messages.append(
            {
                "role": _role_for(msg),
                "content": msg.content,
            }
        )

    messages.append({"role": "user", "content": current_user_message})
    return messages
