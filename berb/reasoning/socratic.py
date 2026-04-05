"""Socratic reasoning method.

This module implements Socratic questioning for deep understanding:
1. Clarify the question/concept
2. Challenge assumptions
3. Examine evidence
4. Explore perspectives
5. Question implications
6. Meta-question the questioning

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    # Option 1: Direct import (backward compatible)
    from berb.reasoning import SocraticMethod
    method = SocraticMethod(llm_client)
    result = await method.execute(context)

    # Option 2: With router (recommended for cost optimization)
    from berb.reasoning import SocraticMethod
    from berb.llm.extended_router import ExtendedNadirClawRouter
    router = ExtendedNadirClawRouter(...)
    method = SocraticMethod(router=router)
    result = await method.execute(context)

    # Option 3: Registry singleton (recommended)
    from berb.reasoning.registry import get_reasoner
    method = get_reasoner("socratic", router)
    result = await method.execute(context)
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
from .registry import ReasonerRegistry

logger = logging.getLogger(__name__)


@dataclass
class SocraticQuestion:
    """A Socratic question."""

    category: str  # clarification, assumptions, evidence, perspectives, implications, meta
    question: str
    answer: str = ""
    insights: list[str] = field(default_factory=list)


@dataclass
class SocraticResult:
    """Result of Socratic questioning."""

    original_question: str = ""
    questions: list[SocraticQuestion] = field(default_factory=list)
    final_understanding: str = ""
    key_insights: list[str] = field(default_factory=list)
    remaining_questions: list[str] = field(default_factory=list)
    confidence: float = 0.5


class SocraticMethod(ReasoningMethod):
    """Socratic reasoning method.

    Implements Socratic questioning for deep understanding.

    Usage:
        socratic = SocraticMethod(llm_client)
        result = await socratic.execute(context)

        # Access results
        print(f"Insights: {result.output['key_insights']}")
        print(f"Understanding: {result.output['final_understanding']}")
    """

    method_type = MethodType.SOCRATIC

    # Question categories
    CATEGORIES = [
        "clarification",
        "assumptions",
        "evidence",
        "perspectives",
        "implications",
        "meta",
    ]

    def __init__(
        self,
        router: Any = None,      # NEW: Primary (ExtendedNadirClawRouter)
        llm_client: Any = None,  # DEPRECATED: Fallback only
        depth: int = 2,  # Questions per category
        **kwargs: Any,
    ):
        """
        Initialize Socratic method.

        Args:
            router: LLM router for cost-optimized model selection (recommended)
            llm_client: LLM client for questioning (fallback)
            depth: Questions per category (default: 2)
            **kwargs: Additional arguments for ReasoningMethod
        """
        super().__init__(
            name="Socratic",
            description="Socratic questioning for deep understanding",
            **kwargs,
        )
        self.router = router
        self.llm_client = llm_client
        self.depth = depth
        self._run_id: str | None = None  # For cost tracking

    async def execute(self, context: ReasoningContext) -> ReasoningResult:
        """
        Execute Socratic questioning.

        Args:
            context: Reasoning context with input data

        Returns:
            ReasoningResult with insights

        Raises:
            Exception: If questioning fails
        """
        import uuid
        
        start_time = time.time()
        self._run_id = f"socratic-{uuid.uuid4().hex[:8]}"

        try:
            if not self.validate_context(context):
                return ReasoningResult.error_result(
                    MethodType.SOCRATIC,
                    "Invalid context: missing required fields",
                )

            question = context.get("question") or context.get("topic")
            if not question:
                return ReasoningResult.error_result(
                    MethodType.SOCRATIC,
                    "Context missing question/topic for Socratic questioning",
                )

            questions: list[SocraticQuestion] = []
            all_insights: list[str] = []

            # Iterate through question categories
            for category in self.CATEGORIES:
                for i in range(self.depth):
                    sq = await self._generate_question(
                        question, category, i, questions, context
                    )
                    questions.append(sq)
                    all_insights.extend(sq.insights)

            # Synthesize final understanding
            final_understanding = await self._synthesize_understanding(
                question, questions, all_insights, context
            )

            # Identify remaining questions
            remaining = await self._identify_remaining_questions(
                question, questions, context
            )

            result = SocraticResult(
                original_question=question,
                questions=questions,
                final_understanding=final_understanding,
                key_insights=all_insights,
                remaining_questions=remaining,
                confidence=0.75 if questions else 0.5,
            )

            duration = time.time() - start_time

            socratic_result = ReasoningResult.success_result(
                MethodType.SOCRATIC,
                output={
                    "original_question": question,
                    "questions_by_category": {
                        cat: [
                            {"question": q.question, "answer": q.answer}
                            for q in questions if q.category == cat
                        ]
                        for cat in self.CATEGORIES
                    },
                    "key_insights": all_insights,
                    "final_understanding": final_understanding,
                    "remaining_questions": remaining,
                    "confidence": result.confidence,
                },
                confidence=result.confidence,
                duration_sec=duration,
                model_used=context.metadata.get("model", "unknown"),
            )
            
            # Track cost if router supports it
            self._track_cost(duration)
            
            return socratic_result

        except Exception as e:
            logger.exception("Socratic questioning failed")
            return ReasoningResult.error_result(
                MethodType.SOCRATIC,
                str(e),
                duration_sec=time.time() - start_time,
            )

    async def _generate_question(
        self,
        original_question: str,
        category: str,
        question_num: int,
        previous_questions: list[SocraticQuestion],
        context: ReasoningContext,
    ) -> SocraticQuestion:
        """Generate a Socratic question in the specified category."""
        if self.llm_client:
            # Build context from previous Q&A
            prev_context = "\n".join(
                f"Q: {q.question}\nA: {q.answer}"
                for q in previous_questions[-3:]  # Last 3 for context
            )

            category_prompts = {
                "clarification": "Clarify the meaning, scope, or definition",
                "assumptions": "Challenge underlying assumptions",
                "evidence": "Examine evidence and reasoning",
                "perspectives": "Explore alternative perspectives",
                "implications": "Question implications and consequences",
                "meta": "Question the question itself",
            }

            prompt = f"""Original question: {original_question}

