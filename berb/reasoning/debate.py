"""Debate reasoning method.

This module implements debate-style reasoning with Pro/Con arguments and a Judge evaluation.

The debate method:
1. Generates Pro arguments supporting a position
2. Generates Con arguments opposing the position
3. Uses a Judge to evaluate arguments and declare a winner
4. Provides a balanced conclusion based on the debate

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import asyncio
import logging
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
class Argument:
    """A single argument in the debate."""

    side: str  # "pro" or "con"
    claim: str
    evidence: str = ""
    strength: float = 0.5  # 0-1 score
    rebuttals: list[str] = field(default_factory=list)


@dataclass
class DebateResult:
    """Result of a debate session."""

    pro_arguments: list[Argument] = field(default_factory=list)
    con_arguments: list[Argument] = field(default_factory=list)
    winner: str = "undecided"  # "pro", "con", or "undecided"
    judge_reasoning: str = ""
    conclusion: str = ""
    confidence: float = 0.5


class DebateMethod(ReasoningMethod):
    """Debate reasoning method.

    Implements structured debate with Pro/Con arguments and Judge evaluation.

    Usage:
        debate = DebateMethod(llm_client)
        result = await debate.execute(context)

        # Access results
        print(f"Winner: {result.output['winner']}")
        print(f"Conclusion: {result.output['conclusion']}")
    """

    method_type = MethodType.DEBATE

    def __init__(
        self,
        llm_client: Any = None,
        num_arguments: int = 3,
        **kwargs: Any,
    ):
        """
        Initialize debate method.

        Args:
            llm_client: LLM client for generating arguments
            num_arguments: Number of arguments per side (default: 3)
            **kwargs: Additional arguments for ReasoningMethod
        """
        super().__init__(
            name="Debate",
            description="Structured debate with Pro/Con arguments and Judge evaluation",
            **kwargs,
        )
        self.llm_client = llm_client
        self.num_arguments = num_arguments

    async def execute(self, context: ReasoningContext) -> ReasoningResult:
        """
        Execute debate reasoning.

        Args:
            context: Reasoning context with input data

        Returns:
            ReasoningResult with debate outcome

        Raises:
            Exception: If debate fails
        """
        import time

        start_time = time.time()

        try:
            if not self.validate_context(context):
                return ReasoningResult.error_result(
                    MethodType.DEBATE,
                    "Invalid context: missing required fields",
                )

            # Extract debate topic and position from context
            topic = context.get("topic") or context.get("hypothesis") or context.get("question")
            if not topic:
                return ReasoningResult.error_result(
                    MethodType.DEBATE,
                    "Context missing topic/hypothesis/question for debate",
                )

            position = context.get("position", f"Should we pursue: {topic}?")

            # Generate arguments
            pro_args = await self._generate_arguments(position, "pro", context)
            con_args = await self._generate_arguments(position, "con", context)

            # Allow rebuttals (optional)
            if context.get("enable_rebuttals", False):
                await self._generate_rebuttals(pro_args, con_args)

            # Judge evaluates
            judge_result = await self._judge_debate(position, pro_args, con_args, context)

            # Build result
            debate_result = DebateResult(
                pro_arguments=pro_args,
                con_arguments=con_args,
                winner=judge_result["winner"],
                judge_reasoning=judge_result["reasoning"],
                conclusion=judge_result["conclusion"],
                confidence=judge_result.get("confidence", 0.5),
            )

            duration = time.time() - start_time

            return ReasoningResult.success_result(
                MethodType.DEBATE,
                output={
                    "topic": topic,
                    "position": position,
                    "pro_arguments": [
                        {"claim": a.claim, "evidence": a.evidence, "strength": a.strength}
                        for a in pro_args
                    ],
                    "con_arguments": [
                        {"claim": a.claim, "evidence": a.evidence, "strength": a.strength}
                        for a in con_args
                    ],
                    "winner": debate_result.winner,
                    "judge_reasoning": debate_result.judge_reasoning,
                    "conclusion": debate_result.conclusion,
                    "confidence": debate_result.confidence,
                },
                confidence=debate_result.confidence,
                duration_sec=duration,
                model_used=context.metadata.get("model", "unknown"),
            )

        except Exception as e:
            logger.exception("Debate failed")
            return ReasoningResult.error_result(
                MethodType.DEBATE,
                str(e),
                duration_sec=time.time() - start_time,
            )

    async def _generate_arguments(
        self,
        position: str,
        side: str,
        context: ReasoningContext,
    ) -> list[Argument]:
        """Generate arguments for one side of the debate."""
        arguments = []

        if self.llm_client:
            # Use LLM to generate arguments
            prompt = f"""Consider the following position:

