"""Conversation health analyzer for Supervisor agents.

Rule-based (no LLM calls). Detects:
- Over-convergence: everyone agreeing without new ideas
- Over-divergence: topics scattering without depth
- Topic staleness: same topic too long without progress
- Participation imbalance: some agents dominating
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Agreement markers in Chinese
_AGREEMENT_MARKERS = ("同意", "對", "沒錯", "好的", "贊成", "附和", "也覺得", "我也是")

# Thresholds
_OVER_CONVERGENCE_RATIO = 0.6   # > 60% agreement messages
_OVER_DIVERGENCE_MIN_CLUSTERS = 4  # ≥ 4 topic clusters
_STALE_TURN_COUNT = 8  # > 8 turns without new note
_IMBALANCE_THRESHOLD = 0.55  # Gini > 0.55

# Persist count before injecting warning into Supervisor prompt
_PERSIST_CYCLES = 3


@dataclass
class ConversationHealthReport:
    over_convergence: bool = False
    over_divergence: bool = False
    topic_stale: bool = False
    participation_imbalance: bool = False
    quiet_agents: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    suggestion: str = ""


def _has_agreement_only(content: str) -> bool:
    """Check if a message is primarily agreement without new content."""
    content_lower = content.lower()
    has_agreement = any(m in content_lower for m in _AGREEMENT_MARKERS)
    # If the message is short (< 30 chars) and contains agreement marker, likely pure agreement
    if has_agreement and len(content) < 40:
        return True
    return False


def _extract_ngrams(text: str, n: int = 3) -> set[str]:
    """Extract CJK n-grams."""
    cjk = "".join(c for c in text if "\u4e00" <= c <= "\u9fff")
    if len(cjk) < n:
        return set()
    return {cjk[i : i + n] for i in range(len(cjk) - n + 1)}


def _count_topic_clusters(messages: list[dict], min_overlap: float = 0.25) -> int:
    """Count distinct topic clusters using n-gram similarity."""
    if len(messages) < 2:
        return len(messages)

    ngram_sets = [
        _extract_ngrams(m.get("content", ""))
        for m in messages
    ]
    # Simple greedy clustering
    clusters: list[set[str]] = []
    for ngs in ngram_sets:
        if not ngs:
            continue
        merged = False
        for cluster in clusters:
            overlap = len(ngs & cluster) / min(len(ngs), len(cluster)) if min(len(ngs), len(cluster)) > 0 else 0
            if overlap >= min_overlap:
                cluster.update(ngs)
                merged = True
                break
        if not merged:
            clusters.append(set(ngs))
    return max(len(clusters), 1)


def _compute_gini(counts: list[int]) -> float:
    """Compute Gini coefficient for participation balance (0=equal, 1=unequal)."""
    if not counts or sum(counts) == 0:
        return 0.0
    n = len(counts)
    sorted_counts = sorted(counts)
    total = sum(sorted_counts)
    numerator = sum((2 * (i + 1) - n - 1) * c for i, c in enumerate(sorted_counts))
    return numerator / (n * total)


class ConversationHealthAnalyzer:
    """Analyzes conversation health from recent chat messages."""

    def __init__(self) -> None:
        self._issue_persistence: dict[str, int] = {}

    def analyze(
        self,
        recent_chat: list[dict],
        active_thread: dict | None,
        all_seat_roles: list[str],
    ) -> ConversationHealthReport:
        """Analyze conversation health. Returns report with issues that have persisted."""
        report = ConversationHealthReport()

        if len(recent_chat) < 5:
            return report  # Not enough data

        last_10 = recent_chat[-10:]

        # 1. Over-convergence: too many agreement-only messages
        agreement_count = sum(1 for m in last_10 if _has_agreement_only(m.get("content", "")))
        convergence_ratio = agreement_count / len(last_10)
        if convergence_ratio > _OVER_CONVERGENCE_RATIO:
            self._tick("over_convergence")
            if self._is_persistent("over_convergence"):
                report.over_convergence = True
                report.issues.append(
                    f"過度收斂：最近 {agreement_count}/{len(last_10)} 則都在附和，缺乏新觀點"
                )
        else:
            self._reset("over_convergence")

        # 2. Over-divergence: too many distinct topic clusters
        cluster_count = _count_topic_clusters(last_10)
        avg_per_cluster = len(last_10) / cluster_count if cluster_count > 0 else 0
        if cluster_count >= _OVER_DIVERGENCE_MIN_CLUSTERS and avg_per_cluster < 2.5:
            self._tick("over_divergence")
            if self._is_persistent("over_divergence"):
                report.over_divergence = True
                report.issues.append(
                    f"過度發散：最近討論分散在 {cluster_count} 個話題，每個都不深入"
                )
        else:
            self._reset("over_divergence")

        # 3. Topic staleness
        if active_thread:
            turn_count = active_thread.get("turn_count", 0)
            if turn_count > _STALE_TURN_COUNT:
                self._tick("topic_stale")
                if self._is_persistent("topic_stale"):
                    topic = active_thread.get("topic_summary", "")
                    report.topic_stale = True
                    report.issues.append(
                        f"話題停滯：「{topic}」已討論 {turn_count} 輪，建議換個方向"
                    )
            else:
                self._reset("topic_stale")

        # 4. Participation imbalance
        last_20 = recent_chat[-20:]
        sender_counts = Counter(m.get("sender", "") for m in last_20)
        # Only count agent seats (exclude system messages)
        agent_counts = []
        quiet = []
        for seat in all_seat_roles:
            count = sum(v for k, v in sender_counts.items() if seat.lower() in k.lower())
            agent_counts.append(count)
            if count == 0:
                quiet.append(seat)

        if len(agent_counts) >= 3:
            gini = _compute_gini(agent_counts)
            if gini > _IMBALANCE_THRESHOLD:
                self._tick("imbalance")
                if self._is_persistent("imbalance"):
                    report.participation_imbalance = True
                    report.quiet_agents = quiet
                    if quiet:
                        report.issues.append(
                            f"參與不均：{', '.join(quiet)} 已經很久沒發言"
                        )
            else:
                self._reset("imbalance")

        # Generate suggestion
        if report.issues:
            if report.over_convergence:
                report.suggestion = "挑戰現有共識，邀請沉默成員提出不同看法"
            elif report.over_divergence:
                report.suggestion = "選擇一個主題聚焦深入，暫時擱置其他方向"
            elif report.topic_stale:
                report.suggestion = "總結目前觀點，引導轉向新的面向"
            elif report.participation_imbalance and report.quiet_agents:
                report.suggestion = f"邀請 {report.quiet_agents[0]} 發言"

        return report

    def _tick(self, key: str) -> None:
        self._issue_persistence[key] = self._issue_persistence.get(key, 0) + 1

    def _reset(self, key: str) -> None:
        self._issue_persistence.pop(key, None)

    def _is_persistent(self, key: str) -> bool:
        return self._issue_persistence.get(key, 0) >= _PERSIST_CYCLES

    def get_health_context(
        self,
        recent_chat: list[dict],
        active_thread: dict | None,
        all_seat_roles: list[str],
    ) -> dict | None:
        """Analyze and return health context for injection into Supervisor prompt."""
        report = self.analyze(recent_chat, active_thread, all_seat_roles)
        if not report.issues:
            return None
        return {
            "issues": report.issues,
            "suggestion": report.suggestion,
        }
