"""Spatial Analyzer: orchestrates spatial + semantic analysis with Redis caching.

Main entry point for the Canvas Perception layer (Layer 2).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis

from app.canvas.clustering import (
    ClusterResult,
    ClusterState,
    compute_clusters,
    generate_cluster_labels,
)
from app.canvas.embedding_client import get_embedding_client
from app.canvas.spatial import (
    SpatialNote,
    assign_region,
    compute_board_bounds,
    compute_orderliness,
    detect_overlaps,
    find_free_regions,
)
from app.config import settings

logger = logging.getLogger(__name__)

# Cache TTL for semantic layer (embeddings + clusters + labels)
SEMANTIC_CACHE_TTL = 60  # seconds

# Redis key patterns
_SEMANTIC_KEY = "canvas:{project_id}:semantic"
_PREV_CLUSTER_KEY = "canvas:{project_id}:prev_clusters"


@dataclass
class CanvasAnalysis:
    """Complete analysis result for a project's canvas."""

    notes: list[SpatialNote] = field(default_factory=list)
    cluster_state: ClusterState = field(default_factory=ClusterState)
    cluster_labels: dict[str, str] = field(default_factory=dict)
    orderliness_score: float = 1.0
    overlap_pairs: list[tuple[str, str]] = field(default_factory=list)
    board_bounds: dict[str, Any] = field(default_factory=dict)
    free_regions: list[str] = field(default_factory=list)
    largest_cluster_ratio: float = 0.0
    cross_cluster_max_similarity: float = 0.0


