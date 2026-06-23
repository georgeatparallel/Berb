"""Prompt building helpers for the pipeline executor.

Extracted from _helpers.py — all functions re-exported from _helpers.py
for backward compatibility.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from berb.config import RCConfig
from berb.llm.client import LLMClient
from berb.pipeline._io_helpers import _read_prior_artifact
from berb.pipeline.stages import Stage
from berb.prompts import PromptManager

logger = logging.getLogger(__name__)


def _build_fallback_queries(topic: str) -> list[str]:
    """Build fallback search queries from topic text."""
    import re as _re

    topic_lower = topic.lower()
    words = _re.findall(r"\b[a-zA-Z]{3,}\b", topic_lower)
    from collections import Counter

    common = {"the", "and", "for", "with", "from", "that", "this", "are", "can"}
    significant = [w for w in words if w not in common]
    if not significant:
        return [topic]
    # Generate queries: up to 3 combinations of significant words
    queries = []
    n = min(len(significant), 4)
    for i in range(n):
        for j in range(i + 1, n):
            q = f"{significant[i]} {significant[j]} machine learning"
            if q not in queries:
                queries.append(q)
    if not queries:
        queries.append(" ".join(significant[:3]))
    return queries[:5]


def _get_evolution_overlay(run_dir: Path | None, stage_name: str) -> str:
    """Fetch evolution overlay for a stage.

    Reads ``run_dir/evolution/lessons.json`` and filters for relevant lessons.
    """
    if run_dir is None:
        return ""
    evo_path = run_dir / "evolution" / "lessons.json"
    if not evo_path.exists():
        return ""
    try:
        from pathlib import Path as _Path

        data = json.loads(evo_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return ""
        # Filter lessons relevant to this stage
        stage_num = int(stage_name.split("_")[-1]) if stage_name.split("_")[-1].isdigit() else None
        relevant: list[dict[str, object]] = []
        for lesson in data:
            if not isinstance(lesson, dict):
                continue
            lesson_stage = lesson.get("stage")
            if lesson_stage and (lesson_stage == stage_name or str(lesson_stage) == str(stage_num)):
                relevant.append(lesson)
            if len(relevant) >= 5:
                break
        if relevant:
            overlay = json.dumps(relevant, indent=2)
            logger.debug("Evolution overlay for %s: %d lessons", stage_name, len(relevant))
            return overlay
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        pass
    return ""


def _ensure_sandbox_deps(code: str, python_path: str) -> list[str]:
    """Extract required packages from import statements in code."""
    import re as _re

    imports = _re.findall(r"^(?:from|import)\s+(\S+)", code, _re.MULTILINE)
    safe_packages = {
        "numpy", "scipy", "torch", "sklearn", "pandas", "matplotlib",
        "seaborn", "tqdm", "gymnasium", "networkx", "torchdiffeq",
        "PIL", "Pillow", "timm", "einops", "torchmetrics",
        "transformers", "datasets", "accelerate", "peft", "trl",
        "sentencepiece", "tokenizers", "safetensors",
    }
    needed: set[str] = set()
    for imp in imports:
        top_level = imp.split(".")[0]
        if top_level in safe_packages:
            needed.add(top_level)
    return sorted(needed)


def _read_best_analysis(run_dir: Path) -> str:
    """Read the best analysis from experiment results."""
    best_path = run_dir / "analysis_best.md"
    if best_path.exists():
        return best_path.read_text(encoding="utf-8")
    analysis_path = run_dir / "stage-14" / "analysis.md"
    if analysis_path.exists():
        return analysis_path.read_text(encoding="utf-8")
    return ""


def _chat_with_prompt(
    llm: LLMClient,
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = 4096,
    json_mode: bool = False,
    strip_thinking: bool = False,
    stage: object = None,
) -> str:
    """Send a prompt to the LLM and return the response content."""
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    response = llm.chat(
        messages,
        max_tokens=max_tokens,
        json_mode=json_mode,
        strip_thinking=strip_thinking,
        stage=stage,
    )
    return response.content


def _build_context_preamble(
    run_dir: Path,
    stage: Stage,
    config: RCConfig,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
    *,
    stage_name: str = "",
    evolution_overlay: str = "",
    verbose: bool = True,
) -> list[dict[str, str]]:
    """Build a context preamble from prior stage artifacts."""
    messages: list[dict[str, str]] = []

    # System context
    system_context = f"You are an expert AI researcher working on {config.research.topic}."
    if config.research.domains:
        domains_str = ", ".join(config.research.domains)
        system_context += f"\nDomain(s): {domains_str}"

    messages.append({"role": "system", "content": system_context})

    # Load prior artifacts
    prior_artifacts = {
        "goal.md": "Research Goal",
        "problem_tree.md": "Problem Decomposition",
        "search_plan.yaml": "Search Strategy",
        "cards/": "Literature Knowledge Cards",
        "synthesis.md": "Knowledge Synthesis",
        "hypotheses.md": "Research Hypotheses",
    }
    for fname, label in prior_artifacts.items():
        if (run_dir / fname).exists():
            messages.append({
                "role": "user",
                "content": f"[Prior: {label}]\n{(run_dir / fname).read_text()[:2000]}",
            })

    return messages


def _extract_topic_keywords(topic: str, domains: tuple[str, ...] | list[str] = ()) -> list[str]:
    """Extract significant keywords from a research topic."""
    import re as _re

    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "that", "this", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "can", "could", "shall", "should", "may", "might",
    }
    words = _re.findall(r"[a-zA-Z]{3,}", topic.lower())
    keywords = [w for w in words if w not in stop_words]
    # Add domain-specific terms
    for domain in domains:
        domain_words = _re.findall(r"[a-zA-Z]{3,}", domain.lower())
        for dw in domain_words:
            if dw not in keywords:
                keywords.append(dw)
    return keywords[:15]


def _topic_constraint_block(topic: str) -> str:
    """Build a constraint block for prompt injection."""
    return (
        f"Research Topic: {topic}\n"
        "Constraints:\n"
        "- Must be novel and non-trivial\n"
        "- Must be implementable within computational constraints\n"
        "- Must produce publishable results\n"
    )
