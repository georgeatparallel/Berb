"""A4-1: run-correlated logging.

Before this, all ~278 getLogger(__name__) call sites emitted records with no
run_id and no stage, so concurrently-executing DAG stages produced mutually
unattributable log lines.
"""

from __future__ import annotations

import logging

from berb.llm.cost_tracker import stage_attribution
from berb.logging_setup import (
    configure_run_logging,
    run_context,
    set_run_id,
)


def _record(name: str = "berb.pipeline.runner") -> logging.LogRecord:
    """Build a record through the live factory, as logging itself would."""
    return logging.getLogRecordFactory()(
        name, logging.INFO, __file__, 1, "hello", None, None
    )


def test_record_carries_run_id_and_stage() -> None:
    configure_run_logging()
    with run_context("rc-abc123"), stage_attribution(17, "G: Paper Writing"):
        record = _record()
    assert record.run_id == "rc-abc123"
    assert record.stage == "s17"


def test_record_outside_a_run_still_formats() -> None:
    """A record emitted at import/CLI time must not KeyError the formatter."""
    configure_run_logging()
    record = _record("berb.cli")
    assert record.run_id == "-"
    assert record.stage == "--"
    formatted = logging.Formatter("[%(run_id)s|%(stage)s] %(message)s").format(record)
    assert formatted == "[-|--] hello"


def test_child_loggers_are_stamped_too() -> None:
    """The reason this uses a record factory rather than a logger Filter:
    filters on the `berb` logger never see records from `berb.*` children."""
    configure_run_logging()
    with run_context("rc-child"):
        record = _record("berb.literature.arxiv")
    assert record.run_id == "rc-child"


def test_run_context_restores_previous_value() -> None:
    configure_run_logging()
    set_run_id("outer")
    with run_context("inner"):
        assert _record().run_id == "inner"
    assert _record().run_id == "outer"


def test_configure_is_idempotent() -> None:
    """Called once per run (and again on PIVOT recursion) — must not stack
    handlers or re-chain the record factory each time."""
    configure_run_logging()
    factory_after_first = logging.getLogRecordFactory()
    handlers_after_first = list(logging.getLogger("berb").handlers)

    configure_run_logging()
    configure_run_logging()

    assert logging.getLogRecordFactory() is factory_after_first
    assert logging.getLogger("berb").handlers == handlers_after_first


def test_does_not_raise_the_berb_logger_level() -> None:
    """Regression: an earlier draft did setLevel(INFO) on the `berb` logger,
    which filtered every berb.* DEBUG record for the rest of the process.
    Consumers raise verbosity elsewhere (pytest's caplog.at_level(DEBUG)
    adjusts root, not `berb`), so those records vanished before reaching
    them — an order-dependent failure that only showed up once a runner test
    had configured logging first. The level belongs on our handler."""
    configure_run_logging()
    berb_logger = logging.getLogger("berb")
    assert berb_logger.level == logging.NOTSET, (
        "configure_run_logging must not set a level on the berb logger; "
        "it suppresses DEBUG package-wide"
    )


def test_debug_records_survive_configuration(caplog) -> None:
    """The concrete symptom of the bug above: a berb.* DEBUG record must
    still reach caplog after configure_run_logging() has run."""
    configure_run_logging()
    child = logging.getLogger("berb.reasoning.registry")
    with caplog.at_level(logging.DEBUG):
        child.debug("auto_register_all already called, skipping")
    assert "already called" in caplog.text


def test_does_not_steal_output_from_configured_root() -> None:
    """pytest and embedding apps own root; we must not attach a competing
    handler (which would double-emit) — the factory still stamps records."""
    root = logging.getLogger()
    sentinel = logging.NullHandler()
    root.addHandler(sentinel)
    berb_logger = logging.getLogger("berb")
    saved = list(berb_logger.handlers)
    berb_logger.handlers.clear()
    try:
        configure_run_logging()
        assert berb_logger.handlers == []
        with run_context("rc-root"):
            assert _record().run_id == "rc-root"
    finally:
        berb_logger.handlers[:] = saved
        root.removeHandler(sentinel)
