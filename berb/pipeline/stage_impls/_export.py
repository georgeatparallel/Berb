"""Stage 22: Export and publish."""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from pathlib import Path

import yaml  # noqa: F401 — available for downstream use

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.llm.client import LLMClient
from berb.pipeline._domain import _detect_domain  # noqa: F401
from berb.pipeline._helpers import (
    StageResult,
    _chat_with_prompt,
    _collect_experiment_results,  # noqa: F401
    _extract_paper_title,
    _generate_framework_diagram_prompt,
    _generate_neurips_checklist,
    _get_evolution_overlay,
    _read_prior_artifact,
    _safe_json_loads,
    _topic_constraint_block,  # noqa: F401
    reconcile_figure_refs,
)
from berb.pipeline.contracts import StageContract
from berb.pipeline.registry import register_stage
from berb.pipeline.stage_impls._archive import _sanitize_fabricated_data
from berb.pipeline.stage_impls._citations import (
    _remove_bibtex_entries,
    _resolve_missing_citations,
)
from berb.pipeline.stage_impls._review import _get_review_compiled_pdf
from berb.pipeline.stages import Stage, StageStatus
from berb.prompts import PromptManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage 22 helpers
# ---------------------------------------------------------------------------

_KNOWN_PACKAGES: dict[str, str] = {
    "numpy": "numpy",
    "torch": "torch",
    "tensorflow": "tensorflow",
    "sklearn": "scikit-learn",
    "scikit-learn": "scikit-learn",
    "scipy": "scipy",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "transformers": "transformers",
    "datasets": "datasets",
    "jax": "jax",
}


def _detect_dependencies(source_code: str) -> list[str]:
    """Return sorted list of known PyPI packages imported by *source_code*."""
    import ast as _ast

    detected: set[str] = set()
    try:
        tree = _ast.parse(source_code)
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in _KNOWN_PACKAGES:
                        detected.add(_KNOWN_PACKAGES[top])
            elif isinstance(node, _ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if top in _KNOWN_PACKAGES:
                    detected.add(_KNOWN_PACKAGES[top])
    except SyntaxError:
        pass
    return sorted(detected)


def _package_code_release(
    stage_dir: Path,
    run_dir: Path,
    final_paper: str,
) -> list[str]:
    """Package experiment code into stage_dir/code/.

    Handles both multi-file (experiment_final/) and single-file
    (experiment_final.py / experiment.py) layouts.

    Returns list of artifact paths added (e.g. ["code/"]).
    """
    exp_final_dir_path = _read_prior_artifact(run_dir, "experiment_final/")
    if exp_final_dir_path and Path(exp_final_dir_path).is_dir():
        code_dir = stage_dir / "code"
        code_dir.mkdir(parents=True, exist_ok=True)
        all_code_combined = ""
        code_file_names: list[str] = []
        for src in sorted(Path(exp_final_dir_path).glob("*.py")):
            (code_dir / src.name).write_bytes(src.read_bytes())
            all_code_combined += src.read_text(encoding="utf-8") + "\n"
            code_file_names.append(src.name)

        requirements = _detect_dependencies(all_code_combined)
        (code_dir / "requirements.txt").write_text(
            "\n".join(requirements) + ("\n" if requirements else ""),
            encoding="utf-8",
        )
        paper_title = _extract_paper_title(final_paper)
        file_list_md = "\n".join(f"- `{f}`" for f in code_file_names)
        readme = (
            f"# Code Package for {paper_title}\n\n"
            "## Description\n"
            "This directory contains the experiment project used for the paper.\n\n"
            "## Project Files\n"
            f"{file_list_md}\n\n"
            "## How to Run\n"
            "`python main.py`\n\n"
            "## Dependencies\n"
            "Install dependencies with `pip install -r requirements.txt` if needed.\n"
        )
        (code_dir / "README.md").write_text(readme, encoding="utf-8")
        logger.info(
            "Stage 22: Packaged multi-file code release (%d files, %d deps)",
            len(code_file_names),
            len(requirements),
        )
        return ["code/"]

    # Backward compat: single-file packaging
    code_payload = _read_prior_artifact(run_dir, "experiment_final.py")
    if not code_payload:
        code_payload = _read_prior_artifact(run_dir, "experiment.py")
    if not code_payload:
        return []

    code_dir = stage_dir / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "experiment.py").write_text(code_payload, encoding="utf-8")
    requirements = _detect_dependencies(code_payload)
    (code_dir / "requirements.txt").write_text(
        "\n".join(requirements) + ("\n" if requirements else ""),
        encoding="utf-8",
    )
    paper_title = _extract_paper_title(final_paper)
    readme = (
        f"# Code Package for {paper_title}\n\n"
        "## Description\n"
        "This directory contains the final experiment script used for the paper.\n\n"
        "## How to Run\n"
        "`python experiment.py`\n\n"
        "## Dependencies\n"
        "Install dependencies with `pip install -r requirements.txt` if needed.\n"
    )
    (code_dir / "README.md").write_text(readme, encoding="utf-8")
    logger.info(
        "Stage 22: Packaged single-file code release with %d deps",
        len(requirements),
    )
    return ["code/"]


# ---------------------------------------------------------------------------
# Stage 22: Export & Publish
# ---------------------------------------------------------------------------


