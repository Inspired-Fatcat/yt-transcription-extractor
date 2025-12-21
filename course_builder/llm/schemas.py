"""Pydantic schemas for LLM responses."""

from typing import Optional
from pydantic import BaseModel, Field


class ExtractedTopic(BaseModel):
    """A topic extracted from a transcript chunk."""
    name: str = Field(description="Short name for the topic (2-5 words)")
    description: str = Field(description="Brief description of what the topic covers (1-2 sentences)")
    category: str = Field(description="Category: concept, technique, tool, example, or tip")
    relevance_score: float = Field(
        description="How central this topic is to the chunk (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    keywords: list[str] = Field(
        description="3-5 keywords associated with this topic",
        default_factory=list
    )


class ChunkTopicExtraction(BaseModel):
    """Topics extracted from a single chunk."""
    topics: list[ExtractedTopic] = Field(
        description="List of topics found in this chunk",
        default_factory=list
    )
    main_theme: str = Field(description="The primary theme or focus of this chunk")
    summary: str = Field(description="2-3 sentence summary of the chunk content")


class DuplicateAnalysis(BaseModel):
    """Analysis of potential duplicate content."""
    is_duplicate: bool = Field(description="Whether the chunks cover the same content")
    similarity_type: str = Field(
        description="Type of similarity: exact, paraphrase, related, or different"
    )
    shared_concepts: list[str] = Field(
        description="Concepts shared between the chunks",
        default_factory=list
    )
    unique_to_first: list[str] = Field(
        description="Concepts unique to the first chunk",
        default_factory=list
    )
    unique_to_second: list[str] = Field(
        description="Concepts unique to the second chunk",
        default_factory=list
    )
    merged_summary: Optional[str] = Field(
        description="If duplicates, a merged summary combining both",
        default=None
    )


class CurriculumModule(BaseModel):
    """A proposed module in the curriculum."""
    title: str = Field(description="Module title")
    description: str = Field(description="What this module covers")
    learning_objectives: list[str] = Field(
        description="What learners will be able to do after this module",
        default_factory=list
    )
    suggested_topics: list[str] = Field(
        description="Topic names that belong in this module",
        default_factory=list
    )
    sequence_order: int = Field(description="Position in the curriculum (1-based)")


class CurriculumProposal(BaseModel):
    """A proposed curriculum structure."""
    title: str = Field(description="Course title")
    description: str = Field(description="Course description")
    target_audience: str = Field(description="Who this course is for")
    prerequisites: list[str] = Field(
        description="What learners should know beforehand",
        default_factory=list
    )
    modules: list[CurriculumModule] = Field(
        description="Proposed modules in order",
        default_factory=list
    )


class LessonContent(BaseModel):
    """Generated content for a lesson."""
    title: str = Field(description="Lesson title")
    summary: str = Field(description="Brief summary of the lesson")
    body: str = Field(description="Main lesson content in markdown")
    key_takeaways: list[str] = Field(
        description="3-5 key points to remember",
        default_factory=list
    )
    practical_exercises: list[str] = Field(
        description="Suggested exercises or practice activities",
        default_factory=list
    )
