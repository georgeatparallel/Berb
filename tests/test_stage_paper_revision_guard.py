"""Stage 19 (PAPER_REVISION) token-conservation wiring.

tasks/ars_integration_plan.md W6 Layer A. No existing test calls
_execute_paper_revision directly, so this file owns its own minimal
fixtures. A tiny fake LLM client stands in for a real one — no network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.pipeline import executor as rc_executor
from berb.pipeline.stages import StageStatus

_BASE_CONFIG: dict[str, Any] = {
    "project": {"name": "rc-test", "mode": "docs-first"},
    "research": {"topic": "test topic", "domains": ["ml"], "quality_threshold": 8.0},
    "runtime": {"timezone": "UTC"},
    "notifications": {"channel": "local"},
    "openclaw_bridge": {"use_memory": True, "use_message": True},
    "llm": {
        "provider": "openai-compatible",
        "base_url": "http://localhost:1234/v1",
        "api_key_env": "RC_TEST_KEY",
        "primary_model": "fake-model",
    },
    "security": {"hitl_required_stages": [5, 9, 20]},
    "experiment": {"mode": "sandbox"},
}


class _FakeLLMClient:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> Any:
        from berb.llm.client import LLMResponse

        return LLMResponse(content=self.response_text, model="fake-model")


def _rc_config(tmp_path: Path) -> RCConfig:
    data = dict(_BASE_CONFIG)
    data["knowledge_base"] = {"backend": "markdown", "root": str(tmp_path / "kb")}
    return RCConfig.from_dict(data, project_root=tmp_path, check_paths=False, check_security=False)


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "run" / "stage-17"
    d.mkdir(parents=True)
    (d / "paper_draft.md").write_text(
        "# Paper\n\nAccuracy improved by 62% \\cite{he2016deep}.\n", encoding="utf-8"
    )
    (tmp_path / "run" / "stage-18").mkdir()
    (tmp_path / "run" / "stage-18" / "reviews.md").write_text(
        "Please clarify the method section.", encoding="utf-8"
    )
    return d.parent


def _stage_dir(run_dir: Path) -> Path:
    d = run_dir / "stage-19"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_no_change_produces_no_artifact(run_dir: Path, tmp_path: Path) -> None:
    llm = _FakeLLMClient("# Paper\n\nAccuracy improved by 62% \\cite{he2016deep}.\n")
    result = rc_executor._execute_paper_revision(
        _stage_dir(run_dir), run_dir, _rc_config(tmp_path), AdapterBundle(), llm=llm
    )
    assert result.status is StageStatus.DONE
    assert "revision_findings.json" not in result.artifacts


def test_dropped_number_produces_advisory_artifact_but_stage_succeeds(
    run_dir: Path, tmp_path: Path
) -> None:
    llm = _FakeLLMClient("# Paper\n\nAccuracy improved significantly \\cite{he2016deep}.\n")
    result = rc_executor._execute_paper_revision(
        _stage_dir(run_dir), run_dir, _rc_config(tmp_path), AdapterBundle(), llm=llm
    )
    assert result.status is StageStatus.DONE  # advisory: never fails the stage
    assert "revision_findings.json" in result.artifacts
    payload = json.loads((_stage_dir(run_dir) / "revision_findings.json").read_text())
    assert len(payload) == 1
    assert payload[0]["check"] == "token_conservation"
    assert payload[0]["severity"] == "warn"
    assert payload[0]["locator"] == "62%"


def test_dropped_citation_produces_advisory_artifact(run_dir: Path, tmp_path: Path) -> None:
    llm = _FakeLLMClient("# Paper\n\nAccuracy improved by 62%.\n")
    result = rc_executor._execute_paper_revision(
        _stage_dir(run_dir), run_dir, _rc_config(tmp_path), AdapterBundle(), llm=llm
    )
    assert result.status is StageStatus.DONE
    payload = json.loads((_stage_dir(run_dir) / "revision_findings.json").read_text())
    assert any(f["locator"] == "he2016deep" for f in payload)


def test_conserved_tokens_exception_does_not_crash_stage(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("simulated check failure")

    monkeypatch.setattr("berb.pipeline.stage_impls._review.conserved_tokens", _boom)
    llm = _FakeLLMClient("# Paper\n\nAccuracy improved significantly.\n")
    result = rc_executor._execute_paper_revision(
        _stage_dir(run_dir), run_dir, _rc_config(tmp_path), AdapterBundle(), llm=llm
    )
    assert result.status is StageStatus.DONE
    assert "revision_findings.json" not in result.artifacts
    assert (_stage_dir(run_dir) / "paper_revised.md").exists()


def test_no_llm_means_revised_equals_draft_no_findings(run_dir: Path, tmp_path: Path) -> None:
    result = rc_executor._execute_paper_revision(
        _stage_dir(run_dir), run_dir, _rc_config(tmp_path), AdapterBundle(), llm=None
    )
    assert result.status is StageStatus.DONE
    assert "revision_findings.json" not in result.artifacts
