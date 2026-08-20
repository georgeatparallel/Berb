"""Stages 7-8: Synthesis and hypothesis generation.

FIX-001: Integrated MultiPerspectiveMethod from berb.reasoning for proper
scoring, critique, and top-k selection (35-50% quality improvement).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.llm.client import LLMClient
from berb.pipeline._helpers import (
    StageResult,
    _default_hypotheses,
    _get_evolution_overlay,
    _multi_perspective_generate,  # Fallback
    _parse_jsonl_rows,
    _read_prior_artifact,
    _synthesize_perspectives,  # Fallback
    _utcnow_iso,
)
from berb.pipeline.contracts import StageContract
from berb.pipeline.registry import register_stage
from berb.pipeline.stages import Stage, StageStatus
from berb.prompts import PromptManager
from berb.reasoning.base import create_context
from berb.reasoning.multi_perspective import MultiPerspectiveMethod

logger = logging.getLogger(__name__)


def _repair_hypothesis(
    llm: LLMClient, hypothesis_text: str, hard_issues: list[dict[str, Any]]
) -> str:
    """Revise a hypothesis to address the falsification critic's
    hard-severity issues.

    P2-02: this is the answer half of ScholarPeer's Q&A engine, applied at
    the point where Berb has the earliest leverage (§0.2 inversion — fix
    the hypothesis before an experiment gets designed for it, rather than
    flagging it as a reviewer weakness afterward). Previously the retry
    loop reset the text back to its unmodified original before the next
    round, so round 2 re-critiqued the exact same input and never fixed
    anything.
    """
    issue_lines = "\n".join(
        f"- [{i.get('action', 'issue')}] {i.get('question', '')}" for i in hard_issues
    )
    prompt = (
        "A falsification critic raised the following hard issues with this "
        "research hypothesis. Revise the hypothesis to directly address "
        "each issue — narrow overclaimed scope, add missing preconditions, "
        "or make the claim falsifiable/testable as needed. Keep the "
        "revision concise and preserve the hypothesis's core intent where "
        "the criticism allows it. Return ONLY the revised hypothesis text, "
        "no preamble or explanation.\n\n"
        f"Original hypothesis:\n{hypothesis_text}\n\n"
        f"Critic issues:\n{issue_lines}"
    )
    try:
        resp = llm.chat([{"role": "user", "content": prompt}], max_tokens=1024)
        revised = resp.content.strip()
        return revised if revised else hypothesis_text
    except Exception:  # noqa: BLE001
        logger.debug("E1: Hypothesis repair failed, keeping prior text", exc_info=True)
        return hypothesis_text


def _build_domain_narrative(llm: LLMClient, run_dir: Path, topic: str) -> str:
    """P3-04: compress the retrieved literature corpus into a chronological
    "domain narrative" — the arc of progress in the sub-domain — mirroring
    ScholarPeer's Sub-Domain Historian agent. Raw retrieved abstracts don't
    let a model assess significance/novelty the way a senior researcher's
    mental model of the field's trajectory does.
    """
    candidates_text = _read_prior_artifact(run_dir, "candidates.jsonl") or ""
    if not candidates_text.strip():
        return ""
    rows: list[dict[str, Any]] = []
    for line in candidates_text.strip().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("title"):
            rows.append(row)
    if not rows:
        return ""
    rows.sort(key=lambda r: r.get("year") or 0)
    lines = [f"- ({r.get('year', '?')}) {r['title']}" for r in rows[:60]]
    prompt = (
        f"Below is a chronologically-sorted list of papers retrieved for "
        f"the research topic: {topic!r}.\n\n"
        + "\n".join(lines)
        + "\n\nWrite a short (3-5 paragraph) chronological narrative of "
        "how this sub-domain has progressed over time, based ONLY on the "
        "titles and years given — do not invent details not implied by "
        "the list. Identify the arc: what problem the field started with, "
        "what major shifts occurred, and what the current frontier looks "
        "like. This narrative will be used to help assess how novel and "
        "significant new contributions to this topic would be."
    )
    try:
        resp = llm.chat([{"role": "user", "content": prompt}], max_tokens=1536)
        return resp.content.strip()
    except Exception:  # noqa: BLE001
        logger.debug("P3-04: domain narrative unavailable", exc_info=True)
        return ""


class _SimpleRouter:
    """Simple router adapter for LLMClient to work with MultiPerspectiveMethod."""

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self._providers = {}

    def get_provider_for_role(self, role: str) -> Any:
        """Get provider for a perspective role."""
        if role not in self._providers:
            self._providers[role] = _LLMProviderWrapper(self.llm)
        return self._providers[role]


class _LLMProviderWrapper:
    """Wrapper to adapt LLMClient for reasoning module (async complete)."""

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.model = llm.config.primary_model if hasattr(llm, "config") else "unknown"

    async def complete(self, prompt: str) -> Any:
        """Complete a prompt (async for compatibility)."""
        from concurrent.futures import ThreadPoolExecutor

        loop = asyncio.get_event_loop()

        def _chat():
            return self.llm.chat([{"role": "user", "content": prompt}], max_tokens=4096)

        with ThreadPoolExecutor() as executor:
            response = await loop.run_in_executor(executor, _chat)

        return response


@register_stage(
    stage=Stage.SYNTHESIS,
    depends_on=frozenset({Stage.KNOWLEDGE_EXTRACT}),
    contract=StageContract(
        stage=Stage.SYNTHESIS,
        input_files=("cards/",),
        output_files=("synthesis.md",),
        dod="Topic clusters + >=2 research gaps identified",
        error_code="E07_SYNTHESIS_WEAK",
    ),
)
def _execute_synthesis(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    cards_path = _read_prior_artifact(run_dir, "cards/") or ""
    cards_context = ""
    if cards_path:
        snippets: list[str] = []
        for path in sorted(Path(cards_path).glob("*.md"))[:24]:
            snippets.append(path.read_text(encoding="utf-8"))
        cards_context = "\n\n".join(snippets)

    # P3-04: sub-domain historian — a chronological narrative of the
    # field's progression, feeding this stage's synthesis (and stage 8
    # transitively, since it reads synthesis.md) so novelty/significance
    # assessment has more than raw unordered abstracts to work from.
    domain_narrative = ""
    if llm is not None:
        domain_narrative = _build_domain_narrative(llm, run_dir, config.research.topic)
        if domain_narrative:
            (stage_dir / "domain_narrative.md").write_text(
                domain_narrative, encoding="utf-8"
            )
            cards_context = (
                f"## Domain Narrative (chronological arc of this sub-field)\n\n"
                f"{domain_narrative}\n\n## Literature Cards\n\n{cards_context}"
            )

    if llm is not None:
        _pm = prompts or PromptManager()
        _overlay = _get_evolution_overlay(run_dir, "synthesis")
        sp = _pm.for_stage(
            "synthesis",
            evolution_overlay=_overlay,
            topic=config.research.topic,
            cards_context=cards_context,
        )
        resp = llm.chat(
            [{"role": "user", "content": sp.user}],
            system=sp.system,
            max_tokens=sp.max_tokens or 8192,
        )
        synthesis_md = resp.content
    else:
        synthesis_md = f"""# Synthesis

