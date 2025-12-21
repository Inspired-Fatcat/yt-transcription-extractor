"""Topic extraction service using Claude."""

from typing import Optional, Callable

from ..config import LLMConfig
from ..models import Chunk, Topic, TopicCategory, ChunkTopic
from ..llm import (
    ClaudeClient,
    ChunkTopicExtraction,
    TOPIC_EXTRACTION_SYSTEM,
    topic_extraction_prompt,
)


# Map LLM category strings to TopicCategory enum
CATEGORY_MAP = {
    "concept": TopicCategory.CONCEPT,
    "technique": TopicCategory.TECHNIQUE,
    "tool": TopicCategory.TOOL,
    "example": TopicCategory.TECHNIQUE,  # Map example to technique
    "tip": TopicCategory.BEST_PRACTICE,
    "pattern": TopicCategory.PATTERN,
    "workflow": TopicCategory.WORKFLOW,
    "best_practice": TopicCategory.BEST_PRACTICE,
}


class TopicExtractor:
    """Extract topics from transcript chunks using Claude."""

    def __init__(self, api_key: str, config: Optional[LLMConfig] = None):
        self.client = ClaudeClient(api_key=api_key, config=config)

    def extract_from_chunk(
        self,
        chunk: Chunk,
        video_title: str,
        channel: str,
    ) -> tuple[list[Topic], str, str]:
        """
        Extract topics from a single chunk.

        Args:
            chunk: The chunk to analyze
            video_title: Title of the source video
            channel: Channel name

        Returns:
            Tuple of (topics, main_theme, summary)
        """
        prompt = topic_extraction_prompt(
            chunk_text=chunk.text,
            video_title=video_title,
            channel=channel,
        )

        result = self.client.complete_json(
            prompt=prompt,
            response_model=ChunkTopicExtraction,
            system=TOPIC_EXTRACTION_SYSTEM,
            max_tokens=2000,
        )

        topics = []
        for extracted in result.topics:
            # Map category string to enum
            category = CATEGORY_MAP.get(
                extracted.category.lower(),
                TopicCategory.CONCEPT
            )

            topic = Topic(
                name=extracted.name,
                description=extracted.description,
                category=category,
                confidence=extracted.relevance_score,
            )
            topic.relevance_scores[chunk.id] = extracted.relevance_score
            topics.append(topic)

        return topics, result.main_theme, result.summary

    def extract_from_chunks(
        self,
        chunks: list[Chunk],
        video_metadata: dict[str, dict],  # video_id -> {title, channel}
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict[int, tuple[list[Topic], str, str]]:
        """
        Extract topics from multiple chunks.

        Args:
            chunks: List of chunks to analyze
            video_metadata: Dict mapping video_id to {title, channel}
            on_progress: Callback (current, total, chunk_id)

        Returns:
            Dict mapping chunk_id to (topics, main_theme, summary)
        """
        results = {}
        total = len(chunks)

        for i, chunk in enumerate(chunks, 1):
            meta = video_metadata.get(chunk.video_id, {})
            video_title = meta.get('title', 'Unknown Video')
            channel = meta.get('channel', 'Unknown Channel')

            if on_progress:
                on_progress(i, total, f"Extracting topics from chunk {chunk.id}")

            try:
                topics, theme, summary = self.extract_from_chunk(
                    chunk=chunk,
                    video_title=video_title,
                    channel=channel,
                )
                results[chunk.id] = (topics, theme, summary)
            except Exception as e:
                # Log error but continue processing
                results[chunk.id] = ([], "", f"Error: {str(e)}")

        return results

    def deduplicate_topics(
        self,
        all_topics: list[Topic],
        similarity_threshold: float = 0.85,
    ) -> list[Topic]:
        """
        Merge similar topics from multiple chunks.

        This is a simple string-based deduplication. For semantic
        deduplication, use the vector store.

        Args:
            all_topics: List of all extracted topics
            similarity_threshold: Not used yet (placeholder for semantic matching)

        Returns:
            Deduplicated list of topics with merged chunk associations
        """
        # Simple name-based deduplication
        seen_names = {}  # normalized_name -> topic

        for topic in all_topics:
            normalized = topic.name.lower().strip()

            if normalized in seen_names:
                # Merge into existing topic
                existing = seen_names[normalized]
                existing.mention_count += 1

                # Merge relevance scores
                for chunk_id, score in topic.relevance_scores.items():
                    if chunk_id not in existing.relevance_scores:
                        existing.relevance_scores[chunk_id] = score
                    else:
                        # Keep higher score
                        existing.relevance_scores[chunk_id] = max(
                            existing.relevance_scores[chunk_id],
                            score
                        )

                # Update confidence based on mention frequency
                existing.confidence = min(1.0, existing.confidence + 0.1)

                # Use better description if available
                if len(topic.description) > len(existing.description):
                    existing.description = topic.description
            else:
                topic.mention_count = 1
                seen_names[normalized] = topic

        return list(seen_names.values())


def format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"
