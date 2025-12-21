"""Extract metadata from YouTube videos using yt-dlp."""

import re
from dataclasses import dataclass
from typing import Optional

import yt_dlp

from .exceptions import (
    VideoNotFoundError,
    RateLimitError,
    ValidationError,
    InvalidVideoIdError,
    PlaylistError,
)
from .logging_config import get_logger
from .retry import with_retry

logger = get_logger('video_info')

# Video ID validation pattern
VIDEO_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{11}$')


@dataclass
class VideoMetadata:
    """Stores YouTube video metadata."""
    video_id: str
    title: str
    channel: str
    channel_id: str
    upload_date: str
    duration: int  # seconds
    description: str
    view_count: Optional[int]
    like_count: Optional[int]
    thumbnail_url: str
    tags: list[str]

    def __post_init__(self):
        """Validate metadata after initialization."""
        # Validate video_id
        if not self.video_id:
            raise ValidationError("Video ID cannot be empty", field='video_id')
        if not VIDEO_ID_PATTERN.match(self.video_id):
            raise InvalidVideoIdError(self.video_id)

        # Validate title
        if not self.title:
            raise ValidationError("Title cannot be empty", field='title')

        # Validate duration
        if self.duration is not None and self.duration < 0:
            raise ValidationError(
                f"Duration cannot be negative: {self.duration}",
                field='duration',
                value=str(self.duration)
            )

        # Validate counts
        if self.view_count is not None and self.view_count < 0:
            logger.warning(f"Negative view count for {self.video_id}: {self.view_count}")
            self.view_count = 0
        if self.like_count is not None and self.like_count < 0:
            logger.warning(f"Negative like count for {self.video_id}: {self.like_count}")
            self.like_count = 0

        # Ensure tags is a list
        if self.tags is None:
            self.tags = []


def extract_video_id(url_or_id: str) -> str:
    """Extract video ID from a YouTube URL or return as-is if already an ID.

    Args:
        url_or_id: YouTube URL or video ID

    Returns:
        11-character video ID

    Raises:
        ValueError: If video ID cannot be extracted
    """
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            video_id = match.group(1)
            logger.debug(f"Extracted video ID: {video_id}")
            return video_id

    logger.warning(f"Could not extract video ID from: {url_or_id}")
    raise ValueError(f"Could not extract video ID from: {url_or_id}")


def _check_rate_limit_error(error_message: str) -> bool:
    """Check if an error message indicates rate limiting."""
    rate_limit_patterns = [
        'too many requests',
        'rate limit',
        '429',
        'sign in to confirm',
        'bot',
        'blocked',
    ]
    error_lower = error_message.lower()
    return any(pattern in error_lower for pattern in rate_limit_patterns)


@with_retry(
    max_attempts=3,
    initial_delay=2.0,
    backoff_factor=2.0,
    retryable_exceptions=(RateLimitError, ConnectionError, TimeoutError),
)
def get_video_metadata(
    video_id: str,
    timeout: int = 30,
) -> VideoMetadata:
    """Fetch metadata for a YouTube video.

    Args:
        video_id: YouTube video ID
        timeout: Request timeout in seconds

    Returns:
        VideoMetadata object

    Raises:
        VideoNotFoundError: Video doesn't exist or is unavailable
        RateLimitError: YouTube is rate-limiting requests
    """
    logger.debug(f"Fetching metadata for video: {video_id}")
    url = f"https://www.youtube.com/watch?v={video_id}"

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'socket_timeout': timeout,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            raise VideoNotFoundError(video_id, reason="No info returned")

        metadata = VideoMetadata(
            video_id=video_id,
            title=info.get('title', '') or 'Untitled',
            channel=info.get('channel', info.get('uploader', '')) or 'Unknown',
            channel_id=info.get('channel_id', '') or '',
            upload_date=info.get('upload_date', '') or '',
            duration=info.get('duration', 0) or 0,
            description=info.get('description', '') or '',
            view_count=info.get('view_count'),
            like_count=info.get('like_count'),
            thumbnail_url=info.get('thumbnail', '') or '',
            tags=info.get('tags', []) or [],
        )

        logger.info(f"Fetched metadata for '{metadata.title}' ({video_id})")
        return metadata

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)

        if _check_rate_limit_error(error_msg):
            logger.warning(f"Rate limited for video {video_id}")
            raise RateLimitError(video_id=video_id, retry_after=60)

        if 'Video unavailable' in error_msg or 'Private video' in error_msg:
            logger.warning(f"Video unavailable: {video_id}")
            raise VideoNotFoundError(video_id, reason="Video unavailable or private")

        logger.error(f"Download error for {video_id}: {e}")
        raise VideoNotFoundError(video_id, reason=str(e))

    except Exception as e:
        error_msg = str(e)

        if _check_rate_limit_error(error_msg):
            raise RateLimitError(video_id=video_id, retry_after=60)

        logger.error(f"Error fetching metadata for {video_id}: {e}", exc_info=True)
        raise VideoNotFoundError(video_id, reason=str(e))


def get_playlist_video_ids(
    playlist_url: str,
    timeout: int = 60,
) -> list[str]:
    """Extract all video IDs from a YouTube playlist.

    Args:
        playlist_url: YouTube playlist URL
        timeout: Request timeout in seconds

    Returns:
        List of video IDs

    Raises:
        PlaylistError: Failed to fetch playlist
        RateLimitError: YouTube is rate-limiting requests
    """
    logger.info(f"Fetching playlist: {playlist_url}")

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'ignoreerrors': True,
        'socket_timeout': timeout,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)

        if not info:
            logger.warning(f"No playlist info returned for: {playlist_url}")
            return []

        video_ids = []
        entries = info.get('entries', [])

        for entry in entries:
            if entry and entry.get('id'):
                video_ids.append(entry['id'])

        logger.info(f"Found {len(video_ids)} videos in playlist")
        return video_ids

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)

        if _check_rate_limit_error(error_msg):
            logger.warning(f"Rate limited for playlist: {playlist_url}")
            raise RateLimitError(retry_after=60)

        logger.error(f"Failed to fetch playlist: {e}")
        raise PlaylistError(playlist_url, reason=str(e))

    except Exception as e:
        logger.error(f"Error fetching playlist: {e}", exc_info=True)
        raise PlaylistError(playlist_url, reason=str(e))


def validate_video_id(video_id: str) -> bool:
    """Check if a string is a valid YouTube video ID.

    Args:
        video_id: String to validate

    Returns:
        True if valid, False otherwise
    """
    return bool(VIDEO_ID_PATTERN.match(video_id))