@register_stage(
    stage=Stage.EXPORT_PUBLISH,
    depends_on=frozenset({Stage.PAPER_REVISION}),
    contract=StageContract(
        stage=Stage.EXPORT_PUBLISH,
        input_files=("paper_revised.md",),
        output_files=("paper_final.md", "code/"),
        dod="Final paper exported in target format",
        error_code="E22_EXPORT_FAIL",
    ),
)
def _execute_export_publish(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    revised = _read_prior_artifact(run_dir, "paper_revised.md") or ""
    if llm is not None:
        _pm = prompts or PromptManager()
        _overlay = _get_evolution_overlay(run_dir, "export_publish")
        sp = _pm.for_stage(
            "export_publish", evolution_overlay=_overlay, revised=revised
        )
        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=sp.max_tokens,
        )
        final_paper = resp.content
        # Content guard: reject LLM output that truncates the paper
        if revised and len(final_paper) < 0.6 * len(revised):
            logger.warning(
                "Stage 22: LLM output is %.0f%% of input length — using original",
                100 * len(final_paper) / max(len(revised), 1),
            )
            final_paper = revised
    else:
        final_paper = revised
    if not final_paper.strip():
        final_paper = "# Final Paper\n\nNo content generated."

    # --- Always-on fabrication sanitization (Phase 1 anti-fabrication) ---
    # Back up pre-sanitized version
    (stage_dir / "paper_presanitized.md").write_text(final_paper, encoding="utf-8")

    # Sanitize unverified data in tables — always-on, not just degraded mode
    final_paper, _san_report = _sanitize_fabricated_data(final_paper, run_dir)
    (stage_dir / "sanitization_report.json").write_text(
        json.dumps(_san_report, indent=2), encoding="utf-8"
    )
    if _san_report.get("numbers_replaced", 0) > 0:
        logger.info(
            "Stage 22: Fabrication sanitization — %d numbers replaced, %d kept",
            _san_report.get("numbers_replaced", 0),
            _san_report.get("numbers_kept", 0),
        )

    # Graceful degradation: insert notice only when quality gate was degraded
    _degradation_signal_path = run_dir / "degradation_signal.json"
    if _degradation_signal_path.exists():
        try:
            _deg_signal = json.loads(
                _degradation_signal_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            _deg_signal = {}

        # Insert degradation notice after abstract
        _deg_score = _deg_signal.get("score", "N/A")
        _deg_threshold = _deg_signal.get("threshold", "N/A")
        _deg_notice = (
            "\n\n> **Note:** This paper was produced in degraded mode. "
            f"Quality gate score ({_deg_score}/{_deg_threshold}) was below "
            "threshold. Unverified numerical results in tables have been "
            "replaced with `---` and require independent verification.\n\n"
        )
        # Try to insert after ## Abstract section
        _abstract_markers = ["## Abstract\n", "# Abstract\n"]
        _notice_inserted = False
        for _marker in _abstract_markers:
            if _marker in final_paper:
                _marker_end = final_paper.index(_marker) + len(_marker)
                # Find the end of the abstract paragraph
                _next_section = final_paper.find("\n## ", _marker_end)
                _next_heading = final_paper.find("\n# ", _marker_end)
                _insert_pos = (
                    min(p for p in (_next_section, _next_heading) if p > 0)
                    if any(p > 0 for p in (_next_section, _next_heading))
                    else len(final_paper)
                )
                final_paper = (
                    final_paper[:_insert_pos] + _deg_notice + final_paper[_insert_pos:]
                )
                _notice_inserted = True
                break
        if not _notice_inserted:
            # Fallback: prepend to paper
            final_paper = _deg_notice + final_paper

        logger.info(
            "Stage 22: Applied degraded-mode notice (score=%s, threshold=%s)",
            _deg_score,
            _deg_threshold,
        )

    # IMP-3: Deduplicate "due to computational constraints" — keep at most 1
    import re as _re_imp3

    _CONSTRAINT_PAT = _re_imp3.compile(
        r"[Dd]ue to computational constraints", _re_imp3.IGNORECASE
    )
    _matches = list(_CONSTRAINT_PAT.finditer(final_paper))
    if len(_matches) > 1:
        # Keep only the first occurrence; remove subsequent ones by
        # deleting the enclosing sentence.
        for m in reversed(_matches[1:]):
            # Find sentence boundaries around the match
            start = final_paper.rfind(".", 0, m.start())
            start = start + 1 if start >= 0 else m.start()
            end = final_paper.find(".", m.end())
            end = end + 1 if end >= 0 else m.end()
            sentence = final_paper[start:end].strip()
            if sentence:
                final_paper = final_paper[:start] + final_paper[end:]
        final_paper = re.sub(r"[^\S\n]{2,}", " ", final_paper)
        logger.info(
            "Stage 22: Removed %d duplicate 'computational constraints' disclaimers",
            len(_matches) - 1,
        )

    # IMP-19 Layer 2: Ensure at least figures are referenced in the paper
    import re as _re_fig

    chart_files = []
    # BUG-215: Also search stage-14* versioned dirs (stage-14_v1, etc.)
    # in case stage-14/ was renamed and never recreated.
    _chart_search_dirs = [stage_dir / "charts", run_dir / "stage-14" / "charts"]
    for _s14_charts in sorted(run_dir.glob("stage-14*/charts"), reverse=True):
        if _s14_charts not in _chart_search_dirs:
            _chart_search_dirs.append(_s14_charts)
    for _chart_src_dir in _chart_search_dirs:
        if _chart_src_dir.is_dir():
            chart_files.extend(sorted(_chart_src_dir.glob("*.png")))
    # BUG-190: Also inject charts not already referenced in the paper.
    # The old condition only fired when NO figures were present. Now we
    # filter to only unreferenced charts, so partially-illustrated papers
    # also get the remaining charts injected.
    _already_referenced = set()
    for _cf in chart_files:
        if _cf.name in final_paper:
            _already_referenced.add(_cf.name)
    chart_files = [cf for cf in chart_files if cf.name not in _already_referenced]
    if chart_files:
        # Distribute figures to relevant sections based on filename keywords
        _fig_placement: dict[str, list[str]] = {
            "method": [],  # architecture, method, model, pipeline diagrams
            "result": [],  # experiment, comparison, ablation charts
            "intro": [],  # concept, overview, illustration
        }
        _fig_counter = len(_already_referenced)  # start numbering after existing figs
        for cf in chart_files[:6]:
            _fig_counter += 1
            stem_lower = cf.stem.lower()
            label = cf.stem.replace("_", " ").title()
            fig_md = f"![Figure {_fig_counter}: {label}](charts/{cf.name})"
            if any(
                k in stem_lower
                for k in ("architecture", "model", "pipeline", "method", "flowchart")
            ):
                _fig_placement["method"].append(fig_md)
            elif any(
                k in stem_lower
                for k in ("experiment", "comparison", "ablation", "result", "metric")
            ):
                _fig_placement["result"].append(fig_md)
            elif any(
                k in stem_lower
                for k in ("concept", "overview", "illustration", "threat", "attack")
            ):
                _fig_placement["intro"].append(fig_md)
            else:
                _fig_placement["result"].append(fig_md)  # default to results

        # Insert figures at relevant section boundaries.
        # BUG-200: Match both H1 (#) and H2 (##) headings — LLMs generate
        # either level depending on the writing_structure prompt.
        _section_markers = {
            "method": [
                "# Method",
                "## Method",
                "# Methodology",
                "## Methodology",
                "# Approach",
                "## Approach",
                "# Framework",
                "## Framework",
                "## 3. Method",
                "## 3 Method",
            ],
            "result": [
                "# Results",
                "## Results",
                "# Experiments",
                "## Experiments",
                "# Evaluation",
                "## Evaluation",
                "## 5. Results",
                "## 4. Experiments",
                "## 5 Results",
            ],
            "intro": [
                "# Related Work",
                "## Related Work",
                "# Background",
                "## Background",
                "## 2. Related",
                "## 2 Related Work",
            ],
        }
        _total_inserted = 0
        for category, figs in _fig_placement.items():
            if not figs:
                continue
            fig_block = "\n\n" + "\n\n".join(figs) + "\n\n"
            inserted = False
            for marker in _section_markers.get(category, []):
                if marker in final_paper:
                    # Insert BEFORE the marker section (so figure appears at end of previous section)
                    final_paper = final_paper.replace(marker, fig_block + marker, 1)
                    inserted = True
                    _total_inserted += len(figs)
                    break
            if not inserted:
                # Fallback: insert before Conclusion/Limitations/Discussion
                for fallback in [
                    "# Conclusion",
                    "## Conclusion",
                    "# Limitations",
                    "## Limitations",
                    "# Discussion",
                    "## Discussion",
                ]:
                    if fallback in final_paper:
                        final_paper = final_paper.replace(
                            fallback, fig_block + fallback, 1
                        )
                        inserted = True
                        _total_inserted += len(figs)
                        break
            if not inserted:
                # BUG-200: Last resort — insert before closing fence marker
                # rather than appending after it (which puts content outside
                # the markdown fence and gets dropped by converter).
                _fence_end = final_paper.rfind("\n```")
                if _fence_end > 0:
                    final_paper = (
                        final_paper[:_fence_end] + fig_block + final_paper[_fence_end:]
                    )
                else:
                    final_paper += fig_block
                _total_inserted += len(figs)

        logger.info(
            "IMP-19: Injected %d figure references into paper_final.md (distributed across sections)",
            _total_inserted,
        )

    # IMP-24: Detect excessive number repetition
    _numbers_found = _re_fig.findall(r"\b\d+\.\d{2,}\b", final_paper)
    _num_counts = Counter(_numbers_found)
    _repeated = {n: c for n, c in _num_counts.items() if c > 3}
    if _repeated:
        logger.warning(
            "IMP-24: Numbers repeated >3 times: %s",
            _repeated,
        )

    (stage_dir / "paper_final.md").write_text(final_paper, encoding="utf-8")

    # --- Legacy fabrication sanitization (disabled — superseded by Phase 1 _sanitize_fabricated_data above) ---
    # Kept but guarded: Phase 1 always-on sanitization handles this now.
    # Only run if Phase 1 was somehow skipped (should never happen).
    _fab_flags_text = _read_prior_artifact(run_dir, "fabrication_flags.json") or ""
    _fab_flags = _safe_json_loads(_fab_flags_text, {}) if _fab_flags_text else {}
    if (
        isinstance(_fab_flags, dict)
        and _fab_flags.get("fabrication_suspected")
        and _san_report.get("numbers_replaced", 0) == 0  # Phase 1 didn't run/replace
    ):
        import re as _re_fab

        _real_vals = set()
        for rv in _fab_flags.get("real_metric_values", []):
            if isinstance(rv, (int, float)) and math.isfinite(rv):
                _real_vals.add(str(round(rv, 4)))
                _real_vals.add(str(round(rv, 2)))
                _real_vals.add(str(round(rv, 1)))
                if rv == int(rv):
                    _real_vals.add(str(int(rv)))

        def _sanitize_number(m: _re_fab.Match) -> str:  # type: ignore[name-defined]
            """Replace fabricated numbers with '--' but keep real ones."""
            num_str = m.group(0)
            # Keep the number if it matches any known real metric value
            try:
                num_val = float(num_str)
                if not math.isfinite(num_val):
                    return "--"
                rounded_strs = {
                    str(round(num_val, 4)),
                    str(round(num_val, 2)),
                    str(round(num_val, 1)),
                    *([str(int(num_val))] if num_val == int(num_val) else []),
                }
                if rounded_strs & _real_vals:
                    return num_str  # real value — keep it
            except (ValueError, OverflowError):
                return num_str
            return "--"

        # Only sanitize numbers in Results/Experiments/Evaluation/Ablation sections
        _result_section_pat = _re_fab.compile(
            r"(##\s*(?:\d+\.?\s*)?(?:Results|Experiments|Evaluation|Ablation"
            r"|Experimental Results|Quantitative).*?)(?=\n##\s|\Z)",
            _re_fab.DOTALL | _re_fab.IGNORECASE,
        )
        _sanitized_count = 0

        def _sanitize_section(sec_match: _re_fab.Match) -> str:  # type: ignore[name-defined]
            nonlocal _sanitized_count
            section_text = sec_match.group(0)

            # Replace decimal numbers (e.g., 73.42, 0.891) but NOT integers
            # that are likely structural (year, section number, figure number)
            def _replace_in_section(m: _re_fab.Match) -> str:  # type: ignore[name-defined]
                nonlocal _sanitized_count
                result = _sanitize_number(m)
                if result == "--":
                    _sanitized_count += 1
                return result

            return _re_fab.sub(r"\b\d+\.\d{1,6}\b", _replace_in_section, section_text)

        final_paper = _result_section_pat.sub(_sanitize_section, final_paper)

        if _sanitized_count > 0:
            logger.warning(
                "Stage 22: Fabrication sanitization — blanked %d unsupported "
                "numbers in Results sections (experiment had no real metrics)",
                _sanitized_count,
            )
            # Rewrite the sanitized paper
            (stage_dir / "paper_final.md").write_text(final_paper, encoding="utf-8")

    # Initialize artifacts list
    artifacts = ["paper_final.md"]
    # F2.7: Post-process citations — [cite_key] → \cite{cite_key}
    # and copy final references.bib to export stage
    _ay_map: dict[str, str] = {}  # BUG-102: author-year → cite_key map
    bib_text = _read_prior_artifact(run_dir, "references.bib")
    final_paper_latex = final_paper  # default: no citation conversion (no bib_text)
    if bib_text:
        # Replace [cite_key] patterns in the final paper with \cite{cite_key}
        # Collect all valid cite_keys from the bib file
        import re as _re

        valid_keys = set(_re.findall(r"@\w+\{([^,]+),", bib_text))

        # BUG-102: Recover author-year citations → [cite_key] format.
        # When Stage 19 (paper_revision) converts [cite_key] to [Author et al., 2024],
        # the downstream regex can't match them. Build a reverse map from bib entries.
        def _build_author_year_map(bib: str, keys: set[str]) -> dict[str, str]:
            """Build mapping from author-year patterns to cite_keys.

            Returns dict like:
              "Raissi et al., 2019" → "raissi2019physicsinformed"
              "Tavella and Randall, 2000" → "tavella2000pricing"
            """
            mapping: dict[str, str] = {}
            # Parse each bib entry for author + year
            # BUG-DA8-17: Allow newline OR whitespace before closing brace
            # Use \n} or just } at start-of-line to avoid greedy cross-entry match
            entry_pat = _re.compile(
                r"@\w+\{([^,]+),\s*(.*?)(?:\n\}|^[ \t]*\})", _re.DOTALL | _re.MULTILINE
            )
            for m in entry_pat.finditer(bib):
                key = m.group(1).strip()
                if key not in keys:
                    continue
                body = m.group(2)
                # Extract author field
                author_m = _re.search(
                    r"author\s*=\s*[\{\"](.*?)[\}\"]", body, _re.IGNORECASE
                )
                year_m = _re.search(
                    r"year\s*=\s*[\{\"]?(\d{4})[\}\"]?", body, _re.IGNORECASE
                )
                if not author_m or not year_m:
                    continue
                author_raw = author_m.group(1).strip()
                year = year_m.group(1)
                # Parse author names (split on " and ")
                authors = [a.strip() for a in _re.split(r"\s+and\s+", author_raw)]
                # Extract last names
                last_names = []
                for a in authors:
                    if "," in a:
                        last_names.append(a.split(",")[0].strip())
                    else:
                        parts = a.split()
                        last_names.append(parts[-1] if parts else a)
                if not last_names:
                    continue
                # Generate author-year patterns:
                # 1 author: "Smith, 2024"
                # 2 authors: "Smith and Jones, 2024"
                # 3+ authors: "Smith et al., 2024"
                if len(last_names) == 1:
                    patterns = [f"{last_names[0]}, {year}"]
                elif len(last_names) == 2:
                    patterns = [
                        f"{last_names[0]} and {last_names[1]}, {year}",
                        f"{last_names[0]} \\& {last_names[1]}, {year}",
                    ]
                else:
                    patterns = [
                        f"{last_names[0]} et al., {year}",
                        f"{last_names[0]} et al. {year}",
                    ]
                    # Also add "Smith and Jones, 2024" for first two authors
                    patterns.append(f"{last_names[0]} and {last_names[1]}, {year}")
                for pat in patterns:
                    mapping[pat] = key
            return mapping

        _ay_map = _build_author_year_map(bib_text, valid_keys)
        if _ay_map:
            # Count how many author-year citations exist in the paper
            _ay_found = 0
            for _ay_pat in _ay_map:
                if _ay_pat in final_paper:
                    _ay_found += 1
            if _ay_found > 0:
                logger.info(
                    "Stage 22: Found %d author-year citation patterns — "
                    "converting back to [cite_key] format.",
                    _ay_found,
                )
                # Sort by longest pattern first to avoid partial matches
                for _ay_pat in sorted(_ay_map, key=len, reverse=True):
                    _ay_key = _ay_map[_ay_pat]
                    # Match [Author et al., 2024] or [Author and Jones, 2024; ...]
                    # Handle single-citation brackets
                    final_paper = final_paper.replace(f"[{_ay_pat}]", f"[{_ay_key}]")
                    # Handle multi-citation brackets [A et al., 2020; B et al., 2021]
                    # Replace the author-year segment only inside [...] brackets
                    final_paper = _re.sub(
                        r"\[([^\]]*?)" + _re.escape(_ay_pat) + r"([^\]]*?)\]",
                        lambda _m, _key=_ay_key: "["
                        + _m.group(1)
                        + _key
                        + _m.group(2)
                        + "]",
                        final_paper,
                    )

                # Fix multi-key brackets: [key1; key2] → [key1, key2]
                # (author-year uses semicolons, cite-keys use commas)
                def _fix_semicolon_cites(m_sc: _re.Match[str]) -> str:
                    inner = m_sc.group(1)
                    # Only convert if ALL segments look like cite keys
                    parts = [p.strip() for p in inner.split(";")]
                    _ck = r"[a-zA-Z][a-zA-Z0-9_-]*\d{4}[a-zA-Z0-9_]*"
                    if all(_re.fullmatch(_ck, p) for p in parts):
                        return "[" + ", ".join(parts) + "]"
                    return m_sc.group(0)

                final_paper = _re.sub(
                    r"\[([^\]]+;[^\]]+)\]", _fix_semicolon_cites, final_paper
                )
                (stage_dir / "paper_final.md").write_text(final_paper, encoding="utf-8")

        # R10-Fix4: Citation cross-validation
        # BUG-187: Also parse multi-key brackets like [key1, key2, key3].
        # The old regex only matched single-key brackets [key2020word].
        _cite_key_pat = r"[a-zA-Z]+\d{4}[a-zA-Z0-9_-]*"
        cited_keys_in_paper: set[str] = set()
        # Single-key brackets
        for m in _re.finditer(rf"\[({_cite_key_pat})\]", final_paper):
            cited_keys_in_paper.add(m.group(1))
        # Multi-key brackets [key1, key2] or [key1; key2]
        for m in _re.finditer(r"\[([^\]]{10,300})\]", final_paper):
            inner = m.group(1)
            # Only parse if it looks like citation keys (has year-like digits)
            parts = _re.split(r"[,;]\s*", inner)
            if all(_re.fullmatch(_cite_key_pat, p.strip()) for p in parts if p.strip()):
                for p in parts:
                    if p.strip():
                        cited_keys_in_paper.add(p.strip())

        if valid_keys and cited_keys_in_paper:
            invalid_keys = cited_keys_in_paper - valid_keys
            if invalid_keys:
                logger.warning(
                    "Stage 22: Found %d citation keys in paper not in references.bib: %s",
                    len(invalid_keys),
                    ", ".join(sorted(invalid_keys)[:20]),
                )
                # P2-01: _resolve_missing_citations is diagnostic-only now —
                # it used to inject its API-search match straight into
                # references.bib/valid_keys, which repairs a model-invented
                # citation into legitimacy instead of treating it as the
                # hallucination it is. Every invented key is now stripped
                # from the paper regardless of whether a plausible match was
                # found; the match is logged for debugging only.
                resolved_keys: set[str] = set()
                new_bib_entries: list[str] = []
                if len(invalid_keys) <= 30:  # Sanity: don't flood APIs
                    resolved_keys, new_bib_entries = _resolve_missing_citations(
                        invalid_keys, bib_text
                    )
                    if resolved_keys:
                        logger.info(
                            "Stage 22: Found plausible matches for %d/%d invented "
                            "citations via API lookup — NOT injecting into "
                            "references.bib (P2-01: detection, not repair). "
                            "Removing all invented citations from the paper.",
                            len(resolved_keys),
                            len(invalid_keys),
                        )

                still_invalid = invalid_keys
                if still_invalid:
                    # IMP-29: Remove remaining unresolvable citations from
                    # BOTH single-key and multi-key brackets.
                    import re as _re_imp29

                    for bad_key in still_invalid:
                        # Remove single-key brackets
                        final_paper = final_paper.replace(f"[{bad_key}]", "")

                        # Remove from multi-key brackets: [good, BAD, good] → [good, good]
                        def _remove_from_multi(m: _re.Match, _bad_key=bad_key) -> str:
                            inner = m.group(1)
                            parts = [p.strip() for p in _re.split(r"[,;]\s*", inner)]
                            filtered = [p for p in parts if p != _bad_key]
                            if not filtered:
                                return ""
                            return "[" + ", ".join(filtered) + "]"

                        final_paper = _re_imp29.sub(
                            r"\[([^\]]*\b" + _re.escape(bad_key) + r"\b[^\]]*)\]",
                            _remove_from_multi,
                            final_paper,
                        )
                    # Clean up whitespace artifacts from removed citations
                    final_paper = _re_imp29.sub(r"  +", " ", final_paper)
                    final_paper = _re_imp29.sub(r" ([.,;:)])", r"\1", final_paper)
                (stage_dir / "paper_final.md").write_text(final_paper, encoding="utf-8")
                if still_invalid:
                    (stage_dir / "invalid_citations.json").write_text(
                        json.dumps(sorted(still_invalid), indent=2), encoding="utf-8"
                    )
                    artifacts.append("invalid_citations.json")
                if resolved_keys:
                    (stage_dir / "resolved_citations.json").write_text(
                        json.dumps(sorted(resolved_keys), indent=2), encoding="utf-8"
                    )
                    artifacts.append("resolved_citations.json")

        if valid_keys:
            _CITE_KEY_PAT = r"[a-zA-Z][a-zA-Z0-9_-]*\d{4}[a-zA-Z0-9]*"

            # Step 1: Convert multi-key brackets [key1, key2] → \cite{key1, key2}
            def _replace_multi_cite(m: _re.Match[str]) -> str:
                keys = [k.strip() for k in m.group(1).split(",")]
                matched = [k for k in keys if k in valid_keys]
                if matched:
                    return "\\cite{" + ", ".join(matched) + "}"
                return m.group(0)

            final_paper_latex = _re.sub(
                rf"\[({_CITE_KEY_PAT}(?:\s*,\s*{_CITE_KEY_PAT})+)\]",
                _replace_multi_cite,
                final_paper,
            )

            # Step 2: Convert single-key brackets [key] → \cite{key}
            def _replace_cite(m: _re.Match[str]) -> str:
                key = m.group(1)
                if key in valid_keys:
                    return f"\\cite{{{key}}}"
                return m.group(0)

            final_paper_latex = _re.sub(
                rf"\[({_CITE_KEY_PAT})\]", _replace_cite, final_paper_latex
            )

            # Step 3: Merge adjacent \cite{a} \cite{b} → \cite{a, b}
            def _merge_adjacent_cites(m: _re.Match[str]) -> str:
                keys = _re.findall(r"\\cite\{([^}]+)\}", m.group(0))
                return "\\cite{" + ", ".join(keys) + "}"

            final_paper_latex = _re.sub(
                r"\\cite\{[^}]+\}(?:\s*\\cite\{[^}]+\})+",
                _merge_adjacent_cites,
                final_paper_latex,
            )

            (stage_dir / "paper_final_latex.md").write_text(
                final_paper_latex, encoding="utf-8"
            )
            artifacts.append("paper_final_latex.md")
        # IMP-1: Prune uncited bibliography entries — keep only keys
        # that actually appear in the paper text (bracket or \cite form).
        if valid_keys:
            _all_cited: set[str] = set()
            # Bracket-format citations [key]
            _all_cited.update(
                _re.findall(r"\[([a-zA-Z]+\d{4}[a-zA-Z0-9_-]*)\]", final_paper)
            )
            # \cite{key, key2} format (original + latex-converted)
            for _src in (
                final_paper,
                final_paper_latex,
            ):
                for _cm in _re.finditer(r"\\cite\{([^}]+)\}", _src):
                    _all_cited.update(k.strip() for k in _cm.group(1).split(","))
            uncited_keys = valid_keys - _all_cited
            if uncited_keys:
                bib_text = _remove_bibtex_entries(bib_text, uncited_keys)
                logger.info(
                    "Stage 22: Pruned %d uncited bibliography entries (kept %d)",
                    len(uncited_keys),
                    len(valid_keys) - len(uncited_keys),
                )

        # Write final references.bib
        (stage_dir / "references.bib").write_text(bib_text, encoding="utf-8")
        artifacts.append("references.bib")
        logger.info(
            "Stage 22: Exported references.bib with %d entries",
            len(valid_keys) if valid_keys else 0,
        )

        # P2-01: invalid_citations.json lists cite_keys the LLM wrote in the
        # paper that were never in references.bib at all — invented out of
        # parametric memory, not merely mismatched. They've already been
        # stripped from the prose (see the still_invalid handling above),
        # but the draft process did fabricate a citation, and per P2-01 that
        # is no longer silently repaired — it blocks export instead.
        _invalid_citations_path = stage_dir / "invalid_citations.json"
        if _invalid_citations_path.is_file():
            try:
                _invented_keys = json.loads(
                    _invalid_citations_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                _invented_keys = []
            if _invented_keys:
                logger.error(
                    "Stage 22: %d citation key(s) invented by the LLM (never in "
                    "references.bib) — blocking export: %s",
                    len(_invented_keys),
                    ", ".join(_invented_keys[:20]),
                )
                return StageResult(
                    stage=Stage.EXPORT_PUBLISH,
                    status=StageStatus.FAILED,
                    artifacts=tuple(artifacts),
                    evidence_refs=tuple(f"stage-22/{a}" for a in artifacts),
                    error=(
                        f"E22_EXPORT_FAIL: {len(_invented_keys)} invented citation "
                        f"key(s) found in draft: {', '.join(_invented_keys[:10])}"
                    ),
                )

        # P0-03: verify citations here, not in stage 23. stages.py's own
        # comment says hallucinated citations MUST block export, but
        # CITATION_VERIFY (stage 23) depends on EXPORT_PUBLISH (stage 22) —
        # it ran after export, so it could never actually block it. This
        # must run AFTER _resolve_missing_citations above (not before, and
        # not by reordering the stage graph): that step mutates the
        # citation key-space by resolving/adding entries for LLM-invented
        # keys, so verifying any earlier would miss exactly the
        # hallucination-prone additions.
        try:
            from berb.literature.verify import verify_citations as _verify_export

            _export_report = _verify_export(
                bib_text, s2_api_key=getattr(config.llm, "s2_api_key", "") or ""
            )
            if _export_report.hallucinated > 0:
                _halluc_keys = ", ".join(
                    r.cite_key
                    for r in _export_report.results
                    if r.status.value == "hallucinated"
                )
                logger.error(
                    "Stage 22: %d hallucinated citation(s) in references.bib — "
                    "blocking export: %s",
                    _export_report.hallucinated,
                    _halluc_keys,
                )
                (stage_dir / "citation_verification_report.json").write_text(
                    json.dumps(_export_report.to_dict(), indent=2), encoding="utf-8"
                )
                artifacts.append("citation_verification_report.json")
                return StageResult(
                    stage=Stage.EXPORT_PUBLISH,
                    status=StageStatus.FAILED,
                    artifacts=tuple(artifacts),
                    evidence_refs=tuple(f"stage-22/{a}" for a in artifacts),
                    error=(
                        f"E22_EXPORT_FAIL: {_export_report.hallucinated} hallucinated "
                        f"citation(s) found: {_halluc_keys}"
                    ),
                )
        except Exception as _verify_exc:  # noqa: BLE001
            logger.warning(
                "Stage 22: citation verification failed, proceeding without gate: %s",
                _verify_exc,
            )

    # Conference template: generate .tex file
    try:
        from berb.templates import get_template, markdown_to_latex

        tpl = get_template(config.export.target_conference)
        # Use the latex-citation-processed version if available
        tex_source = final_paper_latex
        # Append NeurIPS-style checklist if target is a ML conference
        if tpl.name in (
            "neurips_2024",
            "neurips_2025",
            "icml_2025",
            "icml_2026",
            "iclr_2025",
            "iclr_2026",
        ):
            _has_exp = bool(_read_prior_artifact(run_dir, "experiment_summary.json"))
            _checklist = _generate_neurips_checklist(
                has_experiments=_has_exp,
                has_code=True,
            )
            if "NeurIPS Paper Checklist" not in tex_source:
                tex_source = tex_source.rstrip() + "\n\n" + _checklist
        _t = _extract_paper_title(tex_source)
        tex_content = markdown_to_latex(
            tex_source,
            tpl,
            title=_t if _t != "Untitled Paper" else "",
            authors=config.export.authors,
            bib_file=config.export.bib_file,
            bib_entries=_ay_map or None,
        )
        (stage_dir / "paper.tex").write_text(tex_content, encoding="utf-8")
        artifacts.append("paper.tex")
        logger.info(
            "Stage 22: Generated paper.tex for %s (%d chars)",
            tpl.display_name,
            len(tex_content),
        )
        # --- Phase 1 anti-fabrication: verify paper against VerifiedRegistry ---
        _vresult = (
            None  # BUG-DA8-04: Initialize before try to avoid fragile dir() check
        )
        try:
            from berb.pipeline.paper_verifier import verify_paper as _verify_paper

            # BUG-222: Use best_only=True to validate against promoted best data only
            from berb.pipeline.verified_registry import (
                VerifiedRegistry as _VR22,  # noqa: N814
            )

            _vr22 = _VR22.from_run_dir(
                run_dir,
                metric_direction=config.experiment.metric_direction,
                best_only=True,
            )
            if _vr22.values:
                _vresult = _verify_paper(tex_content, _vr22)
                (stage_dir / "paper_verification.json").write_text(
                    json.dumps(
                        {
                            "passed": _vresult.passed,
                            "severity": _vresult.severity,
                            "total_checked": _vresult.total_numbers_checked,
                            "total_verified": _vresult.total_numbers_verified,
                            "strict_violations": _vresult.strict_violations,
                            "lenient_violations": _vresult.lenient_violations,
                            "fabrication_rate": round(_vresult.fabrication_rate, 4),
                            "unverified_numbers": [
                                {
                                    "value": u.value,
                                    "line": u.line_number,
                                    "section": u.section,
                                    "in_table": u.in_table,
                                }
                                for u in _vresult.unverified_numbers[:20]
                            ],
                            "fabricated_conditions": [
                                {"name": fc.name, "line": fc.line_number}
                                for fc in _vresult.fabricated_conditions
                            ],
                            "config_warnings": getattr(_vresult, "config_warnings", []),
                            "summary": _vresult.summary,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                logger.info(
                    "Stage 22: Paper verification — %s (%d checked, %d verified, "
                    "%d strict violations, fabrication_rate=%.1f%%)",
                    _vresult.severity,
                    _vresult.total_numbers_checked,
                    _vresult.total_numbers_verified,
                    _vresult.strict_violations,
                    _vresult.fabrication_rate * 100,
                )
        except Exception as _pv_exc:
            logger.debug("Stage 22: Paper verification skipped: %s", _pv_exc)

        # BUG-23 P1: Enforce REJECT verdict — sanitize unverified numbers
        if _vresult is not None and getattr(_vresult, "severity", None) == "REJECT":
            logger.warning(
                "Stage 22: Paper REJECTED by verifier (fabrication_rate=%.1f%%, "
                "%d strict violations). Sanitizing unverified numbers.",
                _vresult.fabrication_rate * 100,
                _vresult.strict_violations,
            )
            # Replace unverified numbers in strict sections/tables with "---"
            import re as _re_san2

            # BUG-R49-02: Section names that sound like results but are
            # actually protocol/setup sections should NOT trigger strict
            # sanitization.  Exempt sections containing "dataset", "setup",
            # "protocol", "hyperparameter", or "implementation".
            _STRICT_EXEMPT_KW = {
                "dataset",
                "setup",
                "protocol",
                "hyperparameter",
                "implementation",
                "hardware",
                "infrastructure",
            }

            _sanitized_tex = tex_content
            _san2_count = 0
            for _uv in sorted(
                _vresult.unverified_numbers, key=lambda u: -u.line_number
            ):
                # Only sanitize strict-section / in-table numbers
                _uv_section_lower = (_uv.section or "").lower()
                _uv_is_strict = any(
                    s in _uv_section_lower
                    for s in (
                        "results",
                        "experiment",
                        "evaluation",
                        "ablation",
                        "comparison",
                        "analysis",
                    )
                )
                # BUG-R49-02: Exempt protocol/setup sections from strict mode
                if _uv_is_strict and any(
                    kw in _uv_section_lower for kw in _STRICT_EXEMPT_KW
                ):
                    _uv_is_strict = False
                if _uv_is_strict or _uv.in_table:
                    _lines = _sanitized_tex.split("\n")
                    if 0 < _uv.line_number <= len(_lines):
                        _orig_line = _lines[_uv.line_number - 1]
                        # BUG-R49-01: Use word-boundary regex instead of
                        # naive substring matching to avoid replacing numbers
                        # inside identifiers (e.g. "18" in "ResNet18").
                        # BUG-206: Include ASCII hyphen and Unicode hyphens
                        # (U+2010 hyphen, U+2011 non-breaking hyphen,
                        # U+2013 en-dash) so that model variant numbers
                        # like "34" in "ResNet-34" or "ResNet‑34" are not
                        # mistaken for unverified experimental values.
                        # BUG-210: Include period (.) so that fractional
                        # parts of decimals in condition names like
                        # "ema_decay_0.9" are not treated as standalone
                        # numbers (prevents "0.9" → "0.---").
                        _BOUNDARY = "A-Za-z0-9_\u2010\u2011\u2013\\-."
                        for _rep in (
                            f"{_uv.value:.4f}".rstrip("0").rstrip("."),
                            f"{_uv.value:.3f}",
                            f"{_uv.value:.2f}",
                            f"{_uv.value:.1f}",
                            f"{_uv.value:g}",
                            str(_uv.value),
                        ):
                            # Word boundary: number must NOT be adjacent to
                            # alphanumeric, underscore, or hyphen on either side.
                            _pat = (
                                rf"(?<![{_BOUNDARY}])"
                                + _re_san2.escape(_rep)
                                + rf"(?![{_BOUNDARY}])"
                            )
                            if _re_san2.search(_pat, _orig_line):
                                _lines[_uv.line_number - 1] = _re_san2.sub(
                                    _pat,
                                    "---",
                                    _orig_line,
                                    count=1,
                                )
                                _san2_count += 1
                                break
                        _sanitized_tex = "\n".join(_lines)
            if _sanitized_tex != tex_content:
                tex_content = _sanitized_tex
                (stage_dir / "paper.tex").write_text(tex_content, encoding="utf-8")
                logger.info(
                    "Stage 22: Sanitized paper.tex — replaced %d unverified numbers with '---'",
                    _san2_count,
                )

        # Copy bundled style files alongside paper.tex
        for sf in tpl.get_style_files():
            import shutil as _shutil_sty

            _shutil_sty.copy2(sf, stage_dir / sf.name)

        # --- Pre-compilation: copy charts and fix figure paths ---
        # BUG-R41-12: Charts MUST be available before compile_latex(),
        # otherwise \includegraphics references fail → "Float(s) lost".
        try:
            chart_dir = stage_dir / "charts"
            chart_dir.mkdir(parents=True, exist_ok=True)
            charts: list[Path] = []

            # Copy FigureAgent charts from stage-14 (any version)
            _fa_charts_found = False
            for _fa_dir in sorted(run_dir.glob("stage-14*/charts"), reverse=True):
                _fa_pngs = list(_fa_dir.glob("fig_*.png"))
                if _fa_pngs:
                    import shutil

                    for _fa_png in _fa_pngs:
                        dest = chart_dir / _fa_png.name
                        shutil.copy2(_fa_png, dest)
                        charts.append(dest)
                    _fa_charts_found = True
                    logger.info(
                        "Stage 22: Copied %d FigureAgent charts from %s",
                        len(_fa_pngs),
                        _fa_dir,
                    )
                    break

            # Generate structured charts from visualize.py
            from berb.experiment.visualize import generate_all_charts

            _metric_dir = getattr(config.experiment, "metric_direction", "minimize")
            _viz_charts = generate_all_charts(
                run_dir,
                chart_dir,
                metric_key=config.experiment.metric_key,
                metric_direction=_metric_dir,
            )
            charts.extend(_viz_charts)

            if charts:
                artifacts.append("charts/")
                logger.info("Stage 22: Generated %d chart(s) total", len(charts))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chart generation failed: %s", exc)

        # BUG-99: Fix \includegraphics paths that don't match actual chart files
        try:
            reconcile_figure_refs(stage_dir / "paper.tex", stage_dir / "charts")
        except Exception as _fig_exc:  # noqa: BLE001
            logger.debug("Stage 22: Figure path validation skipped: %s", _fig_exc)

        # BUG-R41-12: Remove figure blocks referencing files that still don't exist
        try:
            tex_path = stage_dir / "paper.tex"
            if tex_path.exists():
                from berb.templates.compiler import remove_missing_figures

                _tex_text = tex_path.read_text(encoding="utf-8")
                _fixed_tex, _removed_figs = remove_missing_figures(_tex_text, stage_dir)
                if _removed_figs:
                    tex_path.write_text(_fixed_tex, encoding="utf-8")
                    logger.warning(
                        "Stage 22: Removed %d figure block(s) with missing images: %s",
                        len(_removed_figs),
                        _removed_figs,
                    )
        except Exception as _rmf_exc:  # noqa: BLE001
            logger.debug("Stage 22: remove_missing_figures skipped: %s", _rmf_exc)

        # Compile verification
        try:
            from berb.templates.compiler import compile_latex

            _compile_result = compile_latex(stage_dir / "paper.tex", max_attempts=2)
            if _compile_result.success:
                logger.info("Stage 22: LaTeX compilation verification PASSED")
                artifacts.append("paper.pdf")
                # PDF-as-reviewer: LLM-based visual review of compiled PDF
                _pdf_path = stage_dir / "paper.pdf"
                if _pdf_path.exists() and llm is not None:
                    try:
                        _pdf_review = _get_review_compiled_pdf()(
                            _pdf_path, llm, config.research.topic
                        )
                        if _pdf_review:
                            (stage_dir / "pdf_review.json").write_text(
                                json.dumps(_pdf_review, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )
                            artifacts.append("pdf_review.json")
                            _pdf_score = _pdf_review.get("overall_score", 0)
                            if _pdf_score < 5:
                                logger.warning(
                                    "Stage 22: PDF visual review score %d/10 — %s",
                                    _pdf_score,
                                    _pdf_review.get("summary", ""),
                                )
                            else:
                                logger.info(
                                    "Stage 22: PDF visual review score %d/10",
                                    _pdf_score,
                                )
                    except Exception as _pdf_exc:  # noqa: BLE001
                        logger.debug("Stage 22: PDF review skipped: %s", _pdf_exc)
                # Claim-citation hallucination check: does each \cite{} actually
                # support the specific claim it's attached to, and does the key
                # exist in this paper's own bibliography?
                if _pdf_path.exists() and llm is not None:
                    try:
                        import asyncio

                        from berb.literature.verify import parse_bibtex_entries
                        from berb.pipeline.hallucination_detector import (
                            HallucinationDetector,
                        )

                        _bib_text_h = (
                            _read_prior_artifact(run_dir, "references.bib") or ""
                        )
                        _known_keys = {
                            e["key"] for e in parse_bibtex_entries(_bib_text_h)
                        }
                        _hdet = HallucinationDetector(
                            llm_client=llm, known_bib_keys=_known_keys
                        )
                        _tex_text_h = tex_path.read_text(encoding="utf-8")
                        _halluc_report = asyncio.run(
                            _hdet.verify_paper(tex_path, paper_text=_tex_text_h)
                        )
                        (stage_dir / "hallucination_report.json").write_text(
                            json.dumps(
                                _halluc_report.to_dict(), indent=2, ensure_ascii=False
                            ),
                            encoding="utf-8",
                        )
                        artifacts.append("hallucination_report.json")
                        if _halluc_report.has_hallucinations:
                            logger.warning(
                                "Stage 22: Hallucination check %.1f/10 — %d unverified "
                                "citation(s), %d unsupported claim(s)",
                                _halluc_report.overall_score,
                                _halluc_report.hallucinated_citations,
                                _halluc_report.unsupported_claims,
                            )
                        else:
                            logger.info(
                                "Stage 22: Hallucination check passed (%.1f/10)",
                                _halluc_report.overall_score,
                            )
                    except Exception as _halluc_exc:  # noqa: BLE001
                        logger.debug(
                            "Stage 22: Hallucination check skipped: %s", _halluc_exc
                        )
                # P1-03: 5-reviewer ensemble moved to stage 20 (_execute_quality_gate)
                # so its verdict can actually gate the pipeline instead of being
                # computed on the already-exported paper and read by nothing.
                # Humanitarian impact assessment: contribution-type classification
                # and a broader-impact statement, non-blocking, informational only.
                if _pdf_path.exists() and llm is not None:
                    try:
                        import asyncio

                        from berb.writing.impact_assessment import (
                            HumanitarianImpactAssessment,
                        )

                        _tex_text_i = tex_path.read_text(encoding="utf-8")
                        _title_i = (
                            _extract_paper_title(_tex_text_i) or config.research.topic
                        )
                        _impact_assessor = HumanitarianImpactAssessment(llm_client=llm)
                        _contribution = asyncio.run(
                            _impact_assessor.assess_contribution_type(
                                _tex_text_i, title=_title_i
                            )
                        )
                        _broader_impact = asyncio.run(
                            _impact_assessor.generate_broader_impact(
                                _tex_text_i, title=_title_i
                            )
                        )
                        (stage_dir / "impact_assessment.json").write_text(
                            json.dumps(
                                {
                                    **_contribution.to_dict(),
                                    "broader_impact_statement": _broader_impact,
                                },
                                indent=2,
                                ensure_ascii=False,
                            ),
                            encoding="utf-8",
                        )
                        artifacts.append("impact_assessment.json")
                        logger.info(
                            "Stage 22: Contribution type: %s (novelty=%.1f/10)",
                            _contribution.contribution_type.value,
                            _contribution.novelty_score,
                        )
                        if (
                            _contribution.contribution_type.value
                            == "text_without_insight"
                        ):
                            logger.warning(
                                "Stage 22: Impact assessment flagged this paper as "
                                "text-without-insight — %s",
                                _contribution.reasoning,
                            )
                    except Exception as _impact_exc:  # noqa: BLE001
                        logger.debug(
                            "Stage 22: Impact assessment skipped: %s", _impact_exc
                        )
                # Source-grounding check: does the paper's text share
                # vocabulary with the literature corpus actually gathered in
                # Phase B? A cheap, deterministic, complementary signal to
                # the LLM-based claim-citation check above (this one ignores
                # \cite{} entirely and just checks topical overlap).
                if _pdf_path.exists():
                    try:
                        import asyncio

                        from berb.writing.source_writer import SourceGroundingVerifier

                        _tex_text_g = tex_path.read_text(encoding="utf-8")
                        _candidates_text_g = (
                            _read_prior_artifact(run_dir, "candidates.jsonl") or ""
                        )
                        _sources_g = [
                            row
                            for row in (
                                _safe_json_loads(line, {})
                                for line in _candidates_text_g.strip().splitlines()
                            )
                            if isinstance(row, dict) and row.get("abstract")
                        ]
                        if _sources_g:
                            _verifier = SourceGroundingVerifier(min_grounding_score=0.3)
                            _grounding = asyncio.run(
                                _verifier.verify_grounding(_tex_text_g, _sources_g)
                            )
                            (stage_dir / "grounding_report.json").write_text(
                                _grounding.model_dump_json(indent=2),
                                encoding="utf-8",
                            )
                            artifacts.append("grounding_report.json")
                            logger.info(
                                "Stage 22: Source grounding score %.2f (%d/%d claims grounded)",
                                _grounding.grounding_score,
                                _grounding.grounded_claims,
                                _grounding.total_claims,
                            )
                    except Exception as _ground_exc:  # noqa: BLE001
                        logger.debug(
                            "Stage 22: Source grounding check skipped: %s", _ground_exc
                        )
                # Post-compilation quality checks
                try:
                    from berb.templates.compiler import check_compiled_quality

                    _qc = check_compiled_quality(stage_dir / "paper.tex")
                    if _qc.warnings_summary:
                        logger.warning(
                            "Stage 22: Quality checks: %s",
                            "; ".join(_qc.warnings_summary),
                        )
                    (stage_dir / "compilation_quality.json").write_text(
                        json.dumps(
                            {
                                "page_count": _qc.page_count,
                                "unresolved_refs": _qc.unresolved_refs,
                                "unresolved_cites": _qc.unresolved_cites,
                                "overfull_hboxes": len(_qc.overfull_hboxes),
                                "orphan_figures": _qc.orphan_figures,
                                "orphan_labels": _qc.orphan_labels,
                                "warnings": _qc.warnings_summary,
                            },
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    artifacts.append("compilation_quality.json")
                    # BUG-27: Warn if page count exceeds limit
                    _page_limit = 10
                    if _qc.page_count and _qc.page_count > _page_limit:
                        logger.warning(
                            "BUG-27: Paper is %d pages (limit %d). "
                            "Consider tightening content in revision.",
                            _qc.page_count,
                            _page_limit,
                        )
                except Exception as _qc_exc:  # noqa: BLE001
                    logger.debug("Stage 22: Quality checks skipped: %s", _qc_exc)
            else:
                logger.warning(
                    "Stage 22: LaTeX compilation verification FAILED: %s",
                    _compile_result.errors[:3],
                )
                # Add compilation failure comment to .tex
                _tex_path = stage_dir / "paper.tex"
                if _tex_path.exists():
                    _tex_content = _tex_path.read_text(encoding="utf-8")
                    if "% WARNING: Compilation failed" not in _tex_content:
                        _tex_content = (
                            "% WARNING: Compilation failed. Errors:\n"
                            + "".join(f"% {e}\n" for e in _compile_result.errors[:5])
                            + _tex_content
                        )
                        _tex_path.write_text(_tex_content, encoding="utf-8")
        except Exception as _compile_exc:  # noqa: BLE001
            logger.debug("Stage 22: Compile verification skipped: %s", _compile_exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("LaTeX generation failed: %s", exc, exc_info=True)

    # (Charts, BUG-99 path fix, and remove_missing_figures are now handled
    #  BEFORE compile_latex() — see "Pre-compilation" block above.)

    # --- Code packaging ---
    artifacts.extend(_package_code_release(stage_dir, run_dir, final_paper))

    # WS-5.5: Generate framework diagram prompt for methodology section
    try:
        _framework_prompt = _generate_framework_diagram_prompt(
            final_paper, config, llm=llm
        )
        if _framework_prompt:
            _chart_dir = stage_dir / "charts"
            _chart_dir.mkdir(parents=True, exist_ok=True)
            (_chart_dir / "framework_diagram_prompt.md").write_text(
                _framework_prompt, encoding="utf-8"
            )
            logger.info(
                "Stage 22: Generated framework diagram prompt → charts/framework_diagram_prompt.md"
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Stage 22: Framework diagram prompt generation skipped: %s", exc)

    # Export to PDF/LaTeX/other formats using MultiFormatExporter
    try:
        from berb.export import ExportConfig, ExportFormat, MultiFormatExporter

        _export_config = config.export
        _output_dir = run_dir / _export_config.output_dir
        _output_dir.mkdir(parents=True, exist_ok=True)

        # Parse paper content for export
        _paper_content = {
            "title": _extract_paper_title(final_paper),
            "content": final_paper,
            "authors": _export_config.authors,
        }

        # Get references
        _bib_path = stage_dir / "references.bib"
        _references = []
        if _bib_path.exists():
            try:
                import re as _bib_re

                _bib_text = _bib_path.read_text(encoding="utf-8")
                # Parse bib entries into dict format
                for _entry in _bib_re.findall(
                    r"@(\w+)\{([^,]+),\s*(.*?)\n\}", _bib_text, _bib_re.DOTALL
                ):
                    _references.append(
                        {"type": _entry[0], "key": _entry[1], "content": _entry[2]}
                    )
            except Exception:
                pass

        # Get figures
        _figures = []
        for _chart_dir in sorted(stage_dir.glob("charts")):
            if _chart_dir.is_dir():
                _figures.extend([str(f) for f in _chart_dir.glob("*.png")])

        # Create exporter config and run export
        _exp_config = ExportConfig(
            formats=[
                ExportFormat(f)
                for f in _export_config.formats
                if f in [e.value for e in ExportFormat]
            ],
            output_dir=str(_output_dir),
            template=_export_config.template,
        )
        _exporter = MultiFormatExporter(config=_exp_config)

        # Run async export
        import asyncio

        _export_result = asyncio.run(
            _exporter.export(_paper_content, _references, _figures)
        )

        if _export_result.exported_formats:
            logger.info(
                "Stage 22: Exported paper to formats: %s",
                ", ".join(_export_result.exported_formats),
            )
            # Add exported files to artifacts
            for _fmt in _export_result.exported_formats:
                _fmt_dir = _output_dir / _fmt
                if _fmt_dir.exists():
                    for _f in _fmt_dir.rglob("*"):
                        if _f.is_file() and _f.suffix in [
                            ".pdf",
                            ".tex",
                            ".html",
                            ".docx",
                        ]:
                            artifacts.append(str(_f.relative_to(run_dir)))
    except Exception as _exc:  # noqa: BLE001
        logger.warning("Stage 22: Export to PDF/LaTeX failed: %s", _exc)

    return StageResult(
        stage=Stage.EXPORT_PUBLISH,
        status=StageStatus.DONE,
        artifacts=tuple(artifacts),
        evidence_refs=tuple(f"stage-22/{a}" for a in artifacts),
    )


# ---------------------------------------------------------------------------
# Citation helpers
# ---------------------------------------------------------------------------
