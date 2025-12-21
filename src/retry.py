"""Retry decorator with exponential backoff for handling transient failures.

Usage:
    @with_retry(max_attempts=3, backoff_factor=2.0)
    def fetch_data():
        ...

    @with_retry(retryable_exceptions=(RateLimitError, TimeoutError))
    def api_call():
        ...
"""

import functools
import random
import time
from typing import Callable, Optional, Tuple, Type, TypeVar, Union

from .exceptions import RateLimitError, TranscriptExtractorError
from .logging_config import get_logger

logger = get_logger('retry')

T = TypeVar('T')


def with_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        RateLimitError,
        TimeoutError,
        ConnectionError,
    ),
    on_retry: Optional[Callable[[Exception, int, float], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for retrying functions with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (including initial)
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_factor: Multiplier for delay after each retry
        jitter: Add random jitter to prevent thundering herd
        retryable_exceptions: Tuple of exception types to retry
        on_retry: Optional callback called before each retry
                  with (exception, attempt_number, delay)

    Returns:
        Decorated function with retry behavior

    Example:
        @with_retry(max_attempts=3, backoff_factor=2.0)
        def fetch_transcript(video_id):
            return get_transcript(video_id)

        # Will retry up to 3 times with delays: 1s, 2s, 4s
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception: Optional[Exception] = None
            delay = initial_delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)

                except retryable_exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        logger.error(
                            f"Failed after {max_attempts} attempts: {func.__name__}",
                            exc_info=True
                        )
                        raise

                    # Check if exception has a specific retry_after value
                    if hasattr(e, 'retry_after') and e.retry_after:
                        delay = min(e.retry_after, max_delay)

                    # Add jitter to prevent thundering herd
                    if jitter:
                        actual_delay = delay * (0.5 + random.random())
                    else:
                        actual_delay = delay

                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. "
                        f"Retrying in {actual_delay:.1f}s..."
                    )

                    # Call optional callback
                    if on_retry:
                        on_retry(e, attempt, actual_delay)

                    time.sleep(actual_delay)

                    # Increase delay for next attempt
                    delay = min(delay * backoff_factor, max_delay)

                except Exception:
                    # Non-retryable exception, re-raise immediately
                    raise

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


class RetryContext:
    """Context manager for retry blocks with state tracking.

    Useful when you need more control than the decorator provides.

    Example:
        retry = RetryContext(max_attempts=3)
        while retry.should_retry():
            try:
                result = do_something()
                break
            except RateLimitError as e:
                retry.record_failure(e)
        else:
            raise retry.last_exception
    """

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        self._attempt = 0
        self._delay = initial_delay
        self._last_exception: Optional[Exception] = None
        self._success = False

    @property
    def attempt(self) -> int:
        """Current attempt number (1-indexed)."""
        return self._attempt

    @property
    def last_exception(self) -> Optional[Exception]:
        """Last recorded exception."""
        return self._last_exception

    @property
    def succeeded(self) -> bool:
        """Whether the operation succeeded."""
        return self._success

    def should_retry(self) -> bool:
        """Check if we should make another attempt.

        Returns True and increments attempt counter if more attempts available.
        """
        if self._success:
            return False

        if self._attempt >= self.max_attempts:
            return False

        self._attempt += 1
        return True

    def record_success(self) -> None:
        """Record that the operation succeeded."""
        self._success = True
        logger.debug(f"Succeeded on attempt {self._attempt}")

    def record_failure(self, exception: Exception, wait: bool = True) -> None:
        """Record a failure and optionally wait before next attempt.

        Args:
            exception: The exception that occurred
            wait: Whether to sleep before returning
        """
        self._last_exception = exception

        if self._attempt >= self.max_attempts:
            logger.error(f"Failed after {self.max_attempts} attempts")
            return

        # Check for retry_after hint
        if hasattr(exception, 'retry_after') and exception.retry_after:
            self._delay = min(exception.retry_after, self.max_delay)

        # Calculate actual delay with jitter
        if self.jitter:
            actual_delay = self._delay * (0.5 + random.random())
        else:
            actual_delay = self._delay

        logger.warning(
            f"Attempt {self._attempt}/{self.max_attempts} failed: {exception}. "
            f"Retrying in {actual_delay:.1f}s..."
        )

        if wait:
            time.sleep(actual_delay)

        # Increase delay for next attempt
        self._delay = min(self._delay * self.backoff_factor, self.max_delay)


def retry_with_backoff(
    func: Callable[..., T],
    *args,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        RateLimitError,
        TimeoutError,
        ConnectionError,
    ),
    **kwargs
) -> T:
    """Functional interface for retrying a single call.

    Args:
        func: Function to call
        *args: Arguments to pass to function
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay between retries
        max_delay: Maximum delay between retries
        backoff_factor: Multiplier for delay after each retry
        retryable_exceptions: Exception types to retry
        **kwargs: Keyword arguments to pass to function

    Returns:
        Result of the function call

    Example:
        result = retry_with_backoff(
            get_transcript,
            video_id,
            max_attempts=5,
            retryable_exceptions=(RateLimitError,)
        )
    """
    decorated = with_retry(
        max_attempts=max_attempts,
        initial_delay=initial_delay,
        max_delay=max_delay,
        backoff_factor=backoff_factor,
        retryable_exceptions=retryable_exceptions,
    )(func)

    return decorated(*args, **kwargs)
