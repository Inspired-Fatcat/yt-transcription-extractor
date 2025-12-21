"""Main extractor that orchestrates video processing."""

import time
from dataclasses import dataclass
from typing import Callable, Optional

from .database import TranscriptDatabase
from .video_info import VideoMetadata, extract_video_id, get_video_metadata, get_playlist_video_ids
from .transcript import Transcript, get_transcript
from .exceptions import (
    ExtractionError,
    VideoNotFoundError,
    RateLimitError,
    PlaylistError,
    InvalidUrlError,
)
from .logging_config import get_logger

logger = get_logger('extractor')


@dataclass
class ExtractionResult:
    """Result of processing a single video."""
    video_id: str
    success: bool
    has_transcript: bool
    error: Optional[str] = None
    error_type: Optional[str] = None  # Exception class name for categorization


class YouTubeExtractor:
    """Extracts and stores YouTube video transcripts."""

    def __init__(
        self,
        db_path: str = "data/transcripts.db",
        languages: Optional[list[str]] = None,
        delay_between_requests: float = 1.0,
    ):
        logger.info(f"Initializing YouTubeExtractor with db={db_path}, languages={languages}, delay={delay_between_requests}s")
        self.db = TranscriptDatabase(db_path)
        self.languages = languages or ['en']
        self.delay = delay_between_requests

    def process_video(
        self,
        url_or_id: str,
        skip_existing: bool = True,
        on_progress: Optional[Callable[[str, str], None]] = None,
    ) -> ExtractionResult:
        """
        Process a single video: fetch metadata and transcript.

        Args:
            url_or_id: YouTube URL or video ID
            skip_existing: Skip if already in database
            on_progress: Callback for progress updates (video_id, status)
        """
        # Extract video ID
        try:
            video_id = extract_video_id(url_or_id)
            logger.debug(f"Extracted video ID: {video_id} from {url_or_id}")
        except ValueError as e:
            logger.warning(f"Invalid video URL/ID: {url_or_id} - {e}")
            return ExtractionResult(
                video_id=url_or_id,
                success=False,
                has_transcript=False,
                error=str(e),
                error_type='InvalidUrlError'
            )

        # Check if already exists
        if skip_existing and self.db.video_exists(video_id):
            logger.debug(f"Skipping {video_id} - already in database")
            if on_progress:
                on_progress(video_id, "skipped (already exists)")
            return ExtractionResult(
                video_id=video_id,
                success=True,
                has_transcript=True,
            )

        # Fetch metadata
        logger.info(f"Processing video: {video_id}")
        if on_progress:
            on_progress(video_id, "fetching metadata...")

        try:
            metadata = get_video_metadata(video_id)
            self.db.save_video(metadata)
            logger.debug(f"Saved metadata for {video_id}: {metadata.title}")
        except VideoNotFoundError as e:
            logger.error(f"Video not found: {video_id}")
            return ExtractionResult(
                video_id=video_id,
                success=False,
                has_transcript=False,
                error=str(e),
                error_type='VideoNotFoundError'
            )
        except RateLimitError as e:
            logger.error(f"Rate limited while fetching metadata for {video_id}")
            return ExtractionResult(
                video_id=video_id,
                success=False,
                has_transcript=False,
                error=str(e),
                error_type='RateLimitError'
            )
        except Exception as e:
            logger.error(f"Failed to fetch metadata for {video_id}: {e}", exc_info=True)
            return ExtractionResult(
                video_id=video_id,
                success=False,
                has_transcript=False,
                error=f"Failed to fetch metadata: {e}",
                error_type=type(e).__name__
            )

        # Fetch transcript
        if on_progress:
            on_progress(video_id, "fetching transcript...")

        try:
            transcript = get_transcript(video_id, self.languages)
            has_transcript = transcript is not None

            if transcript:
                self.db.save_transcript(transcript)
                logger.info(f"Saved transcript for {video_id} ({len(transcript.segments)} segments)")
            else:
                logger.info(f"No transcript available for {video_id}")

        except RateLimitError as e:
            logger.error(f"Rate limited while fetching transcript for {video_id}")
            # We already saved the metadata, so partial success
            return ExtractionResult(
                video_id=video_id,
                success=False,
                has_transcript=False,
                error=str(e),
                error_type='RateLimitError'
            )
        except Exception as e:
            logger.error(f"Error fetching transcript for {video_id}: {e}", exc_info=True)
            # Metadata was saved, transcript failed - still a partial success
            has_transcript = False

        if on_progress:
            status = "done" if has_transcript else "done (no transcript)"
            on_progress(video_id, status)

        logger.debug(f"Completed processing {video_id} - transcript: {has_transcript}")
        return ExtractionResult(
            video_id=video_id,
            success=True,
            has_transcript=has_transcript,
        )

    def process_videos(
        self,
        urls_or_ids: list[str],
        skip_existing: bool = True,
        on_progress: Optional[Callable[[int, int, str, str], None]] = None,
    ) -> list[ExtractionResult]:
        """
        Process multiple videos.

        Args:
            urls_or_ids: List of YouTube URLs or video IDs
            skip_existing: Skip videos already in database
            on_progress: Callback (current, total, video_id, status)
        """
        results = []
        total = len(urls_or_ids)
        successful = 0
        failed = 0
        skipped = 0

        logger.info(f"Starting batch processing of {total} videos (delay={self.delay}s)")

        for i, url_or_id in enumerate(urls_or_ids, 1):
            def progress_wrapper(vid: str, status: str):
                if on_progress:
                    on_progress(i, total, vid, status)

            result = self.process_video(
                url_or_id,
                skip_existing=skip_existing,
                on_progress=progress_wrapper
            )
            results.append(result)

            # Track statistics
            if result.success:
                if result.error is None and "skipped" not in str(result):
                    successful += 1
                else:
                    skipped += 1
            else:
                failed += 1
                if result.error_type == 'RateLimitError':
                    logger.warning(f"Rate limit hit at video {i}/{total} - consider increasing delay")

            # Rate limiting
            if i < total:
                logger.debug(f"Waiting {self.delay}s before next request...")
                time.sleep(self.delay)

        logger.info(f"Batch complete: {successful} extracted, {skipped} skipped, {failed} failed")
        return results

    def process_playlist(
        self,
        playlist_url: str,
        skip_existing: bool = True,
        on_progress: Optional[Callable[[int, int, str, str], None]] = None,
    ) -> list[ExtractionResult]:
        """Process all videos in a YouTube playlist."""
        logger.info(f"Processing playlist: {playlist_url}")

        if on_progress:
            on_progress(0, 0, "", "fetching playlist...")

        try:
            video_ids = get_playlist_video_ids(playlist_url)
        except Exception as e:
            logger.error(f"Failed to fetch playlist: {e}", exc_info=True)
            raise PlaylistError(playlist_url, reason=str(e))

        if not video_ids:
            logger.warning(f"No videos found in playlist: {playlist_url}")
            return []

        logger.info(f"Found {len(video_ids)} videos in playlist")

        return self.process_videos(
            video_ids,
            skip_existing=skip_existing,
            on_progress=on_progress
        )

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Search transcripts for a query."""
        logger.debug(f"Searching transcripts for: '{query}' (limit={limit})")
        results = self.db.search_transcripts(query, limit)
        logger.debug(f"Found {len(results)} results")
        return results

    def get_stats(self) -> dict:
        """Get database statistics."""
        stats = self.db.get_stats()
        logger.debug(f"Database stats: {stats}")
        return stats

    def close(self):
        """Close database connection."""
        logger.debug("Closing database connection")
        self.db.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures database is closed."""
        self.close()
        return False
