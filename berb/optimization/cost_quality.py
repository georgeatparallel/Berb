"""Cost-Quality Optimization Loop for Berb.

Based on AI Scientist (Nature 2026) - Section 4.3: Cost Analysis

Features:
- Track cost per stage
- Correlate cost with quality metrics
- Identify diminishing returns
- Auto-adjust model selection per stage
- Budget-aware quality optimization

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.optimization.cost_quality import CostQualityOptimizer
    
    optimizer = CostQualityOptimizer(budget=5.0)
    optimizer.track_stage("hypothesis_gen", cost=0.15, quality=8.2)
    recommendations = optimizer.get_optimization_recommendations()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    """LLM model tiers by cost/quality."""
    BUDGET = "budget"  # Cheapest, fastest (e.g., gpt-4o-mini)
    MID = "mid"  # Balanced (e.g., gpt-4o)
    PREMIUM = "premium"  # Best quality (e.g., o1, claude-opus)


@dataclass
class StageCostRecord:
    """Cost record for a single stage execution."""
    
    stage_name: str
    stage_number: int
    cost_usd: float
    input_tokens: int
    output_tokens: int
    model_used: str
    model_tier: ModelTier
    quality_score: float  # 1-10
    duration_sec: float
    timestamp: datetime = field(default_factory=datetime.now)
    run_id: str = ""


@dataclass
class CostQualityCorrelation:
    """Correlation between cost and quality for a stage."""
    
    stage_name: str
    total_cost: float
    avg_quality: float
    cost_per_quality_point: float
    diminishing_returns_threshold: float | None  # Cost where returns diminish
    optimal_model_tier: ModelTier
    data_points: int


@dataclass
class OptimizationRecommendation:
    """Recommendation for cost optimization."""
    
    stage_name: str
    current_model_tier: ModelTier
    recommended_model_tier: ModelTier
    expected_cost_savings_usd: float
    expected_quality_impact: float  # Negative = quality decrease
    confidence: float  # 0-1
    reasoning: str


@dataclass
class BudgetStatus:
    """Current budget status."""
    
    total_budget_usd: float
    spent_usd: float
    remaining_usd: float
    percentage_used: float
    projected_total_usd: float
    on_track: bool
    stages_completed: int
    stages_remaining: int
    avg_cost_per_stage: float


class CostQualityOptimizer:
    """Optimize cost-quality tradeoff for research pipeline."""
    
    def __init__(
        self,
        total_budget_usd: float = 5.0,
        min_quality_threshold: float = 7.0,
    ) -> None:
        """Initialize optimizer.
        
        Args:
            total_budget_usd: Total budget for research run
            min_quality_threshold: Minimum acceptable quality score
        """
        self._budget = total_budget_usd
        self._min_quality = min_quality_threshold
        self._cost_records: list[StageCostRecord] = []
        self._stage_history: dict[str, list[StageCostRecord]] = {}
        self._model_costs = self._load_model_costs()
    
    def _load_model_costs(self) -> dict[str, dict[str, Any]]:
        """Load model cost information."""
        return {
            # Budget tier
            "gpt-4o-mini": {"tier": ModelTier.BUDGET, "input_per_1m": 0.15, "output_per_1m": 0.60},
            "claude-3-haiku": {"tier": ModelTier.BUDGET, "input_per_1m": 0.25, "output_per_1m": 1.25},
            # Mid tier
            "gpt-4o": {"tier": ModelTier.MID, "input_per_1m": 2.50, "output_per_1m": 10.0},
            "claude-3-sonnet": {"tier": ModelTier.MID, "input_per_1m": 3.00, "output_per_1m": 15.0},
            # Premium tier
            "o1": {"tier": ModelTier.PREMIUM, "input_per_1m": 15.0, "output_per_1m": 60.0},
            "claude-3-opus": {"tier": ModelTier.PREMIUM, "input_per_1m": 15.0, "output_per_1m": 75.0},
        }
    
    def track_stage(
        self,
        stage_name: str,
        stage_number: int,
        cost_usd: float,
        quality_score: float,
        model_used: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration_sec: float = 0.0,
        run_id: str = "",
    ) -> None:
        """Track cost and quality for a stage.
        
        Args:
            stage_name: Name of stage
            stage_number: Stage number (1-23)
            cost_usd: Cost in USD
            quality_score: Quality score (1-10)
            model_used: Model name used
            input_tokens: Input tokens consumed
            output_tokens: Output tokens consumed
            duration_sec: Execution duration
            run_id: Run identifier
        """
        # Determine model tier
        model_info = self._model_costs.get(model_used, {})
        model_tier = model_info.get("tier", ModelTier.MID)
        
        record = StageCostRecord(
            stage_name=stage_name,
            stage_number=stage_number,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_used=model_used,
            model_tier=model_tier,
            quality_score=quality_score,
            duration_sec=duration_sec,
            run_id=run_id,
        )
        
        self._cost_records.append(record)
        
        # Add to stage history
        if stage_name not in self._stage_history:
            self._stage_history[stage_name] = []
        self._stage_history[stage_name].append(record)
        
        logger.info(
            f"Tracked {stage_name}: ${cost_usd:.3f}, quality={quality_score:.1f}, "
            f"model={model_used} ({model_tier.value})"
        )
    
    def get_budget_status(self) -> BudgetStatus:
        """Get current budget status."""
        spent = sum(r.cost_usd for r in self._cost_records)
        stages_completed = len(set(r.stage_name for r in self._cost_records))
        
        # Estimate total based on current average
        if stages_completed > 0:
            avg_cost = spent / stages_completed
            projected_total = avg_cost * 23  # 23 stages total
            stages_remaining = 23 - stages_completed
        else:
            avg_cost = 0
            projected_total = 0
            stages_remaining = 23
        
        return BudgetStatus(
            total_budget_usd=self._budget,
            spent_usd=spent,
            remaining_usd=self._budget - spent,
            percentage_used=spent / self._budget if self._budget > 0 else 0,
            projected_total_usd=projected_total,
            on_track=projected_total <= self._budget,
            stages_completed=stages_completed,
            stages_remaining=stages_remaining,
            avg_cost_per_stage=avg_cost,
        )
    
    def analyze_cost_quality_correlations(self) -> list[CostQualityCorrelation]:
        """Analyze cost-quality correlations per stage."""
        correlations = []
        
        for stage_name, records in self._stage_history.items():
            if len(records) < 2:
                # Need multiple data points for correlation
                continue
            
            total_cost = sum(r.cost_usd for r in records)
            avg_quality = sum(r.quality_score for r in records) / len(records)
            
            # Calculate cost per quality point
            cost_per_qp = total_cost / avg_quality if avg_quality > 0 else float('inf')
            
            # Find diminishing returns threshold
            threshold = self._find_diminishing_returns(records)
            
            # Determine optimal model tier
            optimal_tier = self._find_optimal_tier(records)
            
            correlations.append(CostQualityCorrelation(
                stage_name=stage_name,
                total_cost=total_cost,
                avg_quality=avg_quality,
                cost_per_quality_point=cost_per_qp,
                diminishing_returns_threshold=threshold,
                optimal_model_tier=optimal_tier,
                data_points=len(records),
            ))
        
        return correlations
    
    def _find_diminishing_returns(
        self,
        records: list[StageCostRecord],
    ) -> float | None:
        """Find cost threshold where quality returns diminish."""
        if len(records) < 3:
            return None
        
        # Sort by cost
        sorted_records = sorted(records, key=lambda r: r.cost_usd)
        
        # Look for point where quality increase slows
        for i in range(1, len(sorted_records) - 1):
            prev_cost = sorted_records[i-1].cost_usd
            curr_cost = sorted_records[i].cost_usd
            next_cost = sorted_records[i+1].cost_usd
            
            prev_quality = sorted_records[i-1].quality_score
            curr_quality = sorted_records[i].quality_score
            next_quality = sorted_records[i+1].quality_score
            
            # Calculate marginal returns
            if curr_cost - prev_cost > 0:
                return_1 = (curr_quality - prev_quality) / (curr_cost - prev_cost)
            else:
                return_1 = 0
            
            if next_cost - curr_cost > 0:
                return_2 = (next_quality - curr_quality) / (next_cost - curr_cost)
            else:
                return_2 = 0
            
            # If returns drop by >50%, we found diminishing returns
            if return_1 > 0 and return_2 < return_1 * 0.5:
                return curr_cost
        
        return None
    
    def _find_optimal_tier(
        self,
        records: list[StageCostRecord],
    ) -> ModelTier:
        """Find optimal model tier for stage."""
        if not records:
            return ModelTier.MID
        
        # Group by tier
        tier_quality: dict[ModelTier, list[float]] = {
            ModelTier.BUDGET: [],
            ModelTier.MID: [],
            ModelTier.PREMIUM: [],
        }
        
        for record in records:
            tier_quality[record.model_tier].append(record.quality_score)
        
        # Calculate average quality per tier
        tier_avg = {}
        for tier, qualities in tier_quality.items():
            if qualities:
                tier_avg[tier] = sum(qualities) / len(qualities)
        
        # Find cheapest tier that meets quality threshold
        for tier in [ModelTier.BUDGET, ModelTier.MID, ModelTier.PREMIUM]:
            if tier in tier_avg and tier_avg[tier] >= self._min_quality:
                return tier
        
        # If no tier meets threshold, return best available
        if tier_avg.get(ModelTier.PREMIUM, 0) > 0:
            return ModelTier.PREMIUM
        elif tier_avg.get(ModelTier.MID, 0) > 0:
            return ModelTier.MID
        else:
            return ModelTier.BUDGET
    
    def get_optimization_recommendations(self) -> list[OptimizationRecommendation]:
        """Get cost optimization recommendations."""
        recommendations = []
        
        correlations = self.analyze_cost_quality_correlations()
        
        for corr in correlations:
            # Get most recent record for this stage
            recent_records = self._stage_history.get(corr.stage_name, [])
            if not recent_records:
                continue
            
            current_record = recent_records[-1]
            current_tier = current_record.model_tier
            
            # If using higher tier than optimal, recommend downgrade
            if self._tier_rank(current_tier) > self._tier_rank(corr.optimal_model_tier):
                # Calculate expected savings
                savings = self._estimate_savings(
                    current_tier,
                    corr.optimal_model_tier,
                    current_record.cost_usd,
                )
                
                # Estimate quality impact (usually minimal)
                quality_impact = self._estimate_quality_impact(
                    current_tier,
                    corr.optimal_model_tier,
                    corr.avg_quality,
                )
                
                recommendations.append(OptimizationRecommendation(
                    stage_name=corr.stage_name,
                    current_model_tier=current_tier,
                    recommended_model_tier=corr.optimal_model_tier,
                    expected_cost_savings_usd=savings,
                    expected_quality_impact=quality_impact,
                    confidence=0.8 if corr.data_points >= 3 else 0.5,
                    reasoning=f"Analysis of {corr.data_points} runs shows {corr.optimal_model_tier.value} tier achieves {corr.avg_quality:.1f}/10 quality at lower cost",
                ))
        
        return recommendations
    
    def _tier_rank(self, tier: ModelTier) -> int:
        """Get numeric rank for tier comparison."""
        ranks = {
            ModelTier.BUDGET: 0,
            ModelTier.MID: 1,
            ModelTier.PREMIUM: 2,
        }
        return ranks.get(tier, 1)
    
    def _estimate_savings(
        self,
        current_tier: ModelTier,
        recommended_tier: ModelTier,
        current_cost: float,
    ) -> float:
        """Estimate cost savings from tier change."""
        # Approximate cost ratios between tiers
        tier_multipliers = {
            ModelTier.BUDGET: 0.1,  # Budget is ~10% of premium cost
            ModelTier.MID: 0.3,     # Mid is ~30% of premium cost
            ModelTier.PREMIUM: 1.0,
        }
        
        current_mult = tier_multipliers.get(current_tier, 0.3)
        recommended_mult = tier_multipliers.get(recommended_tier, 0.3)
        
        if current_mult > 0:
            savings_ratio = 1 - (recommended_mult / current_mult)
            return current_cost * max(0, savings_ratio)
        
        return 0.0
    
    def _estimate_quality_impact(
        self,
        current_tier: ModelTier,
        recommended_tier: ModelTier,
        avg_quality: float,
    ) -> float:
        """Estimate quality impact from tier change."""
        # Downgrading typically has minimal impact if above threshold
        tier_diff = self._tier_rank(current_tier) - self._tier_rank(recommended_tier)
        
        if tier_diff > 0:
            # Downgrade: small quality decrease expected
            return -0.2 * tier_diff  # -0.2 per tier
        elif tier_diff < 0:
            # Upgrade: small quality increase expected
            return 0.1 * abs(tier_diff)
        
        return 0.0
    
    def suggest_model_for_stage(
        self,
        stage_name: str,
        importance: str = "normal",  # low, normal, high, critical
    ) -> dict[str, Any]:
        """Suggest best model for a stage based on historical data.
        
        Args:
            stage_name: Name of stage
            importance: Stage importance level
            
        Returns:
            Model recommendation with reasoning
        """
        # Get historical data for this stage
        records = self._stage_history.get(stage_name, [])
        
        if records:
            # Use data-driven recommendation
            correlation = next(
                (c for c in self.analyze_cost_quality_correlations()
                 if c.stage_name == stage_name),
                None,
            )
            
            if correlation:
                optimal_tier = correlation.optimal_model_tier
            else:
                optimal_tier = ModelTier.MID
        else:
            # No history: use importance-based default
            tier_defaults = {
                "low": ModelTier.BUDGET,
                "normal": ModelTier.MID,
                "high": ModelTier.MID,
                "critical": ModelTier.PREMIUM,
            }
            optimal_tier = tier_defaults.get(importance, ModelTier.MID)
        
        # Select specific model
        model_recommendations = {
            ModelTier.BUDGET: "gpt-4o-mini",
            ModelTier.MID: "gpt-4o",
            ModelTier.PREMIUM: "o1",
        }
        
        recommended_model = model_recommendations.get(optimal_tier, "gpt-4o")
        
        return {
            "stage": stage_name,
            "recommended_model": recommended_model,
            "model_tier": optimal_tier.value,
            "importance": importance,
            "data_driven": len(records) > 0,
            "historical_avg_quality": sum(r.quality_score for r in records) / len(records) if records else None,
            "historical_avg_cost": sum(r.cost_usd for r in records) / len(records) if records else None,
        }
    
    def get_cost_breakdown(self) -> dict[str, Any]:
        """Get cost breakdown by stage and tier."""
        breakdown = {
            "total_cost": sum(r.cost_usd for r in self._cost_records),
            "by_stage": {},
            "by_tier": {
                "budget": 0.0,
                "mid": 0.0,
                "premium": 0.0,
            },
            "by_model": {},
        }
        
        for record in self._cost_records:
            # By stage
            if record.stage_name not in breakdown["by_stage"]:
                breakdown["by_stage"][record.stage_name] = 0.0
            breakdown["by_stage"][record.stage_name] += record.cost_usd
            
            # By tier
            tier_key = record.model_tier.value
            breakdown["by_tier"][tier_key] += record.cost_usd
            
            # By model
            if record.model_used not in breakdown["by_model"]:
                breakdown["by_model"][record.model_used] = 0.0
            breakdown["by_model"][record.model_used] += record.cost_usd
        
        return breakdown
    
    def export_report(self) -> dict[str, Any]:
        """Export comprehensive cost-quality report."""
        return {
            "budget_status": self.get_budget_status().__dict__,
            "cost_breakdown": self.get_cost_breakdown(),
            "correlations": [
                {
                    "stage": c.stage_name,
                    "total_cost": c.total_cost,
                    "avg_quality": c.avg_quality,
                    "cost_per_quality_point": c.cost_per_quality_point,
                    "optimal_tier": c.optimal_model_tier.value,
                    "data_points": c.data_points,
                }
                for c in self.analyze_cost_quality_correlations()
            ],
            "recommendations": [
                {
                    "stage": r.stage_name,
                    "current_tier": r.current_model_tier.value,
                    "recommended_tier": r.recommended_model_tier.value,
                    "savings_usd": r.expected_cost_savings_usd,
                    "quality_impact": r.expected_quality_impact,
                    "confidence": r.confidence,
                    "reasoning": r.reasoning,
                }
                for r in self.get_optimization_recommendations()
            ],
        }


# Global optimizer instance
_optimizer: CostQualityOptimizer | None = None


def get_optimizer(budget_usd: float = 5.0) -> CostQualityOptimizer:
    """Get global optimizer instance."""
    global _optimizer
    if _optimizer is None:
        _optimizer = CostQualityOptimizer(total_budget_usd=budget_usd)
    return _optimizer
