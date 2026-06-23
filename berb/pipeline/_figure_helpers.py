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

    safe = _re.sub(r"[^\w\-_. ]", "_", name)
    safe = safe.strip().replace(" ", "_")[:64]
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
    """Extract the paper title from markdown text."""
    import re as _re

    # Look for first # Title
    match = _re.search(r"^#\s+(.+)$", md_text, _re.MULTILINE)
    if match:
        return match.group(1).strip()
    # Fallback: first non-empty line
    for line in md_text.split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            continue
        if line.startswith("# "):
            return line[2:].strip()
    return "Untitled"


def _generate_neurips_checklist(paper_text: str, topic: str) -> str:
    """Generate a NeurIPS-style checklist for the paper."""
    # Lazy import to avoid circular dependency
    import textwrap

    return textwrap.dedent(f"""\
        # NeurIPS Paper Checklist

        1. **Claims**: Question: Do the main claims made in the abstract and introduction accurately reflect the paper's contributions and scope?

        2. **Limitations**: Question: Does the paper discuss the limitations of the work performed by the authors?

        3. **Theory Assumptions and Proofs**: Question: For each theoretical result, does the paper provide the full set of assumptions and a complete explanation of the theory?

        4. **Experimental Result Reproducibility**: Question: Does the paper provide sufficient detail to reproduce the experimental results?

        5. **Open access to data and code**: Question: Does the paper provide open access to the data and code, with sufficient instructions to faithfully reproduce the main experimental results?
    """)


def _generate_framework_diagram_prompt(framework_description: str, style: str = "matplotlib") -> str:
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
    prompt: str,
    llm,
    *,
    perspectives: int = 3,
    temperature_range: tuple[float, float] = (0.3, 0.9),
) -> list[str]:
    """Generate multiple responses from different perspectives."""
    import random as _random

    responses: list[str] = []
    for _ in range(perspectives):
        temp = _random.uniform(*temperature_range)
        try:
            resp = llm.chat([{"role": "user", "content": prompt}], temperature=temp)
            responses.append(resp.content)
        except Exception:
            continue
    return responses


def _synthesize_perspectives(responses: list[str], llm, max_length: int = 1000) -> str:
    """Synthesize multiple perspectives into a single coherent response."""
    if not responses:
        return ""
    if len(responses) == 1:
        return responses[0][:max_length]
    combined = "\n---\n".join(r[:500] for r in responses)
    synthesis_prompt = (
        "Synthesize the following perspectives into a single coherent analysis:\n\n"
        f"{combined}"
    )
    try:
        resp = llm.chat([{"role": "user", "content": synthesis_prompt}])
        return resp.content[:max_length]
    except Exception:
        return responses[0][:max_length]


def reconcile_figure_refs(
    text: str,
) -> str:
    """Reconcile figure references in paper text.

    Ensures that all \Fig{{ref}} and \Figure{{ref}} tags are consistent.
    """
    import re as _re

    # Replace \Fig{ref} with Figure~\ref{{ref}}
    text = _re.sub(r"\\Fig\{([^}]+)\}", r"Figure~\\ref{\1}", text)
    text = _re.sub(r"\\Figure\{([^}]+)\}", r"Figure~\\ref{\1}", text)
    return text
