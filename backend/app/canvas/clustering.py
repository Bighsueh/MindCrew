"""Semantic clustering of sticky notes using HDBSCAN.

Provides stable cluster IDs via content hashing, incremental updates,
and LLM-generated cluster labels.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.canvas.spatial import SpatialNote

logger = logging.getLogger(__name__)

# Minimum notes required for clustering (below this, skip HDBSCAN)
MIN_NOTES_FOR_CLUSTERING = 10

# HDBSCAN parameters
HDBSCAN_MIN_CLUSTER_SIZE = 3
HDBSCAN_MIN_SAMPLES = 2

# Similarity threshold for incremental assignment to existing cluster
INCREMENTAL_SIMILARITY_THRESHOLD = 0.6


@dataclass
class ClusterResult:
    """A single semantic cluster of notes."""

    cluster_id: str
    note_ids: list[str]
    centroid: list[float]  # mean embedding vector
    suggested_label: str = ""
    coherence_score: float = 0.0


@dataclass
class ClusterState:
    """Full clustering state for a project, cacheable."""

    clusters: list[ClusterResult] = field(default_factory=list)
    ungrouped_note_ids: list[str] = field(default_factory=list)
    version_hash: str = ""


def _stable_cluster_id(note_texts: list[str]) -> str:
    """Generate a stable cluster ID from sorted content hash."""
    combined = "|".join(sorted(note_texts))
    h = hashlib.sha256(combined.encode()).hexdigest()[:8]
    return f"c{h}"


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def compute_coherence(embeddings: list[list[float]]) -> float:
    """Mean pairwise cosine similarity within a cluster."""
    if len(embeddings) < 2:
        return 1.0
    vecs = np.array(embeddings)
    total = 0.0
    count = 0
    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            total += _cosine_similarity(vecs[i], vecs[j])
            count += 1
    return total / count if count > 0 else 1.0


def compute_clusters(
    notes: list[SpatialNote],
    embeddings: list[list[float]],
    previous_state: ClusterState | None = None,
) -> ClusterState:
    """Cluster notes by semantic similarity.

    If fewer than MIN_NOTES_FOR_CLUSTERING notes, returns all as ungrouped.
    Uses HDBSCAN when enough data is available, with incremental update
    support via previous_state.
    """
    if len(notes) != len(embeddings):
        raise ValueError("notes and embeddings must have same length")

    note_map = {n.id: (n, emb) for n, emb in zip(notes, embeddings)}

    if len(notes) < MIN_NOTES_FOR_CLUSTERING:
        return ClusterState(
            clusters=[],
            ungrouped_note_ids=[n.id for n in notes],
            version_hash=_stable_cluster_id([n.text for n in notes]),
        )

    # If we have a previous state, try incremental assignment first
    if previous_state and previous_state.clusters:
        return _incremental_update(notes, embeddings, previous_state, note_map)

    # Full HDBSCAN clustering
    return _full_clustering(notes, embeddings, note_map)


def _full_clustering(
    notes: list[SpatialNote],
    embeddings: list[list[float]],
    note_map: dict[str, tuple[SpatialNote, list[float]]],
) -> ClusterState:
    """Run HDBSCAN from scratch."""
    try:
        import hdbscan
    except ImportError:
        logger.warning("hdbscan not installed, returning all notes as ungrouped")
        return ClusterState(
            clusters=[],
            ungrouped_note_ids=[n.id for n in notes],
        )

    vecs = np.array(embeddings)
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,
        min_samples=HDBSCAN_MIN_SAMPLES,
        metric="euclidean",
    )
    labels = clusterer.fit_predict(vecs)

    # Group by label
    label_groups: dict[int, list[int]] = {}
    ungrouped_indices: list[int] = []
    for idx, label in enumerate(labels):
        if label == -1:
            ungrouped_indices.append(idx)
        else:
            label_groups.setdefault(label, []).append(idx)

    clusters: list[ClusterResult] = []
    for _label, indices in sorted(label_groups.items()):
        member_notes = [notes[i] for i in indices]
        member_embeddings = [embeddings[i] for i in indices]
        cluster_id = _stable_cluster_id([n.text for n in member_notes])
        centroid = np.mean(member_embeddings, axis=0).tolist()
        coherence = compute_coherence(member_embeddings)

        clusters.append(ClusterResult(
            cluster_id=cluster_id,
            note_ids=[n.id for n in member_notes],
            centroid=centroid,
            coherence_score=round(coherence, 2),
        ))

    ungrouped_ids = [notes[i].id for i in ungrouped_indices]
    version_hash = _stable_cluster_id([n.text for n in notes])

    return ClusterState(
        clusters=clusters,
        ungrouped_note_ids=ungrouped_ids,
        version_hash=version_hash,
    )


def _incremental_update(
    notes: list[SpatialNote],
    embeddings: list[list[float]],
    prev: ClusterState,
    note_map: dict[str, tuple[SpatialNote, list[float]]],
) -> ClusterState:
    """Assign new notes to existing clusters; keep clusters stable."""
    prev_assigned: set[str] = set()
    for c in prev.clusters:
        prev_assigned.update(c.note_ids)

    new_notes = [(n, emb) for n, emb in zip(notes, embeddings) if n.id not in prev_assigned]
    removed_ids = prev_assigned - {n.id for n in notes}

    # Start with existing clusters, removing notes that no longer exist
    clusters: list[ClusterResult] = []
    for prev_c in prev.clusters:
        surviving = [nid for nid in prev_c.note_ids if nid not in removed_ids]
        if not surviving:
            continue
        clusters.append(ClusterResult(
            cluster_id=prev_c.cluster_id,
            note_ids=surviving,
            centroid=prev_c.centroid,
            suggested_label=prev_c.suggested_label,
            coherence_score=prev_c.coherence_score,
        ))

    # Assign new notes to nearest cluster or leave ungrouped
    ungrouped_ids = [
        nid for nid in prev.ungrouped_note_ids
        if nid not in removed_ids and nid in {n.id for n in notes}
    ]

    for note, emb in new_notes:
        best_sim = -1.0
        best_cluster_idx = -1
        emb_arr = np.array(emb)

        for ci, c in enumerate(clusters):
            sim = _cosine_similarity(emb_arr, np.array(c.centroid))
            if sim > best_sim:
                best_sim = sim
                best_cluster_idx = ci

        if best_sim >= INCREMENTAL_SIMILARITY_THRESHOLD and best_cluster_idx >= 0:
            clusters[best_cluster_idx].note_ids.append(note.id)
            # Update centroid
            member_embs = [
                note_map[nid][1]
                for nid in clusters[best_cluster_idx].note_ids
                if nid in note_map
            ]
            if member_embs:
                clusters[best_cluster_idx].centroid = np.mean(member_embs, axis=0).tolist()
        else:
            ungrouped_ids.append(note.id)

    # Recompute coherence for modified clusters
    for c in clusters:
        member_embs = [note_map[nid][1] for nid in c.note_ids if nid in note_map]
        if member_embs:
            c.coherence_score = round(compute_coherence(member_embs), 2)

    version_hash = _stable_cluster_id([n.text for n in notes])
    return ClusterState(
        clusters=clusters,
        ungrouped_note_ids=ungrouped_ids,
        version_hash=version_hash,
    )


async def generate_cluster_labels(
    clusters: list[ClusterResult],
    notes_by_id: dict[str, SpatialNote],
    llm_call: Any,
) -> dict[str, str]:
    """Generate 2-6 word Chinese labels for each cluster via LLM.

    Args:
        clusters: Cluster results to label.
        notes_by_id: Mapping of note ID to SpatialNote for text lookup.
        llm_call: Async callable(messages, max_tokens) -> str.
            Typically wraps LLMProviderFactory.

    Returns:
        Mapping of cluster_id → suggested_label.
    """
    from app.chinese.converter import chinese_converter

    labels: dict[str, str] = {}

    for cluster in clusters:
        texts = [
            notes_by_id[nid].text
            for nid in cluster.note_ids
            if nid in notes_by_id
        ]
        if not texts:
            continue

        text_list = "\n".join(f"- {t}" for t in texts[:10])  # cap at 10
        prompt = (
            "以下是設計思考工作坊中一組語意相近的便條紙內容：\n\n"
            f"{text_list}\n\n"
            "請用 2-6 個繁體中文字為這組便條紙命名一個主題標籤。"
            "只回覆標籤本身，不要任何解釋。"
        )

        try:
            messages = [{"role": "user", "content": prompt}]
            raw_label = await llm_call(messages, max_tokens=32)
            label = chinese_converter.convert(raw_label.strip().strip('"').strip("'"))
            labels[cluster.cluster_id] = label
        except Exception:
            logger.warning("Failed to generate label for cluster %s", cluster.cluster_id)
            labels[cluster.cluster_id] = f"叢集 {cluster.cluster_id}"

    return labels
