"""Pipeline summary — aggregate stage results into a run summary JSON.

Builds the final pipeline_summary.json and collects content authenticity
metrics from stage outputs.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import importlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from berb.pipeline.stages import Stage, StageStatus

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def build_pipeline_summary(
    *,
    run_id: str,
    results: list,
    from_stage: Stage,
    run_dir: Path | None = None,
) -> dict[str, object]:
    """Aggregate stage results into a pipeline summary dict."""
    from berb.pipeline.executor import StageResult

    summary: dict[str, object] = {
        "run_id": run_id,
        "stages_executed": len(results),
        "stages_done": sum(1 for item in results if item.status == StageStatus.DONE),
        "stages_blocked": sum(1 for item in results if item.status == StageStatus.BLOCKED_APPROVAL),
        "stages_failed": sum(1 for item in results if item.status == StageStatus.FAILED),
        "degraded": any(r.decision == "degraded" for r in results),
        "from_stage": int(from_stage),
        "final_stage": int(results[-1].stage) if results else int(from_stage),
        "final_status": results[-1].status.value if results else "no_stages",
        "generated": _utcnow_iso(),
        "content_metrics": _collect_content_metrics(run_dir),
    }
    return summary


def write_pipeline_summary(run_dir: Path, summary: dict[str, object]) -> None:
    """Write pipeline summary to disk."""
    (run_dir / "pipeline_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )


def _collect_content_metrics(run_dir: Path | None) -> dict[str, object]:
    """Collect content authenticity metrics from stage outputs."""
    metrics: dict[str, object] = {
        "template_ratio": None,
        "citation_verify_score": None,
        "total_citations": None,
        "verified_citations": None,
        "degraded_sources": [],
    }
    if run_dir is None:
        return metrics

    draft_path = run_dir / "stage-17" / "paper_draft.md"
    if draft_path.exists():
        try:
            quality_module = importlib.import_module("berb.quality")
            compute_template_ratio = quality_module.compute_template_ratio
            text = draft_path.read_text(encoding="utf-8")
            metrics["template_ratio"] = round(compute_template_ratio(text), 4)
        except (
            AttributeError,
            ModuleNotFoundError,
            UnicodeDecodeError,
            OSError,
            ValueError,
            TypeError,
        ):
            pass

    verify_path = run_dir / "stage-23" / "verification_report.json"
    if verify_path.exists():
        try:
            vdata = json.loads(verify_path.read_text(encoding="utf-8"))
            if isinstance(vdata, dict):
                summary = vdata.get("summary", vdata)
                total = summary.get("total", 0) if isinstance(summary, dict) else None
                verified = summary.get("verified", 0) if isinstance(summary, dict) else None
                if isinstance(total, int | float) and isinstance(verified, int | float):
                    total_num = int(total)
                    verified_num = int(verified)
                    metrics["total_citations"] = total_num
                    metrics["verified_citations"] = verified_num
                    if total_num > 0:
                        metrics["citation_verify_score"] = round(verified_num / total_num, 4)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    return metrics
