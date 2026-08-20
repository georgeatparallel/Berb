"""Stage 21: Knowledge archive."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml  # noqa: F401 — available for downstream use

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.llm.client import LLMClient
from berb.pipeline._domain import _detect_domain  # noqa: F401
from berb.pipeline._helpers import (
    StageResult,
    _build_context_preamble,
    _chat_with_prompt,
    _collect_experiment_results,  # noqa: F401
    _get_evolution_overlay,
    _read_best_analysis,
    _read_prior_artifact,
    _topic_constraint_block,  # noqa: F401
    _utcnow_iso,
)
from berb.pipeline.contracts import StageContract
from berb.pipeline.registry import register_stage
from berb.pipeline.stages import Stage, StageStatus
from berb.prompts import PromptManager

logger = logging.getLogger(__name__)


@register_stage(
    stage=Stage.KNOWLEDGE_ARCHIVE,
    depends_on=frozenset({Stage.QUALITY_GATE}),
    contract=StageContract(
        stage=Stage.KNOWLEDGE_ARCHIVE,
        input_files=(),
        output_files=("archive.md", "bundle_index.json"),
        dod="Retrospective + reproducibility bundle archived",
        error_code="E21_ARCHIVE_FAIL",
    ),
)
def _execute_knowledge_archive(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    revised = _read_prior_artifact(run_dir, "paper_revised.md") or ""
    analysis = _read_best_analysis(run_dir)
    decision = _read_prior_artifact(run_dir, "decision.md") or ""
    preamble = _build_context_preamble(config, run_dir, include_goal=True)
    if llm is not None:
        _pm = prompts or PromptManager()
        _overlay = _get_evolution_overlay(run_dir, "knowledge_archive")
        sp = _pm.for_stage(
            "knowledge_archive",
            evolution_overlay=_overlay,
            preamble=preamble,
            decision=decision,
            analysis=analysis,
            revised=revised[:15000],
        )
        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=sp.max_tokens,
        )
        archive = resp.content
    else:
        archive = f"""# Knowledge Archive

## Lessons Learned
- Preserve strict metric reporting protocol.
- Keep refinement logs aligned with code changes.

## Reproducibility
- Include exact experiment script and schedule.
- Capture run-level JSON metrics.

## Future Work
- Extend robustness and external validity checks.

