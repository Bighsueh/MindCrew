"""Blackboard coordination rules injected into the system prompt.

These rules are only included when Blackboard data is available.
Full text from docs/blackboard-design.md §5.
"""

BLACKBOARD_COORDINATION_RULES: str = """\
你可以看到其他 AI 團隊成員的思考摘要（blackboard 欄位）。
請遵守以下規則：

【關於主題選擇】
- 查看 topic_saturation：如果某主題已是 "high" 且觀點多元性也高，\
優先考慮探索 blind_spots 或 "low" saturation 的主題
- 但如果你能從自己的專長角度對已有主題提出「不同觀點」，\
仍然歡迎加入該主題的討論
- 查看 missing_angles 欄位，這些是該主題尚未被覆蓋的觀點方向

【關於避免重複】
- 查看 other_agent_intentions：如果另一個成員的 focus_topic 跟你一樣，\
且他的 viewpoint 跟你想說的觀點相似，則換一個切入角度或換主題
- 判斷標準是「觀點是否相似」，不是「主題是否相同」
- 同一主題下的不同觀點是有價值的，不應被抑制

【關於深化討論】
- 如果你對某個已有觀點有延伸、質疑或不同角度的看法，\
主動在聊天室回應該觀點，這是有價值的互動
- 在 reasoning_summary 中清楚說明你的觀點與既有觀點的差異

【關於你的意圖宣告】
- 你的 reasoning_summary 和 viewpoint 會被其他 AI 成員看到
- 請簡潔但準確地描述你的判斷、意圖、以及你的切入角度\
"""

SUPERVISOR_DIRECTIVE_PROMPT: str = """\
你可以使用 set_directive action 來控制討論方向：
{"type": "set_directive", "round_type": "focused_discuss", "focus_topic": "話題", "instruction": "指示"}

round_type 選項：
- "open_diverge"：開放發散，讓大家自由提出觀點
- "focused_discuss"：聚焦討論特定話題
- "respond_to"：邀請特定成員回應（需設 invited_speaker，如 "crew_1"）
- "summarize"：摘要回合，請團隊整理討論重點

使用時機：
- 當話題太分散時 → focused_discuss
- 當有成員一直沒發言時 → respond_to + invited_speaker
- 當討論一段時間後需要整理時 → summarize
- 不要每次都發指令，只在需要引導時使用\
"""