{position}

Generate {self.num_arguments} strong arguments for the {side.upper()} side.
For each argument, provide:
1. A clear claim
2. Supporting evidence or reasoning

Respond in JSON format:
{{
    "arguments": [
        {{"claim": "...", "evidence": "..."}},
        ...
    ]
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                for arg_data in data.get("arguments", []):
                    arguments.append(
                        Argument(
                            side=side,
                            claim=arg_data.get("claim", ""),
                            evidence=arg_data.get("evidence", ""),
                            strength=0.7,  # Default strength
                        )
                    )
            except Exception as e:
                logger.warning(f"LLM argument generation failed: {e}, using fallback")
                arguments = self._generate_fallback_arguments(side, position)
        else:
            # Fallback without LLM
            arguments = self._generate_fallback_arguments(side, position)

        return arguments

    def _generate_fallback_arguments(self, side: str, position: str) -> list[Argument]:
        """Generate fallback arguments without LLM."""
        # Simple template-based arguments
        arguments = []
        for i in range(self.num_arguments):
            arguments.append(
                Argument(
                    side=side,
                    claim=f"{side.title()} argument {i + 1} for: {position}",
                    evidence="This argument requires LLM-based generation for substantive content.",
                    strength=0.5,
                )
            )
        return arguments

    async def _generate_rebuttals(
        self,
        pro_args: list[Argument],
        con_args: list[Argument],
    ) -> None:
        """Generate rebuttals for arguments."""
        # Each side rebuts the other's arguments
        for pro_arg in pro_args:
            # Con rebuts this pro argument
            rebuttal = f"Rebuttal to: {pro_arg.claim}"
            pro_arg.rebuttals.append(rebuttal)

        for con_arg in con_args:
            # Pro rebuts this con argument
            rebuttal = f"Rebuttal to: {con_arg.claim}"
            con_arg.rebuttals.append(rebuttal)

    async def _judge_debate(
        self,
        position: str,
        pro_args: list[Argument],
        con_args: list[Argument],
        context: ReasoningContext,
    ) -> dict[str, Any]:
        """Judge evaluates the debate and declares a winner."""
        if self.llm_client:
            # Format arguments for judge
            pro_text = "\n".join(
                f"- {a.claim} (Evidence: {a.evidence})" for a in pro_args
            )
            con_text = "\n".join(
                f"- {a.claim} (Evidence: {a.evidence})" for a in con_args
            )

            prompt = f"""As an impartial judge, evaluate this debate:

Position: {position}

PRO Arguments:
{pro_text}

CON Arguments:
{con_text}

Evaluate the strength, evidence, and logic of each side.
Declare a winner and explain your reasoning.

Respond in JSON format:
{{
    "winner": "pro" | "con" | "undecided",
    "reasoning": "...",
    "conclusion": "...",
    "confidence": 0.0-1.0
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                return json.loads(response.content)
            except Exception as e:
                logger.warning(f"LLM judge failed: {e}, using fallback")

        # Fallback: simple strength-based judging
        pro_strength = sum(a.strength for a in pro_args) / len(pro_args) if pro_args else 0.5
        con_strength = sum(a.strength for a in con_args) / len(con_args) if con_args else 0.5

        if pro_strength > con_strength + 0.1:
            winner = "pro"
        elif con_strength > pro_strength + 0.1:
            winner = "con"
        else:
            winner = "undecided"

        return {
            "winner": winner,
            "reasoning": f"Pro average strength: {pro_strength:.2f}, Con average strength: {con_strength:.2f}",
            "conclusion": f"The debate favors the {winner} side based on argument strength." if winner != "undecided" else "The debate is too close to call.",
            "confidence": abs(pro_strength - con_strength),
        }
