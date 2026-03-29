"""Dialectical reasoning method.

This module implements dialectical reasoning following the Hegelian triad:
Thesis → Antithesis → Aufhebung (Synthesis)

The dialectical method:
1. Establishes a thesis (initial position)
2. Generates an antithesis (opposing position)
3. Resolves contradictions through aufhebung (sublation/synthesis)
4. Produces a higher-level understanding that preserves truths from both

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
class DialecticalPosition:
    """A position in the dialectical process."""

    type: str  # "thesis", "antithesis", or "synthesis"
    statement: str
    supporting_arguments: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    preserved_truths: list[str] = field(default_factory=list)


@dataclass
class DialecticalResult:
    """Result of dialectical reasoning."""

    thesis: DialecticalPosition | None = None
    antithesis: DialecticalPosition | None = None
    synthesis: DialecticalPosition | None = None
    contradictions_resolved: list[str] = field(default_factory=list)
    higher_truth: str = ""
    confidence: float = 0.5


class DialecticalMethod(ReasoningMethod):
    """Dialectical reasoning method.

    Implements Hegelian dialectic: Thesis → Antithesis → Aufhebung

    Usage:
        dialectic = DialecticalMethod(llm_client)
        result = await dialectic.execute(context)

        # Access results
        print(f"Thesis: {result.output['thesis']}")
        print(f"Antithesis: {result.output['antithesis']}")
        print(f"Synthesis: {result.output['synthesis']}")
    """

    method_type = MethodType.DIALECTICAL

    def __init__(
        self,
        llm_client: Any = None,
        **kwargs: Any,
    ):
        """
        Initialize dialectical method.

        Args:
            llm_client: LLM client for generating positions
            **kwargs: Additional arguments for ReasoningMethod
        """
        super().__init__(
            name="Dialectical",
            description="Hegelian dialectic: Thesis → Antithesis → Aufhebung (Synthesis)",
            **kwargs,
        )
        self.llm_client = llm_client

    async def execute(self, context: ReasoningContext) -> ReasoningResult:
        """
        Execute dialectical reasoning.

        Args:
            context: Reasoning context with input data

        Returns:
            ReasoningResult with dialectical synthesis

        Raises:
            Exception: If dialectic fails
        """
        start_time = time.time()

        try:
            if not self.validate_context(context):
                return ReasoningResult.error_result(
                    MethodType.DIALECTICAL,
                    "Invalid context: missing required fields",
                )

            # Extract topic/thesis from context
            topic = context.get("topic") or context.get("hypothesis") or context.get("idea")
            if not topic:
                return ReasoningResult.error_result(
                    MethodType.DIALECTICAL,
                    "Context missing topic/hypothesis/idea for dialectic",
                )

            # Step 1: Establish thesis
            thesis = await self._establish_thesis(topic, context)

            # Step 2: Generate antithesis
            antithesis = await self._generate_antithesis(thesis, context)

            # Step 3: Identify contradictions
            contradictions = await self._identify_contradictions(thesis, antithesis)

            # Step 4: Resolve through aufhebung (synthesis)
            synthesis = await self._resolve_synthesis(thesis, antithesis, contradictions, context)

            # Build result
            result = DialecticalResult(
                thesis=thesis,
                antithesis=antithesis,
                synthesis=synthesis,
                contradictions_resolved=contradictions,
                higher_truth=synthesis.statement if synthesis else "",
                confidence=0.8 if synthesis else 0.5,
            )

            duration = time.time() - start_time

            return ReasoningResult.success_result(
                MethodType.DIALECTICAL,
                output={
                    "topic": topic,
                    "thesis": {
                        "statement": thesis.statement,
                        "arguments": thesis.supporting_arguments,
                    },
                    "antithesis": {
                        "statement": antithesis.statement,
                        "arguments": antithesis.supporting_arguments,
                        "contradictions": antithesis.contradictions,
                    },
                    "synthesis": {
                        "statement": synthesis.statement if synthesis else "",
                        "arguments": synthesis.supporting_arguments if synthesis else [],
                        "preserved_truths": synthesis.preserved_truths if synthesis else [],
                    },
                    "contradictions_resolved": contradictions,
                    "higher_truth": result.higher_truth,
                    "confidence": result.confidence,
                },
                confidence=result.confidence,
                duration_sec=duration,
                model_used=context.metadata.get("model", "unknown"),
            )

        except Exception as e:
            logger.exception("Dialectical reasoning failed")
            return ReasoningResult.error_result(
                MethodType.DIALECTICAL,
                str(e),
                duration_sec=time.time() - start_time,
            )

    async def _establish_thesis(
        self,
        topic: str,
        context: ReasoningContext,
    ) -> DialecticalPosition:
        """Establish the thesis (initial position)."""
        if self.llm_client:
            prompt = f"""Consider the following topic:

