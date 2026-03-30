"""Local query cache for literature search results.

Caches search results by (query, source, limit) hash to avoid
redundant API calls. Cache entries expire after TTL_SEC seconds.
Cache directory: .berb_cache/literature/
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path(".berb_cache") / "literature"
_TTL_SEC = 86400 * 7  # 7 days (default for S2, OpenAlex)

# Per-source TTLs: arXiv updates daily at midnight, so 24h cache is optimal.
# Citation verification results are permanent (verified papers don't change).
_SOURCE_TTL: dict[str, float] = {
    "arxiv": 86400,         # 24 hours — arXiv metadata updates once/day
    "semantic_scholar": 86400 * 3,  # 3 days
    "openalex": 86400 * 3,  # 3 days
    "citation_verify": 86400 * 365,  # ~permanent
}


def _cache_dir(base: Path | None = None) -> Path:
    d = base or _DEFAULT_CACHE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_key(query: str, source: str, limit: int) -> str:
    """Deterministic cache key from query parameters."""
    raw = f"{query.strip().lower()}|{source.strip().lower()}|{limit}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def get_cached(
    query: str,
    source: str,
    limit: int,
    *,
    cache_base: Path | None = None,
    ttl: float | None = None,
) -> list[dict[str, Any]] | None:
    """Return cached results or None if miss/expired.

    If *ttl* is not provided, uses source-specific TTL from
    ``_SOURCE_TTL``, falling back to the global ``_TTL_SEC``.
    """
    d = _cache_dir(cache_base)
    key = cache_key(query, source, limit)
    path = d / f"{key}.json"

    if not path.exists():
        return None

    effective_ttl = ttl if ttl is not None else _SOURCE_TTL.get(source, _TTL_SEC)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = data.get("timestamp", 0)
        age_sec = time.time() - ts
        if age_sec > effective_ttl:
            logger.debug("Cache expired for key %s (age=%.0fs > ttl=%.0fs)",
                         key, age_sec, effective_ttl)
            return None
        papers = data.get("papers", [])
        if not isinstance(papers, list):
            return None
        age_str = _format_age(age_sec)
        logger.info(
            "[cache] HIT query=%r source=%s age=%s (%d papers)",
            query[:50], source, age_str, len(papers),
        )
        return papers
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _format_age(seconds: float) -> str:
    """Human-readable age string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.0f}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def put_cache(
    query: str,
    source: str,
    limit: int,
    papers: list[dict[str, Any]],
    *,
    cache_base: Path | None = None,
) -> None:
    """Write search results to cache atomically.

    BUG-006 fix: the previous ``path.write_text(...)`` call truncates the
    target file and then fills it in two separate I/O operations.  A
    concurrent writer (or a crash between truncate and write) leaves a
    zero-length or partial JSON file.  Subsequent reads hit JSONDecodeError,
    treat the entry as a cache miss, and trigger redundant API calls.

    The fix writes to a sibling temp file and renames it onto the target.
    ``Path.replace()`` maps to ``os.replace()`` which is atomic on POSIX and
    as close to atomic as Windows allows (the kernel swap is not interruptible
    by another writer operating on the same path).
    """
    d = _cache_dir(cache_base)
    key = cache_key(query, source, limit)
    path = d / f"{key}.json"

    payload = {
        "query": query,
        "source": source,
        "limit": limit,
        "timestamp": time.time(),
        "papers": papers,
    }
    serialized = json.dumps(payload, indent=2)

    # Write to a uniquely-named temp file in the same directory so that:
    #   (a) the rename is within the same filesystem (no cross-device error),
    #   (b) concurrent writers each have their own temp file and don't race on
    #       a shared ".tmp" name (Windows raises PermissionError if two threads
    #       try to replace/unlink the same file simultaneously).
    # os.replace() is atomic on POSIX and best-effort-atomic on Windows.
    fd, tmp_path = tempfile.mkstemp(dir=d, suffix=".tmp", prefix=f"{key}_")
    os.close(fd)
    try:
        Path(tmp_path).write_text(serialized, encoding="utf-8")
        os.replace(tmp_path, path)  # atomic: readers see old or new, never partial
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    logger.debug("Cached %d papers for key %s", len(papers), key)
    _evict_if_oversized(d)


_MAX_CACHE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB
_EVICT_FRACTION = 0.25  # evict oldest 25% when over limit


def _evict_if_oversized(cache_dir: Path) -> None:
    """Evict oldest cache entries when total size exceeds _MAX_CACHE_BYTES."""
    files = list(cache_dir.glob("*.json"))
    if not files:
        return
    total = sum(f.stat().st_size for f in files)
    if total <= _MAX_CACHE_BYTES:
        return

    # Sort by modification time ascending (oldest first)
    files.sort(key=lambda f: f.stat().st_mtime)
    evict_count = max(1, int(len(files) * _EVICT_FRACTION))
    evicted_bytes = 0
    for f in files[:evict_count]:
        try:
            evicted_bytes += f.stat().st_size
            f.unlink()
        except OSError:
            pass
    logger.info(
        "[cache] Evicted %d entries (%.1f MB) — cache was %.1f MB > limit %.1f MB",
        evict_count,
        evicted_bytes / 1024 / 1024,
        total / 1024 / 1024,
        _MAX_CACHE_BYTES / 1024 / 1024,
    )


def clear_cache(*, cache_base: Path | None = None) -> int:
    """Remove all cache files. Return count of files deleted."""
    d = _cache_dir(cache_base)
    count = 0
    for f in d.glob("*.json"):
        f.unlink()
        count += 1
    return count


def cache_stats(*, cache_base: Path | None = None) -> dict[str, Any]:
    """Return cache statistics."""
    d = _cache_dir(cache_base)
    files = list(d.glob("*.json"))
    total_bytes = sum(f.stat().st_size for f in files)
    return {
        "entries": len(files),
        "total_bytes": total_bytes,
        "cache_dir": str(d),
    }
