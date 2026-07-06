"""Retry utilities for LLM calls with specific error handling.

Implements Decorator Pattern for transparent retry logic.
Follows Berb's functional core / imperative shell paradigm.

SECURITY FIX #7: Prevents transient network errors from causing
pipeline failures with automatic retry and exponential backoff.
"""

from __future__ import annotations

import functools
import http.client
import logging
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def with_retry(
    exceptions: tuple[type[Exception], ...] = (Exception,),
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator for retry logic with exponential backoff.

    Args:
        exceptions: Tuple of exception types to catch and retry
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        backoff_factor: Multiply delay by this factor after each retry

    Returns:
        Decorated function with retry logic

    Example:
        @with_retry(
            exceptions=(http.client.IncompleteRead, ConnectionError),
            max_retries=3,
            base_delay=2.0,
        )
        def call_llm_streaming(...) -> LLMResponse:
            ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            delay = base_delay
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            "%s failed after %d attempts: %s", func.__name__, max_retries + 1, e
                        )
                        raise

                    logger.warning(
                        "%s attempt %d/%d failed: %s. Retrying in %.1fs...",
                        func.__name__,
                        attempt + 1,
                        max_retries + 1,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)

            # Should never reach here
            raise last_exception or RuntimeError("Unexpected retry loop exit")

        return wrapper

    return decorator


# Pre-configured retry decorators for common scenarios

incomplete_read_retry = with_retry(
    exceptions=(http.client.IncompleteRead,),
    max_retries=3,
    base_delay=2.0,
)
"""Retry decorator specifically for IncompleteRead errors."""

connection_retry = with_retry(
    exceptions=(ConnectionError, TimeoutError),
    max_retries=5,
    base_delay=1.0,
)
"""Retry decorator for connection issues."""

llm_call_retry = with_retry(
    exceptions=(
        http.client.IncompleteRead,
        ConnectionError,
        TimeoutError,
    ),
    max_retries=3,
    base_delay=2.0,
)
"""Retry decorator for general LLM calls."""