{topic}

Formulate a clear thesis statement representing the initial position or conventional understanding.
Provide 3-5 supporting arguments.

Respond in JSON format:
{{
    "statement": "...",
    "supporting_arguments": ["...", "...", "..."]
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                return DialecticalPosition(
                    type="thesis",
                    statement=data.get("statement", ""),
                    supporting_arguments=data.get("supporting_arguments", []),
                )
            except Exception as e:
                logger.warning(f"LLM thesis generation failed: {e}, using fallback")

        # Fallback
        return DialecticalPosition(
            type="thesis",
            statement=f"Thesis: {topic}",
            supporting_arguments=[
                f"Supporting argument 1 for {topic}",
                f"Supporting argument 2 for {topic}",
            ],
        )

    async def _generate_antithesis(
        self,
        thesis: DialecticalPosition,
        context: ReasoningContext,
    ) -> DialecticalPosition:
        """Generate the antithesis (opposing position)."""
        if self.llm_client:
            prompt = f"""Given the following thesis:

Statement: {thesis.statement}
Arguments: {chr(10).join(thesis.supporting_arguments)}

Generate a strong antithesis that challenges, contradicts, or opposes the thesis.
Identify specific contradictions with the thesis arguments.
Provide 3-5 supporting arguments for the antithesis.

Respond in JSON format:
{{
    "statement": "...",
    "supporting_arguments": ["...", "...", "..."],
    "contradictions": ["...", "...", "..."]
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                return DialecticalPosition(
                    type="antithesis",
                    statement=data.get("statement", ""),
                    supporting_arguments=data.get("supporting_arguments", []),
                    contradictions=data.get("contradictions", []),
                )
            except Exception as e:
                logger.warning(f"LLM antithesis generation failed: {e}, using fallback")

        # Fallback
        return DialecticalPosition(
            type="antithesis",
            statement=f"Antithesis: Opposing view to {thesis.statement}",
            supporting_arguments=[
                f"Counter-argument 1 to thesis",
                f"Counter-argument 2 to thesis",
            ],
            contradictions=[
                f"Contradiction with thesis argument 1",
            ],
        )

    async def _identify_contradictions(
        self,
        thesis: DialecticalPosition,
        antithesis: DialecticalPosition,
    ) -> list[str]:
        """Identify contradictions between thesis and antithesis."""
        if self.llm_client:
            prompt = f"""Compare the following positions:

THESIS: {thesis.statement}
Arguments: {chr(10).join(thesis.supporting_arguments)}

ANTITHESIS: {antithesis.statement}
Arguments: {chr(10).join(antithesis.supporting_arguments)}

Identify all key contradictions between these positions.

Respond in JSON format:
{{
    "contradictions": ["...", "...", "..."]
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                return data.get("contradictions", [])
            except Exception as e:
                logger.warning(f"LLM contradiction identification failed: {e}, using fallback")

        # Fallback: use antithesis contradictions if available
        return antithesis.contradictions or ["General contradiction between positions"]

    async def _resolve_synthesis(
        self,
        thesis: DialecticalPosition,
        antithesis: DialecticalPosition,
        contradictions: list[str],
        context: ReasoningContext,
    ) -> DialecticalPosition:
        """Resolve contradictions through aufhebung (synthesis).

        Aufhebung (sublation) simultaneously:
        - Cancels/negates the contradictions
        - Preserves the truths from both positions
        - Lifts to a higher level of understanding
        """
        if self.llm_client:
            prompt = f"""Resolve the dialectical tension through aufhebung (synthesis).

THESIS: {thesis.statement}
Arguments: {chr(10).join(thesis.supporting_arguments)}

ANTITHESIS: {antithesis.statement}
Arguments: {chr(10).join(antithesis.supporting_arguments)}

Contradictions: {chr(10).join(contradictions)}

Generate a synthesis that:
1. Resolves/cancels the contradictions
2. Preserves the valid truths from both thesis and antithesis
3. Achieves a higher-level understanding

Respond in JSON format:
{{
    "statement": "...",
    "supporting_arguments": ["...", "...", "..."],
    "preserved_truths": ["...", "...", "..."]
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                return DialecticalPosition(
                    type="synthesis",
                    statement=data.get("statement", ""),
                    supporting_arguments=data.get("supporting_arguments", []),
                    preserved_truths=data.get("preserved_truths", []),
                )
            except Exception as e:
                logger.warning(f"LLM synthesis generation failed: {e}, using fallback")

        # Fallback
        return DialecticalPosition(
            type="synthesis",
            statement=f"Synthesis: Integrated understanding of {topic if (topic := context.get('topic')) else 'the issue'}",
            supporting_arguments=[
                "Integrated insight from both positions",
            ],
            preserved_truths=[
                "Truth from thesis",
                "Truth from antithesis",
            ],
        )
