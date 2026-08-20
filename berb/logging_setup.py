"""Run-correlated logging for the Berb pipeline (A4-1).

The pipeline has ~278 ``logging.getLogger(__name__)`` call sites, all
printf-style free text, and **no record carried a run_id or stage**. Because
DAG-level stages execute concurrently via ``asyncio.gather()``, interleaved
log lines from different stages were mutually indistinguishable.

This fixes that without touching a single call site.

Why a ``LogRecordFactory`` rather than a ``Filter`` or ``LoggerAdapter``:

- A ``LoggerAdapter`` must be threaded to every call site — exactly what we
  are avoiding.
- A ``Filter`` on the ``berb`` logger does *not* see records from child
  loggers (``berb.pipeline.runner`` etc.); logger filters only apply to
  records logged directly on that logger. A filter on a *handler* works,
  but only for records that specific handler processes — so run_id would
  vanish the moment an embedding application supplied its own handler.
- The record factory runs for every record ever created, so ``run_id`` and
  ``stage`` are attached regardless of who ends up formatting them.

Values come from ``contextvars``: per-asyncio-task, and copied into
``asyncio.to_thread`` workers, so concurrently-running stages cannot
cross-attribute each other the way a plain module global would.
"""

from __future__ import annotations

import contextvars
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from berb.llm.cost_tracker import current_attribution

BERB_LOGGER_NAME = "berb"
_HANDLER_FLAG = "_berb_run_handler"
_LOG_FORMAT = "%(asctime)s [%(run_id)s|%(stage)s] %(levelname)-7s %(name)s: %(message)s"

_current_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "berb_log_run_id", default=None
)

_factory_installed = False


def set_run_id(run_id: str) -> None:
    """Tag subsequent log records in this context with *run_id*.

    Used by the runner, whose whole body is the run — there is nothing to
    unwind at the end, so it takes the plain setter rather than wrapping
    ~180 lines in a ``with`` block.
    """
    _current_run_id.set(run_id)


@contextmanager
def run_context(run_id: str) -> Iterator[None]:
    """Scoped form of :func:`set_run_id`, restoring the prior value on exit."""
    token = _current_run_id.set(run_id)
    try:
        yield
    finally:
        _current_run_id.reset(token)


def _install_record_factory() -> None:
    """Chain a factory that stamps run_id/stage onto every LogRecord."""
    global _factory_installed  # noqa: PLW0603
    if _factory_installed:
        return

    previous = logging.getLogRecordFactory()

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        # Always set both: a record emitted outside any run (CLI setup,
        # import time) would otherwise raise KeyError in the formatter.
        record.run_id = _current_run_id.get() or "-"
        stage, _phase = current_attribution()
        record.stage = f"s{stage:02d}" if stage is not None else "--"
        return record

    logging.setLogRecordFactory(factory)
    _factory_installed = True


def configure_run_logging(level: int = logging.INFO) -> None:
    """Install run-correlated logging. Idempotent; safe to call per run.

    Attaches a rendering handler only when nothing else has configured
    logging, so an embedding application (or pytest) keeps ownership of
    output. The record factory runs either way, so ``run_id``/``stage`` are
    available to whatever formatter ends up handling the record.
    """
    _install_record_factory()

    logger = logging.getLogger(BERB_LOGGER_NAME)

    if any(getattr(h, _HANDLER_FLAG, False) for h in logger.handlers):
        return
    if logger.handlers or logging.getLogger().handlers:
        return

    # Level goes on the handler, NOT on the `berb` logger. Setting it on the
    # logger would filter records for the whole package before they can
    # propagate — which silently breaks any consumer that raises verbosity
    # downstream (pytest's caplog.at_level(DEBUG) adjusts root, not `berb`,
    # so berb.*'s DEBUG records would vanish before ever reaching it).
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    setattr(handler, _HANDLER_FLAG, True)
    logger.addHandler(handler)