Previous questions and answers:
{prev_context if prev_context else 'None yet'}

Generate a {category} question: {category_prompts[category]}

Provide the question, a thoughtful answer, and key insights.

Respond in JSON format:
{{
    "question": "...",
    "answer": "...",
    "insights": ["...", "..."]
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                return SocraticQuestion(
                    category=category,
                    question=data.get("question", ""),
                    answer=data.get("answer", ""),
                    insights=data.get("insights", []),
                )
            except Exception as e:
                logger.warning(f"LLM Socratic question failed: {e}")

        # Fallback
        return SocraticQuestion(
            category=category,
            question=f"{category.title()} question about: {original_question}",
            answer=f"Answer requires deeper reflection on {original_question}",
            insights=[f"Insight from {category} questioning"],
        )

    async def _synthesize_understanding(
        self,
        original_question: str,
        questions: list[SocraticQuestion],
        insights: list[str],
        context: ReasoningContext,
    ) -> str:
        """Synthesize final understanding from Socratic dialogue."""
        if self.llm_client:
            qa_text = "\n\n".join(
                f"Q{q.category}: {q.question}\nA: {q.answer}"
                for q in questions
            )

            prompt = f"""Original question: {original_question}

Socratic dialogue:
{qa_text}

Key insights: {', '.join(insights)}

Synthesize a deeper understanding that emerges from this Socratic exploration.

Respond with the synthesis text only.
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=800,
                )
                return response.content.strip()
            except Exception as e:
                logger.warning(f"Socratic synthesis failed: {e}")

        # Fallback
        return f"Through Socratic questioning, we developed a deeper understanding of: {original_question}. Key insights: {', '.join(insights[:5])}"

    async def _identify_remaining_questions(
        self,
        original_question: str,
        questions: list[SocraticQuestion],
        context: ReasoningContext,
    ) -> list[str]:
        """Identify questions that remain after Socratic dialogue."""
        if self.llm_client:
            qa_text = "\n".join(
                f"{q.category}: {q.question} → {q.answer}"
                for q in questions
            )

            prompt = f"""Original question: {original_question}

Questions explored:
{qa_text}

What important questions remain unanswered or require further exploration?

Respond in JSON format:
{{
    "remaining_questions": ["...", "..."]
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                return data.get("remaining_questions", [])
            except Exception as e:
                logger.warning(f"Remaining questions identification failed: {e}")

        return ["Further empirical validation needed"]
    
    def _track_cost(self, duration_sec: float) -> None:
        """Track cost for Socratic execution."""
        if self.router is None or self._run_id is None:
            return
        
        if hasattr(self.router, 'track_cost'):
            # Estimate tokens for Socratic (6 categories × depth questions)
            estimated_input = 400 * 6 * self.depth + 1000  # questions + synthesis
            estimated_output = 300 * 6 * self.depth + 800
            
            self.router.track_cost(
                method="socratic",
                phase="all",
                model=self.router.role_models.get("clarification", self.router.simple_model),
                input_tokens=estimated_input,
                output_tokens=estimated_output,
                duration_ms=int(duration_sec * 1000),
                run_id=self._run_id,
            )


# Auto-register with the reasoner registry
ReasonerRegistry.register(
    MethodType.SOCRATIC,
    SocraticMethod,
)
