"""Prompt building helpers for the pipeline executor.

Extracted from _helpers.py — all functions re-exported from _helpers.py
for backward compatibility.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from berb.config import RCConfig
from berb.llm.client import LLMClient, LLMResponse
from berb.pipeline._io_helpers import _read_prior_artifact
from berb.utils.sanitize import wrap_untrusted  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)

# experiment_summary.json aggregates per-condition metrics plus (capped, but
# not zero) raw sandbox stdout across every experiment iteration — with
# enough iterations/conditions it has no upper bound. This is the single
# choke point every include_experiment_data=True caller goes through
# (outline, paper draft, analysis, ...), so capping here bounds the leak
# for all of them at once rather than chasing each writer.
_EXPERIMENT_DATA_CHAR_LIMIT = 50_000


def _build_fallback_queries(topic: str) -> list[str]:
    """Build fallback search queries from topic text."""
    import re as _re

    topic_lower = topic.lower()
    words = _re.findall(r"\b[a-zA-Z]{3,}\b", topic_lower)

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
        data = json.loads(evo_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return ""
        # Filter lessons relevant to this stage
        stage_num = (
            int(stage_name.split("_")[-1])
            if stage_name.split("_")[-1].isdigit()
            else None
        )
        relevant: list[dict[str, object]] = []
        for lesson in data:
            if not isinstance(lesson, dict):
                continue
            lesson_stage = lesson.get("stage")
            if lesson_stage and (
                lesson_stage == stage_name or str(lesson_stage) == str(stage_num)
            ):
                relevant.append(lesson)
            if len(relevant) >= 5:
                break
        if relevant:
            overlay = json.dumps(relevant, indent=2)
            logger.debug(
                "Evolution overlay for %s: %d lessons", stage_name, len(relevant)
            )
            return overlay
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        pass
    return ""


def _ensure_sandbox_deps(code: str, python_path: str) -> list[str]:
    """Extract required packages from import statements in code."""
    import re as _re

    imports = _re.findall(r"^(?:from|import)\s+(\S+)", code, _re.MULTILINE)
    safe_packages = {
        "numpy",
        "scipy",
        "torch",
        "sklearn",
        "pandas",
        "matplotlib",
        "seaborn",
        "tqdm",
        "gymnasium",
        "networkx",
        "torchdiffeq",
        "PIL",
        "Pillow",
        "timm",
        "einops",
        "torchmetrics",
        "transformers",
        "datasets",
        "accelerate",
        "peft",
        "trl",
        "sentencepiece",
        "tokenizers",
        "safetensors",
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
    retries: int = 1,
    call_timeout_sec: int | None = None,
    cached_prefix: str | None = None,
    cache_ttl: str = "5m",
) -> LLMResponse:
    """Send a prompt to the LLM and return the full response.

    Args:
        retries: Total attempts (>=1) if the call raises; retries the
            same request on failure before giving up. Retries resend the
            same `messages`, so a passed `cached_prefix` benefits repeats
            too — no separate wiring needed for that.
        call_timeout_sec: Per-call timeout override, restored afterward.
        cached_prefix: Stable, reused text (e.g. shared across several
            calls in one stage) marked with a provider-side cache_control
            breakpoint. See `LLMClient.chat`'s docstring for the mechanic.
        cache_ttl: "5m" (default) or "1h" — see `LLMClient.chat`.
    """
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    # Only touch llm.config when actually overriding the timeout — test
    # doubles and other minimal LLMClient-shaped callers may not have a
    # .config attribute at all, and shouldn't need one for the common path.
    original_timeout = None
    if call_timeout_sec is not None:
        original_timeout = getattr(getattr(llm, "config", None), "timeout_sec", None)
        if hasattr(llm, "config"):
            llm.config.timeout_sec = call_timeout_sec

    attempts = max(1, retries)
    last_error: Exception | None = None
    try:
        for attempt in range(attempts):
            try:
                return llm.chat(
                    messages,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    strip_thinking=strip_thinking,
                    stage=stage,
                    cached_prefix=cached_prefix,
                    cache_ttl=cache_ttl,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt == attempts - 1:
                    raise
                logger.warning(
                    "_chat_with_prompt attempt %d/%d failed: %s",
                    attempt + 1,
                    attempts,
                    exc,
                )
        raise RuntimeError("Unreachable") from last_error
    finally:
        if call_timeout_sec is not None and original_timeout is not None:
            llm.config.timeout_sec = original_timeout


def _build_context_preamble(
    config: RCConfig,
    run_dir: Path,
    *,
    include_goal: bool = False,
    include_hypotheses: bool = False,
    include_synthesis: bool = False,
    include_analysis: bool = False,
    include_decision: bool = False,
    include_experiment_data: bool = False,
) -> str:
    """Build a markdown context preamble from prior stage artifacts.

    Callers opt into specific prior artifacts via the include_* flags
    rather than always pulling in the full set — keeps prompts focused
    on what each stage actually needs.
    """
    lines = ["## Research Context", f"Topic: {config.research.topic}"]
    if config.research.domains:
        lines.append(f"Domains: {', '.join(config.research.domains)}")

    sections: list[tuple[bool, str, str]] = [
        (include_goal, "goal.md", "Goal"),
        (include_hypotheses, "hypotheses.md", "Hypotheses"),
        (include_synthesis, "synthesis.md", "Synthesis"),
        (include_analysis, "analysis.md", "Analysis"),
        (include_decision, "decision.md", "Decision"),
    ]
    for enabled, fname, label in sections:
        if not enabled:
            continue
        content = _read_prior_artifact(run_dir, fname)
        if content:
            lines.append(f"\n### {label}\n{content}")

    if include_experiment_data:
        exp_summary = _read_prior_artifact(run_dir, "experiment_summary.json")
        if exp_summary:
            if len(exp_summary) > _EXPERIMENT_DATA_CHAR_LIMIT:
                logger.warning(
                    "experiment_summary.json is %d chars — truncating to %d for prompt context",
                    len(exp_summary),
                    _EXPERIMENT_DATA_CHAR_LIMIT,
                )
                exp_summary = exp_summary[:_EXPERIMENT_DATA_CHAR_LIMIT]
            lines.append(f"\n### Experiment Data\n{exp_summary}")

    return "\n".join(lines)


def _extract_topic_keywords(
    topic: str, domains: tuple[str, ...] | list[str] = ()
) -> list[str]:
    """Extract significant keywords from a research topic."""
    import re as _re

    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "that",
        "this",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "can",
        "could",
        "shall",
        "should",
        "may",
        "might",
    }
    # Allow internal hyphens so compound terms like "agent-based" stay
    # a single keyword instead of splitting into "agent" + "based".
    words = _re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", topic.lower())
    keywords: list[str] = []
    seen: set[str] = set()
    for w in words:
        if w not in stop_words and w not in seen:
            seen.add(w)
            keywords.append(w)
    # Add domain-specific terms. Domains are curated short labels (e.g.
    # "ml", "cv") rather than prose, so no 3-char minimum here.
    for domain in domains:
        for dw in _re.findall(r"[a-zA-Z][a-zA-Z-]*", domain.lower()):
            if dw not in seen:
                seen.add(dw)
                keywords.append(dw)
    return keywords[:15]


def _topic_constraint_block(topic: str) -> str:
    """Build a hard constraint block for prompt injection.

    Prevents topic drift into unrelated environment/infrastructure changes
    when injected ahead of code-generation or experiment-design prompts.
    """
    return (
        "=== HARD TOPIC CONSTRAINT ===\n"
        f"Research Topic: {topic}\n"
        "PROHIBITED: Do not change the research environment, infrastructure, "
        "or topic. Stay strictly within the defined research scope.\n"
        "Constraints:\n"
        "- Must be novel and non-trivial\n"
        "- Must be implementable within computational constraints\n"
        "- Must produce publishable results\n"
        "=== END CONSTRAINT ===\n"
    )
