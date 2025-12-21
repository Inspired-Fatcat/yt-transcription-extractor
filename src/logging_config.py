"""Logging configuration for the YT Transcription Extractor.

Provides structured logging with:
- File rotation (10MB, 5 backups)
- Console handler for interactive use
- JSON formatter option for production
- Configurable log levels
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class JsonFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, 'video_id'):
            log_data['video_id'] = record.video_id
        if hasattr(record, 'details'):
            log_data['details'] = record.details

        return json.dumps(log_data)


class ColoredFormatter(logging.Formatter):
    """Colored console formatter for better readability."""

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[41m',  # Red background
    }
    RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        # Check if output supports colors (not redirected)
        if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
            color = self.COLORS.get(record.levelname, '')
            record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    json_format: bool = False,
    console: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> logging.Logger:
    """Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (creates directory if needed)
        json_format: Use JSON format for file logs
        console: Enable console logging
        max_bytes: Max size per log file before rotation
        backup_count: Number of backup files to keep

    Returns:
        Root logger for the application
    """
    # Get the root logger for our package
    logger = logging.getLogger('yt_extractor')
    logger.setLevel(getattr(logging, level.upper()))

    # Clear any existing handlers
    logger.handlers.clear()

    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)

        console_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        console_handler.setFormatter(ColoredFormatter(console_format, datefmt='%H:%M:%S'))
        logger.addHandler(console_handler)

    # File handler with rotation
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)

        if json_format:
            file_handler.setFormatter(JsonFormatter())
        else:
            file_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(module)s:%(lineno)d | %(message)s"
            file_handler.setFormatter(logging.Formatter(file_format))

        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger for a specific module.

    Args:
        name: Module name (e.g., 'extractor', 'transcript')

    Returns:
        Logger instance
    """
    return logging.getLogger(f'yt_extractor.{name}')


class LogContext:
    """Context manager for adding extra fields to log records."""

    def __init__(self, logger: logging.Logger, **fields):
        self.logger = logger
        self.fields = fields
        self.old_factory = None

    def __enter__(self):
        self.old_factory = logging.getLogRecordFactory()
        fields = self.fields

        def record_factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            for key, value in fields.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.setLogRecordFactory(self.old_factory)
        return False


def log_exception(logger: logging.Logger, exc: Exception,
                  message: str = "An error occurred",
                  level: int = logging.ERROR) -> None:
    """Log an exception with full context.

    Args:
        logger: Logger instance
        exc: Exception to log
        message: Custom message prefix
        level: Log level (default ERROR)
    """
    extra = {}
    if hasattr(exc, 'video_id'):
        extra['video_id'] = exc.video_id
    if hasattr(exc, 'details'):
        extra['details'] = exc.details

    logger.log(level, f"{message}: {exc}", exc_info=True, extra=extra)
