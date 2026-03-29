"""Stages 7-8: Synthesis and hypothesis generation — FIXED VERSION.

This is the FIXED version that integrates berb.reasoning.MultiPerspectiveMethod
instead of the simplified _multi_perspective_generate helper.

Changes from original:
- Import MultiPerspectiveMethod from berb.reasoning
- Create SimpleRouter adapter for LLMClient
- Use proper reasoning module with scoring, critique, top-k selection
- Preserve fallback to helper if reasoning module fails
"""

from __future__ import annotations

import json
import logging
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
from berb.pipeline.stages import Stage, StageStatus
from berb.prompts import PromptManager
from berb.reasoning.multi_perspective import (
    MultiPerspectiveMethod,
    PerspectiveCandidate,
)
from berb.reasoning.base import create_context

logger = logging.getLogger(__name__)


class _SimpleRouter:
    """Simple router adapter for LLMClient to work with MultiPerspectiveMethod.
    
    The reasoning module expects a router with get_provider_for_role().
    This adapter wraps LLMClient to provide that interface.
    """
    
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self._providers = {}
    
    def get_provider_for_role(self, role: str) -> Any:
        """Get provider for a perspective role.
        
        For now, return the same LLMClient for all roles.
        Future enhancement: route different roles to different models.
        """
        if role not in self._providers:
            # Create a provider wrapper that has complete() method
            self._providers[role] = _LLMProviderWrapper(self.llm)
        return self._providers[role]


class _LLMProviderWrapper:
    """Wrapper to adapt LLMClient for reasoning module.
    
    MultiPerspectiveMethod expects providers with async complete() method.
    LLMClient has sync chat() method.
    """
    
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.model = llm.config.primary_model if hasattr(llm, 'config') else "unknown"
    
    async def complete(self, prompt: str) -> Any:
        """Complete a prompt (async for compatibility)."""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        # Run sync chat() in executor to make it async-compatible
        loop = asyncio.get_event_loop()
        
        def _chat():
            return self.llm.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=4096,
            )
        
        with ThreadPoolExecutor() as executor:
            response = await loop.run_in_executor(executor, _chat)
        
        return response


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
    return StageResult(
        stage=Stage.SYNTHESIS,
        status=StageStatus.DONE,
        artifacts=("synthesis.md",),
        evidence_refs=("stage-07/synthesis.md",),
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
    """Execute Stage 8: Hypothesis Generation — FIXED VERSION.
    
    Uses MultiPerspectiveMethod for proper scoring, critique, and top-k selection.
    Falls back to helper function if reasoning module fails.
    """
    import asyncio
    
    synthesis = _read_prior_artifact(run_dir, "synthesis.md") or ""
    hypotheses_md = ""
    
    if llm is not None:
        try:
            # FIX: Use MultiPerspectiveMethod instead of helper
            logger.info("Using MultiPerspectiveMethod for hypothesis generation")
            
            # Create router adapter
            router = _SimpleRouter(llm)
            
            # Create reasoning method
            method = MultiPerspectiveMethod(
                router=router,
                parallel=True,  # Run perspectives in parallel
                top_k=2,  # Select top 2 candidates
            )
            
            # Build context
            problem = f"Research topic: {config.research.topic}\n\nSynthesis:\n{synthesis}"
            context = create_context(
                stage_id="hypothesis_gen",
                input_data={"problem": problem, "topic": config.research.topic},
                query=problem,
            )
            
            # Execute reasoning method (async)
            async def _run_reasoning():
                return await method.execute(context)
            
            # Run async reasoning
            result = asyncio.run(_run_reasoning())
            
            if result.success and result.output:
                # Extract top candidates from reasoning result
                top_candidates = result.output.get("top_candidates", [])
                perspectives = result.output.get("perspectives", [])
                scores = result.output.get("scores", [])
                
                # Log reasoning quality metrics
                logger.info(
                    "MultiPerspectiveMethod: %d perspectives, %d top candidates, confidence=%.2f",
                    len(perspectives),
                    len(top_candidates),
                    result.confidence,
                )
                
                # Synthesize hypotheses from top candidates
                if top_candidates:
                    hypotheses_parts = []
                    for i, candidate in enumerate(top_candidates, 1):
                        candidate_dict = candidate.to_dict() if hasattr(candidate, 'to_dict') else candidate
                        hypotheses_parts.append(
                            f"## Hypothesis {i}\n\n{candidate_dict.get('content', candidate_dict.get('solution', ''))}"
                        )
                    
                    hypotheses_md = "\n\n".join(hypotheses_parts)
                    
                    # Add scoring summary
                    if scores:
                        hypotheses_md += "\n\n---\n\n## Perspective Scores\n\n"
                        for score in scores:
                            score_dict = score.to_dict() if hasattr(score, 'to_dict') else score
                            hypotheses_md += f"- {score_dict.get('perspective', 'unknown')}: {score_dict.get('total', 0):.1f}/10\n"
                else:
                    # No top candidates, use fallback
                    logger.warning("No top candidates from MultiPerspectiveMethod, using fallback")
                    perspectives_dict = {
                        f"perspective_{i}": p.content if hasattr(p, 'content') else p.get('content', '')
                        for i, p in enumerate(perspectives, 1)
                    }
                    if perspectives_dict:
                        _pm = prompts or PromptManager()
                        hypotheses_md = _synthesize_perspectives(llm, perspectives_dict, "hypothesis_synthesize", _pm)
                    else:
                        hypotheses_md = _default_hypotheses(config.research.topic)
            else:
                # Reasoning failed, use fallback
                logger.warning("MultiPerspectiveMethod failed: %s, using fallback", result.error or "unknown error")
                perspectives_dir = stage_dir / "perspectives"
                from berb.prompts import DEBATE_ROLES_HYPOTHESIS
                variables = {"topic": config.research.topic, "synthesis": synthesis}
                perspectives = _multi_perspective_generate(llm, DEBATE_ROLES_HYPOTHESIS, variables, perspectives_dir)
                if perspectives:
                    _pm = prompts or PromptManager()
                    hypotheses_md = _synthesize_perspectives(llm, perspectives, "hypothesis_synthesize", _pm)
                else:
                    hypotheses_md = _default_hypotheses(config.research.topic)
                    
        except Exception as e:
            # Critical failure, use fallback
            logger.error("MultiPerspectiveMethod integration failed: %s", e, exc_info=True)
            hypotheses_md = _default_hypotheses(config.research.topic)
    else:
        # No LLM available
        hypotheses_md = _default_hypotheses(config.research.topic)
    
    # Write output
    (stage_dir / "hypotheses.md").write_text(hypotheses_md, encoding="utf-8")

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
        artifacts=("hypotheses.md",) + novelty_artifacts,
        evidence_refs=("stage-08/hypotheses.md",),
    )
