"""共用文字度量（Phase 42 A2）。

`meaningful_char_count` 原為 `progression/watcher.py` 私有；A2 抽出共用——
watcher（暖場參與閘）、human_input_check（tier-1 實質檢核）、signal_panel
（真人參與面板）統一引用同一份計法，避免口徑漂移與「import watcher 私有」技術債。

純函式、零 app 相依——任何模組 import 皆不致循環。
"""

from __future__ import annotations


def meaningful_char_count(text: str | None) -> int:
    """有意義字元數（CJK 統一表意 + 英數）；emoji / 標點 / 空白不計。

    沿用既有口徑：``str.isalnum()`` 對 CJK 與英數皆為 True、對 emoji / 標點 /
    空白為 False。
    """
    if not text:
        return 0
    return sum(1 for ch in text if ch.isalnum())