Generated: {_utcnow_iso()}
"""
    (stage_dir / "archive.md").write_text(archive, encoding="utf-8")

    files: list[str] = []
    for stage_subdir in sorted(run_dir.glob("stage-*")):
        for artifact in sorted(stage_subdir.rglob("*")):
            if artifact.is_file() and artifact != (stage_dir / "bundle_index.json"):
                files.append(str(artifact.relative_to(run_dir)))
    index = {
        "run_id": run_dir.name,
        "generated": _utcnow_iso(),
        "artifact_count": len(files),
        "artifacts": files,
    }
    (stage_dir / "bundle_index.json").write_text(
        json.dumps(index, indent=2), encoding="utf-8"
    )
    return StageResult(
        stage=Stage.KNOWLEDGE_ARCHIVE,
        status=StageStatus.DONE,
        artifacts=("archive.md", "bundle_index.json"),
        evidence_refs=("stage-21/archive.md", "stage-21/bundle_index.json"),
    )


# ---------------------------------------------------------------------------
# _sanitize_fabricated_data helper
# ---------------------------------------------------------------------------


def _sanitize_fabricated_data(
    paper: str,
    run_dir: Path,
) -> tuple[str, dict[str, Any]]:
    """Replace unverified numerical data in markdown tables with '---'.

    Loads experiment_summary.json as ground truth, extracts all verified
    metric values, then scans markdown tables in Results/Experiment sections.
    Numbers not matching any verified value (within 1% relative tolerance)
    are replaced with ``---``.

    Returns (sanitized_paper, sanitization_report).
    """
    import re as _re_san

    # --- 1. Build verified values set from experiment_summary.json ---
    # BUG-222: After REFINE cycles, merging ALL stage-14* data creates a
    # permissive registry that validates fabricated numbers from regressed
    # iterations.  Use ONLY the promoted best data as ground truth.
    # experiment_summary_best.json is written by _promote_best_stage14() and
    # contains the single best iteration's data.
    verified_values: set[float] = set()

    def _richness(path: Path) -> int:
        """Score an experiment_summary.json by how many conditions it has."""
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return -1
        if not isinstance(d, dict):
            return -1
        conds = d.get("condition_summaries", {})
        metrics = d.get("metrics_summary", {})
        return len(conds) + len(metrics)

    # BUG-222: Prefer experiment_summary_best.json (promoted best iteration).
    # Only fall back to "richest stage-14*" scanning if best.json is missing
    # (single-iteration runs without REFINE).
    _root_best = run_dir / "experiment_summary_best.json"
    if _root_best.exists() and _richness(_root_best) > 0:
        exp_path = _root_best
    else:
        _candidates = list(run_dir.glob("stage-14*/experiment_summary.json"))
        exp_path = (
            max(_candidates, key=_richness)
            if _candidates
            else run_dir / "stage-14" / "experiment_summary.json"
        )

    if exp_path.exists():
        try:
            exp_data = json.loads(exp_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            exp_data = {}

        def _collect_numbers(obj: Any, depth: int = 0) -> None:
            if depth > 10:
                return
            if isinstance(obj, (int, float)) and not isinstance(obj, bool):
                import math as _math_vv

                if _math_vv.isfinite(float(obj)):
                    verified_values.add(float(obj))
            elif isinstance(obj, dict):
                for v in obj.values():
                    _collect_numbers(v, depth + 1)
            elif isinstance(obj, list):
                for v in obj:
                    _collect_numbers(v, depth + 1)

        # Extract from well-known keys
        for key in (
            "metrics_summary",
            "condition_summaries",
            "best_run",
            "condition_metrics",
            "conditions",
            "ablation_results",
        ):
            if key in exp_data:
                _collect_numbers(exp_data[key])

    # BUG-222: Removed BUG-206 refinement_log scanning.  The original BUG-206
    # rationale was "Stage 17 injects sandbox metrics, so the sanitizer must
    # recognise them".  But that created a loophole: after REFINE regression,
    # the LLM would cite regressed iteration numbers and the sanitizer would
    # pass them because they were in the refinement log.  Now that Stage 17
    # also uses only the promoted best data (BUG-222), there is no need to
    # whitelist all sandbox metrics here.

    if not verified_values:
        report: dict[str, Any] = {
            "sanitized": False,
            "reason": "no verified values found in experiment_summary.json",
            "tables_processed": 0,
            "numbers_replaced": 0,
        }
        return paper, report

    def _is_verified(num: float) -> bool:
        """Check if num matches any verified value within 1% relative tolerance.

        BUG-R5-20: Also checks percentage/decimal cross-matching
        (e.g., 73.42 in paper vs 0.7342 in experiment, or vice versa).
        """
        for v in verified_values:
            if v == 0.0:
                if abs(num) < 1e-9:
                    return True
            elif abs(num - v) / abs(v) <= 0.01:
                return True
            # Cross-match: num might be percentage form of v (or vice versa)
            elif v != 0.0 and abs(num / 100.0 - v) / abs(v) <= 0.01:
                return True
            elif v != 0.0 and abs(num - v * 100.0) / abs(v * 100.0) <= 0.01:
                return True
        return False

    # --- 2. Find and sanitize markdown tables ---
    # BUG-175: Always-allowed set — common constants, hyperparameters, and
    # structural values that should never be sanitized (matches paper_verifier.py).
    _SANITIZER_ALWAYS_ALLOWED: set[float] = {
        0.0,
        1.0,
        2.0,
        3.0,
        4.0,
        5.0,
        10.0,
        20.0,
        50.0,
        100.0,
        200.0,
        0.5,
        0.01,
        0.001,
        0.0001,
        0.1,
        0.05,
        0.95,
        0.99,
        2024.0,
        2025.0,
        2026.0,
        2027.0,
        8.0,
        16.0,
        32.0,
        64.0,
        128.0,
        256.0,
        512.0,
        1024.0,
        2048.0,
        224.0,
        299.0,
        384.0,  # Common image sizes
        # BUG-192: Common hyperparameter values
        0.0003,
        0.0005,
        0.002,  # learning rates
        0.2,
        0.3,
        0.25,
        0.7,
        0.6,
        0.8,  # clip epsilon, dropout, gradient clip, GCE q, common HP
        0.9,
        0.999,
        0.9999,  # Adam betas, momentum
        0.02,
        0.03,  # weight init std
        1e-5,
        1e-6,
        1e-8,  # epsilon, weight decay
        300.0,
        400.0,
        500.0,  # epochs
        4096.0,
        8192.0,  # larger batch sizes / hidden dims
    }
    # Match markdown table blocks (header + separator + data rows)
    table_pat = _re_san.compile(
        r"((?:^[ \t]*\|.+\|[ \t]*\n)+"  # one or more pipe-delimited lines
        r")",
        _re_san.MULTILINE,
    )
    # Match numbers in table cells (integers, decimals, percentages, scientific)
    # BUG-175: Also exclude hyphen in lookaround to protect method names like
    # "Cos-200", "StepLR-100" from partial number extraction.
    # BUG-206: Include Unicode hyphens (U+2010 hyphen, U+2011 non-breaking
    # hyphen, U+2013 en-dash) — LLMs frequently emit these instead of ASCII
    # hyphens in model names like "ResNet‑34".
    # BUG-206: Unicode hyphens placed before escaped ASCII hyphen (\\-)
    # to avoid creating unintended character ranges in the class.
    _HYPH = "\u2010\u2011\u2013\\-"  # U+2010 + U+2011 + U+2013 + ASCII hyphen
    num_pat = _re_san.compile(
        f"(?<![a-zA-Z_{_HYPH}])"  # not preceded by letter/underscore/any-hyphen
        r"(-?\d+\.?\d*(?:[eE][+-]?\d+)?)"
        r"(%?)"  # optional percent
        f"(?![a-zA-Z_{_HYPH}])"  # not followed by letter/underscore/any-hyphen
    )

    numbers_replaced = 0
    numbers_kept = 0
    tables_processed = 0
    replaced_values: list[str] = []

    # Shared helper — verifies a single number match, replaces if unverified.
    # Used by both markdown-table and LaTeX-tabular sanitizers.
    def _replace_num(m: _re_san.Match[str]) -> str:
        nonlocal numbers_replaced, numbers_kept
        num_str = m.group(1)
        pct = m.group(2)
        try:
            val = float(num_str)
        except ValueError:
            return m.group(0)
        # BUG-175: Always allow common constants / hyperparameters
        if val in _SANITIZER_ALWAYS_ALLOWED:
            numbers_kept += 1
            return m.group(0)
        # BUG-175: Small integer exemption — counts, indices,
        # epoch numbers, etc. (≤ 20 auto-pass)
        if val == int(val) and abs(val) <= 20:
            numbers_kept += 1
            return m.group(0)
        if _is_verified(val):
            numbers_kept += 1
            return m.group(0)
        numbers_replaced += 1
        replaced_values.append(num_str + pct)
        return "---"

    def _sanitize_table(match: _re_san.Match[str]) -> str:
        nonlocal numbers_replaced, numbers_kept, tables_processed
        table_text = match.group(0)
        lines = table_text.split("\n")

        # Check if this looks like a results/experiment table
        # (heuristic: has a separator row with dashes)
        has_separator = any(
            _re_san.match(r"^[ \t]*\|[\s:|-]+\|[ \t]*$", line) for line in lines
        )
        if not has_separator:
            return table_text

        # BUG-192: Detect hyperparameter/config tables and SKIP sanitization.
        # These tables contain design choices, not experimental results.
        _HP_TABLE_KW = {
            "hyperparameter",
            "hyper-parameter",
            "configuration",
            "config",
            "setting",
            "parameter",
            "learning rate",
            "lr",
            "batch size",
            "optimizer",
            "architecture",
            "schedule",
            "warmup",
            "decay",
            "dropout",
            "weight decay",
            "momentum",
            "epsilon",
            "clip",
        }
        # BUG-224: Statistical analysis tables contain derived values
        # (t-statistics, p-values, effect sizes) that are computed from
        # the experiment data but never appear in experiment_summary.json.
        # These tables should NOT be sanitized.
        _STAT_TABLE_KW = {
            "t-statistic",
            "t-stat",
            "t statistic",
            "p-value",
            "p value",
            "paired",
            "cohen",
            "effect size",
            "wilcoxon",
            "mann-whitney",
            "statistical",
            "significance",
            "confidence interval",
        }
        _RESULT_TABLE_KW = {
            "accuracy",
            "acc",
            "loss",
            "f1",
            "auroc",
            "auc",
            "precision",
            "recall",
            "bleu",
            "rouge",
            "reward",
            "return",
            "rmse",
            "mae",
            "mse",
            "error",
            "score",
            "metric",
            "performance",
            "improvement",
            "top-1",
            "top1",
            "top-5",
            "top5",
        }
        _header_lower = lines[0].lower() if lines else ""
        _is_hp_table = any(kw in _header_lower for kw in _HP_TABLE_KW)
        _is_result_table = any(kw in _header_lower for kw in _RESULT_TABLE_KW)
        # BUG-224: Statistical analysis tables (t-tests, p-values) contain
        # derived values that are never in experiment_summary.json.
        _is_stat_table = any(kw in _header_lower for kw in _STAT_TABLE_KW)
        if _is_hp_table and not _is_result_table:
            return table_text  # Skip sanitization for HP/config tables
        if _is_stat_table:
            return table_text  # Skip sanitization for statistical test tables

        # BUG-184: Per-column HP detection — classify each column header
        # as HP-type (skip sanitization) or result-type (sanitize).
        # This handles mixed tables like "| Method | LR | Acc | F1 |"
        # where LR should be preserved but Acc/F1 are verified.
        _HP_COL_KW = {
            "lr",
            "learning rate",
            "batch",
            "epoch",
            "optimizer",
            "schedule",
            "warmup",
            "decay",
            "dropout",
            "momentum",
            "clip",
            "epsilon",
            "eps",
            "beta",
            "alpha",
            "gamma",
            "lambda",
            "weight decay",
            "wd",
            "temperature",
            "temp",
            "hidden",
            "dim",
            "layers",
            "heads",
            "steps",
            "iterations",
            "seed",
            "patience",
            "#param",
            "params",
            "size",
            "depth",
            "width",
            "channels",
            "kernel",
            "stride",
            "padding",
            # BUG-224: Statistical test columns (derived, not in experiment data)
            "t-stat",
            "t stat",
            "p-value",
            "p value",
            "p-val",
            "cohen",
            "effect",
            "ci lower",
            "ci upper",
            "difference",
        }
        _hp_cols: set[int] = set()  # column indices that are HP columns
        if lines:
            _hdr_cells = lines[0].split("|")
            for _ci, _hc in enumerate(_hdr_cells):
                _hc_low = _hc.strip().lower()
                if any(kw in _hc_low for kw in _HP_COL_KW):
                    _hp_cols.add(_ci)

        tables_processed += 1
        sanitized_lines: list[str] = []
        for i, line in enumerate(lines):
            # Skip header row and separator row
            is_separator = bool(_re_san.match(r"^[ \t]*\|[\s:|-]+\|[ \t]*$", line))
            is_header = i == 0  # first line is typically the header
            if is_separator or is_header:
                sanitized_lines.append(line)
                continue

            # BUG-175: Split by pipe and only sanitize cells after
            # the first data column (which typically contains method
            # names, condition labels, etc.)
            cells = line.split("|")
            sanitized_cells: list[str] = []

            for ci, cell in enumerate(cells):
                # Skip first non-empty cell (method/label column),
                # empty edge cells, and BUG-184 HP-classified columns
                if ci <= 1 or not cell.strip() or ci in _hp_cols:
                    sanitized_cells.append(cell)
                else:
                    sanitized_cells.append(num_pat.sub(_replace_num, cell))
            sanitized_lines.append("|".join(sanitized_cells))
        return "\n".join(sanitized_lines)

    sanitized = table_pat.sub(_sanitize_table, paper)

    # --- BUG-211: LaTeX tabular sanitization ---
    # LLMs sometimes write results in LaTeX \begin{tabular} format inside
    # the markdown paper (often within ```latex fences).  The markdown
    # table regex above misses these entirely, allowing fabricated numbers
    # to pass through unchecked.
    latex_tab_pat = _re_san.compile(
        r"(\\begin\{tabular\}.*?\\end\{tabular\})",
        _re_san.DOTALL,
    )

    # Keywords for HP-table vs result-table classification (reuse from above)
    _LTX_HP_KW = {
        "hyperparameter",
        "hyper-parameter",
        "configuration",
        "config",
        "setting",
        "learning rate",
        "lr",
        "batch size",
        "optimizer",
    }
    _LTX_RESULT_KW = {
        "accuracy",
        "acc",
        "loss",
        "f1",
        "auroc",
        "auc",
        "precision",
        "recall",
        "reward",
        "score",
        "metric",
        "performance",
        "result",
    }
    # BUG-224: Statistical analysis LaTeX tables — derived values
    _LTX_STAT_KW = {
        "t-statistic",
        "t-stat",
        "t statistic",
        "p-value",
        "p value",
        "paired",
        "cohen",
        "effect size",
        "statistical",
        "significance",
    }

    def _sanitize_latex_table(match: _re_san.Match[str]) -> str:
        nonlocal tables_processed
        block = match.group(0)

        # Heuristic: look at the first ~300 chars (column spec + header row)
        # to decide HP vs result table.  Also check preceding \caption if
        # the match is part of a \begin{table} environment — we can look
        # backwards a bit in the full text for the caption.
        _start = match.start()
        _context = sanitized[max(0, _start - 300) : _start + 300].lower()
        _is_hp = any(kw in _context for kw in _LTX_HP_KW)
        _is_res = any(kw in _context for kw in _LTX_RESULT_KW)
        # BUG-224: Statistical test tables — derived values not in experiment data
        _is_stat = any(kw in _context for kw in _LTX_STAT_KW)
        if _is_hp and not _is_res:
            return block  # HP/config table — skip
        if _is_stat:
            return block  # Statistical analysis table — skip

        tables_processed += 1

        # Split into rows by \\ (LaTeX row separator).
        # We split on \\ but keep the delimiter so we can reconstruct.
        parts = _re_san.split(r"(\\\\)", block)
        result_parts: list[str] = []
        _seen_midrule = False

        for part in parts:
            # Preserve row separators as-is
            if part == "\\\\":
                result_parts.append(part)
                continue

            _stripped = part.strip()
            # Rule lines — no numbers to sanitize
            if _re_san.search(
                r"\\(hline|toprule|midrule|bottomrule|cline|cmidrule)",
                _stripped,
            ):
                if "midrule" in _stripped or "hline" in _stripped:
                    _seen_midrule = True
                result_parts.append(part)
                continue

            # Column spec line (contains \begin{tabular}{...})
            if r"\begin{tabular}" in part:
                result_parts.append(part)
                continue

            # End line
            if r"\end{tabular}" in part:
                result_parts.append(part)
                continue

            # Header row: rows before the first \midrule/\hline
            if not _seen_midrule:
                result_parts.append(part)
                continue

            # Data row — split by & and sanitize cells after the first
            cells = part.split("&")
            sanitized_cells: list[str] = []
            for ci, cell in enumerate(cells):
                if ci == 0:
                    # First cell is method/condition name — preserve
                    sanitized_cells.append(cell)
                else:
                    sanitized_cells.append(num_pat.sub(_replace_num, cell))
            result_parts.append("&".join(sanitized_cells))

        return "".join(result_parts)

    sanitized = latex_tab_pat.sub(_sanitize_latex_table, sanitized)

    # --- Improvement F: Prose-level anti-fabrication ---
    # Scan Results/Experiments sections for inline numeric claims like
    # "achieved 94.2% accuracy" or "obtained an AUROC of 0.87".
    # Replace unverified numbers with "[value removed]".
    prose_numbers_replaced = 0
    _prose_pattern = _re_san.compile(
        r"(?:achiev|obtain|reach|attain|yield|report|record|produc|demonstrat|show|observ)"
        r"(?:ed|es|ing|s)?\s+"
        r"(?:an?\s+)?(?:\w+\s+)?(?:of\s+)?"
        r"(\d+\.?\d*)\s*"
        r"(%|\\%)?",
        _re_san.IGNORECASE,
    )
    # Only process lines in Results/Experiments sections
    _in_results_section = False
    _results_headers = _re_san.compile(
        r"^#{1,3}\s*(Results|Experiments|Experimental|Evaluation|Ablation)",
        _re_san.IGNORECASE,
    )
    _any_header = _re_san.compile(r"^#{1,3}\s+")
    _sanitized_lines = []
    for _line in sanitized.split("\n"):
        if _results_headers.match(_line):
            _in_results_section = True
        elif _any_header.match(_line) and _in_results_section:
            # Check if we're leaving Results for a different top-level section
            _header_text = _line.lstrip("#").strip().lower()
            if _header_text and not any(
                kw in _header_text
                for kw in (
                    "result",
                    "experiment",
                    "ablation",
                    "evaluation",
                    "comparison",
                )
            ):
                _in_results_section = False
        if _in_results_section and "|" not in _line:  # skip table rows

            def _replace_prose_num(m: _re_san.Match[str]) -> str:
                nonlocal prose_numbers_replaced
                num_str = m.group(1)
                try:
                    val = float(num_str)
                except ValueError:
                    return m.group(0)
                # Skip common constants / small integers
                if val in _SANITIZER_ALWAYS_ALLOWED:
                    return m.group(0)
                if val == int(val) and abs(val) <= 20:
                    return m.group(0)
                if _is_verified(val):
                    return m.group(0)
                prose_numbers_replaced += 1
                return m.group(0).replace(
                    num_str + (m.group(2) or ""), "[value removed]"
                )

            _line = _prose_pattern.sub(_replace_prose_num, _line)
        _sanitized_lines.append(_line)
    sanitized = "\n".join(_sanitized_lines)

    report = {
        "sanitized": numbers_replaced > 0 or prose_numbers_replaced > 0,
        "tables_processed": tables_processed,
        "numbers_replaced": numbers_replaced,
        "numbers_kept": numbers_kept,
        "prose_numbers_replaced": prose_numbers_replaced,
        "verified_values_count": len(verified_values),
        "replaced_samples": replaced_values[:20],
        "generated": _utcnow_iso(),
    }
    return sanitized, report


# ---------------------------------------------------------------------------
# BUG-176: Missing citation resolution
# BUG-194: Validate search results to avoid replacing correct entries with
#           garbage.  Previous code searched by cite-key fragments (e.g.
#           "he 2016 deep") which returned completely unrelated papers.
#           Fix: (1) consult seminal_papers.yaml first, (2) require title-
#           similarity validation for API results, (3) build better queries.
# ---------------------------------------------------------------------------

# Minimum title-similarity between search result and expected title/query
# for a result to be accepted.  Prevents "Jokowi and the New Developmentalism"
# from replacing "Deep Residual Learning for Image Recognition".
_CITATION_RESOLVE_MIN_SIMILARITY = 0.30
