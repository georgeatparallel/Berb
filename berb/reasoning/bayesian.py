"""Bayesian Reasoning Method for Berb.

Bayesian reasoning for evidence-grounded belief updates.

This method:
1. Elicits prior probabilities for hypotheses
2. Assesses likelihood of evidence given hypotheses
3. Updates posterior beliefs using Bayes' rule
4. Performs sensitivity analysis

Key Features:
- Quantitative belief updates
- Evidence-grounded reasoning
- Sensitivity analysis for robustness
- Ideal for screening, analysis, and decision stages

Based on: Bayesian epistemology (Jaynes 2003)
Applications: Clinical trials, intelligence analysis, model selection

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    # Option 1: Direct import (for one-off usage)
    from berb.reasoning import BayesianMethod
    method = BayesianMethod(router)
    result = await method.execute(context)

    # Option 2: Registry singleton (recommended for reuse)
    from berb.reasoning.registry import get_reasoner
    method = get_reasoner("bayesian", router)
    result = await method.execute(context)

    # Access results
    posteriors = result.output["posteriors"]
    sensitivity = result.output["sensitivity"]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from berb.reasoning.base import (
    MethodType,
    ReasoningContext,
    ReasoningMethod,
    ReasoningResult,
)
from berb.reasoning.registry import ReasonerRegistry

logger = logging.getLogger(__name__)


@dataclass
class Hypothesis:
    """A hypothesis with prior and posterior probabilities."""
    
    name: str
    prior: float  # P(H) - prior probability (0-1)
    posterior: float = 0.0  # P(H|E) - posterior probability
    likelihood: float = 1.0  # P(E|H) - likelihood
    description: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "prior": self.prior,
            "posterior": self.posterior,
            "likelihood": self.likelihood,
            "description": self.description,
        }


@dataclass
class Evidence:
    """Evidence item with likelihood assessments."""
    
    name: str
    description: str = ""
    likelihood_given_h: dict[str, float] = field(default_factory=dict)  # P(E|H) for each hypothesis
    likelihood_given_not_h: dict[str, float] = field(default_factory=dict)  # P(E|¬H)
    
    def likelihood_ratio(self, hypothesis_name: str) -> float:
        """Calculate likelihood ratio for a hypothesis."""
        p_e_given_h = self.likelihood_given_h.get(hypothesis_name, 0.5)
        p_e_given_not_h = self.likelihood_given_not_h.get(hypothesis_name, 0.5)
        
        if p_e_given_not_h == 0:
            return float('inf') if p_e_given_h > 0 else 1.0
        
        return p_e_given_h / p_e_given_not_h
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "likelihood_given_h": self.likelihood_given_h,
            "likelihood_given_not_h": self.likelihood_given_not_h,
        }


@dataclass
class BayesianResult:
    """Result of Bayesian reasoning."""
    
    hypotheses: list[Hypothesis]
    evidence: list[Evidence]
    posteriors: dict[str, float]  # Final posterior probabilities
    sensitivity: dict[str, Any]  # Sensitivity analysis results
    recommendation: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "evidence": [e.to_dict() for e in self.evidence],
            "posteriors": self.posteriors,
            "sensitivity": self.sensitivity,
            "recommendation": self.recommendation,
        }


class BayesianMethod(ReasoningMethod):
    """Bayesian reasoning method.
    
    Implements Bayesian belief updates:
    P(H|E) = P(E|H) × P(H) / P(E)
    
    Where:
    - P(H) = Prior probability of hypothesis
    - P(E|H) = Likelihood of evidence given hypothesis
    - P(H|E) = Posterior probability after seeing evidence
    
    Attributes:
        router: LLM model router
    """
    
    method_type = MethodType.BAYESIAN
    
    def __init__(
        self,
        router: Any | None = None,
        name: str | None = None,
        description: str | None = None,
    ):
        """
        Initialize Bayesian reasoning method.

        Args:
            router: LLM model router (provides get_provider_for_role)
            llm_client: LLM client for direct API calls (backward compatibility)
            name: Human-readable name
            description: Description of the method
        """
        super().__init__(
            name=name or "Bayesian Reasoning",
            description=description or (
                "Evidence-grounded belief updates using Bayes' rule"
            ),
        )
        self.router = router
        self.llm_client = llm_client
    
    async def execute(self, context: ReasoningContext) -> ReasoningResult:
        """
        Execute Bayesian reasoning.
        
        Args:
            context: Reasoning context with hypotheses and evidence
        
        Returns:
            ReasoningResult with posteriors and sensitivity analysis
        """
        import time
        t0 = time.monotonic()
        
        # Validate context
        if not self.validate_context(context):
            return ReasoningResult.error_result(
                self.method_type,
                "Invalid context: missing stage_id or input_data",
            )
        
        # Extract required data from context
        hypotheses_data = context.get("hypotheses", [])
        evidence_data = context.get("evidence", [])
        
        if not hypotheses_data:
            return ReasoningResult.error_result(
                self.method_type,
                "Context missing hypotheses",
            )
        
        try:
            # Phase 1: Elicit priors (if not provided)
            hypotheses = await self._elicit_priors(hypotheses_data, context)
            
            # Phase 2: Assess likelihoods (if evidence provided)
            evidence = await self._assess_likelihoods(evidence_data, hypotheses, context)
            
            # Phase 3: Update posteriors using Bayes' rule
            posteriors = self._update_posteriors(hypotheses, evidence)
            
            # Phase 4: Sensitivity analysis
            sensitivity = await self._analyze_sensitivity(hypotheses, evidence, context)
            
            # Phase 5: Generate recommendation
            recommendation = self._generate_recommendation(posteriors, sensitivity)
            
            # Update hypotheses with posteriors
            for h in hypotheses:
                h.posterior = posteriors.get(h.name, h.prior)
            
            elapsed = time.monotonic() - t0
            
            return ReasoningResult.success_result(
                method_type=self.method_type,
                output={
                    "hypotheses": [h.to_dict() for h in hypotheses],
                    "evidence": [e.to_dict() for e in evidence],
                    "posteriors": posteriors,
                    "sensitivity": sensitivity,
                    "recommendation": recommendation,
                },
                confidence=max(posteriors.values()) if posteriors else 0.0,
                metadata={
                    "num_hypotheses": len(hypotheses),
                    "num_evidence": len(evidence),
                    "duration_sec": elapsed,
                },
            )
            
        except Exception as e:
            self._logger.error("Bayesian reasoning failed: %s", e)
            return ReasoningResult.error_result(
                self.method_type,
                str(e),
            )
    
    async def _elicit_priors(
        self,
        hypotheses_data: list[dict[str, Any]],
        context: ReasoningContext,
    ) -> list[Hypothesis]:
        """
        Elicit prior probabilities for hypotheses.
        
        Args:
            hypotheses_data: List of hypothesis data
            context: Reasoning context
        
        Returns:
            List of Hypothesis objects with priors
        """
        hypotheses = []
        
        # If priors already provided, use them
        for h_data in hypotheses_data:
            if isinstance(h_data, Hypothesis):
                hypotheses.append(h_data)
            elif isinstance(h_data, dict):
                hypothesis = Hypothesis(
                    name=h_data.get("name", "Unknown"),
                    prior=h_data.get("prior", 0.5),
                    description=h_data.get("description", ""),
                )
                hypotheses.append(hypothesis)
            elif isinstance(h_data, str):
                # Just a name, use default prior
                hypothesis = Hypothesis(
                    name=h_data,
                    prior=0.5,
                )
                hypotheses.append(hypothesis)
        
        # If no priors provided, use LLM to elicit
        if all(h.prior == 0.5 for h in hypotheses) and self.router:
            provider = self.router.get_provider_for_role("scoring")
            
            prompt = self._build_prior_elicitation_prompt(hypotheses, context)
            response = await provider.complete(prompt)
            
            # Parse priors from response
            priors = self._parse_priors(response.content, hypotheses)
            for h, prior in zip(hypotheses, priors):
                h.prior = prior
        
        # Normalize priors to sum to 1
        total = sum(h.prior for h in hypotheses)
        if total > 0:
            for h in hypotheses:
                h.prior /= total
        
        return hypotheses
    
    async def _assess_likelihoods(
        self,
        evidence_data: list[dict[str, Any]],
        hypotheses: list[Hypothesis],
        context: ReasoningContext,
    ) -> list[Evidence]:
        """
        Assess likelihood of evidence given hypotheses.
        
        Args:
            evidence_data: List of evidence data
            hypotheses: List of hypotheses
            context: Reasoning context
        
        Returns:
            List of Evidence objects
        """
        evidence = []
        
        for e_data in evidence_data:
            if isinstance(e_data, Evidence):
                evidence.append(e_data)
            elif isinstance(e_data, dict):
                ev = Evidence(
                    name=e_data.get("name", "Unknown"),
                    description=e_data.get("description", ""),
                )
                
                # Extract likelihoods if provided
                ev.likelihood_given_h = e_data.get("likelihood_given_h", {})
                ev.likelihood_given_not_h = e_data.get("likelihood_given_not_h", {})
                
                evidence.append(ev)
        
        # If likelihoods not provided, use LLM to assess
        if evidence and self.router:
            provider = self.router.get_provider_for_role("scoring")
            
            prompt = self._build_likelihood_assessment_prompt(evidence, hypotheses, context)
            response = await provider.complete(prompt)
            
            # Parse likelihoods from response
            evidence = self._parse_likelihoods(response.content, evidence, hypotheses)
        
        return evidence
    
    def _update_posteriors(
        self,
        hypotheses: list[Hypothesis],
        evidence: list[Evidence],
    ) -> dict[str, float]:
        """
        Update posterior probabilities using Bayes' rule.
        
        P(H|E) = P(E|H) × P(H) / P(E)
        
        Args:
            hypotheses: List of hypotheses with priors
            evidence: List of evidence with likelihoods
        
        Returns:
            Dictionary of posterior probabilities
        """
        posteriors = {h.name: h.prior for h in hypotheses}
        
        # Apply each piece of evidence
        for ev in evidence:
            # Calculate marginal likelihood P(E)
            p_e = sum(
                ev.likelihood_given_h.get(h.name, 0.5) * posteriors[h.name]
                for h in hypotheses
            )
            
            # Update each hypothesis
            for h in hypotheses:
                p_e_given_h = ev.likelihood_given_h.get(h.name, 0.5)
                
                if p_e > 0:
                    # Bayes' rule
                    posteriors[h.name] = (p_e_given_h * posteriors[h.name]) / p_e
        
        # Normalize posteriors
        total = sum(posteriors.values())
        if total > 0:
            for name in posteriors:
                posteriors[name] /= total
        
        return posteriors
    
    async def _analyze_sensitivity(
        self,
        hypotheses: list[Hypothesis],
        evidence: list[Evidence],
        context: ReasoningContext,
    ) -> dict[str, Any]:
        """
        Analyze sensitivity to prior assumptions.
        
        Args:
            hypotheses: List of hypotheses
            evidence: List of evidence
            context: Reasoning context
        
        Returns:
            Sensitivity analysis results
        """
        # Base posteriors
        base_posteriors = self._update_posteriors(hypotheses, evidence)
        
        # Perturb each prior and see how posteriors change
        sensitivity = {
            "base_posteriors": base_posteriors,
            "prior_perturbations": [],
        }
        
        for h in hypotheses:
            # Perturb prior by ±10%
            for delta in [-0.1, 0.1]:
                perturbed_prior = max(0.01, min(0.99, h.prior + delta))
                
                # Create perturbed hypothesis
                perturbed_h = Hypothesis(
                    name=h.name,
                    prior=perturbed_prior,
                )
                perturbed_hypotheses = [
                    perturbed_h if h2.name == h.name else h2
                    for h2 in hypotheses
                ]
                
                # Recalculate posteriors
                perturbed_posteriors = self._update_posteriors(
                    perturbed_hypotheses,
                    evidence,
                )
                
                # Calculate sensitivity
                sensitivity_score = sum(
                    abs(perturbed_posteriors.get(name, 0) - base_posteriors.get(name, 0))
                    for name in base_posteriors
                )
                
                sensitivity["prior_perturbations"].append({
                    "hypothesis": h.name,
                    "delta": delta,
                    "sensitivity_score": sensitivity_score,
                    "perturbed_posteriors": perturbed_posteriors,
                })
        
        # Identify most sensitive priors
        sensitivity["most_sensitive"] = max(
            sensitivity["prior_perturbations"],
            key=lambda x: x["sensitivity_score"],
            default=None,
        )
        
        return sensitivity
    
    def _generate_recommendation(
        self,
        posteriors: dict[str, float],
        sensitivity: dict[str, Any],
    ) -> str:
        """
        Generate recommendation based on posteriors.
        
        Args:
            posteriors: Posterior probabilities
            sensitivity: Sensitivity analysis results
        
        Returns:
            Recommendation string
        """
        if not posteriors:
            return "Insufficient data for recommendation"
        
        # Find best hypothesis
        best = max(posteriors.items(), key=lambda x: x[1])
        best_name, best_prob = best
        
        # Check confidence
        if best_prob > 0.8:
            confidence = "HIGH"
        elif best_prob > 0.6:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        # Check sensitivity
        most_sensitive = sensitivity.get("most_sensitive")
        if most_sensitive and most_sensitive["sensitivity_score"] > 0.2:
            sensitivity_warning = f"Note: Results sensitive to prior for {most_sensitive['hypothesis']}"
        else:
            sensitivity_warning = "Results robust to prior perturbations"
        
        return (
            f"Recommendation: {best_name} (P={best_prob:.2f}, {confidence} confidence)\n"
            f"{sensitivity_warning}"
        )
    
    def _build_prior_elicitation_prompt(
        self,
        hypotheses: list[Hypothesis],
        context: ReasoningContext,
    ) -> str:
        """Build prompt for prior elicitation."""
        h_list = "\n".join(f"- {h.name}: {h.description}" for h in hypotheses)
        
        return f"""You are an expert at eliciting prior probabilities.

