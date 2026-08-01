"""Tests for checkpoint module — checksum validation, format, and helpers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from berb.pipeline.checkpoint import (
    _utcnow_iso,
    resume_from_checkpoint,
    validate_checkpoint_checksum,
    write_checkpoint,
)
from berb.pipeline.stages import Stage
from berb.utils.atomic import replace_with_retry as _replace_with_retry


def test_validate_checkpoint_checksum_accepts_valid() -> None:
    """A correctly-signed checkpoint passes validation."""
    data = {
        "last_completed_stage": 10,
        "last_completed_name": "CODE_GENERATION",
        "run_id": "test-run-001",
    }
    import hashlib

    checksum_data = f"{data['last_completed_stage']}:{data['last_completed_name']}:{data['run_id']}"
    data["checksum"] = hashlib.sha256(checksum_data.encode()).hexdigest()[:16]

    assert validate_checkpoint_checksum(data) is True


def test_validate_checkpoint_checksum_rejects_tampered() -> None:
    """A checkpoint with a wrong checksum is rejected."""
    data = {
        "last_completed_stage": 5,
        "last_completed_name": "LITERATURE_SCREEN",
        "run_id": "run-42",
        "checksum": "deadbeef12345678",  # deliberately wrong
    }
    assert validate_checkpoint_checksum(data) is False


def test_validate_checkpoint_accepts_legacy_format() -> None:
    """Old checkpoints without a checksum field are accepted for backward compat."""
    data = {
        "last_completed_stage": 1,
        "last_completed_name": "TOPIC_INIT",
        "run_id": "legacy-run",
    }
    assert validate_checkpoint_checksum(data) is True


def test_validate_checkpoint_rejects_missing_fields() -> None:
    """Missing required fields returns False."""
    data = {
        "checksum": "abc",
        "last_completed_stage": 1,
        # missing last_completed_name and run_id
    }
    assert validate_checkpoint_checksum(data) is False


def test_write_and_read_checkpoint_roundtrip() -> None:
    """Writing a checkpoint and reading it returns the correct next stage."""
    import hashlib

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        write_checkpoint(run_dir, Stage.EXPERIMENT_DESIGN, "test-roundtrip")

        cp_path = run_dir / "checkpoint.json"
        assert cp_path.exists()
        data = json.loads(cp_path.read_text(encoding="utf-8"))

        expected_cs = hashlib.sha256(
            f"{int(Stage.EXPERIMENT_DESIGN)}:{Stage.EXPERIMENT_DESIGN.name}:test-roundtrip".encode()
        ).hexdigest()[:16]
        assert data["checksum"] == expected_cs
        assert data["last_completed_stage"] == 9  # EXPERIMENT_DESIGN = 9


def test_resume_from_checkpoint_no_checkpoint() -> None:
    """resume_from_checkpoint returns default_stage when no checkpoint exists."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        result = resume_from_checkpoint(run_dir, Stage.TOPIC_INIT)
        assert result == Stage.TOPIC_INIT


def test_utcnow_iso_format() -> None:
    """_utcnow_iso returns an ISO-8601 formatted string."""
    result = _utcnow_iso()
    assert isinstance(result, str)
    assert "T" in result  # ISO-8601 date+time separator
    assert result.endswith("+00:00") or result.endswith("Z") or "+00" in result


class TestReplaceWithRetry:
    """Regression tests for the Windows transient-file-lock retry wrapper.

    Windows can intermittently raise PermissionError (WinError 5) from
    Path.replace() when another process briefly holds an open handle on the
    target (real-time antivirus, search indexer). Reproduced via
    `pytest tests/test_berb_runner.py -q` — 3 of ~43 tests failed
    intermittently with this exact error under concurrent DAG stage
    execution before this fix.
    """

    def test_succeeds_immediately_when_no_contention(self, tmp_path: Path) -> None:
        src = tmp_path / "src.tmp"
        dst = tmp_path / "dst.json"
        src.write_text("content", encoding="utf-8")

        _replace_with_retry(src, dst)

        assert dst.read_text(encoding="utf-8") == "content"
        assert not src.exists()

    def test_retries_and_succeeds_after_transient_permission_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src.tmp"
        dst = tmp_path / "dst.json"
        src.write_text("content", encoding="utf-8")

        real_replace = Path.replace
        calls: list[int] = []

        def flaky_replace(self: Path, target: Path) -> Path:
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("[WinError 5] Access is denied")
            return real_replace(self, target)

        with (
            patch.object(Path, "replace", flaky_replace),
            patch("berb.utils.atomic.time.sleep") as mock_sleep,
        ):
            _replace_with_retry(src, dst, attempts=5, base_delay_sec=0.01)

        assert len(calls) == 3
        assert dst.read_text(encoding="utf-8") == "content"
        assert mock_sleep.call_count == 2  # slept before attempts 2 and 3

    def test_reraises_after_exhausting_attempts(self, tmp_path: Path) -> None:
        src = tmp_path / "src.tmp"
        dst = tmp_path / "dst.json"
        src.write_text("content", encoding="utf-8")

        def always_fails(self: Path, target: Path) -> Path:
            raise PermissionError("[WinError 5] Access is denied")

        with patch.object(Path, "replace", always_fails), patch("berb.utils.atomic.time.sleep"):
            with pytest.raises(PermissionError):
                _replace_with_retry(src, dst, attempts=3, base_delay_sec=0.01)

    def test_write_checkpoint_survives_transient_lock(self, tmp_path: Path) -> None:
        """End-to-end: write_checkpoint() itself recovers from one transient failure."""
        real_replace = Path.replace
        calls: list[int] = []

        def flaky_replace(self: Path, target: Path) -> Path:
            calls.append(1)
            if len(calls) == 1:
                raise PermissionError("[WinError 5] Access is denied")
            return real_replace(self, target)

        with patch.object(Path, "replace", flaky_replace), patch("berb.utils.atomic.time.sleep"):
            write_checkpoint(tmp_path, Stage.EXPERIMENT_DESIGN, "test-flaky")

        cp_path = tmp_path / "checkpoint.json"
        assert cp_path.exists()
        data = json.loads(cp_path.read_text(encoding="utf-8"))
        assert data["last_completed_stage"] == 9
