"""Scientific reasoning method.

This module implements scientific method reasoning:
1. Observation/Question
2. Hypothesis formulation
3. Prediction derivation
4. Experiment design
5. Data collection
6. Analysis and conclusion
7. Iteration (refine hypothesis)

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    # Option 1: Direct import (backward compatible)
    from berb.reasoning import ScientificMethod
    method = ScientificMethod(llm_client)
    result = await method.execute(context)

    # Option 2: With router (recommended for cost optimization)
    from berb.reasoning import ScientificMethod
    from berb.llm.extended_router import ExtendedNadirClawRouter
    router = ExtendedNadirClawRouter(...)
    method = ScientificMethod(router=router)
    result = await method.execute(context)

    # Option 3: Registry singleton (recommended)
    from berb.reasoning.registry import get_reasoner
    method = get_reasoner("scientific", router)
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
class Hypothesis:
    """A scientific hypothesis."""

    statement: str
    null_hypothesis: str = ""
    testable_predictions: list[str] = field(default_factory=list)
    falsifiability_criteria: str = ""
    confidence: float = 0.5


@dataclass
class ExperimentDesign:
    """Design for testing hypothesis."""

    description: str
    variables: dict[str, str] = field(default_factory=dict)  # independent, dependent, controlled
    methodology: list[str] = field(default_factory=list)
    expected_outcomes: list[str] = field(default_factory=list)
    potential_confounds: list[str] = field(default_factory=list)


@dataclass
class ScientificResult:
    """Result of scientific reasoning."""

    observation: str = ""
    hypothesis: Hypothesis | None = None
    experiment_design: ExperimentDesign | None = None
    analysis: str = ""
    conclusion: str = ""
    next_steps: list[str] = field(default_factory=list)
    confidence: float = 0.5


class ScientificMethod(ReasoningMethod):
    """Scientific reasoning method.

    Implements the scientific method for hypothesis-driven inquiry.

    Usage:
        # With router (recommended)
        scientific = ScientificMethod(router=router)
        result = await scientific.execute(context)

        # Backward compatible (llm_client fallback)
        scientific = ScientificMethod(llm_client=llm_client)
        result = await scientific.execute(context)

        # Access results
        print(f"Hypothesis: {result.output['hypothesis']}")
        print(f"Conclusion: {result.output['conclusion']}")
    """

    method_type = MethodType.SCIENTIFIC

    def __init__(
        self,
        router: Any = None,      # NEW: Primary (ExtendedNadirClawRouter)
        llm_client: Any = None,  # DEPRECATED: Fallback only
        **kwargs: Any,
    ):
        """
        Initialize scientific method.

        Args:
            router: LLM router for cost-optimized model selection (recommended)
            llm_client: LLM client for reasoning (fallback)
            **kwargs: Additional arguments for ReasoningMethod
        """
        super().__init__(
            name="Scientific",
            description="Scientific method: observation → hypothesis → prediction → test → conclusion",
            **kwargs,
        )
        self.router = router
        self.llm_client = llm_client
        self._run_id: str | None = None  # For cost tracking

    async def execute(self, context: ReasoningContext) -> ReasoningResult:
        """
        Execute scientific reasoning.

        Args:
            context: Reasoning context with input data

        Returns:
            ReasoningResult with scientific analysis

        Raises:
            Exception: If reasoning fails
        """
        import uuid
        
        start_time = time.time()
        self._run_id = f"scientific-{uuid.uuid4().hex[:8]}"

        try:
            if not self.validate_context(context):
                return ReasoningResult.error_result(
                    MethodType.SCIENTIFIC,
                    "Invalid context: missing required fields",
                )

            observation = context.get("observation") or context.get("question")
            if not observation:
                return ReasoningResult.error_result(
                    MethodType.SCIENTIFIC,
                    "Context missing observation/question for scientific method",
                )

            # Step 1: Formulate hypothesis
            hypothesis = await self._formulate_hypothesis(observation, context)

            # Step 2: Design experiment
            experiment = await self._design_experiment(hypothesis, context)

            # Step 3: Analyze (simulated or actual)
            analysis = await self._analyze_results(
                hypothesis, experiment, context
            )

            # Step 4: Draw conclusion
            conclusion = await self._draw_conclusion(
                observation, hypothesis, analysis, context
            )

            # Step 5: Identify next steps
            next_steps = await self._identify_next_steps(conclusion, context)

            result = ScientificResult(
                observation=observation,
                hypothesis=hypothesis,
                experiment_design=experiment,
                analysis=analysis,
                conclusion=conclusion,
                next_steps=next_steps,
                confidence=hypothesis.confidence,
            )

            duration = time.time() - start_time

            scientific_result = ReasoningResult.success_result(
                MethodType.SCIENTIFIC,
                output={
                    "observation": observation,
                    "hypothesis": {
                        "statement": hypothesis.statement,
                        "null_hypothesis": hypothesis.null_hypothesis,
                        "predictions": hypothesis.testable_predictions,
                        "falsifiability": hypothesis.falsifiability_criteria,
                    },
                    "experiment_design": {
                        "description": experiment.description,
                        "variables": experiment.variables,
                        "methodology": experiment.methodology,
                    },
                    "analysis": analysis,
                    "conclusion": conclusion,
                    "next_steps": next_steps,
                    "confidence": result.confidence,
                },
                confidence=result.confidence,
                duration_sec=duration,
                model_used=context.metadata.get("model", "unknown"),
            )
            
            # Track cost if router supports it
            self._track_cost(duration)
            
            return scientific_result

        except Exception as e:
            logger.exception("Scientific reasoning failed")
            return ReasoningResult.error_result(
                MethodType.SCIENTIFIC,
                str(e),
                duration_sec=time.time() - start_time,
            )

    async def _formulate_hypothesis(
        self,
        observation: str,
        context: ReasoningContext,
    ) -> Hypothesis:
        """Formulate a testable hypothesis."""
        if self.llm_client:
            prompt = f"""Based on the following observation:

