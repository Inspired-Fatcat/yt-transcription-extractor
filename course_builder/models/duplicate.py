"""Duplicate detection data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .chunk import Chunk


@dataclass
class DuplicateGroupMember:
    """A chunk that belongs to a duplicate group."""

    group_id: int
    chunk_id: int
    similarity_score: float

    # Populated during queries
    chunk: Optional[Chunk] = None


@dataclass
class DuplicateGroup:
    """A group of semantically similar chunks."""

    id: Optional[int] = None
    group_hash: str = ""           # Hash for deduplication
    canonical_chunk_id: int = 0    # The "best" chunk in the group
    merged_content: str = ""       # AI-synthesized merged version
    created_at: Optional[datetime] = None

    # Members
    members: list[DuplicateGroupMember] = field(default_factory=list)

    @property
    def chunk_count(self) -> int:
        """Number of chunks in this group."""
        return len(self.members)

    @property
    def average_similarity(self) -> float:
        """Average similarity score of members."""
        if not self.members:
            return 0.0
        return sum(m.similarity_score for m in self.members) / len(self.members)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'canonical_chunk_id': self.canonical_chunk_id,
            'chunk_count': self.chunk_count,
            'average_similarity': self.average_similarity,
            'merged_content': self.merged_content,
            'members': [
                {
                    'chunk_id': m.chunk_id,
                    'similarity_score': m.similarity_score,
                }
                for m in self.members
            ],
        }
