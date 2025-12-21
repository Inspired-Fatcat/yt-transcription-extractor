"""Configuration loader for YT Transcription Extractor.

Loads configuration from:
1. Default values (hardcoded)
2. config.yaml file (if exists)
3. Environment variables (highest priority)

Environment variables use the pattern: YTE_SECTION__KEY
Examples:
    YTE_DATABASE__PATH=custom.db
    YTE_EXTRACTION__DELAY_BETWEEN_REQUESTS=60
    YTE_LOGGING__LEVEL=DEBUG
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from .logging_config import get_logger
from .exceptions import ConfigurationError, MissingConfigError

logger = get_logger('config')


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: str = "data/transcripts.db"


@dataclass
class ExtractionConfig:
    """Extraction configuration."""
    delay_between_requests: float = 1.0
    max_retries: int = 3
    retry_backoff_factor: float = 2.0
    retry_initial_delay: float = 1.0
    retry_max_delay: float = 60.0
    timeout_seconds: int = 30
    default_languages: list[str] = field(default_factory=lambda: ["en"])


@dataclass
class BatchConfig:
    """Batch processing configuration."""
    batch_size: int = 10
    delay_between_videos: float = 60.0
    delay_between_batches: float = 120.0
    state_directory: str = "data/batch_state"
    graceful_shutdown: bool = True


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: Optional[str] = "data/logs/extractor.log"
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    json_format: bool = False


@dataclass
class RateLimitingConfig:
    """Rate limiting detection configuration."""
    patterns: list[str] = field(default_factory=lambda: [
        "too many requests",
        "rate limit",
        "429",
        "blocked",
        "sign in to confirm"
    ])
    default_wait: int = 60


@dataclass
class Config:
    """Main configuration container."""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    batch: BatchConfig = field(default_factory=BatchConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    rate_limiting: RateLimitingConfig = field(default_factory=RateLimitingConfig)


def _deep_update(base: dict, updates: dict) -> dict:
    """Recursively update a dictionary."""
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _apply_env_overrides(config_dict: dict) -> dict:
    """Apply environment variable overrides.

    Environment variables use the pattern: YTE_SECTION__KEY
    Double underscore separates nested keys.
    """
    prefix = "YTE_"

    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue

        # Parse the key path
        path = key[len(prefix):].lower().split("__")
        if len(path) < 2:
            continue

        # Navigate to the correct position in config
        current = config_dict
        for part in path[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        # Convert value to appropriate type
        final_key = path[-1]
        if final_key in current:
            original = current[final_key]
            if isinstance(original, bool):
                value = value.lower() in ('true', '1', 'yes')
            elif isinstance(original, int):
                value = int(value)
            elif isinstance(original, float):
                value = float(value)
            elif isinstance(original, list):
                value = value.split(',')

        current[final_key] = value
        logger.debug(f"Applied env override: {key}")

    return config_dict


def _dict_to_config(config_dict: dict) -> Config:
    """Convert a dictionary to Config dataclass."""
    return Config(
        database=DatabaseConfig(**config_dict.get('database', {})),
        extraction=ExtractionConfig(**{
            k: v for k, v in config_dict.get('extraction', {}).items()
            if k in ExtractionConfig.__dataclass_fields__
        }),
        batch=BatchConfig(**{
            k: v for k, v in config_dict.get('batch', {}).items()
            if k in BatchConfig.__dataclass_fields__
        }),
        logging=LoggingConfig(**{
            k: v for k, v in config_dict.get('logging', {}).items()
            if k in LoggingConfig.__dataclass_fields__
        }),
        rate_limiting=RateLimitingConfig(**{
            k: v for k, v in config_dict.get('rate_limiting', {}).items()
            if k in RateLimitingConfig.__dataclass_fields__
        }),
    )


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from file and environment.

    Args:
        config_path: Path to config file. If None, searches for config.yaml
                    in the project root.

    Returns:
        Config object with all settings loaded
    """
    # Start with defaults
    config = Config()
    config_dict = {
        'database': {'path': config.database.path},
        'extraction': {
            'delay_between_requests': config.extraction.delay_between_requests,
            'max_retries': config.extraction.max_retries,
            'retry_backoff_factor': config.extraction.retry_backoff_factor,
            'retry_initial_delay': config.extraction.retry_initial_delay,
            'retry_max_delay': config.extraction.retry_max_delay,
            'timeout_seconds': config.extraction.timeout_seconds,
            'default_languages': config.extraction.default_languages,
        },
        'batch': {
            'batch_size': config.batch.batch_size,
            'delay_between_videos': config.batch.delay_between_videos,
            'delay_between_batches': config.batch.delay_between_batches,
            'state_directory': config.batch.state_directory,
            'graceful_shutdown': config.batch.graceful_shutdown,
        },
        'logging': {
            'level': config.logging.level,
            'file': config.logging.file,
            'max_bytes': config.logging.max_bytes,
            'backup_count': config.logging.backup_count,
            'json_format': config.logging.json_format,
        },
        'rate_limiting': {
            'patterns': config.rate_limiting.patterns,
            'default_wait': config.rate_limiting.default_wait,
        },
    }

    # Find config file
    if config_path is None:
        # Search in common locations
        search_paths = [
            Path("config.yaml"),
            Path("config.yml"),
            Path(__file__).parent.parent / "config.yaml",
            Path(__file__).parent.parent / "config.yml",
        ]
        for path in search_paths:
            if path.exists():
                config_path = str(path)
                break

    # Load from file if exists
    if config_path and Path(config_path).exists():
        if not YAML_AVAILABLE:
            logger.warning("PyYAML not installed, skipping config file. Install with: pip install pyyaml")
        else:
            try:
                with open(config_path, 'r') as f:
                    file_config = yaml.safe_load(f) or {}
                config_dict = _deep_update(config_dict, file_config)
                logger.debug(f"Loaded config from: {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config file: {e}")

    # Apply environment overrides
    config_dict = _apply_env_overrides(config_dict)

    # Convert to dataclass
    return _dict_to_config(config_dict)


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance.

    Loads config on first call, returns cached instance on subsequent calls.
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(config_path: Optional[str] = None) -> Config:
    """Reload configuration, clearing the cache.

    Args:
        config_path: Optional path to config file

    Returns:
        Newly loaded Config object
    """
    global _config
    _config = load_config(config_path)
    return _config