class SpatialAnalyzer:
    """Orchestrates spatial + semantic analysis pipeline."""

    def __init__(self) -> None:
        self._embedding_client = get_embedding_client()

    async def get_full_state(self, project_id: UUID) -> list[SpatialNote]:
        """Fetch full geometry from sidecar canvas-state/full endpoint."""
        import httpx

        url = f"{settings.SIDECAR_URL}/api/projects/{project_id}/canvas-state/full"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning("Sidecar canvas-state/full returned %d", resp.status_code)
                    return []
                shapes = resp.json()
        except Exception:
            logger.exception("Failed to fetch canvas-state/full from sidecar")
            return []

        return [
            SpatialNote(
                id=s["id"],
                text=s.get("content", ""),
                x=s.get("x", 0),
                y=s.get("y", 0),
                width=s.get("width", 200),
                height=s.get("height", 150),
                color=s.get("color", "yellow"),
                author_type="human" if "human" in s.get("author", "") else "ai",
                created_at=s.get("createdAt", ""),
                group_id=s.get("groupId"),
            )
            for s in shapes
        ]

    async def analyze(self, project_id: UUID) -> CanvasAnalysis:
        """Main analysis entry point. Uses Redis cache for semantic layer."""
        notes = await self.get_full_state(project_id)
        if not notes:
            return CanvasAnalysis()

        # Spatial layer: always recompute (no cache)
        overlap_pairs = detect_overlaps(notes)
        board_bounds = compute_board_bounds(notes)
        free_regions = find_free_regions(notes)

        # Semantic layer: check cache first
        cluster_state, cluster_labels = await self._get_semantic_cached(project_id, notes)

        # Orderliness needs cluster info
        cluster_label_map = {}
        for c in cluster_state.clusters:
            for nid in c.note_ids:
                cluster_label_map[nid] = c.cluster_id
        orderliness = compute_orderliness(notes, cluster_label_map)

        # Phase 15: structural quality metrics
        if cluster_state.clusters and notes:
            max_cluster_size = max(len(c.note_ids) for c in cluster_state.clusters)
            largest_cluster_ratio = round(max_cluster_size / len(notes), 2)
        else:
            largest_cluster_ratio = 0.0

        import numpy as np
        cross_sim = 0.0
        centroids = [c.centroid for c in cluster_state.clusters if c.centroid]
        if len(centroids) >= 2:
            for i in range(len(centroids)):
                for j in range(i + 1, len(centroids)):
                    a = np.array(centroids[i])
                    b = np.array(centroids[j])
                    norm_a = np.linalg.norm(a)
                    norm_b = np.linalg.norm(b)
                    if norm_a > 0 and norm_b > 0:
                        sim = float(np.dot(a, b) / (norm_a * norm_b))
                        cross_sim = max(cross_sim, sim)
        cross_cluster_max_similarity = round(cross_sim, 2)

        return CanvasAnalysis(
            notes=notes,
            cluster_state=cluster_state,
            cluster_labels=cluster_labels,
            orderliness_score=round(orderliness, 2),
            overlap_pairs=overlap_pairs,
            board_bounds=board_bounds,
            free_regions=free_regions,
            largest_cluster_ratio=largest_cluster_ratio,
            cross_cluster_max_similarity=cross_cluster_max_similarity,
        )

    async def _get_semantic_cached(
        self,
        project_id: UUID,
        notes: list[SpatialNote],
    ) -> tuple[ClusterState, dict[str, str]]:
        """Try Redis cache for semantic results; compute if miss."""
        cache_key = _SEMANTIC_KEY.format(project_id=project_id)

        try:
            r = aioredis.from_url(settings.REDIS_URL)
            cached = await r.get(cache_key)
            if cached:
                data = json.loads(cached)
                cluster_state = _deserialize_cluster_state(data["cluster_state"])
                labels = data.get("labels", {})
                await r.aclose()
                return cluster_state, labels
        except Exception:
            logger.debug("Redis cache miss or error for %s", cache_key)
            r = None

        # Cache miss: compute
        cluster_state, labels = await self._compute_semantic(project_id, notes)

        # Store in cache
        try:
            if r is None:
                r = aioredis.from_url(settings.REDIS_URL)
            cache_data = json.dumps({
                "cluster_state": _serialize_cluster_state(cluster_state),
                "labels": labels,
            })
            await r.setex(cache_key, SEMANTIC_CACHE_TTL, cache_data)
            await r.aclose()
        except Exception:
            logger.debug("Failed to cache semantic results")

        return cluster_state, labels

    async def _compute_semantic(
        self,
        project_id: UUID,
        notes: list[SpatialNote],
    ) -> tuple[ClusterState, dict[str, str]]:
        """Compute embeddings, clusters, and labels."""
        texts = [n.text for n in notes]

        try:
            embeddings = await self._embedding_client.embed_texts(texts)
        except Exception:
            logger.exception("Embedding failed, returning no clusters")
            return ClusterState(ungrouped_note_ids=[n.id for n in notes]), {}

        # Load previous cluster state for incremental update
        prev_state = await self._load_prev_cluster_state(project_id)

        cluster_state = compute_clusters(notes, embeddings, prev_state)

        # Save cluster state for next incremental update
        await self._save_prev_cluster_state(project_id, cluster_state)

        # Generate labels via LLM
        notes_by_id = {n.id: n for n in notes}
        labels = await self._generate_labels(cluster_state.clusters, notes_by_id)

        # Apply labels to clusters
        for c in cluster_state.clusters:
            if c.cluster_id in labels:
                c.suggested_label = labels[c.cluster_id]

        return cluster_state, labels

    async def _generate_labels(
        self,
        clusters: list[ClusterResult],
        notes_by_id: dict[str, SpatialNote],
    ) -> dict[str, str]:
        """Generate cluster labels using LLM."""
        from app.llm.factory import LLMProviderFactory

        try:
            llm_service = LLMProviderFactory.get_service()
        except Exception:
            logger.warning("LLM service unavailable for cluster labels")
            return {}

        async def llm_call(messages: list[dict], max_tokens: int = 32) -> str:
            response = await llm_service.chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return response.content

        return await generate_cluster_labels(clusters, notes_by_id, llm_call)

    async def _load_prev_cluster_state(self, project_id: UUID) -> ClusterState | None:
        """Load previous cluster state from Redis for incremental updates."""
        key = _PREV_CLUSTER_KEY.format(project_id=project_id)
        try:
            r = aioredis.from_url(settings.REDIS_URL)
            data = await r.get(key)
            await r.aclose()
            if data:
                return _deserialize_cluster_state(json.loads(data))
        except Exception:
            pass
        return None

    async def _save_prev_cluster_state(self, project_id: UUID, state: ClusterState) -> None:
        """Persist cluster state for incremental updates (long TTL)."""
        key = _PREV_CLUSTER_KEY.format(project_id=project_id)
        try:
            r = aioredis.from_url(settings.REDIS_URL)
            await r.setex(key, 600, json.dumps(_serialize_cluster_state(state)))
            await r.aclose()
        except Exception:
            pass

    async def invalidate_semantic_cache(self, project_id: UUID) -> None:
        """Delete semantic cache — called on note add/delete."""
        cache_key = _SEMANTIC_KEY.format(project_id=project_id)
        try:
            r = aioredis.from_url(settings.REDIS_URL)
            await r.delete(cache_key)
            await r.aclose()
        except Exception:
            pass


def _serialize_cluster_state(state: ClusterState) -> dict:
    return {
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "note_ids": c.note_ids,
                "centroid": c.centroid,
                "suggested_label": c.suggested_label,
                "coherence_score": c.coherence_score,
            }
            for c in state.clusters
        ],
        "ungrouped_note_ids": state.ungrouped_note_ids,
        "version_hash": state.version_hash,
    }


def _deserialize_cluster_state(data: dict) -> ClusterState:
    clusters = [
        ClusterResult(
            cluster_id=c["cluster_id"],
            note_ids=c["note_ids"],
            centroid=c["centroid"],
            suggested_label=c.get("suggested_label", ""),
            coherence_score=c.get("coherence_score", 0.0),
        )
        for c in data.get("clusters", [])
    ]
    return ClusterState(
        clusters=clusters,
        ungrouped_note_ids=data.get("ungrouped_note_ids", []),
        version_hash=data.get("version_hash", ""),
    )


# Module-level singleton
_analyzer: SpatialAnalyzer | None = None


def get_spatial_analyzer() -> SpatialAnalyzer:
    global _analyzer  # noqa: PLW0603
    if _analyzer is None:
        _analyzer = SpatialAnalyzer()
    return _analyzer
