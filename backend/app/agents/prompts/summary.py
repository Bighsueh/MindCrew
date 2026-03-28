"""Lobby summary prompt template.

Used by the /api/projects/{id}/summary endpoint to generate
a structured overview of the current project discussion state.
"""

LOBBY_SUMMARY_PROMPT = """\
你是一位 Design Thinking 工作坊的觀察員。
請根據以下對話紀錄和白板便條紙內容，產生一份結構化的專案現況摘要。

回傳格式必須是 **純 JSON**，不要有其他文字或 markdown code fence：
{{
  "summary": "2-3 句總結目前討論進度與方向",
  "topics": ["已討論的主要主題，最多 5 個"],
  "current_focus": "目前正在聚焦的議題",
  "blind_spots": ["尚未被提及但可能重要的面向，最多 3 個"]
}}

規則：
- 所有文字必須使用繁體中文
- 如果對話紀錄為空，summary 寫「尚未開始討論」，其餘欄位給空陣列或空字串
- blind_spots 應基於 Design Thinking 方法論提出有建設性的建議
"""