{observation}

Formulate a clear, testable scientific hypothesis.
Include:
1. The main hypothesis statement
2. The null hypothesis
3. 3-5 testable predictions
4. Falsifiability criteria (what would prove it wrong)

Respond in JSON format:
{{
    "statement": "...",
    "null_hypothesis": "...",
    "testable_predictions": ["...", "...", "..."],
    "falsifiability_criteria": "..."
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                return Hypothesis(
                    statement=data.get("statement", ""),
                    null_hypothesis=data.get("null_hypothesis", ""),
                    testable_predictions=data.get("testable_predictions", []),
                    falsifiability_criteria=data.get("falsifiability_criteria", ""),
                    confidence=0.6,
                )
            except Exception as e:
                logger.warning(f"LLM hypothesis formulation failed: {e}")

        # Fallback
        return Hypothesis(
            statement=f"Hypothesis: {observation} is caused by factor X",
            null_hypothesis=f"Null: {observation} has no specific cause",
            testable_predictions=[
                "Prediction 1: Manipulating X will change the observation",
                "Prediction 2: Controlling for X will eliminate the observation",
            ],
            falsifiability_criteria="If X is manipulated and observation doesn't change",
            confidence=0.5,
        )

    async def _design_experiment(
        self,
        hypothesis: Hypothesis,
        context: ReasoningContext,
    ) -> ExperimentDesign:
        """Design an experiment to test the hypothesis."""
        if self.llm_client:
            prompt = f"""Design an experiment to test this hypothesis:

{hypothesis.statement}

Predictions to test:
{chr(10).join(hypothesis.testable_predictions)}

Provide:
1. Experiment description
2. Variables (independent, dependent, controlled)
3. Methodology steps
4. Expected outcomes
5. Potential confounds

Respond in JSON format:
{{
    "description": "...",
    "variables": {{"independent": "...", "dependent": "...", "controlled": "..."}},
    "methodology": ["...", "...", "..."],
    "expected_outcomes": ["...", "..."],
    "potential_confounds": ["...", "..."]
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                return ExperimentDesign(
                    description=data.get("description", ""),
                    variables=data.get("variables", {}),
                    methodology=data.get("methodology", []),
                    expected_outcomes=data.get("expected_outcomes", []),
                    potential_confounds=data.get("potential_confounds", []),
                )
            except Exception as e:
                logger.warning(f"LLM experiment design failed: {e}")

        # Fallback
        return ExperimentDesign(
            description=f"Experiment to test: {hypothesis.statement}",
            variables={
                "independent": "Factor X",
                "dependent": "Observation measure",
                "controlled": "All other variables",
            },
            methodology=[
                "Step 1: Establish baseline",
                "Step 2: Manipulate independent variable",
                "Step 3: Measure dependent variable",
                "Step 4: Analyze results",
            ],
            expected_outcomes=[
                "If hypothesis is true: X correlates with observation",
                "If null is true: No correlation",
            ],
            potential_confounds=["Confounding variable 1", "Measurement error"],
        )

    async def _analyze_results(
        self,
        hypothesis: Hypothesis,
        experiment: ExperimentDesign,
        context: ReasoningContext,
    ) -> str:
        """Analyze experimental results (or simulate analysis)."""
        if self.llm_client:
            # Check if actual results are provided
            actual_results = context.get("experiment_results")

            if actual_results:
                prompt = f"""Analyze these experimental results:

Hypothesis: {hypothesis.statement}
Expected outcomes: {chr(10).join(experiment.expected_outcomes)}

Actual results:
{actual_results}

Provide statistical and conceptual analysis.
"""
            else:
                # Simulated analysis
                prompt = f"""Provide a framework for analyzing results from this experiment:

{experiment.description}

Hypothesis: {hypothesis.statement}

What statistical tests and analytical approaches should be used?
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=800,
                )
                return response.content.strip()
            except Exception as e:
                logger.warning(f"LLM analysis failed: {e}")

        # Fallback
        return "Analysis would compare observed outcomes against expected predictions using appropriate statistical tests."

    async def _draw_conclusion(
        self,
        observation: str,
        hypothesis: Hypothesis,
        analysis: str,
        context: ReasoningContext,
    ) -> str:
        """Draw a conclusion based on analysis."""
        if self.llm_client:
            prompt = f"""Observation: {observation}

Hypothesis: {hypothesis.statement}
Null hypothesis: {hypothesis.null_hypothesis}

Analysis:
{analysis}

Draw a scientific conclusion. Does the evidence support or refute the hypothesis?
What is the confidence level?

Respond with the conclusion text only.
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=600,
                )
                return response.content.strip()
            except Exception as e:
                logger.warning(f"LLM conclusion failed: {e}")

        # Fallback
        return f"Based on the analysis, the hypothesis {'is supported' if 'support' in analysis.lower() else 'requires further testing'} by the available evidence."

    async def _identify_next_steps(
        self,
        conclusion: str,
        context: ReasoningContext,
    ) -> list[str]:
        """Identify next steps for research."""
        if self.llm_client:
            prompt = f"""Given this conclusion:

{conclusion}

What are the logical next steps for this research?

Respond in JSON format:
{{
    "next_steps": ["...", "...", "..."]
}}
"""
            try:
                response = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                import json

                data = json.loads(response.content)
                return data.get("next_steps", [])
            except Exception as e:
                logger.warning(f"Next steps identification failed: {e}")

        return [
            "Replicate with larger sample",
            "Test boundary conditions",
            "Explore underlying mechanisms",
        ]
    
    def _track_cost(self, duration_sec: float) -> None:
        """Track cost for scientific execution."""
        if self.router is None or self._run_id is None:
            return
        
        if hasattr(self.router, 'track_cost'):
            # Estimate tokens for scientific method (5 phases)
            estimated_input = 600 + 800 + 600 + 1000 + 800  # observation→hypothesis→prediction→experiment→analysis
            estimated_output = 500 + 600 + 400 + 800 + 600
            
            self.router.track_cost(
                method="scientific",
                phase="all",
                model=self.router.role_models.get("hypothesis", self.router.complex_model),
                input_tokens=estimated_input,
                output_tokens=estimated_output,
                duration_ms=int(duration_sec * 1000),
                run_id=self._run_id,
            )


# Auto-register with the reasoner registry
ReasonerRegistry.register(
    MethodType.SCIENTIFIC,
    ScientificMethod,
)
