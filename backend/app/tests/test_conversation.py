"""Tests for conversation state tracking and health analysis."""
from __future__ import annotations

import pytest

from app.agents.conversation_state import (
    _compute_topic_overlap,
    _detect_addressee,
    _extract_cjk_ngrams,
    _extract_topic_summary,
)
from app.agents.conversation_health import (
    ConversationHealthAnalyzer,
    _count_topic_clusters,
    _has_agreement_only,
    _compute_gini,
)


# ===================================================================
# Conversation State — n-gram extraction
# ===================================================================


class TestNgramExtraction:
    def test_basic_cjk_ngrams(self) -> None:
        text = "使用者痛點分析"  # 7 CJK chars → 7-3+1 = 5 trigrams
        ngrams = _extract_cjk_ngrams(text, n=3)
        assert "使用者" in ngrams
        assert "用者痛" in ngrams
        assert len(ngrams) == 5

    def test_short_text_returns_whole_as_single_entry(self) -> None:
        ngrams = _extract_cjk_ngrams("好", n=3)
        assert ngrams == {"好"}  # Single char returned as-is

    def test_no_cjk_returns_empty(self) -> None:
        assert _extract_cjk_ngrams("hello world", n=3) == set()

    def test_mixed_text_ignores_non_cjk(self) -> None:
        ngrams = _extract_cjk_ngrams("hello使用者world", n=3)
        assert "使用者" in ngrams

    def test_empty_text(self) -> None:
        assert _extract_cjk_ngrams("") == set()


class TestTopicOverlap:
    def test_identical_sets(self) -> None:
        a = {"使用者", "用者痛", "者痛點"}
        assert _compute_topic_overlap(a, a) == 1.0

    def test_no_overlap(self) -> None:
        a = {"使用者", "用者痛"}
        b = {"設計思", "計思考"}
        assert _compute_topic_overlap(a, b) == 0.0

    def test_partial_overlap(self) -> None:
        a = {"使用者", "用者痛", "者痛點"}
        b = {"使用者", "用者需", "者需求"}
        overlap = _compute_topic_overlap(a, b)
        assert 0.0 < overlap < 1.0

    def test_empty_sets(self) -> None:
        assert _compute_topic_overlap(set(), {"abc"}) == 0.0


class TestAddresseeDetection:
    def test_at_mention(self) -> None:
        seats = ["crew_1", "crew_2", "supervisor"]
        result = _detect_addressee("@crew_2 你覺得呢？", seats)
        assert result == "crew_2"

    def test_name_with_question(self) -> None:
        seats = ["crew_1", "crew_2"]
        result = _detect_addressee("crew_1 你怎麼看？", seats)
        assert result == "crew_1"

    def test_no_addressee(self) -> None:
        seats = ["crew_1", "crew_2"]
        result = _detect_addressee("我覺得這個想法很好", seats)
        assert result is None

    def test_comma_addressing(self) -> None:
        seats = ["crew_1", "crew_3"]
        result = _detect_addressee("crew_3，你有什麼不同的想法嗎", seats)
        assert result == "crew_3"


class TestTopicSummary:
    def test_removes_filler(self) -> None:
        summary = _extract_topic_summary("我同意使用者的搜尋體驗很差")
        assert not summary.startswith("我同意")

    def test_truncates_long_text(self) -> None:
        summary = _extract_topic_summary("A" * 50, max_len=20)
        assert len(summary) <= 21  # 20 + "…"


# ===================================================================
# Conversation Health — analysis
# ===================================================================


class TestAgreementDetection:
    def test_short_agreement(self) -> None:
        assert _has_agreement_only("同意") is True
        assert _has_agreement_only("對，沒錯") is True

    def test_agreement_with_substance(self) -> None:
        # Long message (>=40 chars) with agreement + new content should NOT be agreement-only
        long_msg = "同意，不過我覺得我們還需要考慮使用者在不同裝置上的體驗差異，這個面向值得特別關注和深入討論"
        assert len(long_msg) >= 40
        assert _has_agreement_only(long_msg) is False

    def test_no_agreement(self) -> None:
        assert _has_agreement_only("我覺得搜尋速度是最大的問題") is False


class TestTopicClustering:
    def test_single_message(self) -> None:
        msgs = [{"content": "使用者痛點分析"}]
        assert _count_topic_clusters(msgs) == 1

    def test_similar_messages_one_cluster(self) -> None:
        msgs = [
            {"content": "使用者在搜尋時遇到速度慢的問題"},
            {"content": "搜尋速度慢讓使用者放棄"},
        ]
        clusters = _count_topic_clusters(msgs)
        assert clusters <= 2

    def test_diverse_messages_multiple_clusters(self) -> None:
        msgs = [
            {"content": "使用者在搜尋時遇到速度慢的問題"},
            {"content": "介面設計不友善導致操作困難"},
            {"content": "配送速度太慢影響體驗"},
            {"content": "客服態度差讓人失望"},
        ]
        clusters = _count_topic_clusters(msgs)
        assert clusters >= 2


class TestGiniCoefficient:
    def test_perfect_equality(self) -> None:
        assert _compute_gini([5, 5, 5, 5]) == pytest.approx(0.0, abs=0.05)

    def test_high_inequality(self) -> None:
        gini = _compute_gini([10, 0, 0, 0])
        assert gini >= 0.5

    def test_empty(self) -> None:
        assert _compute_gini([]) == 0.0


class TestConversationHealthAnalyzer:
    def test_not_enough_data(self) -> None:
        analyzer = ConversationHealthAnalyzer()
        report = analyzer.analyze(
            [{"content": "hi", "sender": "a"}],
            None,
            ["crew_1", "crew_2"],
        )
        assert report.issues == []

    def test_over_convergence_requires_persistence(self) -> None:
        analyzer = ConversationHealthAnalyzer()
        msgs = [
            {"content": "同意", "sender": f"crew_{i % 4 + 1}"}
            for i in range(10)
        ]
        # First call — detected but not persistent yet
        report = analyzer.analyze(msgs, None, ["crew_1", "crew_2", "crew_3", "crew_4"])
        assert not report.over_convergence

        # 2nd and 3rd calls — persistence builds
        analyzer.analyze(msgs, None, ["crew_1", "crew_2", "crew_3", "crew_4"])
        report = analyzer.analyze(msgs, None, ["crew_1", "crew_2", "crew_3", "crew_4"])
        assert report.over_convergence
        assert any("過度收斂" in issue for issue in report.issues)
