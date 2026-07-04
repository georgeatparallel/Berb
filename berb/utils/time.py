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

import threading
import time
from datetime import UTC, datetime

# Guards _last_timestamp / _last_monotonic below. Windows' system clock
# (GetSystemTimeAsFileTime) only advances in ~15.6ms ticks, so a tight loop
# of datetime.now(UTC).timestamp() calls can return identical values —
# breaking callers that rely on utc_timestamp() for uniqueness (e.g.
# snapshot version strings, generated IDs).
_ts_lock = threading.Lock()
_last_timestamp: float = 0.0
_last_monotonic: float = 0.0


def utcnow() -> datetime:
    """Get current UTC datetime with timezone info.

    Returns:
        Timezone-aware datetime in UTC

    Example:
        >>> now = utcnow()
        >>> now.tzinfo
        datetime.timezone.utc
    """
    return datetime.now(UTC)


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
    return datetime.now(UTC).isoformat(timespec=timespec)


def utc_timestamp() -> float:
    """Get current UTC time as Unix timestamp (seconds since epoch).

    Guarantees strictly increasing (and therefore unique) values across
    calls within the same process, even on platforms where the system
    clock's resolution is coarser than typical call rates (e.g. Windows'
    ~15.6ms tick). When the wall clock hasn't advanced since the previous
    call, a sub-tick offset derived from ``time.monotonic()`` is added so
    repeated rapid calls never collide. Callers that use this value for
    version strings / generated IDs (e.g. self_correcting.py) depend on
    this uniqueness guarantee.

    Returns:
        Unix timestamp as float

    Example:
        >>> ts = utc_timestamp()
        >>> isinstance(ts, float)
        True
    """
    global _last_timestamp, _last_monotonic

    now = datetime.now(UTC).timestamp()
    mono = time.monotonic()

    with _ts_lock:
        if now <= _last_timestamp:
            # Wall clock hasn't advanced (or went backwards) since the last
            # call — nudge forward using elapsed monotonic time so the
            # returned value is always > the previous one.
            elapsed = max(mono - _last_monotonic, 1e-6)
            now = _last_timestamp + elapsed

        _last_timestamp = now
        _last_monotonic = mono

    return now


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
    return datetime.now(UTC).strftime(fmt)


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
        return dt.replace(tzinfo=UTC)

    # Convert to UTC if needed
    return dt.astimezone(UTC)


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
