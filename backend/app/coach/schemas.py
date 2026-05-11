"""DT 教練 endpoint 的 Pydantic schemas。

Phase 20 Step 17.6：endpoint 改為非同步觸發（先 ack，再背景產生 Coach reply）。
- ``DTCoachAskRequest``：與舊版相容（content / stage / micro_phase）。
- ``DTCoachAskResponse``：改為 ack 版，僅回傳剛寫入的 user_message 與
  ``coach_reply_scheduled=True``；Coach 回覆透過 WebSocket 之 ``chat_message``
  事件推送（chat_id=personal）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DTCoachAskRequest(BaseModel):
    """使用者向 DT 教練提問的請求 schema（spec 13 §5.2）。"""

    content: str = Field(..., min_length=1, max_length=2000)
    stage: str = Field(..., min_length=1, max_length=32)
    micro_phase: str = Field(..., min_length=1, max_length=32)


class DTCoachUserMessageBrief(BaseModel):
    """剛寫入的 user message 簡要回傳格式。

    僅給前端確認 message 已落地用；完整 message 體（含 Coach 回覆）會透過
    WS ``chat_message`` 事件推送，前端依 ``chat_id`` 對應到 personal channel。
    """

    id: str
    chat_id: str
    content: str
    created_at: str  # ISO 8601 UTC


class DTCoachAskResponse(BaseModel):
    """POST /dt-coach/ask 的回應 schema（ack 版）。

    spec §5.2：
      - ``user_message``：剛寫入 DB 的 user message brief。
      - ``coach_reply_scheduled``：恆為 True，表示背景任務已排程；實際 Coach
        回覆透過 WS 推送，非此 HTTP 回應。
    """

    user_message: DTCoachUserMessageBrief
    coach_reply_scheduled: bool = True
