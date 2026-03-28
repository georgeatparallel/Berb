"""Improvement Loop for HyperAgent.

Runs the self-improvement loop:
1. Execute task
2. Track performance
3. Analyze for improvements
4. Generate modifications
5. Evaluate variants
6. Select best variant
7. Store improvement

Based on Facebook AI Research paper (arXiv:2603.19461v1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from berb.hyperagent.base import Hyperagent, Improvement, ImprovementResult, TaskResult
from berb.hyperagent.memory import PersistentMemory
from berb.hyperagent.meta_agent import MetaAgent, ModificationResult
from berb.hyperagent.task_agent import TaskAgent

logger = logging.getLogger(__name__)


@dataclass
class Variant:
    """A variant of the Hyperagent."""
    
    variant_id: str
    task_agent_code: str
    meta_agent_code: str | None = None
    performance_score: float = 0.0
    evaluation_results: dict[str, float] = field(default_factory=dict)


class ImprovementLoop:
    """Runs the Hyperagent self-improvement loop.
    
    The improvement loop:
    1. Executes tasks with current variant
    2. Analyzes performance
    3. Generates modifications (task agent + meta agent)
    4. Creates new variants
    5. Evaluates variants
    6. Selects best variant
    7. Stores improvements in memory
    
    Attributes:
        config: Configuration
        memory: Persistent memory for storing improvements
    """
    
    def __init__(self, memory: PersistentMemory):
        """
        Initialize Improvement Loop.
        
        Args:
            memory: Persistent memory instance
        """
        self.memory = memory
        self.variants: list[Variant] = []
        self.current_iteration = 0
        
        logger.info("Improvement Loop initialized")
    
    async def run_iteration(self, hyperagent: Hyperagent) -> ImprovementResult:
        """
        Run one iteration of the self-improvement loop.
        
        Args:
            hyperagent: Hyperagent to improve
        
        Returns:
            ImprovementResult with iteration results
        """
        self.current_iteration += 1
        
        logger.info("Starting improvement iteration %d", self.current_iteration)
        
        improvements_made: list[Improvement] = []
        evaluation_scores: dict[str, float] = {}
        
        try:
            # Step 1: Get current task agent performance
            if hyperagent.task_agent is None:
                return ImprovementResult(
                    iteration=self.current_iteration,
                    success=False,
                    error="Task agent not initialized",
                )
            
            task_agent_state = hyperagent.task_agent.get_state()
            
            # Step 2: Analyze performance
            if hyperagent.meta_agent is None:
                return ImprovementResult(
                    iteration=self.current_iteration,
                    success=False,
                    error="Meta agent not initialized",
                )
            
            # Create dummy task result for analysis
            dummy_result = TaskResult(
                task_id=f"iteration_{self.current_iteration}",
                success=task_agent_state.success_rate > 0.5,
                metrics={"performance": task_agent_state.average_performance},
            )
            
            analysis = await hyperagent.meta_agent.analyze_task_performance(
                dummy_result,
                task_agent_state,
            )
            
            # Step 3: Generate modifications
            modification = await hyperagent.meta_agent.generate_modification(
                analysis,
                hyperagent.task_agent,
            )
            
            if modification.code_diff:
                # Step 4: Apply modification to create new variant
                success = hyperagent.task_agent.apply_code_modification(modification.code_diff)
                
                if success:
                    import uuid
                    improvement = Improvement(
                        improvement_id=f"imp_{uuid.uuid4().hex[:8]}",
                        description=modification.description,
                        code_diff=modification.code_diff,
                        affected_component="task_agent",
                        expected_benefit=modification.expected_benefit,
                        confidence=modification.confidence,
                        transferable=True,
                        timestamp=hyperagent.state.metadata.get("timestamp"),
                    )
                    improvements_made.append(improvement)
                    
                    # Store in memory
                    await self.memory.store_improvement(improvement)
                    
                    logger.info(
                        "Applied improvement %s: %s",
                        improvement.improvement_id,
                        improvement.description,
                    )
            
            # Step 5: Generate metacognitive improvement (modify modification procedure)
            meta_modification = await hyperagent.meta_agent.modify_self()
            
            if meta_modification.code_diff:
                success = hyperagent.meta_agent.apply_self_modification(meta_modification.code_diff)
                
                if success:
                    import uuid
                    meta_improvement = Improvement(
                        improvement_id=f"meta_imp_{uuid.uuid4().hex[:8]}",
                        description=meta_modification.description,
                        code_diff=meta_modification.code_diff,
                        affected_component="meta_agent",
                        expected_benefit=meta_modification.expected_benefit,
                        confidence=meta_modification.confidence,
                        transferable=True,
                        timestamp=hyperagent.state.metadata.get("timestamp"),
                    )
                    improvements_made.append(meta_improvement)
                    await self.memory.store_improvement(meta_improvement)
                    
                    logger.info(
                        "Applied metacognitive improvement %s: %s",
                        meta_improvement.improvement_id,
                        meta_improvement.description,
                    )
            
            # Step 6: Evaluate new variant
            evaluation_scores = await self._evaluate_variant(hyperagent)
            
            # Step 7: Calculate performance delta
            performance_delta = self._calculate_performance_delta(evaluation_scores)
            
            # Step 8: Select best variant (if multiple exist)
            selected_variant = hyperagent.task_agent.get_state().variant_id
            
            return ImprovementResult(
                iteration=self.current_iteration,
                improvements_made=improvements_made,
                performance_delta=performance_delta,
                selected_variant=selected_variant,
                evaluation_scores=evaluation_scores,
                success=True,
            )
            
        except Exception as e:
            logger.error("Improvement iteration failed: %s", e)
            return ImprovementResult(
                iteration=self.current_iteration,
                improvements_made=improvements_made,
                success=False,
                error=str(e),
            )
    
    async def _evaluate_variant(self, hyperagent: Hyperagent) -> dict[str, float]:
        """
        Evaluate current variant performance.
        
        Args:
            hyperagent: Hyperagent with variant to evaluate
        
        Returns:
            Dictionary of evaluation scores
        """
        scores = {
            "success_rate": 0.0,
            "average_performance": 0.0,
            "efficiency": 0.0,
            "robustness": 0.0,
        }
        
        # Get current performance from task agent state
        if hyperagent.task_agent is not None:
            state = hyperagent.task_agent.get_state()
            scores["success_rate"] = state.success_rate
            scores["average_performance"] = state.average_performance
        
        # Get historical performance from memory
        variant_id = hyperagent.state.current_variant_id
        historical_performance = self.memory.calculate_variant_performance(variant_id)
        scores["historical_performance"] = historical_performance
        
        # Calculate composite score
        scores["overall"] = (
            scores["success_rate"] * 0.4 +
            scores["average_performance"] * 0.3 +
            scores["historical_performance"] * 0.3
        )
        
        logger.info(
            "Evaluated variant %s: overall=%.3f, success_rate=%.3f",
            variant_id,
            scores["overall"],
            scores["success_rate"],
        )
        
        return scores
    
    def _calculate_performance_delta(self, evaluation_scores: dict[str, float]) -> float:
        """
        Calculate performance delta from evaluation scores.
        
        Args:
            evaluation_scores: Scores from variant evaluation
        
        Returns:
            Performance delta (positive = improvement)
        """
        if not self.variants:
            # First variant, no baseline
            return 0.0
        
        # Compare to previous best
        previous_best = max(self.variants, key=lambda v: v.performance_score)
        current_score = evaluation_scores.get("overall", 0.0)
        
        delta = current_score - previous_best.performance_score
        
        logger.info("Performance delta: %.3f (current: %.3f, previous: %.3f)", delta, current_score, previous_best.performance_score)
        
        return delta
    
    def store_variant(self, hyperagent: Hyperagent, evaluation_scores: dict[str, float]) -> None:
        """
        Store current variant for comparison.
        
        Args:
            hyperagent: Hyperagent with variant to store
            evaluation_scores: Evaluation scores
        """
        if hyperagent.task_agent is None:
            return
        
        state = hyperagent.task_agent.get_state()
        
        variant = Variant(
            variant_id=state.variant_id,
            task_agent_code=hyperagent.task_agent.get_code(),
            meta_agent_code=hyperagent.meta_agent.get_modification_code() if hyperagent.meta_agent else None,
            performance_score=evaluation_scores.get("overall", 0.0),
            evaluation_results=evaluation_scores,
        )
        
        self.variants.append(variant)
        
        # Keep only top N variants to save memory
        if len(self.variants) > 10:
            # Keep top 5 by performance
            self.variants.sort(key=lambda v: v.performance_score, reverse=True)
            self.variants = self.variants[:5]
        
        logger.info("Stored variant %s (score: %.3f)", variant.variant_id, variant.performance_score)
    
    def get_best_variant(self) -> Variant | None:
        """
        Get the best performing variant.
        
        Returns:
            Best variant, or None if no variants
        """
        if not self.variants:
            return None
        
        return max(self.variants, key=lambda v: v.performance_score)
    
    def get_improvement_summary(self) -> dict[str, Any]:
        """
        Get summary of all improvements.
        
        Returns:
            Summary dictionary
        """
        total_improvements = sum(len(v.evaluation_results) > 0 for v in self.variants)
        # Cache once to avoid non-atomic reads: a concurrent store_variant() call
        # could sort/prune self.variants between calls, making variant_id and
        # performance_score refer to different variants.
        best = self.get_best_variant()
        return {
            "total_iterations": self.current_iteration,
            "total_variants": len(self.variants),
            "total_improvements": total_improvements,
            "best_variant": best.variant_id if best else None,
            "best_performance": best.performance_score if best else 0.0,
        }
