"""Stage 23 (CITATION_VERIFY) retraction-gating wiring.

tasks/ars_integration_plan.md W2: this is the *enforcing* touchpoint —
screening at stage 5 (LITERATURE_SCREEN) is advisory only. No existing test
calls ``_execute_citation_verify`` directly, so this file owns its own
minimal fixtures rather than reusing test_berb_executor.py's.

Both ``verify_citations`` and ``resolve_retraction`` are monkeypatched —
no real network call happens anywhere in this file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.literature.models import Paper
from berb.literature.retraction import RetractionRecord, RetractionState
from berb.literature.verify import CitationResult, VerificationReport, VerifyStatus
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


def _rc_config(tmp_path: Path, *, mode: str, retraction_ack: tuple[str, ...] = ()) -> RCConfig:
    data = dict(_BASE_CONFIG)
    data["knowledge_base"] = {"backend": "markdown", "root": str(tmp_path / "kb")}
    data["integrity"] = {"mode": mode, "retraction_ack": list(retraction_ack)}
    return RCConfig.from_dict(data, project_root=tmp_path, check_paths=False, check_security=False)


def _paper_with_doi(doi: str) -> Paper:
    return Paper(paper_id="p1", title="A Paper", doi=doi, source="crossref")


def _retracted_report() -> VerificationReport:
    result = CitationResult(
        cite_key="retracted2024x",
        title="A Paper",
        status=VerifyStatus.VERIFIED,
        confidence=0.9,
        method="doi",
        matched_paper=_paper_with_doi("10.1234/retracted"),
    )
    return VerificationReport(total=1, verified=1, results=[result])


def _clean_report() -> VerificationReport:
    result = CitationResult(
        cite_key="clean2024x",
        title="A Paper",
        status=VerifyStatus.VERIFIED,
        confidence=0.9,
        method="doi",
        matched_paper=_paper_with_doi("10.1234/clean"),
    )
    return VerificationReport(total=1, verified=1, results=[result])


def _no_doi_report() -> VerificationReport:
    result = CitationResult(
        cite_key="nodoi2024x",
        title="A Paper",
        status=VerifyStatus.VERIFIED,
        confidence=0.9,
        method="title_search",
        matched_paper=None,
    )
    return VerificationReport(total=1, verified=1, results=[result])


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "run" / "stage-22"
    d.mkdir(parents=True)
    (d / "references.bib").write_text("@article{k1, title={x}}\n", encoding="utf-8")
    (d / "paper_final.md").write_text("Some paper text.", encoding="utf-8")
    return d.parent


def _stage_dir(run_dir: Path) -> Path:
    d = run_dir / "stage-23"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run(
    monkeypatch: pytest.MonkeyPatch,
    run_dir: Path,
    tmp_path: Path,
    *,
    report: VerificationReport,
    mode: str,
    retraction_ack: tuple[str, ...] = (),
    resolve_side_effect: Any,
):
    cfg = _rc_config(tmp_path, mode=mode, retraction_ack=retraction_ack)
    # _execute_citation_verify imports verify_citations locally (inside the
    # function body) rather than at module scope, so the source module is
    # the correct patch target.
    monkeypatch.setattr("berb.literature.verify.verify_citations", lambda *a, **k: report)
    monkeypatch.setattr(
        "berb.pipeline.stage_impls._citations.resolve_retraction", resolve_side_effect
    )
    return rc_executor._execute_citation_verify(
        _stage_dir(run_dir), run_dir, cfg, AdapterBundle(), llm=None
    )


def test_no_doi_never_calls_resolve_retraction(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError("resolve_retraction must not be called with no DOI")

    result = _run(
        monkeypatch,
        run_dir,
        tmp_path,
        report=_no_doi_report(),
        mode="strict",
        resolve_side_effect=_boom,
    )
    assert result.status is StageStatus.DONE
    assert "retraction_findings.json" not in result.artifacts


def test_clean_doi_produces_no_findings(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(
        monkeypatch,
        run_dir,
        tmp_path,
        report=_clean_report(),
        mode="strict",
        resolve_side_effect=lambda ck, doi, **k: RetractionRecord(ck, RetractionState.NONE),
    )
    assert result.status is StageStatus.DONE
    assert "retraction_findings.json" not in result.artifacts


def test_retracted_doi_fails_stage_in_strict_mode(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(
        monkeypatch,
        run_dir,
        tmp_path,
        report=_retracted_report(),
        mode="strict",
        resolve_side_effect=lambda ck, doi, **k: RetractionRecord(
            ck, RetractionState.RETRACTED, "mocked"
        ),
    )
    assert result.status is StageStatus.FAILED
    assert result.error is not None
    assert "retracted2024x" in result.error
    assert (run_dir / "stage-23" / "retraction_findings.json").exists()


def test_retracted_doi_fails_stage_in_submission_mode(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(
        monkeypatch,
        run_dir,
        tmp_path,
        report=_retracted_report(),
        mode="submission",
        resolve_side_effect=lambda ck, doi, **k: RetractionRecord(
            ck, RetractionState.RETRACTED, "mocked"
        ),
    )
    assert result.status is StageStatus.FAILED


def test_retracted_doi_does_not_fail_stage_in_draft_mode(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(
        monkeypatch,
        run_dir,
        tmp_path,
        report=_retracted_report(),
        mode="draft",
        resolve_side_effect=lambda ck, doi, **k: RetractionRecord(
            ck, RetractionState.RETRACTED, "mocked"
        ),
    )
    # draft mode never gates (IntegrityConfig's "draft (warn only)" contract)
    # but the finding is still recorded as an artifact for visibility.
    assert result.status is StageStatus.DONE
    assert "retraction_findings.json" in result.artifacts


def test_acknowledged_citation_does_not_fail_stage_but_still_records(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(
        monkeypatch,
        run_dir,
        tmp_path,
        report=_retracted_report(),
        mode="strict",
        retraction_ack=("retracted2024x",),
        resolve_side_effect=lambda ck, doi, **k: RetractionRecord(
            ck, RetractionState.RETRACTED, "mocked"
        ),
    )
    assert result.status is StageStatus.DONE
    assert "retraction_findings.json" in result.artifacts
    payload = json.loads((run_dir / "stage-23" / "retraction_findings.json").read_text())
    assert payload[0]["severity"] == "info"
    assert "acknowledged" in payload[0]["message"]


def test_resolve_retraction_exception_does_not_crash_stage(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("simulated lookup failure")

    result = _run(
        monkeypatch,
        run_dir,
        tmp_path,
        report=_clean_report(),
        mode="strict",
        resolve_side_effect=_boom,
    )
    assert result.status is StageStatus.DONE
    assert "retraction_findings.json" not in result.artifacts
