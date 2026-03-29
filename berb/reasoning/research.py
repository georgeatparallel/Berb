"""Research (iterative) reasoning method.

This module implements iterative research reasoning:
1. Initial search/query formulation
2. Information gathering
3. Analysis and synthesis
4. Gap identification
5. Refined search (iterate)
6. Final synthesis

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .base import (
    ReasoningMethod,
    ReasoningContext,
    ReasoningResult,
    MethodType,
)

logger = logging.getLogger(__name__)


@dataclass
class ResearchIteration:
    """A single iteration of research."""

    iteration: int
    query: str
    findings: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class ResearchResult:
    """Result of iterative research."""

    topic: str = ""
    iterations: list[ResearchIteration] = field(default_factory=list)
    final_synthesis: str = ""
    key_findings: list[str] = field(default_factory=list)
    remaining_gaps: list[str] = field(default_factory=list)
    confidence: float = 0.5


class ResearchMethod(ReasoningMethod):
    """Iterative research reasoning method.

    Implements iterative search-synthesis-gap identification loop.

    Usage:
        research = ResearchMethod(llm_client, search_client)
        result = await research.execute(context)

        # Access results
        print(f"Findings: {result.output['key_findings']}")
        print(f"Gaps: {result.output['remaining_gaps']}")
    """

    method_type = MethodType.RESEARCH

    def __init__(
        self,
        llm_client: Any = None,
        search_client: Any = None,
        max_iterations: int = 3,
        **kwargs: Any,
    ):
        """
        Initialize research method.

        Args:
            llm_client: LLM client for analysis
            search_client: Search client for information gathering
            max_iterations: Maximum research iterations (default: 3)
            **kwargs: Additional arguments for ReasoningMethod
        """
        super().__init__(
            name="Research (Iterative)",
            description="Iterative research: search → analyze → identify gaps → refine",
            **kwargs,
        )
        self.llm_client = llm_client
        self.search_client = search_client
        self.max_iterations = max_iterations

    async def execute(self, context: ReasoningContext) -> ReasoningResult:
        """
        Execute iterative research.

        Args:
            context: Reasoning context with input data

        Returns:
            ReasoningResult with research findings

        Raises:
            Exception: If research fails
        """
        start_time = time.time()

        try:
            if not self.validate_context(context):
                return ReasoningResult.error_result(
                    MethodType.RESEARCH,
                    "Invalid context: missing required fields",
                )

            topic = context.get("topic") or context.get("question")
            if not topic:
                return ReasoningResult.error_result(
                    MethodType.RESEARCH,
                    "Context missing topic/question for research",
                )

            iterations: list[ResearchIteration] = []
            all_findings: list[str] = []
            remaining_gaps: list[str] = [f"Initial understanding of {topic}"]

            # Iterative research loop
            for i in range(self.max_iterations):
                iteration = await self._research_iteration(
                    topic, i, remaining_gaps, context
                )
                iterations.append(iteration)
                all_findings.extend(iteration.findings)
                remaining_gaps = iteration.gaps

                # Stop if no significant gaps
                if not remaining_gaps or len(remaining_gaps) < 2:
                    logger.info(f"Research converged after {i + 1} iterations")
                    break

            # Final synthesis
            final_synthesis = await self._synthesize_findings(
                topic, all_findings, remaining_gaps, context
            )

            result = ResearchResult(
                topic=topic,
                iterations=iterations,
                final_synthesis=final_synthesis,
                key_findings=all_findings,
                remaining_gaps=remaining_gaps,
                confidence=0.7 if iterations else 0.5,
            )

            duration = time.time() - start_time

            return ReasoningResult.success_result(
                MethodType.RESEARCH,
                output={
                    "topic": topic,
                    "iterations": len(iterations),
                    "key_findings": all_findings,
                    "remaining_gaps": remaining_gaps,
                    "final_synthesis": final_synthesis,
                    "confidence": result.confidence,
                },
                confidence=result.confidence,
                duration_sec=duration,
                model_used=context.metadata.get("model", "unknown"),
            )

        except Exception as e:
            logger.exception("Iterative research failed")
            return ReasoningResult.error_result(
                MethodType.RESEARCH,
                str(e),
                duration_sec=time.time() - start_time,
            )

    async def _research_iteration(
        self,
        topic: str,
        iteration_num: int,
        gaps: list[str],
        context: ReasoningContext,
    ) -> ResearchIteration:
        """Execute a single research iteration."""
        # Formulate query based on gaps
        query = await self._formulate_query(topic, gaps, iteration_num)

        # Gather information
        findings = await self._gather_information(query, context)

        # Identify remaining gaps
        new_gaps = await self._identify_gaps(topic, findings, context)

        return ResearchIteration(
            iteration=iteration_num + 1,
            query=query,
            findings=findings,
            gaps=new_gaps,
            confidence=0.6 + (iteration_num * 0.1),  # Confidence increases with iterations
        )

    async def _formulate_query(
        self,
        topic: str,
        gaps: list[str],
        iteration_num: int,
    ) -> str:
        """Formulate search query based on current understanding."""
        if self.llm_client and gaps:
            prompt = f"""Topic: {topic}

