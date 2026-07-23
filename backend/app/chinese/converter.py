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

# 本就是正確台灣用語、但 s2twp 的 TWPhrases 會誤改的片語——轉換前以哨兵護住、轉換後還原。
# 「打開」→「開啟」會把 canonical 標題便條固定文案「發現階段｜把問題打開、先不做決定」
# 改字、並產生「腦袋有開啟」這種不像人話的措辭（Phase 42 B2 live 驗收抓到）。
# 注意：不能用事後 replace（開啟→打開）——會誤傷正當的「開啟」用法。
_PROTECTED_PHRASES: tuple[str, ...] = ("打開",)
# Unicode 私用區字元，LLM 輸出不會出現。
_SENTINEL_TMPL = "{}"


class ChineseConverter:
    """Singleton wrapper around OpenCC s2twp with custom overrides."""

    def __init__(self) -> None:
        self._cc = opencc.OpenCC("s2twp")

    def convert(self, text: str) -> str:
        """Convert simplified Chinese to Traditional Chinese (Taiwan variant).

        Protects already-correct phrases, applies OpenCC s2twp, restores
        protected phrases, then applies custom term overrides.
        """
        for i, phrase in enumerate(_PROTECTED_PHRASES):
            text = text.replace(phrase, _SENTINEL_TMPL.format(i))
        result = self._cc.convert(text)
        for i, phrase in enumerate(_PROTECTED_PHRASES):
            result = result.replace(_SENTINEL_TMPL.format(i), phrase)
        for simplified, traditional in _CUSTOM_OVERRIDES.items():
            result = result.replace(simplified, traditional)
        return result


# Module-level singleton.
chinese_converter = ChineseConverter()
