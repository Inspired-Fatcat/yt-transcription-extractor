# LLM module - Claude API client and prompt templates
from .client import ClaudeClient
from .schemas import (
    ExtractedTopic,
    ChunkTopicExtraction,
    DuplicateAnalysis,
    CurriculumModule,
    CurriculumProposal,
    LessonContent,
)
from .prompts import (
    TOPIC_EXTRACTION_SYSTEM,
    DEDUPLICATION_SYSTEM,
    CURRICULUM_SYSTEM,
    LESSON_GENERATION_SYSTEM,
    topic_extraction_prompt,
    batch_topic_extraction_prompt,
    duplicate_analysis_prompt,
    curriculum_proposal_prompt,
    lesson_generation_prompt,
)

__all__ = [
    'ClaudeClient',
    'ExtractedTopic',
    'ChunkTopicExtraction',
    'DuplicateAnalysis',
    'CurriculumModule',
    'CurriculumProposal',
    'LessonContent',
    'TOPIC_EXTRACTION_SYSTEM',
    'DEDUPLICATION_SYSTEM',
    'CURRICULUM_SYSTEM',
    'LESSON_GENERATION_SYSTEM',
    'topic_extraction_prompt',
    'batch_topic_extraction_prompt',
    'duplicate_analysis_prompt',
    'curriculum_proposal_prompt',
    'lesson_generation_prompt',
]
