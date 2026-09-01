"""Stage 23 (CITATION_VERIFY) citation-locator-anchor verification wiring.

tasks/ars_integration_plan.md W1: the consumer side of the anchors
mechanism. Mirrors tests/test_stage_citation_verify_retraction.py's
self-contained fixture pattern — no existing test calls
``_execute_citation_verify`` directly outside that precedent.

``verify_citations`` is monkeypatched — no real network anywhere here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.integrity import ClaimManifest, ClaimRecord, ClaimType, make_anchor
from berb.literature.verify import VerificationReport
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


def _rc_config(tmp_path: Path, *, mode: str) -> RCConfig:
    data = dict(_BASE_CONFIG)
    data["knowledge_base"] = {"backend": "markdown", "root": str(tmp_path / "kb")}
    data["integrity"] = {"mode": mode}
    return RCConfig.from_dict(data, project_root=tmp_path, check_paths=False, check_security=False)


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "run" / "stage-22"
    d.mkdir(parents=True)
    (d / "references.bib").write_text(
        "@article{he2016deep, title={Deep Residual Learning}}\n", encoding="utf-8"
    )
    return d.parent


def _stage_dir(run_dir: Path) -> Path:
    d = run_dir / "stage-23"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_paper_final(run_dir: Path, text: str) -> None:
    (run_dir / "stage-22" / "paper_final.md").write_text(text, encoding="utf-8")


def _write_claim_manifest(run_dir: Path, manifest: ClaimManifest) -> None:
    d = run_dir / "stage-17"
    d.mkdir(parents=True, exist_ok=True)
    manifest.save(d / "claim_manifest.json")


def _run(monkeypatch: pytest.MonkeyPatch, run_dir: Path, tmp_path: Path, *, mode: str):
    cfg = _rc_config(tmp_path, mode=mode)
    monkeypatch.setattr(
        "berb.literature.verify.verify_citations",
        lambda *a, **k: VerificationReport(total=0, results=[]),
    )
    return rc_executor._execute_citation_verify(
        _stage_dir(run_dir), run_dir, cfg, AdapterBundle(), llm=None
    )


def test_no_markers_no_manifest_produces_no_artifact(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_paper_final(run_dir, "# Paper\n\nNo markers here.\n")
    result = _run(monkeypatch, run_dir, tmp_path, mode="strict")
    assert result.status is StageStatus.DONE
    assert "anchor_findings.json" not in result.artifacts


def test_unresolved_marker_no_manifest_fails_in_strict_mode(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = "<!--berb-cite key=he2016deep kind=quote id=a3f19c-->"
    _write_paper_final(run_dir, f"# Paper\n\nSome claim {marker}.\n")
    result = _run(monkeypatch, run_dir, tmp_path, mode="strict")
    assert result.status is StageStatus.FAILED
    assert result.error is not None
    assert "he2016deep" in result.error


def test_unresolved_marker_does_not_fail_in_draft_mode(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = "<!--berb-cite key=he2016deep kind=quote id=a3f19c-->"
    _write_paper_final(run_dir, f"# Paper\n\nSome claim {marker}.\n")
    result = _run(monkeypatch, run_dir, tmp_path, mode="draft")
    assert result.status is StageStatus.DONE
    assert "anchor_findings.json" in result.artifacts
    payload = json.loads((_stage_dir(run_dir) / "anchor_findings.json").read_text())
    assert payload[0]["check"] == "anchor_unresolved"


def test_resolved_quote_anchor_with_no_source_text_is_info_never_fails(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    anchor = make_anchor("he2016deep", "quote", "deep residual learning")
    assert anchor is not None
    manifest = ClaimManifest(paper_stage="draft")
    manifest.add_claim(
        ClaimRecord(
            claim_id="",
            text="claim text",
            claim_type=ClaimType.EMPIRICAL,
            anchors=(anchor,),
        )
    )
    _write_claim_manifest(run_dir, manifest)
    marker = f"<!--berb-cite key=he2016deep kind=quote id={anchor.anchor_id}-->"
    _write_paper_final(run_dir, f"# Paper\n\nSome claim {marker}.\n")

    result = _run(monkeypatch, run_dir, tmp_path, mode="strict")

    assert result.status is StageStatus.DONE  # INFO never gates in any mode
    assert "anchor_findings.json" in result.artifacts
    payload = json.loads((_stage_dir(run_dir) / "anchor_findings.json").read_text())
    assert payload[0]["check"] == "anchor_unverifiable"
    assert payload[0]["severity"] == "info"


def test_no_bib_keys_and_no_manifest_skips_computation_entirely(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No references.bib content and no claim_manifest.json -> the wiring's
    # own `if anchors_by_id or _anchor_bib_keys:` guard means verify_anchors
    # is never even called.
    (run_dir / "stage-22" / "references.bib").write_text("", encoding="utf-8")
    _write_paper_final(run_dir, "# Paper\n\nNothing to anchor.\n")

    def _boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError("verify_anchors must not be called with no keys and no anchors")

    monkeypatch.setattr("berb.pipeline.stage_impls._citations.verify_anchors", _boom)
    result = _run(monkeypatch, run_dir, tmp_path, mode="strict")
    assert result.status is StageStatus.DONE


def test_anchor_verification_exception_does_not_crash_stage(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = "<!--berb-cite key=he2016deep kind=quote id=a3f19c-->"
    _write_paper_final(run_dir, f"# Paper\n\nSome claim {marker}.\n")

    def _boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("simulated anchor verification failure")

    monkeypatch.setattr("berb.pipeline.stage_impls._citations.verify_anchors", _boom)
    result = _run(monkeypatch, run_dir, tmp_path, mode="strict")
    assert result.status is StageStatus.DONE
    assert "anchor_findings.json" not in result.artifacts


def test_corrupt_claim_manifest_does_not_crash_stage(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = run_dir / "stage-17"
    d.mkdir(parents=True, exist_ok=True)
    (d / "claim_manifest.json").write_text("{not valid json", encoding="utf-8")
    _write_paper_final(run_dir, "# Paper\n\nNo markers.\n")
    result = _run(monkeypatch, run_dir, tmp_path, mode="strict")
    assert result.status is StageStatus.DONE
