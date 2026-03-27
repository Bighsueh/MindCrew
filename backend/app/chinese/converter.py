from __future__ import annotations

import opencc


# Custom overrides applied AFTER OpenCC s2twp conversion.
# Keys are simplified Chinese terms that s2twp might not convert correctly.
_CUSTOM_OVERRIDES: dict[str, str] = {
    "项目": "專案",
    "用户": "使用者",
    "视频": "影片",
    "软件": "軟體",
    "信息": "資訊",
    "数据": "資料",
    "服务器": "伺服器",
    "默认": "預設",
    "链接": "連結",
}


class ChineseConverter:
    """Singleton wrapper around OpenCC s2twp with custom overrides."""

    def __init__(self) -> None:
        self._cc = opencc.OpenCC("s2twp")

    def convert(self, text: str) -> str:
        """Convert simplified Chinese to Traditional Chinese (Taiwan variant).

        Applies OpenCC s2twp first, then applies custom term overrides.
        """
        result = self._cc.convert(text)
        for simplified, traditional in _CUSTOM_OVERRIDES.items():
            result = result.replace(simplified, traditional)
        return result


# Module-level singleton.
chinese_converter = ChineseConverter()
