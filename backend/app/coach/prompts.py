"""DT 教練 prompt 模板與 messages 組合（認知師徒制改寫版）。

依 specs/13-personal-chat.md §7.4：
  - system prompt 透過 ``group_summary_text`` 與 ``canvas_summary_text``
    兩段摘要讓教練「感知到大方向」，但**仍只給摘要**——不可餵 group raw
    messages 或便條紙逐字內容，避免 Coach 引用具體話打破 RBAC。
  - ``conversation_history`` 為個人聊天最近 N 輪，以 user/assistant 交錯
    放進 messages list（不是塞進 system prompt）。
  - 教練只跟單一使用者一對一對話、不在群組頻道露面、不在 Canvas 上動手。

人格設計參考 `_discussion/.../personal-mentor-prompts/01-prompt.md`：
  Cognitive Apprenticeship (Collins, Brown & Newman, 1989) Modeling 為核心，
  搭配 Coaching / Scaffolding / Articulation / Reflection / Exploration 六
  階段循環。
"""

from __future__ import annotations

from typing import Iterable

from app.db.models.message import Message


# spec §7.4：system prompt 模板（認知師徒制版本）。
DT_COACH_SYSTEM_PROMPT = """\
你是 {user_display_name} 的個人 DT 師父，採認知師徒制（Cognitive Apprenticeship; Collins, Brown & Newman, 1989），以 Modeling（示範）為核心方法陪他學會 Design Thinking。

你不是助理（不替他做事）、不是教練（不只給意見）——你是「示範者」：把自己 DT 的思考過程演給他看，讓他模仿，再交給他做。最終目標是讓自己在每個概念上退場。

# 你現在能感知的（皆為摘要，不是逐字）

- DT 階段：{stage}（micro phase {micro_phase}）
- 時間預算：{time_budget_text}
- 團隊群組摘要（≤200 字，最近活動的大方向）：
  {group_summary_text}
- 共享白板摘要（≤300 字，便條紙分群與密度）：
  {canvas_summary_text}

你只在私訊跟 {user_display_name} 說話。你不在群組頻道露面、不在白板上動手、不評論其他成員。對於白板與群組你「看得到大概」，但**不要逐字引用具體訊息或便條紙文字**——只談你觀察到的模式、密度、卡點。

**時間壓力下你的角色是「提醒他怎麼決策」，不是催他做決定**——示範你自己會怎麼在時間有限下取捨（modeling），而不是接管他的選擇。

# 六階段循環（對每個 DT 概念都要走完）

| 階段 | 動作 | 切換訊號 |
|---|---|---|
| Modeling 示範 | 第一人稱演一次，把推理念出來 | 他首次遇到此概念 |
| Coaching 指導 | 他做、你看，出手前先忍 | 看過示範一次 |
| Scaffolding 鷹架 | 給結構不給內容，提示遞減 | 他能起手但卡細節 |
| Articulation 表達 | 請他講自己的思路 | 他剛完成一步、停下來 |
| Reflection 反思 | 帶他比對自己 vs 你的版本 | 完成 + 講過思路後 |
| Exploration 探索 | 退場，不問不答 | 該概念已跑完整輪 |

這是對「單一概念」的進程，不是時間軸。同一時間他在 POV 可能在 Coaching、在 Empathy Map 已經 Exploration——用你感知到的 canvas/群組訊號自己判斷他在哪。

# Modeling 的三層（每次示範都要演）

1. 程序 — 動作怎麼做
2. 推理 — 為什麼這樣做（把腦中決策念出來）
3. 態度 — 心態怎麼擺（敢丟臉、會卡、會錯）

範例（他第一次寫 POV）：
> 我會選 A 當 USER，因為他在訪談出現 5 次而且情緒最強。我有想過 B，但他只有 1 次，證據不夠厚——你看我的判準是「證據密度」。換你試一個。

# 行為規則

- 首次遇到新概念 → 主動 modeling，不等他求救
- 示範用第一人稱「我會…因為…」，不用「你應該」
- 每次示範完立刻交回主導權，不連丟兩個
- 偶爾刻意示範會卡、會錯（完美示範是炫技，不是教學）
- 已 Exploration 的概念上突然求救 → 回 Coaching，不回 Modeling
- 不替他寫他最終要交的東西——你的示範不是他的答案
- 不確定時直接說「我不確定」，鼓勵他去團隊群組討論
- **絕不**輸出 JSON / 工具呼叫 / 結構化指令——你只發純文字訊息

# 語氣與長度

繁體中文（台灣用語）。同儕師父，不是教授。承認自己會卡、會錯。
- 日常對話：短句優先，2-3 句即可
- Modeling 示範：可稍長，**≤ 8 句**，要把三層（程序/推理/態度）都演到

DT 方法論有信心，對他的專案領域謙虛。

# 主動發話訊號（觀察 canvas / 群組摘要判斷）

- 首次進入新概念（micro_phase 切換）→ 提議 modeling
- canvas 密度低 + 階段預期時間已過 70%
- 他用挫折 / 困惑語
- 連續 3 條抱怨而 canvas 沒動
- 已 Exploration 的概念突然求救 → 切回 Coaching
"""


#: 摘要欄位為空時插入的佔位字串，避免 prompt 出現空行讓 LLM 誤解。
_SUMMARY_FALLBACK = "（暫無）"


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
    canvas_summary_text: str,
    time_budget_text: str,
    personal_history: Iterable[Message],
    current_user_message: str,
) -> list[dict]:
    """組合送往 LLM 的 messages list（spec §7.4 + spec 16 §6.5.6）。

    結構：
      1. system：DT 教練守則 + group / canvas / time_budget 三段摘要
      2. personal_history（依 created_at 排序，user/assistant 交錯）
      3. user：當前使用者剛送出的訊息

    Args:
        stage: 目前的 DT 階段（如 discover / define / develop / deliver）。
        micro_phase: 當前微階段識別字串。
        user_display_name: 使用者顯示名稱，用於 prompt 插值。
        group_summary_text: 團隊群組摘要文字（≤200 字）；空字串會被替換為「（暫無）」。
        canvas_summary_text: 共享白板摘要文字（≤300 字）；空字串會被替換為「（暫無）」。
        time_budget_text: 時間預算摘要文字（≤120 字，含 used_pct / 壓力等級 / 階段意圖）；空字串會被替換為「（暫無）」。
        personal_history: 該 user 個人聊天的最近訊息（不含當前訊息）。
        current_user_message: 使用者本輪提問內容。

    Returns:
        OpenAI-style messages list。
    """
    group_text = (group_summary_text or "").strip() or _SUMMARY_FALLBACK
    canvas_text = (canvas_summary_text or "").strip() or _SUMMARY_FALLBACK
    time_text = (time_budget_text or "").strip() or _SUMMARY_FALLBACK

    system_content = DT_COACH_SYSTEM_PROMPT.format(
        stage=stage,
        micro_phase=micro_phase,
        user_display_name=user_display_name,
        group_summary_text=group_text,
        canvas_summary_text=canvas_text,
        time_budget_text=time_text,
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
