"""Topic data model for extracted concepts and techniques."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TopicCategory(str, Enum):
    """Categories for extracted topics."""
    CONCEPT = "concept"           # Abstract ideas (e.g., "context window")
    TECHNIQUE = "technique"       # How-to methods (e.g., "prompt chaining")
    PATTERN = "pattern"           # Reusable patterns (e.g., "tool use pattern")
    TOOL = "tool"                 # Specific tools (e.g., "ChromaDB", "yt-dlp")
    WORKFLOW = "workflow"         # Multi-step processes (e.g., "skill creation")
    BEST_PRACTICE = "best_practice"  # Recommendations


@dataclass
class Topic:
    """An extracted concept, technique, or pattern."""

    id: Optional[int] = None
    name: str = ""
    description: str = ""
    category: TopicCategory = TopicCategory.CONCEPT
    parent_topic_id: Optional[int] = None
    created_at: Optional[datetime] = None

    # Relationships (populated during queries)
    children: list['Topic'] = field(default_factory=list)
    chunk_ids: list[int] = field(default_factory=list)
    relevance_scores: dict[int, float] = field(default_factory=dict)  # chunk_id -> score

    # Extraction metadata
    confidence: float = 1.0
    mention_count: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category.value,
            'parent_topic_id': self.parent_topic_id,
            'confidence': self.confidence,
            'mention_count': self.mention_count,
        }


@dataclass
class ChunkTopic:
    """Association between a chunk and a topic."""
    chunk_id: int
    topic_id: int
    relevance_score: float = 1.0
