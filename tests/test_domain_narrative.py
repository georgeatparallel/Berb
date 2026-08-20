"""Unit tests for P3-04's sub-domain historian (_build_domain_narrative,
berb/pipeline/stage_impls/_synthesis.py) and its wiring into stage 7.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.pipeline import executor as rc_executor
from berb.pipeline.stage_impls._synthesis import _build_domain_narrative
from berb.pipeline.stages import StageStatus


def _write_prior_artifact(
    run_dir: Path, stage_num: int, filename: str, content: str
) -> None:
    stage_dir = run_dir / f"stage-{stage_num:02d}"
    target = stage_dir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


class TestBuildDomainNarrative:
    def test_returns_empty_without_candidates(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        llm = MagicMock()
        assert _build_domain_narrative(llm, run_dir, "test topic") == ""
        llm.chat.assert_not_called()

    def test_sends_chronologically_sorted_titles(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        candidates = [
            {"title": "Newer Paper", "year": 2023},
            {"title": "Older Paper", "year": 2018},
        ]
        _write_prior_artifact(
            run_dir, 4, "candidates.jsonl", "\n".join(json.dumps(c) for c in candidates)
        )
        llm = MagicMock()
        llm.chat.return_value = MagicMock(
            content="The field started with X and evolved to Y."
        )

        result = _build_domain_narrative(llm, run_dir, "test topic")

        assert result == "The field started with X and evolved to Y."
        prompt = llm.chat.call_args.args[0][0]["content"]
        older_idx = prompt.index("Older Paper")
        newer_idx = prompt.index("Newer Paper")
        assert older_idx < newer_idx  # chronological order in the prompt

    def test_llm_failure_returns_empty(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _write_prior_artifact(
            run_dir,
            4,
            "candidates.jsonl",
            json.dumps({"title": "A Paper", "year": 2020}),
        )
        llm = MagicMock()
        llm.chat.side_effect = RuntimeError("unavailable")

        assert _build_domain_narrative(llm, run_dir, "test topic") == ""

    def test_skips_rows_without_title(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _write_prior_artifact(
            run_dir, 4, "candidates.jsonl", json.dumps({"year": 2020})
        )
        llm = MagicMock()

        assert _build_domain_narrative(llm, run_dir, "test topic") == ""
        llm.chat.assert_not_called()


class TestSynthesisStageWiring:
    @pytest.fixture()
    def rc_config(self, tmp_path: Path) -> RCConfig:
        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {"topic": "test-driven science", "domains": ["ml"]},
            "runtime": {"timezone": "UTC"},
            "notifications": {
                "channel": "local",
                "on_stage_start": True,
                "on_stage_fail": False,
                "on_gate_required": True,
            },
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key_env": "RC_TEST_KEY",
                "primary_model": "fake-model",
            },
        }
        return RCConfig.from_dict(
            data, project_root=tmp_path, check_paths=False, check_security=False
        )

    def test_domain_narrative_written_when_candidates_present(
        self, tmp_path: Path, rc_config: RCConfig
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _write_prior_artifact(
            run_dir,
            4,
            "candidates.jsonl",
            json.dumps({"title": "A Paper", "year": 2020}),
        )
        _write_prior_artifact(run_dir, 6, "cards/dummy.md", "# Card\nSome notes.")
        stage_dir = run_dir / "stage-07"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MagicMock()
        llm.chat.return_value = MagicMock(content="A narrative.")
        adapters = AdapterBundle()

        result = rc_executor._execute_synthesis(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )

        assert result.status == StageStatus.DONE
        assert (stage_dir / "domain_narrative.md").is_file()
        assert "domain_narrative.md" in result.artifacts

    def test_no_narrative_file_without_candidates(
        self, tmp_path: Path, rc_config: RCConfig
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-07"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MagicMock()
        llm.chat.return_value = MagicMock(content="# Synthesis\n## Gap 1\nSomething.")
        adapters = AdapterBundle()

        result = rc_executor._execute_synthesis(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )

        assert result.status == StageStatus.DONE
        assert not (stage_dir / "domain_narrative.md").exists()
        assert "domain_narrative.md" not in result.artifacts