Current knowledge gaps: {', '.join(gaps)}

Generate a focused search query to address these gaps.

Respond with just the query string.
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=100,
                )
                return response.content.strip()
            except Exception as e:
                logger.warning(f"Query formulation failed: {e}")

        # Fallback
        if iteration_num == 0:
            return topic
        elif gaps:
            return f"{topic} {' '.join(gaps[:2])}"
        else:
            return topic

    async def _gather_information(
        self,
        query: str,
        context: ReasoningContext,
    ) -> list[str]:
        """Gather information using search client."""
        findings = []

        if self.search_client:
            try:
                # Use search client if available
                search_results = await self.search_client.search(query)
                for result in search_results.get("results", [])[:5]:
                    findings.append(result.get("snippet", ""))
            except Exception as e:
                logger.warning(f"Search failed: {e}")

        if not findings and self.llm_client:
            # Fallback to LLM knowledge
            prompt = f"""Provide key information about: {query}

List 3-5 important findings or facts.

Respond in JSON format:
{{
    "findings": ["...", "...", "..."]
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                findings = data.get("findings", [])
            except Exception as e:
                logger.warning(f"LLM knowledge retrieval failed: {e}")

        return findings or [f"Information about: {query}"]

    async def _identify_gaps(
        self,
        topic: str,
        findings: list[str],
        context: ReasoningContext,
    ) -> list[str]:
        """Identify remaining knowledge gaps."""
        if self.llm_client:
            prompt = f"""Topic: {topic}

Current findings:
{chr(10).join(findings)}

What important questions remain unanswered? Identify 2-3 key knowledge gaps.

Respond in JSON format:
{{
    "gaps": ["...", "..."]
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                return data.get("gaps", [])
            except Exception as e:
                logger.warning(f"Gap identification failed: {e}")

        return []

    async def _synthesize_findings(
        self,
        topic: str,
        findings: list[str],
        gaps: list[str],
        context: ReasoningContext,
    ) -> str:
        """Synthesize all findings into final summary."""
        if self.llm_client:
            prompt = f"""Topic: {topic}

Key findings:
{chr(10).join(findings)}

Remaining gaps: {', '.join(gaps) if gaps else 'None identified'}

Write a comprehensive synthesis summarizing the research findings.

Respond with the synthesis text only.
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=1000,
                )
                return response.content.strip()
            except Exception as e:
                logger.warning(f"Synthesis failed: {e}")

        # Fallback
        return f"Research synthesis for {topic}: {len(findings)} findings collected. {'Remaining gaps: ' + ', '.join(gaps) if gaps else 'No significant gaps identified.'}"
