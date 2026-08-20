"""Checkpoint and heartbeat — atomic state persistence for pipeline recovery.

P0 2026-04-02: Added Event Sourcing for debugging, audit trails, and state recovery.
P1 FIX: Added SHA-256 checksum + fsync() for durability.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from berb.pipeline.stages import Stage
from berb.utils.atomic import replace_with_retry

logger = logging.getLogger(__name__)


# ============================================================================
# Helpers
# ============================================================================


def _utcnow_iso() -> str:
    """Return current UTC time as ISO-8601 string (seconds precision)."""
    return datetime.now(UTC).isoformat(timespec="seconds")


# ============================================================================
# Heartbeat
# ============================================================================


def write_heartbeat(run_dir: Path, stage: Stage, run_id: str) -> None:
    """Write heartbeat file for sentinel watchdog monitoring."""
    heartbeat = {
        "run_id": run_id,
        "pid": os.getpid(),
        "last_stage": int(stage),
        "last_stage_name": stage.name,
        "timestamp": _utcnow_iso(),
    }
    (run_dir / "heartbeat.json").write_text(
        json.dumps(heartbeat, indent=2),
        encoding="utf-8",
    )


# ============================================================================
# Checkpoint
# ============================================================================


def write_checkpoint(run_dir: Path, stage: Stage, run_id: str) -> None:
    """Write checkpoint atomically via temp file + rename to prevent corruption.

    Includes SHA-256 checksum for integrity validation and fsync() for
    durability against power failure/crashes.
    """
    checkpoint = {
        "last_completed_stage": int(stage),
        "last_completed_name": stage.name,
        "run_id": run_id,
        "timestamp": _utcnow_iso(),
    }

    # Compute checksum of core fields
    checksum_data = f"{int(stage)}:{stage.name}:{run_id}"
    checkpoint["checksum"] = hashlib.sha256(checksum_data.encode()).hexdigest()[:16]

    target = run_dir / "checkpoint.json"
    fd, tmp_path = tempfile.mkstemp(dir=run_dir, suffix=".tmp", prefix="checkpoint_")
    os.close(fd)
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(checkpoint, indent=2))
            fh.flush()
            os.fsync(fh.fileno())

        replace_with_retry(Path(tmp_path), target)

        if hasattr(os, "O_DIRECTORY"):
            dir_fd = os.open(run_dir, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def validate_checkpoint_checksum(data: dict) -> bool:
    """Validate checkpoint checksum.

    Returns True if checksum is valid or missing (for backward compat).
    """
    if "checksum" not in data:
        logger.debug("Checkpoint has no checksum (legacy format), accepting")
        return True

    expected = data["checksum"]
    stage = data.get("last_completed_stage")
    stage_name = data.get("last_completed_name")
    run_id = data.get("run_id")

    if None in (stage, stage_name, run_id):
        logger.warning("Checkpoint missing required fields for checksum validation")
        return False

    checksum_data = f"{stage}:{stage_name}:{run_id}"
    actual = hashlib.sha256(checksum_data.encode()).hexdigest()[:16]

    if actual != expected:
        logger.error(
            "Checkpoint checksum mismatch! Expected %s, got %s. "
            "Checkpoint may be corrupted or tampered with.",
            expected,
            actual,
        )
        return False

    return True


def read_checkpoint(run_dir: Path) -> Stage | None:
    """Read checkpoint and return the NEXT stage to execute, or None if no checkpoint.

    Validates checksum before returning. Returns None if corrupted.
    Now uses DAG resolution instead of STAGE_SEQUENCE.
    """
    from berb.pipeline.resolution import resolve_stage_order

    cp_path = run_dir / "checkpoint.json"
    if not cp_path.exists():
        return None
    try:
        data = json.loads(cp_path.read_text(encoding="utf-8"))

        if not validate_checkpoint_checksum(data):
            logger.error(
                "Checkpoint at %s failed checksum validation. "
                "File may be corrupted. Consider deleting and restarting.",
                cp_path,
            )
            return None

        last_num = data.get("last_completed_stage")
        if last_num is None:
            return None
        last_stage = Stage(last_num)
        order = resolve_stage_order()
        for i, stage in enumerate(order):
            if stage == last_stage:
                if i + 1 < len(order):
                    return order[i + 1]
                return None
        return None
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.error("Failed to parse checkpoint: %s", e)
        return None


# ============================================================================
# Concurrency-safe checkpoint manager (Phase 3 — DAG parallelism)
# ============================================================================


class CheckpointManager:
    """Serializes concurrent checkpoint writes for the parallel DAG executor.

    The current ``write_checkpoint`` uses an atomic temp+rename pattern,
    which is safe for sequential writes. When parallel stages complete
    simultaneously (Phase 3 Step 7), this manager ensures only one write
    at a time updates the checkpoint file.
    """

    def __init__(self) -> None:
        import threading

        self._lock = threading.Lock()

    def write(self, run_dir: Path, stage: Stage, run_id: str) -> None:
        """Thread-safe checkpoint write."""
        with self._lock:
            write_checkpoint(run_dir, stage, run_id)

    def read(self, run_dir: Path) -> Stage | None:
        """Thread-safe checkpoint read (readers don't conflict on write lock)."""
        return read_checkpoint(run_dir)


def resume_from_checkpoint(
    run_dir: Path, default_stage: Stage = Stage.TOPIC_INIT
) -> Stage:
    """Resolve the stage to resume from using checkpoint metadata."""
    next_stage = read_checkpoint(run_dir)
    return next_stage if next_stage is not None else default_stage
