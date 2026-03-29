"""Time utilities for consistent UTC timestamp handling.

This module provides centralized datetime utilities to ensure
all timestamps across Berb use timezone-aware UTC datetimes.

Usage:
    from berb.utils.time import utcnow, utcnow_iso

    # Get current UTC datetime
    now = utcnow()

    # Get ISO-formatted UTC timestamp
    timestamp = utcnow_iso()

    # Get Unix timestamp (seconds since epoch)
    ts = utc_timestamp()

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Get current UTC datetime with timezone info.

    Returns:
        Timezone-aware datetime in UTC

    Example:
        >>> now = utcnow()
        >>> now.tzinfo
        datetime.timezone.utc
    """
    return datetime.now(timezone.utc)


def utcnow_iso(timespec: str = "seconds") -> str:
    """Get current UTC timestamp as ISO-formatted string.

    Args:
        timespec: Passed to datetime.isoformat()

    Returns:
        ISO 8601 formatted UTC timestamp

    Example:
        >>> ts = utcnow_iso()
        >>> ts  # doctest: +SKIP
        '2026-03-29T12:34:56+00:00'
    """
    return datetime.now(timezone.utc).isoformat(timespec=timespec)


def utc_timestamp() -> float:
    """Get current UTC time as Unix timestamp (seconds since epoch).

    Returns:
        Unix timestamp as float

    Example:
        >>> ts = utc_timestamp()
        >>> isinstance(ts, float)
        True
    """
    return datetime.now(timezone.utc).timestamp()


def utcnow_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Get current UTC timestamp as formatted string.

    Args:
        fmt: strftime format string

    Returns:
        Formatted UTC timestamp

    Example:
        >>> ts = utcnow_str("%Y%m%d_%H%M%S")
        >>> len(ts)  # doctest: +SKIP
        15
    """
    return datetime.now(timezone.utc).strftime(fmt)


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware and in UTC.

    If datetime is naive (no timezone), assumes it's UTC and makes it aware.
    If datetime has a different timezone, converts to UTC.

    Args:
        dt: Datetime to normalize

    Returns:
        Timezone-aware datetime in UTC

    Raises:
        ValueError: If dt is not a datetime instance

    Example:
        >>> from datetime import datetime, timezone
        >>> naive = datetime(2026, 3, 29, 12, 0, 0)
        >>> aware = ensure_utc(naive)
        >>> aware.tzinfo
        datetime.timezone.utc
    """
    if not isinstance(dt, datetime):
        raise TypeError(f"Expected datetime, got {type(dt).__name__}")

    if dt.tzinfo is None:
        # Naive datetime - assume UTC
        return dt.replace(tzinfo=timezone.utc)

    # Convert to UTC if needed
    return dt.astimezone(timezone.utc)


def duration_seconds(start: datetime, end: datetime | None = None) -> float:
    """Calculate duration between two UTC datetimes.

    Args:
        start: Start datetime
        end: End datetime (defaults to now)

    Returns:
        Duration in seconds as float

    Example:
        >>> import time
        >>> start = utcnow()
        >>> time.sleep(0.1)
        >>> duration_seconds(start) > 0.1
        True
    """
    if end is None:
        end = utcnow()

    # Ensure both are UTC
    start_utc = ensure_utc(start)
    end_utc = ensure_utc(end)

    return (end_utc - start_utc).total_seconds()
