"""Tests for checkpoint module — checksum validation, format, and helpers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from berb.pipeline.checkpoint import (
    _utcnow_iso,
    resume_from_checkpoint,
    validate_checkpoint_checksum,
    write_checkpoint,
)
from berb.pipeline.stages import Stage


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
