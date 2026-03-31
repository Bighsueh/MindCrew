"""Heuristic helpers for AssessEngine.

These are fallback functions used when LLM is unavailable.
As the system matures, proven heuristics may replace LLM judgments.
"""
from __future__ import annotations


def extract_cjk_ngrams(text: str, n: int = 3) -> set[str]:
    """Extract character n-grams from CJK text."""
    cjk = "".join(c for c in text if "\u4e00" <= c <= "\u9fff")
    if len(cjk) < n:
        return set()
    return {cjk[i : i + n] for i in range(len(cjk) - n + 1)}


def heuristic_topic_overlap(text_a: str, text_b: str) -> bool:
    """Return True if two texts share >= 4 CJK trigrams."""
    ngrams_a = extract_cjk_ngrams(text_a)
    ngrams_b = extract_cjk_ngrams(text_b)
    if not ngrams_a or not ngrams_b:
        return False
    return len(ngrams_a & ngrams_b) >= 4


_STANCE_KEYWORDS: tuple[str, ...] = (
    "我覺得", "我認為", "我建議", "我想", "應該", "可以考慮",
    "不同意", "問題是", "關鍵是", "重點是", "值得", "必須",
)


def heuristic_has_stance(candidates: list[str]) -> bool:
    """Return True if any candidate text has CJK >= 20 chars + stance keyword."""
    for content in candidates:
        cjk_chars = sum(1 for c in content if "\u4e00" <= c <= "\u9fff")
        if cjk_chars >= 20 and any(kw in content for kw in _STANCE_KEYWORDS):
            return True
    return False


def has_relevant_event_ngram(context: dict) -> bool:
    """Return True if latest chat shares n-gram overlap with my recent action."""
    my_actions: list[dict] = context.get("my_recent_actions", [])
    if not my_actions:
        return False
    recent_chat: list[dict] = context.get("recent_chat", [])
    if not recent_chat:
        return False

    last_action = my_actions[-1]
    my_content: str = last_action.get("content", "")
    if not my_content:
        return False

    last_chat_content = recent_chat[-1].get("content", "")

    my_ngrams = extract_cjk_ngrams(my_content)
    chat_ngrams = extract_cjk_ngrams(last_chat_content)

    if len(my_ngrams) < 2 or len(chat_ngrams) < 2:
        return False

    overlap = my_ngrams & chat_ngrams
    return len(overlap) >= 2
