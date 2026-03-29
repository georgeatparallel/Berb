"""Jury (orchestrated) reasoning method.

This module implements jury-style orchestrated multi-agent evaluation:
1. Select diverse "jurors" (agents with different perspectives)
2. Present evidence/arguments to all jurors
3. Each juror deliberates independently
4. Foreman (orchestrator) synthesizes verdict
5. Unanimous/majority decision with reasoning

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .base import (
    ReasoningMethod,
    ReasoningContext,
    ReasoningResult,
    MethodType,
)

logger = logging.getLogger(__name__)


class JurorRole(str, Enum):
    """Role of a juror in the jury."""

    OPTIMIST = "optimist"  # Sees potential and benefits
    SKEPTIC = "skeptic"  # Questions assumptions and evidence
    PRACTITIONER = "practitioner"  # Focuses on feasibility
    ETHICIST = "ethicist"  # Considers ethical implications
    INNOVATOR = "innovator"  # Values novelty and creativity
    ECONOMIST = "economist"  # Analyzes cost-benefit


@dataclass
class Juror:
    """A juror in the jury."""

    role: JurorRole
    name: str
    perspective: str
    verdict: str = ""  # "approve", "reject", "abstain"
    reasoning: str = ""
    confidence: float = 0.5
    concerns: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)  # Conditions for approval


@dataclass
class JuryResult:
    """Result of jury deliberation."""

    case: str = ""
    jurors: list[Juror] = field(default_factory=list)
    verdict: str = ""  # "unanimous_approve", "majority_approve", "majority_reject", "unanimous_reject", "hung"
    foreman_synthesis: str = ""
    vote_count: dict[str, int] = field(default_factory=dict)  # approve, reject, abstain
    key_arguments: list[str] = field(default_factory=list)
    dissenting_opinions: list[str] = field(default_factory=list)
    confidence: float = 0.5


class JuryMethod(ReasoningMethod):
    """Jury reasoning method.

    Implements orchestrated multi-agent evaluation with jury deliberation.

    Usage:
        jury = JuryMethod(llm_client)
        result = await jury.execute(context)

        # Access results
        print(f"Verdict: {result.output['verdict']}")
        print(f"Vote: {result.output['vote_count']}")
    """

    method_type = MethodType.JURY

    # Default jury composition
    DEFAULT_JURORS = [
        JurorRole.OPTIMIST,
        JurorRole.SKEPTIC,
        JurorRole.PRACTITIONER,
        JurorRole.ETHICIST,
        JurorRole.INNOVATOR,
        JurorRole.ECONOMIST,
    ]

    def __init__(
        self,
        llm_client: Any = None,
        jury_size: int = 6,
        require_unanimous: bool = False,
        **kwargs: Any,
    ):
        """
        Initialize jury method.

        Args:
            llm_client: LLM client for juror simulation
            jury_size: Number of jurors (default: 6)
            require_unanimous: Require unanimous verdict (default: False)
            **kwargs: Additional arguments for ReasoningMethod
        """
        super().__init__(
            name="Jury (Orchestrated)",
            description="Multi-agent jury deliberation for balanced evaluation",
            **kwargs,
        )
        self.llm_client = llm_client
        self.jury_size = jury_size
        self.require_unanimous = require_unanimous

    async def execute(self, context: ReasoningContext) -> ReasoningResult:
        """
        Execute jury deliberation.

        Args:
            context: Reasoning context with input data

        Returns:
            ReasoningResult with jury verdict

        Raises:
            Exception: If deliberation fails
        """
        start_time = time.time()

        try:
            if not self.validate_context(context):
                return ReasoningResult.error_result(
                    MethodType.JURY,
                    "Invalid context: missing required fields",
                )

            case = context.get("case") or context.get("proposal") or context.get("hypothesis")
            if not case:
                return ReasoningResult.error_result(
                    MethodType.JURY,
                    "Context missing case/proposal/hypothesis for jury",
                )

            # Select jurors
            jurors = await self._select_jurors(context)

            # Present case to jury
            await self._present_case(case, jurors, context)

            # Individual deliberation
            for juror in jurors:
                await self._juror_deliberation(juror, case, context)

            # Foreman synthesis
            verdict, synthesis, vote_count = await self._foreman_synthesis(
                jurors, case, context
            )

            # Collect key arguments and dissenting opinions
            key_args = self._collect_key_arguments(jurors)
            dissenting = self._collect_dissenting_opinions(jurors)

            result = JuryResult(
                case=case,
                jurors=jurors,
                verdict=verdict,
                foreman_synthesis=synthesis,
                vote_count=vote_count,
                key_arguments=key_args,
                dissenting_opinions=dissenting,
                confidence=self._calculate_confidence(jurors, verdict),
            )

            duration = time.time() - start_time

            return ReasoningResult.success_result(
                MethodType.JURY,
                output={
                    "case": case,
                    "verdict": verdict,
                    "vote_count": vote_count,
                    "juror_votes": {
                        f"{j.name} ({j.role.value})": {
                            "verdict": j.verdict,
                            "confidence": j.confidence,
                        }
                        for j in jurors
                    },
                    "foreman_synthesis": synthesis,
                    "key_arguments": key_args,
                    "dissenting_opinions": dissenting,
                    "juror_reasoning": {
                        f"{j.name} ({j.role.value})": j.reasoning
                        for j in jurors
                    },
                    "confidence": result.confidence,
                },
                confidence=result.confidence,
                duration_sec=duration,
                model_used=context.metadata.get("model", "unknown"),
            )

        except Exception as e:
            logger.exception("Jury deliberation failed")
            return ReasoningResult.error_result(
                MethodType.JURY,
                str(e),
                duration_sec=time.time() - start_time,
            )

    async def _select_jurors(
        self,
        context: ReasoningContext,
    ) -> list[Juror]:
        """Select jurors based on case type."""
        # Use default jury composition
        selected_roles = self.DEFAULT_JURORS[: self.jury_size]

        # Create jurors with role-specific perspectives
        jurors = []
        for role in selected_roles:
            perspective = self._get_role_perspective(role)
            jurors.append(
                Juror(
                    role=role,
                    name=role.value.title(),
                    perspective=perspective,
                )
            )

        return jurors

    def _get_role_perspective(self, role: JurorRole) -> str:
        """Get the perspective for a juror role."""
        perspectives = {
            JurorRole.OPTIMIST: "Focuses on potential benefits, opportunities, and positive outcomes",
            JurorRole.SKEPTIC: "Questions assumptions, demands strong evidence, identifies weaknesses",
            JurorRole.PRACTITIONER: "Evaluates feasibility, practicality, and implementation challenges",
            JurorRole.ETHICIST: "Considers ethical implications, fairness, and societal impact",
            JurorRole.INNOVATOR: "Values novelty, creativity, and breakthrough potential",
            JurorRole.ECONOMIST: "Analyzes costs, benefits, ROI, and resource efficiency",
        }
        return perspectives.get(role, "General evaluation perspective")

    async def _present_case(
        self,
        case: str,
        jurors: list[Juror],
        context: ReasoningContext,
    ) -> None:
        """Present the case to all jurors."""
        # In a full implementation, this would customize the presentation
        # based on each juror's role
        pass

    async def _juror_deliberation(
        self,
        juror: Juror,
        case: str,
        context: ReasoningContext,
    ) -> None:
        """Individual juror deliberation."""
        if self.llm_client:
            prompt = f"""You are a {juror.role.value} juror.

