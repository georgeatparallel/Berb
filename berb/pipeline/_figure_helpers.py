"""Figure generation and review helpers for the pipeline.

Extracted from _helpers.py — all functions re-exported from _helpers.py
for backward compatibility.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    import re as _re

    # Collapse ".." (path traversal) into a single underscore before
    # general sanitization, but preserve single dots (e.g. file extensions).
    safe = _re.sub(r"\.\.+", "_", name)
    safe = _re.sub(r"[^\w\-_. ]", "_", safe)
    safe = safe.strip().replace(" ", "_")[:100]
    return safe or "unnamed"


def _default_hypotheses(topic: str) -> str:
    """Generate default hypotheses when the LLM fails."""
    import datetime

    return (
        f"# Research Hypotheses\n\n"
        f"## Hypothesis 1: Performance Baseline\n"
        f"**Claim:** The proposed method will achieve competitive results on standard benchmarks.\n"
        f"**Rationale:** Based on established theory in {topic}.\n"
        f"**Test:** Compare against SOTA baselines using standard metrics.\n\n"
        f"## Hypothesis 2: Ablation Study\n"
        f"**Claim:** Each component of the proposed method contributes to overall performance.\n"
        f"**Rationale:** Component analysis will reveal relative importance.\n"
        f"**Test:** Systematic ablation with statistical significance testing.\n\n"
        f"_Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"
    )


def _default_paper_outline(topic: str) -> str:
    """Generate a default paper outline when the LLM fails."""
    return (
        f"# Paper Outline: {topic}\n\n"
        f"1. Introduction\n"
        f"   - Background and motivation\n"
        f"   - Problem statement\n"
        f"   - Contributions\n\n"
        f"2. Related Work\n"
        f"   - Prior approaches\n"
        f"   - Gaps in literature\n\n"
        f"3. Method\n"
        f"   - Proposed approach\n"
        f"   - Theoretical analysis\n\n"
        f"4. Experiments\n"
        f"   - Setup and baselines\n"
        f"   - Results and analysis\n\n"
        f"5. Conclusion\n"
        f"   - Summary of findings\n"
        f"   - Limitations and future work\n"
    )


def _default_quality_report(threshold: float) -> dict[str, Any]:
    """Generate a default quality report."""
    return {
        "score_1_to_10": max(1.0, min(10.0, threshold * 0.7)),
        "threshold": threshold,
        "met_threshold": False,
        "issues": ["Default quality report — LLM evaluation was unavailable"],
        "passed": False,
    }


def _extract_paper_title(md_text: str) -> str:
    """Extract the paper title from markdown text.

    Searches only the region before the first "Abstract" heading (of any
    level) — a title appearing after Abstract isn't the paper title.
    Prefers the first H1 (``# Title``) heading; falls back to a leading
    bold line (``**Title**``); otherwise returns "Untitled Paper".
    """
    import re as _re

    bold_fallback: str | None = None
    for line in md_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        heading_match = _re.match(r"^(#+)\s+(.+)$", stripped)
        if heading_match:
            heading_text = heading_match.group(2).strip()
            if heading_text.lower() == "abstract":
                break
            if len(heading_match.group(1)) == 1:
                return heading_text
            continue
        bold_match = _re.match(r"^\*\*(.+?)\*\*$", stripped)
        if bold_match and bold_fallback is None:
            bold_fallback = bold_match.group(1).strip()
    return bold_fallback or "Untitled Paper"


def _generate_neurips_checklist(
    has_experiments: bool = True, has_code: bool = True
) -> str:
    """Generate a NeurIPS-style checklist for the paper."""
    import textwrap

    reproducibility_answer = (
        "Yes — see the Experiments section and released code for full detail."
        if has_experiments
        else "N/A — this paper presents theoretical/mathematical results with no empirical experiments."
    )
    code_answer = (
        "Yes — code is released alongside the paper."
        if has_code
        else "N/A — no code artifacts accompany this paper."
    )

    return textwrap.dedent(f"""\
        # NeurIPS Paper Checklist

        1. **Claims**: Question: Do the main claims made in the abstract and introduction accurately reflect the paper's contributions and scope?

        2. **Limitations**: Question: Does the paper discuss the limitations of the work performed by the authors?

        3. **Theory Assumptions and Proofs**: Question: For each theoretical result, does the paper provide the full set of assumptions and a complete explanation of the theory?

        4. **Experimental Result Reproducibility**: Question: Does the paper provide sufficient detail to reproduce the experimental results? Answer: {reproducibility_answer}

        5. **Open access to data and code**: Question: Does the paper provide open access to the data and code, with sufficient instructions to faithfully reproduce the main experimental results? Answer: {code_answer}
    """)


def _generate_framework_diagram_prompt(
    framework_description: str, style: str = "matplotlib"
) -> str:
    """Generate a prompt for creating a framework diagram."""
    return (
        f"Create a {style} figure illustrating: {framework_description}\n\n"
        "The figure should be:\n"
        "- Clear and publication-ready\n"
        "- Include labeled components and arrows showing data flow\n"
        "- Use a clean, professional color scheme\n"
        "- Save as 'framework_diagram.pdf'\n"
    )


def _multi_perspective_generate(
    llm,
    roles: dict[str, dict[str, str]],
    variables: dict[str, object],
    perspectives_dir: Path,
) -> dict[str, str]:
    """Generate one debate response per role, writing each to <role>.md.

    Each role dict has "system" and "user" prompt templates; "user" is
    rendered with str.format(**variables) (e.g. "{topic}", "{synthesis}").
    Roles whose LLM call fails are silently skipped — callers treat a
    partial or empty result as "fall back to default".
    """
    perspectives_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}
    for role_name, role_spec in roles.items():
        system = role_spec.get("system", "")
        user_template = role_spec.get("user", "")
        try:
            user = user_template.format(**variables)
        except (KeyError, IndexError):
            user = user_template
        try:
            resp = llm.chat([{"role": "user", "content": user}], system=system)
        except Exception:  # noqa: BLE001
            continue
        results[role_name] = resp.content
        (perspectives_dir / f"{role_name}.md").write_text(
            resp.content, encoding="utf-8"
        )
    return results


def _synthesize_perspectives(
    llm,
    perspectives: dict[str, str],
    stage_name: str,
    prompt_manager,
) -> str:
    """Synthesize multiple named debate perspectives into one response.

    Uses prompt_manager.for_stage(stage_name, perspectives=...) — the
    stage's YAML template must define a {perspectives} placeholder.
    """
    if not perspectives:
        return ""
    formatted = "\n\n".join(
        f"## {name}\n{content}" for name, content in perspectives.items()
    )
    sp = prompt_manager.for_stage(stage_name, perspectives=formatted)
    resp = llm.chat([{"role": "user", "content": sp.user}], system=sp.system)
    return resp.content


def reconcile_figure_refs(
    text: str,
) -> str:
    r"""Reconcile figure references in paper text.

    Ensures that all \Fig{{ref}} and \Figure{{ref}} tags are consistent.
    """
    import re as _re

    # Replace \Fig{ref} with Figure~\ref{{ref}}
    text = _re.sub(r"\\Fig\{([^}]+)\}", r"Figure~\\ref{\1}", text)
    text = _re.sub(r"\\Figure\{([^}]+)\}", r"Figure~\\ref{\1}", text)
    return text
