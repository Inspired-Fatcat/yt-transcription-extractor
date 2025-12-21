"""Custom exceptions for the YT Transcription Extractor.

Exception Hierarchy:
    TranscriptExtractorError (base)
    ├── ExtractionError
    │   ├── TranscriptNotFoundError
    │   ├── VideoNotFoundError
    │   ├── RateLimitError (with retry_after)
    │   └── TranscriptDisabledError
    ├── DatabaseError
    │   ├── ConnectionError
    │   └── IntegrityError
    ├── ValidationError
    └── ConfigurationError
"""

from typing import Optional


class TranscriptExtractorError(Exception):
    """Base exception for all transcript extractor errors."""

    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


# =============================================================================
# Extraction Errors
# =============================================================================

class ExtractionError(TranscriptExtractorError):
    """Base class for extraction-related errors."""

    def __init__(self, message: str, video_id: Optional[str] = None, **kwargs):
        self.video_id = video_id
        details = kwargs.pop('details', {})
        if video_id:
            details['video_id'] = video_id
        super().__init__(message, details=details)


class TranscriptNotFoundError(ExtractionError):
    """Raised when no transcript is available for a video."""

    def __init__(self, video_id: str, language: Optional[str] = None,
                 available_languages: Optional[list] = None):
        self.language = language
        self.available_languages = available_languages or []
        message = f"No transcript found for video '{video_id}'"
        if language:
            message += f" in language '{language}'"
        super().__init__(
            message,
            video_id=video_id,
            details={
                'requested_language': language,
                'available_languages': self.available_languages
            }
        )


class TranscriptDisabledError(ExtractionError):
    """Raised when transcripts are disabled for a video."""

    def __init__(self, video_id: str):
        super().__init__(
            f"Transcripts are disabled for video '{video_id}'",
            video_id=video_id
        )


class VideoNotFoundError(ExtractionError):
    """Raised when a video cannot be found or accessed."""

    def __init__(self, video_id: str, reason: Optional[str] = None):
        self.reason = reason
        message = f"Video '{video_id}' not found"
        if reason:
            message += f": {reason}"
        super().__init__(message, video_id=video_id, details={'reason': reason})


class RateLimitError(ExtractionError):
    """Raised when YouTube rate-limits the request.

    Attributes:
        retry_after: Suggested wait time in seconds before retrying
    """

    def __init__(self, video_id: Optional[str] = None,
                 retry_after: Optional[int] = None,
                 message: Optional[str] = None):
        self.retry_after = retry_after or 60  # Default to 60 seconds
        msg = message or "YouTube is rate-limiting requests"
        if retry_after:
            msg += f" (retry after {retry_after}s)"
        super().__init__(msg, video_id=video_id, details={'retry_after': self.retry_after})


class PlaylistError(ExtractionError):
    """Raised when there's an error processing a playlist."""

    def __init__(self, playlist_id: str, reason: Optional[str] = None):
        self.playlist_id = playlist_id
        message = f"Error processing playlist '{playlist_id}'"
        if reason:
            message += f": {reason}"
        super().__init__(message, details={'playlist_id': playlist_id, 'reason': reason})


# =============================================================================
# Database Errors
# =============================================================================

class DatabaseError(TranscriptExtractorError):
    """Base class for database-related errors."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""

    def __init__(self, db_path: str, reason: Optional[str] = None):
        self.db_path = db_path
        message = f"Failed to connect to database at '{db_path}'"
        if reason:
            message += f": {reason}"
        super().__init__(message, details={'db_path': db_path, 'reason': reason})


class DatabaseIntegrityError(DatabaseError):
    """Raised when a database integrity constraint is violated."""

    def __init__(self, message: str, constraint: Optional[str] = None):
        self.constraint = constraint
        super().__init__(message, details={'constraint': constraint})


class TransactionError(DatabaseError):
    """Raised when a database transaction fails."""

    def __init__(self, operation: str, reason: Optional[str] = None):
        self.operation = operation
        message = f"Transaction failed during '{operation}'"
        if reason:
            message += f": {reason}"
        super().__init__(message, details={'operation': operation, 'reason': reason})


# =============================================================================
# Validation Errors
# =============================================================================

class ValidationError(TranscriptExtractorError):
    """Raised when data validation fails."""

    def __init__(self, message: str, field: Optional[str] = None,
                 value: Optional[str] = None):
        self.field = field
        self.value = value
        details = {}
        if field:
            details['field'] = field
        if value is not None:
            details['value'] = str(value)[:100]  # Truncate long values
        super().__init__(message, details=details)


class InvalidVideoIdError(ValidationError):
    """Raised when a video ID is invalid."""

    def __init__(self, video_id: str):
        super().__init__(
            f"Invalid video ID: '{video_id}' (must be 11 characters)",
            field='video_id',
            value=video_id
        )


class InvalidUrlError(ValidationError):
    """Raised when a URL is invalid or cannot be parsed."""

    def __init__(self, url: str, reason: Optional[str] = None):
        message = f"Invalid URL: '{url}'"
        if reason:
            message += f" ({reason})"
        super().__init__(message, field='url', value=url)


# =============================================================================
# Configuration Errors
# =============================================================================

class ConfigurationError(TranscriptExtractorError):
    """Raised when there's a configuration problem."""

    def __init__(self, message: str, config_key: Optional[str] = None):
        self.config_key = config_key
        super().__init__(message, details={'config_key': config_key})


class MissingConfigError(ConfigurationError):
    """Raised when a required configuration value is missing."""

    def __init__(self, config_key: str):
        super().__init__(
            f"Missing required configuration: '{config_key}'",
            config_key=config_key
        )
