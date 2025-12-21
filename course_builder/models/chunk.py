"""Chunk data model for transcript segments."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Video ID validation pattern
VIDEO_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{11}$')


@dataclass
class Chunk:
    """A semantic chunk of transcript content."""

    id: Optional[int] = None
    video_id: str = ""
    chunk_index: int = 0
    text: str = ""
    start_time: float = 0.0  # seconds
    end_time: float = 0.0    # seconds
    token_count: int = 0
    created_at: Optional[datetime] = None

    # Metadata (not stored in DB, used during processing)
    embedding: Optional[list[float]] = field(default=None, repr=False)
    video_title: Optional[str] = None
    channel: Optional[str] = None

    def __post_init__(self):
        """Validate chunk data after initialization."""
        # Validate video_id format (if provided)
        if self.video_id and not VIDEO_ID_PATTERN.match(self.video_id):
            raise ValueError(f"Invalid video_id format: {self.video_id}")

        # Validate time ranges
        if self.start_time < 0:
            raise ValueError(f"start_time cannot be negative: {self.start_time}")
        if self.end_time < 0:
            raise ValueError(f"end_time cannot be negative: {self.end_time}")
        if self.end_time < self.start_time:
            raise ValueError(
                f"end_time ({self.end_time}) cannot be less than start_time ({self.start_time})"
            )

        # Validate token_count
        if self.token_count < 0:
            raise ValueError(f"token_count cannot be negative: {self.token_count}")

        # Validate chunk_index
        if self.chunk_index < 0:
            raise ValueError(f"chunk_index cannot be negative: {self.chunk_index}")

    @property
    def duration(self) -> float:
        """Duration of the chunk in seconds."""
        return self.end_time - self.start_time

    @property
    def timestamp_str(self) -> str:
        """Human-readable timestamp range."""
        def fmt(secs: float) -> str:
            mins, s = divmod(int(secs), 60)
            hrs, mins = divmod(mins, 60)
            if hrs:
                return f"{hrs}:{mins:02d}:{s:02d}"
            return f"{mins}:{s:02d}"
        return f"{fmt(self.start_time)} - {fmt(self.end_time)}"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'video_id': self.video_id,
            'chunk_index': self.chunk_index,
            'text': self.text,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'token_count': self.token_count,
            'timestamp': self.timestamp_str,
        }
