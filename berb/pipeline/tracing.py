"""Lightweight structured tracing for the Berb pipeline.

Provides span-level timing and metadata without requiring an external
tracing backend. Traces are written to ``<run_dir>/trace.jsonl`` so they
can be consumed by any JSONL-aware tool (Jaeger via collector, custom
dashboards, or plain ``jq``).

Public API
----------
- ``new_trace(run_id)`` → ``str``              — start a new trace, return trace_id
- ``start_span(trace_id, name, **tags)`` → ``Span``
- ``Span`` (context manager) — records start/end, writes on exit
- ``get_trace(trace_id)`` → ``list[SpanRecord]`` — in-memory query

Thread-safe: all state is protected by a module-level ``RLock``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SpanRecord:
    """Immutable record written when a span finishes."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start_time: float          # monotonic seconds
    end_time: float            # monotonic seconds
    duration_ms: float
    status: str                # "ok" | "error"
    error: str | None
    tags: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "error": self.error,
            "tags": self.tags,
        }


# ---------------------------------------------------------------------------
# In-memory registry
# ---------------------------------------------------------------------------

_lock = threading.RLock()
_traces: dict[str, list[SpanRecord]] = {}  # trace_id → spans
_output_dir: Path | None = None


def configure(output_dir: str | Path) -> None:
    """Set the directory where ``trace.jsonl`` files are written.

    Call once at startup before any spans are created.
    """
    global _output_dir  # noqa: PLW0603
    with _lock:
        _output_dir = Path(output_dir)
        _output_dir.mkdir(parents=True, exist_ok=True)


def new_trace(run_id: str | None = None) -> str:
    """Create a new trace and return its trace_id."""
    trace_id = run_id or f"trace-{uuid.uuid4().hex[:12]}"
    with _lock:
        _traces[trace_id] = []
    logger.debug("New trace: %s", trace_id)
    return trace_id


def get_trace(trace_id: str) -> list[SpanRecord]:
    """Return all completed spans for *trace_id* (snapshot copy)."""
    with _lock:
        return list(_traces.get(trace_id, []))


def clear_trace(trace_id: str) -> None:
    """Remove a trace from memory (e.g. after persistence)."""
    with _lock:
        _traces.pop(trace_id, None)


# ---------------------------------------------------------------------------
# Span context manager
# ---------------------------------------------------------------------------

class Span:
    """A single unit of work within a trace.

    Use via ``start_span()`` or the ``span()`` context manager helper.
    """

    def __init__(
        self,
        trace_id: str,
        name: str,
        parent_span_id: str | None = None,
        **tags: Any,
    ) -> None:
        self.trace_id = trace_id
        self.span_id = f"span-{uuid.uuid4().hex[:8]}"
        self.parent_span_id = parent_span_id
        self.name = name
        self.tags: dict[str, Any] = dict(tags)
        self._start: float = 0.0
        self._error: str | None = None
        self._status: str = "ok"

    def set_tag(self, key: str, value: Any) -> None:
        self.tags[key] = value

    def set_error(self, exc: BaseException) -> None:
        self._status = "error"
        self._error = f"{type(exc).__name__}: {exc}"

    def __enter__(self) -> "Span":
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        end = time.monotonic()
        if exc_val is not None:
            self.set_error(exc_val)
        record = SpanRecord(
            trace_id=self.trace_id,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            name=self.name,
            start_time=self._start,
            end_time=end,
            duration_ms=(end - self._start) * 1000,
            status=self._status,
            error=self._error,
            tags=self.tags,
        )
        _record_span(record)
        return False  # do not suppress exceptions


def start_span(
    trace_id: str,
    name: str,
    parent_span_id: str | None = None,
    **tags: Any,
) -> Span:
    """Create and return a ``Span`` that must be used as a context manager."""
    return Span(trace_id=trace_id, name=name, parent_span_id=parent_span_id, **tags)


@contextmanager
def span(
    trace_id: str,
    name: str,
    parent_span_id: str | None = None,
    **tags: Any,
) -> Generator[Span, None, None]:
    """Convenience context manager that enters the span automatically.

    Example::

        with tracing.span(trace_id, "stage.literature", stage=3) as s:
            s.set_tag("query", query)
            papers = search_papers(query)
            s.set_tag("paper_count", len(papers))
    """
    with Span(trace_id=trace_id, name=name, parent_span_id=parent_span_id, **tags) as s:
        yield s


# ---------------------------------------------------------------------------
# Internal persistence
# ---------------------------------------------------------------------------

def _record_span(record: SpanRecord) -> None:
    """Append *record* to in-memory store and flush to disk."""
    with _lock:
        _traces.setdefault(record.trace_id, []).append(record)
        if _output_dir is not None:
            _flush_span(record)


def _flush_span(record: SpanRecord) -> None:
    """Write one span as a JSONL line to ``<output_dir>/<trace_id>/trace.jsonl``."""
    try:
        trace_dir = _output_dir / record.trace_id  # type: ignore[operator]
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_file = trace_dir / "trace.jsonl"
        with trace_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict()) + "\n")
    except OSError as exc:
        logger.warning("tracing: failed to write span to disk: %s", exc)