Your perspective: {juror.perspective}

Case to evaluate:
{case}

Deliberate and provide:
1. Your verdict: "approve", "reject", or "abstain"
2. Your reasoning from your perspective
3. Your confidence level (0-1)
4. Key concerns (if any)
5. Conditions for approval (if any)

Respond in JSON format:
{{
    "verdict": "approve|reject|abstain",
    "reasoning": "...",
    "confidence": 0.0-1.0,
    "concerns": ["...", "..."],
    "conditions": ["...", "..."]
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                juror.verdict = data.get("verdict", "abstain")
                juror.reasoning = data.get("reasoning", "")
                juror.confidence = data.get("confidence", 0.5)
                juror.concerns = data.get("concerns", [])
                juror.conditions = data.get("conditions", [])
                return
            except Exception as e:
                logger.warning(f"LLM juror deliberation failed: {e}")

        # Fallback
        juror.verdict = "abstain"
        juror.reasoning = f"As a {juror.role.value}, I need more information to reach a verdict."
        juror.confidence = 0.3

    async def _foreman_synthesis(
        self,
        jurors: list[Juror],
        case: str,
        context: ReasoningContext,
    ) -> tuple[str, str, dict[str, int]]:
        """Foreman synthesizes the jury's verdict."""
        # Count votes
        vote_count = {"approve": 0, "reject": 0, "abstain": 0}
        for juror in jurors:
            vote_count[juror.verdict] = vote_count.get(juror.verdict, 0) + 1

        # Determine verdict
        if vote_count["approve"] == len(jurors):
            verdict = "unanimous_approve"
        elif vote_count["reject"] == len(jurors):
            verdict = "unanimous_reject"
        elif vote_count["approve"] > vote_count["reject"]:
            verdict = "majority_approve"
        elif vote_count["reject"] > vote_count["approve"]:
            verdict = "majority_reject"
        else:
            verdict = "hung"

        # Generate synthesis
        if self.llm_client:
            juror_summaries = "\n".join(
                f"{j.name} ({j.role.value}): {j.verdict} - {j.reasoning[:100]}..."
                for j in jurors
            )

            prompt = f"""As the jury foreman, synthesize the deliberations:

Case: {case}

Juror votes:
{juror_summaries}

Vote count: Approve={vote_count['approve']}, Reject={vote_count['reject']}, Abstain={vote_count['abstain']}

Provide a synthesis that:
1. Summarizes the key considerations
2. Explains the verdict
3. Highlights important conditions or concerns

Respond in JSON format:
{{
    "synthesis": "..."
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                return verdict, data.get("synthesis", ""), vote_count
            except Exception as e:
                logger.warning(f"LLM foreman synthesis failed: {e}")

        # Fallback
        synthesis = f"The jury reached a {verdict.replace('_', ' ')} verdict with {vote_count['approve']} approving, {vote_count['reject']} rejecting, and {vote_count['abstain']} abstaining."
        return verdict, synthesis, vote_count

    def _collect_key_arguments(self, jurors: list[Juror]) -> list[str]:
        """Collect key arguments from all jurors."""
        arguments = []
        for juror in jurors:
            if juror.reasoning:
                arguments.append(f"[{juror.role.value}] {juror.reasoning[:150]}")
        return arguments

    def _collect_dissenting_opinions(self, jurors: list[Juror]) -> list[str]:
        """Collect dissenting opinions."""
        dissenting = []
        majority_verdict = max(
            ["approve", "reject", "abstain"],
            key=lambda v: sum(1 for j in jurors if j.verdict == v),
        )

        for juror in jurors:
            if juror.verdict != majority_verdict and juror.verdict != "abstain":
                dissenting.append(
                    f"{juror.name} ({juror.role.value}) dissents: {juror.reasoning[:150]}"
                )

        return dissenting

    def _calculate_confidence(
        self,
        jurors: list[Juror],
        verdict: str,
    ) -> float:
        """Calculate overall confidence in the verdict."""
        if not jurors:
            return 0.5

        # Higher confidence for unanimous decisions
        unanimity_bonus = 0.2 if verdict.startswith("unanimous") else 0.0

        # Average juror confidence
        avg_confidence = sum(j.confidence for j in jurors) / len(jurors)

        # Majority size bonus
        vote_counts = {}
        for j in jurors:
            vote_counts[j.verdict] = vote_counts.get(j.verdict, 0) + 1
        majority_size = max(vote_counts.values()) if vote_counts else 0
        majority_bonus = (majority_size / len(jurors)) * 0.2

        return min(1.0, unanimity_bonus + (avg_confidence * 0.6) + majority_bonus)
