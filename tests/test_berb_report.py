# pyright: basic, reportMissingImports=false, reportUnusedCallResult=false
from __future__ import annotations

import json
from pathlib import Path

import pytest

from berb.report import generate_report


class TestReport:
    def test_report_missing_run_dir(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            generate_report(tmp_path / "nonexistent")

    def test_report_no_summary(self, tmp_path: Path):
        with pytest.raises(ValueError, match="pipeline_summary"):
            generate_report(tmp_path)

    def test_report_minimal_run(self, tmp_path: Path):
        (tmp_path / "pipeline_summary.json").write_text(
            json.dumps(
                {
                    "run_id": "rc-test-123",
                    "stages_executed": 23,
                    "stages_done": 23,
                    "stages_blocked": 0,
                    "stages_failed": 0,
                    "final_status": "done",
                    "generated": "2026-03-10T12:00:00Z",
                }
            )
        )
        report = generate_report(tmp_path)
        assert "# Berb Run Report" in report
        assert "rc-test-123" in report
        assert "✅" in report

    def test_report_with_paper(self, tmp_path: Path):
        (tmp_path / "pipeline_summary.json").write_text(
            json.dumps(
                {
                    "run_id": "test",
                    "stages_executed": 1,
                    "stages_done": 1,
                    "stages_failed": 0,
                    "final_status": "done",
                    "generated": "now",
                }
            )
        )
        draft_dir = tmp_path / "stage-17"
        draft_dir.mkdir()
        (draft_dir / "paper_draft.md").write_text("This is a paper with some words in it.")
        report = generate_report(tmp_path)
        assert "Paper" in report
        assert "words" in report

    def test_report_with_citations(self, tmp_path: Path):
        (tmp_path / "pipeline_summary.json").write_text(
            json.dumps(
                {
                    "run_id": "test",
                    "stages_executed": 1,
                    "stages_done": 1,
                    "stages_failed": 0,
                    "final_status": "done",
                    "generated": "now",
                }
            )
        )
        verify_dir = tmp_path / "stage-23"
        verify_dir.mkdir()
        (verify_dir / "verification_report.json").write_text(
            json.dumps(
                {
                    "total_references": 10,
                    "verified_count": 8,
                    "suspicious_count": 1,
                    "hallucinated_count": 1,
                }
            )
        )
        report = generate_report(tmp_path)
        assert "Citations" in report
        assert "8/10" in report
        assert "Suspicious: 1" in report

    def test_report_with_failures(self, tmp_path: Path):
        (tmp_path / "pipeline_summary.json").write_text(
            json.dumps(
                {
                    "run_id": "test",
                    "stages_executed": 5,
                    "stages_done": 3,
                    "stages_failed": 2,
                    "final_status": "failed",
                    "generated": "now",
                }
            )
        )
        report = generate_report(tmp_path)
        assert "❌" in report
        assert "Warnings" in report
        assert "2 stage(s) failed" in report

    def _minimal_summary(self, tmp_path: Path) -> None:
        (tmp_path / "pipeline_summary.json").write_text(
            json.dumps(
                {
                    "run_id": "test",
                    "stages_executed": 1,
                    "stages_done": 1,
                    "stages_failed": 0,
                    "final_status": "done",
                    "generated": "now",
                }
            )
        )

    def test_report_cost_section_absent_when_no_cost_report(self, tmp_path: Path):
        """A4-3: a run with no cost_report.json must say so, not imply $0."""
        self._minimal_summary(tmp_path)
        report = generate_report(tmp_path)
        assert "## Cost" in report
        assert "Not recorded" in report

    def test_report_cost_section_renders_breakdown(self, tmp_path: Path):
        """A4-3: by_stage/by_phase were always {} before the contextvar fix."""
        self._minimal_summary(tmp_path)
        (tmp_path / "cost_report.json").write_text(
            json.dumps(
                {
                    "total_cost_usd": 1.2345,
                    "total_tokens": 45678,
                    "num_events": 12,
                    "by_stage": {"17": 0.9, "14": 0.3, "3": 0.0345},
                    "by_phase": {
                        "G: Paper Writing": 0.9,
                        "F: Analysis & Decision": 0.3,
                    },
                    "by_purpose": {"other": 1.2345},
                    "pricing_version": "test",
                }
            )
        )
        report = generate_report(tmp_path)
        assert "$1.2345" in report
        assert "12 call(s)" in report
        assert "45,678 tokens" in report
        # Stages ranked by spend, not by stage number.
        assert "stage 17 $0.9000, stage 14 $0.3000" in report
        assert "G: Paper Writing $0.9000" in report

    def test_report_cost_section_survives_corrupt_file(self, tmp_path: Path):
        self._minimal_summary(tmp_path)
        (tmp_path / "cost_report.json").write_text("{not json")
        report = generate_report(tmp_path)
        assert "unreadable" in report

    def test_report_with_experiment_results(self, tmp_path: Path):
        (tmp_path / "pipeline_summary.json").write_text(
            json.dumps(
                {
                    "run_id": "test",
                    "stages_executed": 1,
                    "stages_done": 1,
                    "stages_failed": 0,
                    "final_status": "done",
                    "generated": "now",
                }
            )
        )
        exp_dir = tmp_path / "stage-12"
        exp_dir.mkdir()
        (exp_dir / "experiment_results.json").write_text(
            json.dumps(
                {
                    "iterations": [{"loss": 0.5}, {"loss": 0.3}],
                    "best_metric": 0.3,
                }
            )
        )
        report = generate_report(tmp_path)
        assert "Experiments" in report
        assert "2 iterations" in report
