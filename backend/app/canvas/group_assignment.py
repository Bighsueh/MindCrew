"""病根 B：內容便條 group_id 確定性兜底 — Spec 27 (Phase 36)。

接話式模式下 LLM「應該」帶 group_id（同對象同群），但常漏帶，導致便條 fall through
到 region:center、散落不分群。本模組提供**不依賴 LLM** 的確定性兜底：依與既有便條的
CJK 字集相似度，把缺群的內容便條歸到最相似的既有主題群；相似度不足則回傳 None
（寧缺勿濫，避免把不同概念錯併，留給週期整理 / 開新群）。

設計呼應 CLAUDE.md / Spec 27 §4：「同對象聚一起由分群欄位保證，不依賴事後語意聚類」
——本層在「寫入當下」就把分群欄位補齊，是系統側確定性保證，而非靠 LLM 聽話。
"""
from __future__ import annotations

from typing import Any

from app.agents.assess_heuristics import extract_cjk_ngrams

# 保守門檻：CJK 字集 Jaccard ≥ 此值才歸入既有群（比照 dedup 高門檻精神，
# 寧可開新群也不錯併同對象的不同概念）。
_BACKFILL_SIMILARITY = 0.5


def _charset_jaccard(a: str, b: str) -> float:
    """CJK 單字集合 Jaccard，對短概念便條的同主題判定較穩健（與 dedup 同一原語）。"""
    sa = extract_cjk_ngrams(a, n=1)
    sb = extract_cjk_ngrams(b, n=1)
    if not sa or not sb:
        return 0.0
    union = len(sa | sb)
    return len(sa & sb) / union if union else 0.0


def assign_group_id(
    text: str,
    notes: list[Any],
    *,
    min_similarity: float = _BACKFILL_SIMILARITY,
) -> str | None:
    """為缺 group_id 的內容便條確定性挑一個既有主題群；無夠相似群 → None。

    對每張既有、帶群、非標籤的便條，計算「新文字 對 該便條」的 CJK 字集相似度；
    取分數最高者所屬的群，且須 ≥ ``min_similarity`` 才採用（否則回 None）。

    純函式、不需 LLM / DB；``notes`` 元素需有 ``text`` / ``concept_group_id`` /
    ``kind`` 屬性（SpatialNote 即符合）。
    """
    if not text:
        return None
    best_group: str | None = None
    best_score = 0.0
    for n in notes:
        if getattr(n, "kind", "content") == "label":
            continue
        gid = getattr(n, "concept_group_id", None)
        if not gid:
            continue
        score = _charset_jaccard(text, getattr(n, "text", "") or "")
        if score > best_score:
            best_score = score
            best_group = gid
    return best_group if best_score >= min_similarity else None
