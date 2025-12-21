"""Extract transcripts from YouTube videos."""

from dataclasses import dataclass
from typing import Optional

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    TooManyRequests,
)

from .exceptions import (
    TranscriptNotFoundError,
    TranscriptDisabledError,
    VideoNotFoundError,
    RateLimitError,
    ExtractionError,
    ValidationError,
)
from .logging_config import get_logger

logger = get_logger('transcript')


@dataclass
class TranscriptSegment:
    """A single segment of a transcript with timing."""
    text: str
    start: float  # seconds
    duration: float  # seconds

    def __post_init__(self):
        """Validate segment data."""
        if self.start < 0:
            raise ValidationError(
                f"Segment start time cannot be negative: {self.start}",
                field='start',
                value=str(self.start)
            )
        if self.duration < 0:
            raise ValidationError(
                f"Segment duration cannot be negative: {self.duration}",
                field='duration',
                value=str(self.duration)
            )


@dataclass
class Transcript:
    """Full transcript for a video."""
    video_id: str
    language: str
    is_generated: bool  # True if auto-generated
    segments: list[TranscriptSegment]

    def __post_init__(self):
        """Validate transcript data."""
        if not self.video_id:
            raise ValidationError("Video ID cannot be empty", field='video_id')
        if len(self.video_id) != 11:
            raise ValidationError(
                f"Invalid video ID length: {len(self.video_id)} (expected 11)",
                field='video_id',
                value=self.video_id
            )
        if not self.language:
            raise ValidationError("Language cannot be empty", field='language')

    @property
    def full_text(self) -> str:
        """Get the full transcript as a single string."""
        return ' '.join(seg.text for seg in self.segments)

    @property
    def text_with_timestamps(self) -> str:
        """Get transcript with timestamps."""
        lines = []
        for seg in self.segments:
            mins, secs = divmod(int(seg.start), 60)
            hours, mins = divmod(mins, 60)
            if hours:
                timestamp = f"[{hours}:{mins:02d}:{secs:02d}]"
            else:
                timestamp = f"[{mins}:{secs:02d}]"
            lines.append(f"{timestamp} {seg.text}")
        return '\n'.join(lines)


def get_transcript(
    video_id: str,
    languages: Optional[list[str]] = None,
    raise_on_error: bool = False
) -> Optional[Transcript]:
    """
    Fetch transcript for a YouTube video.

    Args:
        video_id: YouTube video ID
        languages: Preferred languages in order (default: ['en'])
        raise_on_error: If True, raise exceptions instead of returning None

    Returns:
        Transcript object or None if unavailable (when raise_on_error=False)

    Raises:
        TranscriptNotFoundError: No transcript available (when raise_on_error=True)
        TranscriptDisabledError: Transcripts disabled for video
        VideoNotFoundError: Video doesn't exist or is unavailable
        RateLimitError: YouTube is rate-limiting requests
    """
    if languages is None:
        languages = ['en']

    logger.debug(f"Fetching transcript for video '{video_id}' in languages {languages}")

    try:
        # Create API instance (required for v1.x)
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)

        # Try to find a manual transcript first
        transcript = None
        is_generated = False

        try:
            transcript = transcript_list.find_manually_created_transcript(languages)
            logger.debug(f"Found manual transcript in {transcript.language_code}")
        except NoTranscriptFound:
            try:
                transcript = transcript_list.find_generated_transcript(languages)
                is_generated = True
                logger.debug(f"Found generated transcript in {transcript.language_code}")
            except NoTranscriptFound:
                # Try to get any available transcript and translate
                available = list(transcript_list)
                if available:
                    transcript = available[0]
                    available_codes = [t.language_code for t in available]
                    logger.debug(f"No transcript in {languages}, available: {available_codes}")

                    if transcript.language_code not in languages:
                        try:
                            transcript = transcript.translate(languages[0])
                            logger.debug(f"Translated from {available[0].language_code} to {languages[0]}")
                        except Exception as e:
                            logger.warning(f"Translation failed: {e}")
                            # Use original if translation fails
                    is_generated = transcript.is_generated
                else:
                    available_langs = [t.language_code for t in transcript_list]
                    logger.warning(f"No transcript found for {video_id}")
                    if raise_on_error:
                        raise TranscriptNotFoundError(
                            video_id,
                            language=languages[0],
                            available_languages=available_langs
                        )
                    return None

        if transcript is None:
            if raise_on_error:
                raise TranscriptNotFoundError(video_id, language=languages[0])
            return None

        data = transcript.fetch()
        segments = [
            TranscriptSegment(
                text=item.text,
                start=item.start,
                duration=item.duration
            )
            for item in data
        ]

        result = Transcript(
            video_id=video_id,
            language=transcript.language_code if hasattr(transcript, 'language_code') else languages[0],
            is_generated=is_generated,
            segments=segments
        )

        logger.info(f"Successfully fetched transcript for '{video_id}' ({len(segments)} segments)")
        return result

    except TranscriptsDisabled:
        logger.warning(f"Transcripts disabled for video '{video_id}'")
        if raise_on_error:
            raise TranscriptDisabledError(video_id)
        return None

    except VideoUnavailable:
        logger.warning(f"Video unavailable: '{video_id}'")
        if raise_on_error:
            raise VideoNotFoundError(video_id, reason="Video unavailable or private")
        return None

    except TooManyRequests as e:
        logger.error(f"Rate limited by YouTube for video '{video_id}'")
        if raise_on_error:
            raise RateLimitError(video_id=video_id, retry_after=60)
        return None

    except (TranscriptNotFoundError, TranscriptDisabledError, VideoNotFoundError, RateLimitError):
        # Re-raise our custom exceptions
        raise

    except Exception as e:
        logger.error(f"Unexpected error fetching transcript for '{video_id}': {e}", exc_info=True)
        if raise_on_error:
            raise ExtractionError(
                f"Failed to fetch transcript: {e}",
                video_id=video_id
            )
        return None


def get_available_languages(video_id: str) -> list[dict]:
    """Get list of available transcript languages for a video.

    Args:
        video_id: YouTube video ID

    Returns:
        List of language info dicts, or empty list on error
    """
    logger.debug(f"Fetching available languages for video '{video_id}'")

    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        languages = []
        for t in transcript_list:
            languages.append({
                'language': t.language,
                'language_code': t.language_code,
                'is_generated': t.is_generated,
                'is_translatable': t.is_translatable,
            })

        logger.debug(f"Found {len(languages)} available languages for '{video_id}'")
        return languages

    except TranscriptsDisabled:
        logger.debug(f"Transcripts disabled for video '{video_id}'")
        return []

    except VideoUnavailable:
        logger.debug(f"Video unavailable: '{video_id}'")
        return []

    except TooManyRequests:
        logger.warning(f"Rate limited when fetching languages for '{video_id}'")
        return []

    except Exception as e:
        logger.error(f"Error fetching languages for '{video_id}': {e}")
        return []
