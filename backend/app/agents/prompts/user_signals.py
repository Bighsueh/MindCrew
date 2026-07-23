"""便條指認高亮 prompt（Phase 42 A3，WP7，#34）。

Prompt 全文 canonical 收錄於 specs/04-03-prompts-base.md §3.0.7（v4.25）；
注入條件：supervisor 恆注入（assembler.py，比照 §3.0.5 推進迴路），crew 不注入。
"""

SUPERVISOR_NOTE_HIGHLIGHT_PROMPT = """\
【指便條給使用者看】
指便條給使用者看的時候，不要用顏色講（「藍色那張」認不出來——便條顏色是每個人的
身分色）。改用兩件事一起做：
1. 在聊天用內容或作者描述那幾張便條（例：「剛剛陳柏宇貼的那張『常忘記帶袋子的上班族』」）。
2. 同一次回應輸出 {"type": "note_highlight", "note_ids": [...]}，系統會把那幾張便條
   亮起來幾秒，使用者一眼就找得到。
note_ids 用白板狀態裡列出的便條 id；不確定 id 就只用內容描述、不要亂猜。\
"""
