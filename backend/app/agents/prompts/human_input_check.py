"""人類輸入實質檢核的 prompt 與退回話術（Phase 42 A2，spec 20 v2.0 §12）。

兩類字串，皆收錄於 spec 04-03 §3.0.6（A1 §3.0.5 慣例）：
1. tier-2 LLM 語意判準（內部 prompt，按 sub_phase 注入；spec 20 §12.3 表）。
2. `input_bounced` 的退回原因／教練式提示（**使用者可見**——大白話、無 emoji、
   不講內部機制名 #29，並給一個例子，spec 20 §12.5）。
"""

from __future__ import annotations

# ── tier-2 判準（spec 20 §12.3）：這則輸入是否為……─────────────────────────
_TIER2_CRITERIA: dict[str, str] = {
    "0.0a": "一個具體的替代用途（例：『衣架可以掰直通水管』這種能想像得到的用法）",
    "1.1a": "一段具體的自身經驗（真的發生過的情境，不是空泛附和）",
    "1.1b": "一個利害關係人的名字，或跟某個利害關係人有關的具體理由",
    "1.2": "一個具體的情境加上其中的卡點（誰、在什麼時候、卡在哪）",
    "2.2": "朝『某使用者需要某需求，因為某洞察』方向的內容（接近問題定義）",
}
_TIER2_DEFAULT = "對當前任務的實質貢獻（接話、表態、給理由），而不是單純附和"

_TIER2_SYSTEM = (
    "你是設計思考討論的內容判讀員。只判斷『這則使用者輸入是否算實質參與』，"
    "寬鬆從寬：只要看得出是認真在想、有具體內容，就算通過。空泛附和、敷衍、"
    "答非所問才算不通過。只回 JSON。"
)


def tier2_judge_messages(text: str, sub_phase: str) -> list[dict]:
    """組 tier-2 判準 messages（送 LLMService.chat_completion）。"""
    criterion = _TIER2_CRITERIA.get(sub_phase, _TIER2_DEFAULT)
    user = (
        f"判準：這則輸入是否為「{criterion}」？\n\n"
        f"使用者輸入：\n\"\"\"\n{text}\n\"\"\"\n\n"
        '回 JSON：{"substantive": true | false, "reason": "一句話說明"}'
    )
    return [
        {"role": "system", "content": _TIER2_SYSTEM},
        {"role": "user", "content": user},
    ]


# ── 退回話術（使用者可見，spec 20 §12.5）────────────────────────────────────
# (reason_zh, hint_zh)：reason 說「這樣還不夠」，hint 說「怎樣才算」並給一個例子。
_BOUNCE: dict[str, tuple[str, str]] = {
    "0.0a": (
        "這還不太算一個點子喔！",
        "請說一個具體的替代用途，例如：衣架可以掰直拿來通水管。",
    ),
    "1.1a": (
        "可以再多講一點你的經驗喔！",
        "說一個你真的遇過的情況，例如：上次我趕時間結帳，排了很久的隊。",
    ),
    "1.1b": (
        "這邊想請你想一個跟這件事有關的人。",
        "說一個會用到或會受影響的角色就好，例如：常來的老客人、外送員。",
    ),
    "1.2": (
        "可以再具體一點喔！",
        "說一個情境加上卡住的地方，例如：媽媽下班買菜時，雙手提滿很難再拿手機付款。",
    ),
    "2.2": (
        "再往問題的方向多講一點喔！",
        "試著說某個人需要什麼、為什麼，例如：忙碌的上班族需要更快結帳，因為他們時間很趕。",
    ),
}
_BOUNCE_DEFAULT = (
    "可以再多說一點你的想法喔！",
    "試著講出具體的看法、疑問或理由，不只是『好』或『可以』。",
)


def bounce_text(sub_phase: str) -> tuple[str, str]:
    """回 (reason_zh, hint_zh)。"""
    return _BOUNCE.get(sub_phase, _BOUNCE_DEFAULT)
