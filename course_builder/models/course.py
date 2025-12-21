"""Course, Module, and Lesson data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class DifficultyLevel(str, Enum):
    """Difficulty levels for courses and lessons."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class CourseStatus(str, Enum):
    """Status of a course."""
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"


class SourceUsageType(str, Enum):
    """How a source chunk is used in a lesson."""
    PRIMARY = "primary"       # Main source for the content
    SUPPORTING = "supporting" # Additional context
    EXAMPLE = "example"       # Used as an example
    QUOTE = "quote"           # Direct quote


@dataclass
class LessonSource:
    """Reference to a source chunk used in a lesson."""

    id: Optional[int] = None
    lesson_id: int = 0
    chunk_id: int = 0
    usage_type: SourceUsageType = SourceUsageType.PRIMARY
    relevance_score: float = 1.0

    # Populated during queries
    video_id: Optional[str] = None
    video_title: Optional[str] = None
    channel: Optional[str] = None
    timestamp_start: Optional[float] = None
    timestamp_end: Optional[float] = None
    quote: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'video_id': self.video_id,
            'video_title': self.video_title,
            'channel': self.channel,
            'timestamp_start': self.timestamp_start,
            'timestamp_end': self.timestamp_end,
            'usage_type': self.usage_type.value,
            'relevance_score': self.relevance_score,
            'quote': self.quote,
        }


@dataclass
class Lesson:
    """A single lesson within a module."""

    id: Optional[int] = None
    module_id: int = 0
    title: str = ""
    sequence_order: int = 0
    content: str = ""           # Main content (Markdown)
    summary: str = ""           # Brief summary
    key_takeaways: list[str] = field(default_factory=list)
    estimated_duration: int = 0  # minutes
    difficulty_level: DifficultyLevel = DifficultyLevel.INTERMEDIATE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Related data
    sources: list[LessonSource] = field(default_factory=list)
    topic_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': f"lesson-{self.id:03d}" if self.id else None,
            'title': self.title,
            'sequence_order': self.sequence_order,
            'estimated_duration_minutes': self.estimated_duration,
            'difficulty_level': self.difficulty_level.value,
            'content': {
                'summary': self.summary,
                'body': self.content,
                'key_takeaways': self.key_takeaways,
            },
            'sources': [s.to_dict() for s in self.sources],
        }


@dataclass
class Module:
    """A module (section) within a course."""

    id: Optional[int] = None
    course_id: int = 0
    title: str = ""
    description: str = ""
    sequence_order: int = 0
    learning_objectives: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = None

    # Related data
    lessons: list[Lesson] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': f"mod-{self.id:03d}" if self.id else None,
            'title': self.title,
            'description': self.description,
            'sequence_order': self.sequence_order,
            'learning_objectives': self.learning_objectives,
            'lessons': [l.to_dict() for l in self.lessons],
        }


@dataclass
class Course:
    """A complete course structure."""

    id: Optional[int] = None
    title: str = ""
    description: str = ""
    target_audience: str = ""
    difficulty_level: DifficultyLevel = DifficultyLevel.INTERMEDIATE
    status: CourseStatus = CourseStatus.DRAFT
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Related data
    modules: list[Module] = field(default_factory=list)

    # Metadata
    source_video_count: int = 0
    total_transcript_hours: float = 0.0
    unique_topics_count: int = 0
    duplicate_groups_merged: int = 0

    @property
    def total_duration_minutes(self) -> int:
        """Total estimated duration of all lessons."""
        return sum(
            lesson.estimated_duration
            for module in self.modules
            for lesson in module.lessons
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            '$schema': 'course-schema-v1.json',
            'course': {
                'id': f"course-{self.id:03d}" if self.id else None,
                'title': self.title,
                'description': self.description,
                'target_audience': self.target_audience,
                'difficulty_level': self.difficulty_level.value,
                'status': self.status.value,
                'total_duration_minutes': self.total_duration_minutes,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'modules': [m.to_dict() for m in self.modules],
                'metadata': {
                    'source_video_count': self.source_video_count,
                    'total_transcript_hours': self.total_transcript_hours,
                    'unique_topics_extracted': self.unique_topics_count,
                    'duplicate_groups_merged': self.duplicate_groups_merged,
                },
            }
        }
