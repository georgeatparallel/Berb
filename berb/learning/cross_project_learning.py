"""Cross-Project Learning for Berb.

This module implements cross-project transfer learning, extracting patterns
from historical research runs to improve future performance. This creates a
competitive moat as the system provably improves over time.

Features:
- Model affinity per stage (which model works best where)
- Failure predictors by domain
- Complexity vs repair cycles correlation
- Literature source quality by domain
- Automatic insight injection into routing

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.learning.cross_project_learning import CrossProjectLearning

    cpl = CrossProjectLearning(data_dir=".berb/runs")
    await cpl.load_runs()
    insights = await cpl.extract_patterns()
    
    # Use insights for model routing
    best_model = insights.get_model_affinity(Stage.HYPOTHESIS_GEN, domain="biology")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RunTrace:
    """Trace data from a single research run."""

    run_id: str
    topic: str
    domain: str
    start_time: datetime
    end_time: datetime
    status: str  # success, failed, pivoted
    total_cost: float
    total_tokens: int
    stages: dict[str, StageTrace] = field(default_factory=dict)
    quality_score: float = 0.0
    literature_count: int = 0
    repair_cycles: int = 0


@dataclass
class StageTrace:
    """Trace data from a single stage execution."""

    stage_number: int
    stage_name: str
    status: str  # success, failed, repaired
    model_used: str
    input_tokens: int
    output_tokens: int
    cost: float
    duration_sec: float
    repair_count: int = 0
    error_message: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelAffinity:
    """Model performance affinity for a stage/domain."""

    stage: str
    domain: str
    model: str
    avg_quality: float
    avg_cost: float
    success_rate: float
    avg_repair_cycles: float
    usage_count: int


@dataclass
class FailurePredictor:
    """Failure pattern predictor for a domain."""

    domain: str
    stage: str
    failure_rate: float
    common_errors: list[str]
    risk_factors: list[str]
    mitigation_strategies: list[str]


@dataclass
class LiteratureSourceQuality:
    """Quality metrics for a literature source by domain."""

    source: str
    domain: str
    avg_relevance: float
    avg_citations: float
    usage_count: int
    quality_score: float


class CrossProjectLearning:
    """Cross-project transfer learning system."""

    def __init__(self, data_dir: str | Path = ".berb/runs"):
        """Initialize cross-project learning.

        Args:
            data_dir: Directory containing historical run traces
        """
        self._data_dir = Path(data_dir)
        self._runs: list[RunTrace] = []
        self._model_affinities: dict[str, list[ModelAffinity]] = {}
        self._failure_predictors: dict[str, FailurePredictor] = {}
        self._literature_quality: dict[str, LiteratureSourceQuality] = {}
        self._complexity_correlations: dict[str, float] = {}

    async def load_runs(self, limit: int = 100) -> int:
        """Load historical run traces.

        Args:
            limit: Maximum number of runs to load

        Returns:
            Number of runs loaded
        """
        if not self._data_dir.exists():
            logger.warning(f"Run data directory {self._data_dir} does not exist")
            return 0

        runs_loaded = 0
        for run_file in sorted(self._data_dir.glob("run_*.json")):
            if runs_loaded >= limit:
                break

            try:
                with open(run_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                run = self._parse_run_trace(data)
                if run:
                    self._runs.append(run)
                    runs_loaded += 1

            except Exception as e:
                logger.warning(f"Failed to load run trace {run_file}: {e}")

        logger.info(f"Loaded {runs_loaded} historical run traces")
        return runs_loaded

    def _parse_run_trace(self, data: dict[str, Any]) -> RunTrace | None:
        """Parse run trace from dictionary.

        Args:
            data: Run trace dictionary

        Returns:
            Parsed RunTrace or None if invalid
        """
        try:
            stages = {}
            for stage_name, stage_data in data.get("stages", {}).items():
                stage = StageTrace(
                    stage_number=stage_data.get("stage_number", 0),
                    stage_name=stage_name,
                    status=stage_data.get("status", "unknown"),
                    model_used=stage_data.get("model_used", "unknown"),
                    input_tokens=stage_data.get("input_tokens", 0),
                    output_tokens=stage_data.get("output_tokens", 0),
                    cost=stage_data.get("cost", 0.0),
                    duration_sec=stage_data.get("duration_sec", 0.0),
                    repair_count=stage_data.get("repair_count", 0),
                    error_message=stage_data.get("error_message"),
                    metrics=stage_data.get("metrics", {}),
                )
                stages[stage_name] = stage

            return RunTrace(
                run_id=data.get("run_id", "unknown"),
                topic=data.get("topic", ""),
                domain=data.get("domain", "unknown"),
                start_time=datetime.fromisoformat(data["start_time"]) if data.get("start_time") else datetime.now(),
                end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else datetime.now(),
                status=data.get("status", "unknown"),
                total_cost=data.get("total_cost", 0.0),
                total_tokens=data.get("total_tokens", 0),
                stages=stages,
                quality_score=data.get("quality_score", 0.0),
                literature_count=data.get("literature_count", 0),
                repair_cycles=data.get("repair_cycles", 0),
            )

        except Exception as e:
            logger.error(f"Failed to parse run trace: {e}")
            return None

    async def extract_patterns(self) -> dict[str, Any]:
        """Extract patterns from historical runs.

        Returns:
            Dictionary of extracted patterns
        """
        if not self._runs:
            logger.warning("No runs loaded, cannot extract patterns")
            return {}

        logger.info(f"Extracting patterns from {len(self._runs)} runs...")

        # Extract model affinities
        await self._extract_model_affinities()

        # Extract failure predictors
        await self._extract_failure_predictors()

        # Extract literature source quality
        await self._extract_literature_quality()

        # Extract complexity correlations
        await self._extract_complexity_correlations()

        return {
            "model_affinities": len(self._model_affinities),
            "failure_predictors": len(self._failure_predictors),
            "literature_quality": len(self._literature_quality),
            "complexity_correlations": self._complexity_correlations,
        }

    async def _extract_model_affinities(self) -> None:
        """Extract model affinity patterns."""
        # Group by stage + domain + model
        affinity_data: dict[str, list[StageTrace]] = {}

        for run in self._runs:
            domain = run.domain
            for stage_name, stage in run.stages.items():
                key = f"{stage_name}|{domain}|{stage.model_used}"
                if key not in affinity_data:
                    affinity_data[key] = []
                affinity_data[key].append(stage)

        # Calculate affinities
        self._model_affinities = {}
        for key, stages in affinity_data.items():
            if len(stages) < 3:  # Need minimum samples
                continue

            stage_name, domain, model = key.split("|")
            avg_quality = sum(s.metrics.get("quality", 0.0) for s in stages) / len(stages)
            avg_cost = sum(s.cost for s in stages) / len(stages)
            success_rate = sum(1 for s in stages if s.status == "success") / len(stages)
            avg_repair_cycles = sum(s.repair_count for s in stages) / len(stages)

            affinity = ModelAffinity(
                stage=stage_name,
                domain=domain,
                model=model,
                avg_quality=avg_quality,
                avg_cost=avg_cost,
                success_rate=success_rate,
                avg_repair_cycles=avg_repair_cycles,
                usage_count=len(stages),
            )

            stage_key = f"{stage_name}|{domain}"
            if stage_key not in self._model_affinities:
                self._model_affinities[stage_key] = []
            self._model_affinities[stage_key].append(affinity)

        logger.info(f"Extracted {len(self._model_affinities)} model affinity patterns")

    async def _extract_failure_predictors(self) -> None:
        """Extract failure prediction patterns."""
        # Group by domain + stage
        failure_data: dict[str, list[StageTrace]] = {}

        for run in self._runs:
            domain = run.domain
            for stage_name, stage in run.stages.items():
                key = f"{domain}|{stage_name}"
                if key not in failure_data:
                    failure_data[key] = []
                failure_data[key].append(stage)

        # Calculate failure predictors
        self._failure_predictors = {}
        for key, stages in failure_data.items():
            if len(stages) < 5:  # Need minimum samples
                continue

            domain, stage_name = key.split("|")
            failures = [s for s in stages if s.status in ("failed", "repaired")]
            failure_rate = len(failures) / len(stages)

            if failure_rate < 0.1:  # Skip low-failure patterns
                continue

            # Extract common errors
            error_counts: dict[str, int] = {}
            for s in failures:
                if s.error_message:
                    error_counts[s.error_message[:100]] = error_counts.get(s.error_message[:100], 0) + 1

            common_errors = sorted(error_counts.keys(), key=lambda x: error_counts[x], reverse=True)[:5]

            # Generate risk factors and mitigations
            risk_factors = self._generate_risk_factors(domain, stage_name, failure_rate, common_errors)
            mitigation_strategies = self._generate_mitigations(domain, stage_name, common_errors)

            predictor = FailurePredictor(
                domain=domain,
                stage=stage_name,
                failure_rate=failure_rate,
                common_errors=common_errors,
                risk_factors=risk_factors,
                mitigation_strategies=mitigation_strategies,
            )

            self._failure_predictors[key] = predictor

        logger.info(f"Extracted {len(self._failure_predictors)} failure predictor patterns")

    def _generate_risk_factors(
        self, domain: str, stage: str, failure_rate: float, errors: list[str]
    ) -> list[str]:
        """Generate risk factors for a domain/stage."""
        risks = []

        if failure_rate > 0.3:
            risks.append(f"High failure rate ({failure_rate:.1%}) in {stage}")

        if "timeout" in str(errors).lower():
            risks.append("Timeout errors common - consider increasing time budget")

        if "parse" in str(errors).lower():
            risks.append("JSON parsing failures - consider structured outputs")

        if "rate_limit" in str(errors).lower():
            risks.append("Rate limiting - consider using fallback models")

        return risks

    def _generate_mitigations(self, domain: str, stage: str, errors: list[str]) -> list[str]:
        """Generate mitigation strategies."""
        mitigations = []

        if "timeout" in str(errors).lower():
            mitigations.append("Increase time_budget_sec by 50%")
            mitigations.append("Use faster model for this stage")

        if "parse" in str(errors).lower():
            mitigations.append("Enable structured output enforcement")
            mitigations.append("Add JSON repair logic")

        if "rate_limit" in str(errors).lower():
            mitigations.append("Enable model cascading with fallbacks")
            mitigations.append("Add retry with exponential backoff")

        return mitigations

    async def _extract_literature_quality(self) -> None:
        """Extract literature source quality patterns."""
        # This would require literature source tracking in run traces
        # For now, placeholder implementation
        logger.info("Literature quality extraction not yet implemented")

    async def _extract_complexity_correlations(self) -> None:
        """Extract complexity vs repair cycles correlation."""
        if len(self._runs) < 10:
            return

        # Calculate correlation between input tokens (complexity proxy) and repair cycles
        complexities = []
        repairs = []

        for run in self._runs:
            complexities.append(run.total_tokens)
            repairs.append(run.repair_cycles)

        # Simple Pearson correlation
        n = len(complexities)
        mean_x = sum(complexities) / n
        mean_y = sum(repairs) / n

        numerator = sum((complexities[i] - mean_x) * (repairs[i] - mean_y) for i in range(n))
        denom_x = sum((x - mean_x) ** 2 for x in complexities) ** 0.5
        denom_y = sum((y - mean_y) ** 2 for y in repairs) ** 0.5

        if denom_x > 0 and denom_y > 0:
            correlation = numerator / (denom_x * denom_y)
            self._complexity_correlations["tokens_vs_repairs"] = correlation
            logger.info(f"Complexity vs repairs correlation: {correlation:.3f}")

    def get_model_affinity(
        self, stage: str, domain: str, min_samples: int = 3
    ) -> ModelAffinity | None:
        """Get best model affinity for a stage/domain.

        Args:
            stage: Stage name
            domain: Research domain
            min_samples: Minimum usage count

        Returns:
            Best ModelAffinity or None
        """
        key = f"{stage}|{domain}"
        affinities = self._model_affinities.get(key, [])

        # Filter by minimum samples
        valid = [a for a in affinities if a.usage_count >= min_samples]

        if not valid:
            return None

        # Sort by quality score (weighted by success rate)
        valid.sort(key=lambda a: a.avg_quality * a.success_rate, reverse=True)

        return valid[0]

    def get_failure_predictor(self, domain: str, stage: str) -> FailurePredictor | None:
        """Get failure predictor for a domain/stage.

        Args:
            domain: Research domain
            stage: Stage name

        Returns:
            FailurePredictor or None
        """
        key = f"{domain}|{stage}"
        return self._failure_predictors.get(key)

    def get_insights_for_stage(self, stage: str, domain: str) -> dict[str, Any]:
        """Get all insights for a stage/domain combination.

        Args:
            stage: Stage name
            domain: Research domain

        Returns:
            Dictionary of insights
        """
        insights = {
            "stage": stage,
            "domain": domain,
            "recommended_model": None,
            "failure_risk": None,
            "mitigations": [],
        }

        # Get model recommendation
        affinity = self.get_model_affinity(stage, domain)
        if affinity:
            insights["recommended_model"] = affinity.model
            insights["expected_quality"] = affinity.avg_quality
            insights["expected_cost"] = affinity.avg_cost

        # Get failure prediction
        predictor = self.get_failure_predictor(domain, stage)
        if predictor:
            insights["failure_risk"] = predictor.failure_rate
            insights["risk_factors"] = predictor.risk_factors
            insights["mitigations"] = predictor.mitigation_strategies

        return insights

    def export_insights(self, output_path: str | Path) -> None:
        """Export insights to JSON file.

        Args:
            output_path: Output file path
        """
        output_path = Path(output_path)

        data = {
            "exported_at": datetime.now().isoformat(),
            "total_runs": len(self._runs),
            "model_affinities": {},
            "failure_predictors": {},
            "complexity_correlations": self._complexity_correlations,
        }

        # Export model affinities
        for key, affinities in self._model_affinities.items():
            data["model_affinities"][key] = [
                {
                    "model": a.model,
                    "avg_quality": a.avg_quality,
                    "avg_cost": a.avg_cost,
                    "success_rate": a.success_rate,
                    "usage_count": a.usage_count,
                }
                for a in affinities
            ]

        # Export failure predictors
        for key, predictor in self._failure_predictors.items():
            data["failure_predictors"][key] = {
                "failure_rate": predictor.failure_rate,
                "common_errors": predictor.common_errors,
                "risk_factors": predictor.risk_factors,
                "mitigation_strategies": predictor.mitigation_strategies,
            }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Exported insights to {output_path}")