Given these hypotheses:
{h_list}

Context: {context.metadata.get("topic", "Research task")}

Assign prior probabilities (0-1) to each hypothesis based on existing knowledge.
Priors should sum to 1.

Output format (JSON):
{{
    "priors": {{
        "hypothesis_name": 0.5,
        ...
    }},
    "rationale": "..."
}}"""
    
    def _build_likelihood_assessment_prompt(
        self,
        evidence: list[Evidence],
        hypotheses: list[Hypothesis],
        context: ReasoningContext,
    ) -> str:
        """Build prompt for likelihood assessment."""
        h_names = [h.name for h in hypotheses]
        e_list = "\n".join(f"- {e.name}: {e.description}" for e in evidence)
        
        return f"""You are an expert at assessing evidence likelihoods.

Hypotheses: {', '.join(h_names)}

Evidence:
{e_list}

For each piece of evidence, estimate:
- P(E|H): Probability of evidence if hypothesis is true
- P(E|¬H): Probability of evidence if hypothesis is false

Output format (JSON):
{{
    "likelihoods": {{
        "evidence_name": {{
            "hypothesis_name": {{
                "p_e_given_h": 0.8,
                "p_e_given_not_h": 0.2
            }}
        }}
    }}
}}"""
    
    def _parse_priors(
        self,
        response: str,
        hypotheses: list[Hypothesis],
    ) -> list[float]:
        """Parse priors from LLM response."""
        import json
        import re
        
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                priors_dict = data.get("priors", {})
                
                priors = []
                for h in hypotheses:
                    priors.append(priors_dict.get(h.name, 0.5))
                
                return priors
            except (json.JSONDecodeError, ValueError):
                pass
        
        # Fallback: equal priors
        return [1.0 / len(hypotheses)] * len(hypotheses)
    
    def _parse_likelihoods(
        self,
        response: str,
        evidence: list[Evidence],
        hypotheses: list[Hypothesis],
    ) -> list[Evidence]:
        """Parse likelihoods from LLM response."""
        import json
        import re
        
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                likelihoods_dict = data.get("likelihoods", {})
                
                for ev in evidence:
                    if ev.name in likelihoods_dict:
                        ev_data = likelihoods_dict[ev.name]
                        for h in hypotheses:
                            if h.name in ev_data:
                                h_data = ev_data[h.name]
                                ev.likelihood_given_h[h.name] = h_data.get("p_e_given_h", 0.5)
                                ev.likelihood_given_not_h[h.name] = h_data.get("p_e_given_not_h", 0.5)

                return evidence
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: neutral likelihoods
        return evidence


# Auto-register with the reasoner registry
ReasonerRegistry.register(
    MethodType.BAYESIAN,
    BayesianMethod,
)
