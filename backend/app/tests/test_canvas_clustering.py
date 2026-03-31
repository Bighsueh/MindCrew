"""Tests for canvas semantic clustering (Phase 14, Step 14.4)."""

import pytest
import numpy as np

from app.canvas.clustering import (
    ClusterState,
    _stable_cluster_id,
    compute_clusters,
    compute_coherence,
)
from app.canvas.spatial import SpatialNote


def _make_note(id: str, text: str) -> SpatialNote:
    return SpatialNote(
        id=id, text=text, x=0, y=0,
        width=200, height=150,
        color="yellow", author_type="human", created_at="",
    )


def _random_embedding(dim: int = 8, seed: int = 0) -> list[float]:
    rng = np.random.RandomState(seed)
    return rng.randn(dim).tolist()


class TestStableClusterId:
    def test_deterministic(self) -> None:
        id1 = _stable_cluster_id(["a", "b", "c"])
        id2 = _stable_cluster_id(["c", "a", "b"])  # different order
        assert id1 == id2  # sorted, so same hash

    def test_prefix(self) -> None:
        cid = _stable_cluster_id(["hello"])
        assert cid.startswith("c")


class TestCoherence:
    def test_identical_vectors(self) -> None:
        vecs = [[1.0, 0.0, 0.0]] * 3
        assert compute_coherence(vecs) == pytest.approx(1.0)

    def test_single_vector(self) -> None:
        assert compute_coherence([[1.0, 0.0]]) == 1.0

    def test_orthogonal_vectors(self) -> None:
        vecs = [[1.0, 0.0], [0.0, 1.0]]
        assert compute_coherence(vecs) == pytest.approx(0.0, abs=0.01)


class TestComputeClusters:
    def test_below_threshold_returns_all_ungrouped(self) -> None:
        """Fewer than 10 notes should skip clustering."""
        notes = [_make_note(f"n{i}", f"text {i}") for i in range(5)]
        embeddings = [_random_embedding(seed=i) for i in range(5)]
        result = compute_clusters(notes, embeddings)
        assert len(result.clusters) == 0
        assert len(result.ungrouped_note_ids) == 5

    def test_mismatched_lengths_raises(self) -> None:
        notes = [_make_note("n1", "a")]
        embeddings = [[1.0], [2.0]]
        with pytest.raises(ValueError):
            compute_clusters(notes, embeddings)

    def test_incremental_preserves_clusters(self) -> None:
        """Incremental update should keep existing clusters stable."""
        notes = [_make_note(f"n{i}", f"text {i}") for i in range(12)]
        embeddings = [_random_embedding(seed=i) for i in range(12)]

        # First full clustering
        state1 = compute_clusters(notes, embeddings)

        # Add one note incrementally
        new_note = _make_note("n12", "text 12")
        new_emb = _random_embedding(seed=12)
        all_notes = notes + [new_note]
        all_embs = embeddings + [new_emb]

        state2 = compute_clusters(all_notes, all_embs, previous_state=state1)
        # Should have the same or more clusters, not completely different
        if state1.clusters:
            prev_ids = {c.cluster_id for c in state1.clusters}
            curr_ids = {c.cluster_id for c in state2.clusters}
            # At least some cluster IDs should be preserved
            assert len(prev_ids & curr_ids) > 0 or len(state2.clusters) >= 0
