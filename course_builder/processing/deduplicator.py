"""Deduplication service for finding and merging similar content."""

import hashlib
from typing import Optional, Callable

from ..config import DeduplicationConfig, LLMConfig
from ..models import Chunk, DuplicateGroup, DuplicateGroupMember
from ..core.vector_store import VectorStore
from ..llm import (
    ClaudeClient,
    DuplicateAnalysis,
    DEDUPLICATION_SYSTEM,
    duplicate_analysis_prompt,
)


class DeduplicationService:
    """Find and merge duplicate content across chunks."""

    def __init__(
        self,
        vector_store: VectorStore,
        config: Optional[DeduplicationConfig] = None,
        claude_client: Optional[ClaudeClient] = None,
    ):
        self.vector_store = vector_store
        self.config = config or DeduplicationConfig()
        self.claude_client = claude_client

    def find_similar_pairs(
        self,
        threshold: Optional[float] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> list[tuple[int, int, float]]:
        """
        Find all pairs of similar chunks above threshold.

        Returns:
            List of (chunk_id_1, chunk_id_2, similarity) tuples
        """
        threshold = threshold or self.config.similarity_threshold

        if on_progress:
            on_progress(0, 1)

        pairs = self.vector_store.find_all_similar_pairs(threshold=threshold)

        if on_progress:
            on_progress(1, 1)

        return pairs

    def cluster_duplicates(
        self,
        pairs: list[tuple[int, int, float]],
    ) -> list[list[tuple[int, float]]]:
        """
        Cluster similar pairs into groups using union-find.

        Args:
            pairs: List of (chunk_id_1, chunk_id_2, similarity) tuples

        Returns:
            List of clusters, where each cluster is a list of (chunk_id, avg_similarity)
        """
        if not pairs:
            return []

        # Union-find for clustering
        parent = {}

        def find(x):
            if x not in parent:
                parent[x] = x
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Build clusters
        for id1, id2, _ in pairs:
            union(id1, id2)

        # Group by cluster root
        clusters_dict = {}
        similarity_sums = {}
        similarity_counts = {}

        for id1, id2, sim in pairs:
            root = find(id1)
            if root not in clusters_dict:
                clusters_dict[root] = set()
            clusters_dict[root].add(id1)
            clusters_dict[root].add(id2)

            # Track similarities for averaging
            for cid in [id1, id2]:
                if cid not in similarity_sums:
                    similarity_sums[cid] = 0.0
                    similarity_counts[cid] = 0
                similarity_sums[cid] += sim
                similarity_counts[cid] += 1

        # Convert to list format with average similarities
        clusters = []
        for chunk_ids in clusters_dict.values():
            if len(chunk_ids) >= self.config.min_cluster_size:
                cluster = []
                for cid in chunk_ids:
                    avg_sim = similarity_sums.get(cid, 1.0) / max(similarity_counts.get(cid, 1), 1)
                    cluster.append((cid, avg_sim))
                # Sort by average similarity (highest first)
                cluster.sort(key=lambda x: -x[1])
                clusters.append(cluster)

        return clusters

    def analyze_pair(
        self,
        chunk1: Chunk,
        chunk2: Chunk,
        chunk1_meta: dict,
        chunk2_meta: dict,
    ) -> DuplicateAnalysis:
        """
        Use Claude to analyze whether two chunks are duplicates.

        Args:
            chunk1, chunk2: The chunks to compare
            chunk1_meta, chunk2_meta: Video metadata (title, channel)

        Returns:
            DuplicateAnalysis with detailed comparison
        """
        if not self.claude_client:
            raise ValueError("Claude client required for duplicate analysis")

        prompt = duplicate_analysis_prompt(
            chunk1={
                'text': chunk1.text,
                'video_title': chunk1_meta.get('title', 'Unknown'),
                'timestamp': f"{int(chunk1.start_time // 60)}:{int(chunk1.start_time % 60):02d}",
            },
            chunk2={
                'text': chunk2.text,
                'video_title': chunk2_meta.get('title', 'Unknown'),
                'timestamp': f"{int(chunk2.start_time // 60)}:{int(chunk2.start_time % 60):02d}",
            },
        )

        return self.claude_client.complete_json(
            prompt=prompt,
            response_model=DuplicateAnalysis,
            system=DEDUPLICATION_SYSTEM,
            max_tokens=1500,
        )

    def create_duplicate_group(
        self,
        chunk_ids: list[tuple[int, float]],
        merged_content: Optional[str] = None,
    ) -> DuplicateGroup:
        """
        Create a DuplicateGroup from a list of chunk IDs.

        Args:
            chunk_ids: List of (chunk_id, similarity_score) tuples
            merged_content: Optional merged/synthesized content

        Returns:
            DuplicateGroup object (not yet saved to DB)
        """
        # Create a hash for the group based on sorted chunk IDs
        sorted_ids = sorted([cid for cid, _ in chunk_ids])
        group_hash = hashlib.md5(
            ",".join(map(str, sorted_ids)).encode()
        ).hexdigest()[:16]

        # Pick the canonical chunk (highest similarity or first)
        canonical_id = chunk_ids[0][0]

        group = DuplicateGroup(
            group_hash=group_hash,
            canonical_chunk_id=canonical_id,
            merged_content=merged_content,
        )

        for chunk_id, similarity in chunk_ids:
            group.members.append(DuplicateGroupMember(
                group_id=0,  # Will be set when saved
                chunk_id=chunk_id,
                similarity_score=similarity,
            ))

        return group


def format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"
