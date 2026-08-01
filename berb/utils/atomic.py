"""Atomic file-replacement helpers.

``os.replace()`` is atomic on POSIX but can fail transiently on Windows: the
kernel refuses a replace while any other handle is open on the destination, so
antivirus scanning, the search indexer, or a second thread writing the same
target all surface as ``PermissionError`` (WinError 5) or ``OSError``
(WinError 32, sharing violation). Retrying with backoff is the standard remedy.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import time
from pathlib import Path

__all__ = ["replace_with_retry"]

# WinError 32 (ERROR_SHARING_VIOLATION) arrives as OSError, not PermissionError.
_SHARING_VIOLATION = 32


def replace_with_retry(
    src: Path | str,
    dst: Path | str,
    *,
    attempts: int = 5,
    base_delay_sec: float = 0.01,
) -> None:
    """Atomically replace *dst* with *src*, retrying on transient file locks.

    Args:
        src: Path to the fully-written temp file.
        dst: Path to replace. Readers see either the old or the new file,
            never a partial one.
        attempts: Total tries, including the first. Must be >= 1.
        base_delay_sec: Delay before the first retry; doubles each attempt.

    Raises:
        PermissionError: The destination stayed locked for every attempt.
        OSError: Any non-transient replace failure, raised immediately.
    """
    src_path = Path(src)
    dst_path = Path(dst)
    last_attempt = max(attempts, 1) - 1

    for attempt in range(last_attempt + 1):
        try:
            src_path.replace(dst_path)
            return
        except PermissionError:
            if attempt == last_attempt:
                raise
        except OSError as exc:
            if getattr(exc, "winerror", None) != _SHARING_VIOLATION or attempt == last_attempt:
                raise
        time.sleep(base_delay_sec * (2**attempt))
