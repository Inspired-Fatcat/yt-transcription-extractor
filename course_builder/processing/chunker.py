"""Chunking service for splitting transcripts into semantic segments."""

import re
from typing import Optional

import tiktoken

from ..models import Chunk
from ..config import ChunkingConfig


class ChunkingService:
    """Split transcripts into semantic chunks."""

    def __init__(self, config: Optional[ChunkingConfig] = None):
        self.config = config or ChunkingConfig()
        # Use cl100k_base tokenizer (used by GPT-4 and text-embedding models)
        self.tokenizer = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens in a text."""
        return len(self.tokenizer.encode(text))

    def chunk_transcript(
        self,
        video_id: str,
        segments: list[dict],
    ) -> list[Chunk]:
        """
        Split transcript segments into semantic chunks.

        Args:
            video_id: YouTube video ID
            segments: List of segment dicts with 'text', 'start', 'duration'

        Returns:
            List of Chunk objects
        """
        if not segments:
            return []

        chunks = []
        current_texts = []
        current_start = segments[0]['start']
        current_duration = 0

        for segment in segments:
            seg_text = segment['text'].strip()
            seg_start = segment['start']
            seg_duration = segment['duration']

            # Calculate what adding this segment would do
            potential_text = ' '.join(current_texts + [seg_text])
            potential_tokens = self.count_tokens(potential_text)
            potential_duration = current_duration + seg_duration

            # Check if we should start a new chunk
            should_split = False

            # Duration threshold
            if potential_duration > self.config.target_duration_seconds:
                should_split = True

            # Token threshold
            if potential_tokens > self.config.max_tokens:
                should_split = True

            # Natural break detection (pause > 2 seconds)
            if current_texts and seg_start - (current_start + current_duration) > 2.0:
                should_split = True

            if should_split and current_texts:
                # Create chunk from accumulated segments
                chunk_text = ' '.join(current_texts)
                chunk_tokens = self.count_tokens(chunk_text)

                if chunk_tokens >= self.config.min_tokens:
                    chunks.append(Chunk(
                        video_id=video_id,
                        chunk_index=len(chunks),
                        text=self._clean_text(chunk_text),
                        start_time=current_start,
                        end_time=current_start + current_duration,
                        token_count=chunk_tokens,
                    ))

                # Start new chunk with overlap
                overlap_texts, overlap_start = self._get_overlap(
                    current_texts, current_start, current_duration
                )
                current_texts = overlap_texts + [seg_text]
                current_start = overlap_start if overlap_texts else seg_start
                # Calculate duration from new start to end of current segment
                current_duration = (seg_start + seg_duration) - current_start
            else:
                # Add to current chunk
                current_texts.append(seg_text)
                if not current_texts[:-1]:  # First segment
                    current_start = seg_start
                current_duration = (seg_start + seg_duration) - current_start

        # Don't forget the last chunk
        if current_texts:
            chunk_text = ' '.join(current_texts)
            chunk_tokens = self.count_tokens(chunk_text)

            if chunk_tokens >= self.config.min_tokens:
                chunks.append(Chunk(
                    video_id=video_id,
                    chunk_index=len(chunks),
                    text=self._clean_text(chunk_text),
                    start_time=current_start,
                    end_time=current_start + current_duration,
                    token_count=chunk_tokens,
                ))

        return chunks

    def _get_overlap(
        self,
        texts: list[str],
        start_time: float,
        total_duration: float
    ) -> tuple[list[str], float]:
        """
        Get overlap texts for the next chunk.

        Returns:
            Tuple of (overlap_texts, overlap_start_time)
        """
        if not texts or self.config.overlap_ratio <= 0:
            return [], start_time + total_duration

        # Calculate target overlap duration
        overlap_duration = total_duration * self.config.overlap_ratio

        # Take texts from the end until we have enough overlap
        overlap_texts = []
        accumulated_duration = 0

        # Estimate duration per text segment
        avg_duration = total_duration / len(texts)

        for text in reversed(texts):
            if accumulated_duration >= overlap_duration:
                break
            overlap_texts.insert(0, text)
            accumulated_duration += avg_duration

        # Calculate overlap start time
        overlap_start = start_time + total_duration - accumulated_duration

        return overlap_texts, overlap_start

    def _clean_text(self, text: str) -> str:
        """Clean and normalize chunk text."""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)

        # Remove common transcript artifacts
        text = re.sub(r'\[Music\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[Applause\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[Laughter\]', '', text, flags=re.IGNORECASE)

        # Clean up
        text = text.strip()

        return text

    def rechunk_all(
        self,
        video_id: str,
        full_text: str,
        total_duration: float
    ) -> list[Chunk]:
        """
        Rechunk a transcript from full text (when segments aren't available).

        This uses sentence-based splitting as a fallback.
        """
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', full_text)

        # Estimate timing (uniform distribution)
        avg_duration_per_char = total_duration / len(full_text) if full_text else 0

        # Convert to pseudo-segments
        segments = []
        current_time = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            duration = len(sentence) * avg_duration_per_char
            segments.append({
                'text': sentence,
                'start': current_time,
                'duration': duration,
            })
            current_time += duration

        return self.chunk_transcript(video_id, segments)