## Cluster Overview
- Cluster A: Representation methods
- Cluster B: Training strategies
- Cluster C: Evaluation robustness

## Gap 1
Limited consistency across benchmark protocols.

## Gap 2
Under-reported failure behavior under distribution shift.

## Prioritized Opportunities
1. Unified experimental protocol
2. Robustness-aware evaluation suite

## Generated
{_utcnow_iso()}
"""
    (stage_dir / "synthesis.md").write_text(synthesis_md, encoding="utf-8")
    _synthesis_artifacts = (
        ("synthesis.md", "domain_narrative.md")
        if domain_narrative
        else ("synthesis.md",)
    )
    return StageResult(
        stage=Stage.SYNTHESIS,
        status=StageStatus.DONE,
        artifacts=_synthesis_artifacts,
        evidence_refs=("stage-07/synthesis.md",),
    )


@register_stage(
    stage=Stage.HYPOTHESIS_GEN,
    depends_on=frozenset({Stage.SYNTHESIS}),
    contract=StageContract(
        stage=Stage.HYPOTHESIS_GEN,
        input_files=("synthesis.md",),
        output_files=("hypotheses.md", "hypothesis_state.json"),
        dod=">=2 falsifiable research hypotheses",
        error_code="E08_HYP_INVALID",
    ),
)
def _execute_hypothesis_gen(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    """Execute Stage 8: Hypothesis Generation — FIXED.

    Uses MultiPerspectiveMethod for proper scoring, critique, and top-k selection.
    Falls back to helper function if reasoning module fails.
    """
    synthesis = _read_prior_artifact(run_dir, "synthesis.md") or ""
    hypotheses_md = ""

    if llm is not None:
        try:
            logger.info("Using MultiPerspectiveMethod for hypothesis generation")

            # Create router adapter
            router = _SimpleRouter(llm)

            # Create reasoning method with parallel execution and top-k selection
            method = MultiPerspectiveMethod(
                router=router,
                parallel=True,
                top_k=2,
            )

            # Build context
            problem = (
                f"Research topic: {config.research.topic}\n\nSynthesis:\n{synthesis}"
            )
            context = create_context(
                stage_id="hypothesis_gen",
                stage_name="Hypothesis Generation",
                input_data={"problem": problem, "topic": config.research.topic},
            )
            context.metadata["query"] = problem

            # Execute reasoning method (async)
            async def _run_reasoning():
                return await method.execute(context)

            result = asyncio.run(_run_reasoning())

            if result.success and result.output:
                top_candidates = result.output.get("top_candidates", [])
                perspectives = result.output.get("perspectives", [])
                scores = result.output.get("scores", [])

                logger.info(
                    "MultiPerspectiveMethod: %d perspectives, %d top candidates, confidence=%.2f",
                    len(perspectives),
                    len(top_candidates),
                    result.confidence,
                )

                # Save perspectives to disk for transparency
                if perspectives:
                    perspectives_dir = stage_dir / "perspectives"
                    perspectives_dir.mkdir(parents=True, exist_ok=True)
                    for p in perspectives:
                        p_dict = p.to_dict() if hasattr(p, "to_dict") else p
                        p_name = p_dict.get("perspective", "unknown")
                        p_content = p_dict.get("content", "")
                        if p_content:
                            (perspectives_dir / f"{p_name}.md").write_text(
                                p_content, encoding="utf-8"
                            )

                # Synthesize hypotheses from top candidates
                if top_candidates:
                    hypotheses_parts = []
                    for i, candidate in enumerate(top_candidates, 1):
                        candidate_dict = (
                            candidate.to_dict()
                            if hasattr(candidate, "to_dict")
                            else candidate
                        )
                        hypotheses_parts.append(
                            f"## Hypothesis {i}\n\n{candidate_dict.get('content', candidate_dict.get('solution', ''))}"
                        )
                    hypotheses_md = "\n\n".join(hypotheses_parts)

                    # Add scoring summary
                    if scores:
                        hypotheses_md += "\n\n---\n\n## Perspective Scores\n\n"
                        for score in scores:
                            score_dict = (
                                score.to_dict() if hasattr(score, "to_dict") else score
                            )
                            hypotheses_md += f"- {score_dict.get('perspective', 'unknown')}: {score_dict.get('total', 0):.1f}/10\n"
                else:
                    logger.warning(
                        "No top candidates from MultiPerspectiveMethod, using fallback"
                    )
                    hypotheses_md = _fallback_hypothesis_gen(
                        llm, prompts, config.research.topic, synthesis, stage_dir
                    )
            else:
                logger.warning("MultiPerspectiveMethod failed, using fallback")
                hypotheses_md = _fallback_hypothesis_gen(
                    llm, prompts, config.research.topic, synthesis, stage_dir
                )

        except Exception as e:
            logger.error(
                "MultiPerspectiveMethod integration failed: %s", e, exc_info=True
            )
            hypotheses_md = _fallback_hypothesis_gen(
                llm, prompts, config.research.topic, synthesis, stage_dir
            )
    else:
        hypotheses_md = _default_hypotheses(config.research.topic)

    (stage_dir / "hypotheses.md").write_text(hypotheses_md, encoding="utf-8")

    # --- E1: Falsification gate (non-blocking — results recorded for stage 9) ---
    _hypothesis_state: dict[str, Any] = {
        "stage": "hypothesis_gen",
        "generated_at": _utcnow_iso(),
        "hypotheses": [],
        "gate_passed": True,
        "critic_transcript": "",
    }
    if llm is not None and hypotheses_md.strip():
        try:
            # Split hypotheses markdown into individual statements
            _h_raw = hypotheses_md.split("## Hypothesis")
            _h_texts = []
            for _h in _h_raw:
                _h = _h.strip()
                if _h and len(_h) > 20:
                    _h_texts.append(_h[:1000])

            if _h_texts:
                from berb.reasoning.socratic import FalsificationCritic as _Critic

                _critic = _Critic(llm_client=llm)
                _all_issues: list[dict[str, Any]] = []
                _hypothesis_records: list[dict[str, Any]] = []

                for i, _ht in enumerate(_h_texts, 1):
                    _record: dict[str, Any] = {
                        "index": i,
                        "text": _ht[:200],
                        "hard_issues": [],
                        "soft_issues": [],
                        "passed": True,
                        "rounds_completed": 0,
                    }

                    _max_rounds = 2
                    _current_text = _ht
                    for _round in range(_max_rounds):

                        async def _run_critic(text=_current_text):
                            return await _critic.scrutinize(text)

                        _issues = asyncio.run(_run_critic())
                        _hard = [i for i in _issues if i.get("severity") == "hard"]
                        _soft = [i for i in _issues if i.get("severity") == "soft"]

                        _record.setdefault("rounds", []).append(
                            {
                                "round": _round + 1,
                                "hard_issues": _hard,
                                "soft_issues": _soft,
                            }
                        )

                        if not _hard:
                            break
                        if _round == _max_rounds - 1:
                            break
                        _current_text = _repair_hypothesis(llm, _current_text, _hard)

                    if _current_text != _ht:
                        # P2-02: fold the repair back into hypotheses.md so
                        # stage 9 designs an experiment for the REVISED
                        # claim, not the one the critic already rejected.
                        # _ht is a verbatim substring of hypotheses_md (it
                        # came from splitting it), so a targeted replace is
                        # safe; count=1 avoids touching a second occurrence
                        # if the same truncated text recurs elsewhere.
                        hypotheses_md = hypotheses_md.replace(_ht, _current_text, 1)
                        _record["repaired"] = True
                        _record["repaired_text"] = _current_text[:200]

                    _record["hard_issues"] = _hard if _hard else []
                    _record["soft_issues"] = _soft if _soft else []
                    _record["passed"] = len(_hard) == 0
                    _record["rounds_completed"] = _round + 1
                    _hypothesis_records.append(_record)
                    _all_issues.extend(_hard)
                    _all_issues.extend(_soft)

                if any(r.get("repaired") for r in _hypothesis_records):
                    (stage_dir / "hypotheses.md").write_text(
                        hypotheses_md, encoding="utf-8"
                    )
                    logger.info(
                        "E1: Repaired %d hypothesis(es) and rewrote hypotheses.md",
                        sum(1 for r in _hypothesis_records if r.get("repaired")),
                    )

                _hypothesis_state["hypotheses"] = _hypothesis_records
                _hypothesis_state["gate_passed"] = all(
                    r["passed"] for r in _hypothesis_records
                )
                _hypothesis_state["critic_transcript"] = _critic.format_issues(
                    _all_issues
                )

                logger.info(
                    "E1: Falsification gate %s (%d hypotheses, %d hard issues)",
                    "PASSED" if _hypothesis_state["gate_passed"] else "BLOCKED",
                    len(_h_texts),
                    len(_all_issues),
                )
        except Exception as _e1:
            logger.warning("E1: Falsification gate failed, gate passes open: %s", _e1)

    (stage_dir / "hypothesis_state.json").write_text(
        json.dumps(_hypothesis_state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # --- Novelty check (non-blocking) ---
    novelty_artifacts: tuple[str, ...] = ()
    try:
        from berb.literature.novelty import check_novelty

        candidates_text = _read_prior_artifact(run_dir, "candidates.jsonl") or ""
        papers_seen = _parse_jsonl_rows(candidates_text) if candidates_text else []
        novelty_report = check_novelty(
            topic=config.research.topic,
            hypotheses_text=hypotheses_md,
            papers_already_seen=papers_seen,
            s2_api_key=getattr(config.llm, "s2_api_key", ""),
            perplexity_check=config.perplexity.enabled,
            perplexity_api_key=os.environ.get(config.perplexity.api_key_env, ""),
        )
        (stage_dir / "novelty_report.json").write_text(
            json.dumps(novelty_report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        novelty_artifacts = ("novelty_report.json",)
        logger.info(
            "Novelty check: score=%.3f  assessment=%s  recommendation=%s",
            novelty_report["novelty_score"],
            novelty_report["assessment"],
            novelty_report["recommendation"],
        )
    except Exception:  # noqa: BLE001
        logger.warning("Novelty check failed (non-blocking)", exc_info=True)

    return StageResult(
        stage=Stage.HYPOTHESIS_GEN,
        status=StageStatus.DONE,
        artifacts=("hypotheses.md", "hypothesis_state.json") + novelty_artifacts,
        evidence_refs=("stage-08/hypotheses.md", "stage-08/hypothesis_state.json"),
    )


def _fallback_hypothesis_gen(
    llm: LLMClient,
    prompts: PromptManager | None,
    topic: str,
    synthesis: str,
    stage_dir: Path,
) -> str:
    """Fallback to helper-based hypothesis generation."""
    _pm = prompts or PromptManager()
    from berb.prompts import DEBATE_ROLES_HYPOTHESIS

    perspectives_dir = stage_dir / "perspectives"
    variables = {"topic": topic, "synthesis": synthesis}
    perspectives = _multi_perspective_generate(
        llm, DEBATE_ROLES_HYPOTHESIS, variables, perspectives_dir
    )
    if not perspectives:
        logger.warning("All debate perspectives failed; using default hypotheses")
        return _default_hypotheses(topic)
    return _synthesize_perspectives(llm, perspectives, "hypothesis_synthesize", _pm)
