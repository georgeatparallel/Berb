"""berb/audit/reproducibility.py — write_reproducibility_files.

Scoped to what P2 actually adds: environment.yml/Dockerfile/requirements.txt
existing, and metadata.json carrying a real git SHA and the run's config.
The pre-existing ReproducibilityGenerator (fake cost/trace data) is
deliberately not exercised here or wired into the pipeline — see the
docstring on write_reproducibility_files.
"""

from __future__ import annotations

import json

from berb.audit.reproducibility import git_commit_sha, write_reproducibility_files


def test_write_reproducibility_files_writes_expected_set(tmp_path) -> None:
    written = write_reproducibility_files(tmp_path, "run-123", {"export": {"target_conference": "neurips"}})

    assert set(written) == {
        "environment.yml",
        "requirements.txt",
        "Dockerfile",
        "metadata.json",
    }
    for name in written:
        assert (tmp_path / name).exists()


def test_metadata_carries_run_id_and_config() -> None:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        write_reproducibility_files(Path(d), "run-abc", {"export": {"target_conference": "icml"}})
        metadata = json.loads((Path(d) / "metadata.json").read_text(encoding="utf-8"))

    assert metadata["run_id"] == "run-abc"
    assert metadata["config"] == {"export": {"target_conference": "icml"}}
    assert "git_commit" in metadata


def test_metadata_config_survives_unserializable_values() -> None:
    """dataclasses.asdict(RCConfig) can carry enums/paths; json.dumps(default=str)
    is the same escape hatch runner.py already uses for cost_report.json."""
    import tempfile
    from pathlib import Path

    class Weird:
        def __str__(self) -> str:
            return "weird-value"

    with tempfile.TemporaryDirectory() as d:
        write_reproducibility_files(Path(d), "run-xyz", {"thing": Weird()})
        metadata = json.loads((Path(d) / "metadata.json").read_text(encoding="utf-8"))

    assert metadata["config"] == {"thing": "weird-value"}


def test_git_commit_sha_returns_str_or_none() -> None:
    sha = git_commit_sha()
    assert sha is None or (isinstance(sha, str) and len(sha) == 40)
