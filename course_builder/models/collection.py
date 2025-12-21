"""Collection model for organizing content into folders."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

# Slug validation pattern: lowercase letters, numbers, hyphens only
SLUG_PATTERN = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


class CollectionType(str, Enum):
    """Types of collections."""
    CREATOR = "creator"         # All content from a specific creator
    TOPIC = "topic"             # Content about a specific topic
    COURSE = "course"           # Curated course material
    PROJECT = "project"         # Project-specific research
    CUSTOM = "custom"           # User-defined


@dataclass
class Collection:
    """
    A folder/collection that organizes related content.

    Each collection has its own:
    - Set of videos
    - Chunks and embeddings
    - Topics and relationships
    - Search index
    """

    id: Optional[int] = None
    name: str = ""
    slug: str = ""              # URL-friendly identifier (e.g., "indydevdan")
    description: str = ""
    collection_type: CollectionType = CollectionType.CUSTOM

    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Configuration
    config: dict = field(default_factory=dict)  # Collection-specific settings

    # Stats (computed)
    video_count: int = 0
    chunk_count: int = 0
    topic_count: int = 0
    total_duration_hours: float = 0.0

    def __post_init__(self):
        """Validate collection data after initialization."""
        # Validate name is not empty
        if not self.name or not self.name.strip():
            raise ValueError("Collection name cannot be empty")

        # Validate slug format (if provided)
        if self.slug:
            if not SLUG_PATTERN.match(self.slug):
                raise ValueError(
                    f"Invalid slug format: '{self.slug}'. "
                    "Slug must be lowercase letters, numbers, and hyphens only."
                )
            if len(self.slug) > 100:
                raise ValueError(f"Slug too long: {len(self.slug)} chars (max 100)")

        # Validate stats are non-negative
        if self.video_count < 0:
            self.video_count = 0
        if self.chunk_count < 0:
            self.chunk_count = 0
        if self.topic_count < 0:
            self.topic_count = 0
        if self.total_duration_hours < 0:
            self.total_duration_hours = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'type': self.collection_type.value,
            'stats': {
                'videos': self.video_count,
                'chunks': self.chunk_count,
                'topics': self.topic_count,
                'duration_hours': self.total_duration_hours,
            },
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# Video ID validation pattern
VIDEO_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{11}$')


@dataclass
class CollectionVideo:
    """Association between a collection and a video."""
    collection_id: int
    video_id: str
    added_at: Optional[datetime] = None
    notes: str = ""  # User notes about why this video is in the collection

    def __post_init__(self):
        """Validate association data after initialization."""
        # Validate collection_id is positive
        if self.collection_id is not None and self.collection_id <= 0:
            raise ValueError(f"Invalid collection_id: {self.collection_id}")

        # Validate video_id format
        if not self.video_id:
            raise ValueError("video_id cannot be empty")
        if not VIDEO_ID_PATTERN.match(self.video_id):
            raise ValueError(f"Invalid video_id format: {self.video_id}")
