"""Automated evaluation dataset builder from production traces.

This module automatically builds evaluation datasets from production failures,
enabling regression testing and continuous quality improvement.

Architecture: Event-driven failure capture with JSONL storage
Paradigm: Observer pattern for failure tracking

Usage:
    from berb.llm.eval_dataset import EvalDatasetBuilder
    
    builder = EvalDatasetBuilder(dataset_path=".berb/eval_dataset.jsonl")
    
    # Record a failure
    await builder.record_failure(
        prompt="Generate hypotheses for...",
        response=low_quality_response,
        errors=["Hallucinated citation", "Missing methodology"],
        eval_scores={"novelty": 0.3, "rigor": 0.4},
    )
    
    # Load dataset for regression testing
    test_cases = await builder.load_test_cases(stage="HYPOTHESIS_GEN")
"""

# Author: Georgios-Chrysovalantis Chatzivantsidis

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FailureRecord:
    """Record of a production failure."""
    
    prompt: str
    response: str
    errors: list[str]
    eval_scores: dict[str, float]
    stage: str
    model: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    run_id: str | None = None
    topic: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class EvalDatasetBuilder:
    """Build evaluation dataset from production failures."""
    
    def __init__(
        self,
        dataset_path: str | Path = ".berb/eval_dataset.jsonl",
        auto_create: bool = True,
    ):
        """Initialize dataset builder.
        
        Args:
            dataset_path: Path to JSONL dataset file
            auto_create: Automatically create directory if needed
        """
        self._dataset_path = Path(dataset_path)
        
        if auto_create:
            self._dataset_path.parent.mkdir(parents=True, exist_ok=True)
    
    async def record_failure(
        self,
        prompt: str,
        response: str,
        errors: list[str],
        eval_scores: dict[str, float],
        stage: str,
        model: str,
        run_id: str | None = None,
        topic: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a production failure.
        
        Args:
            prompt: Original prompt that caused failure
            response: Model response
            errors: List of error descriptions
            eval_scores: Evaluation scores by dimension
            stage: Pipeline stage name
            model: Model that produced the failure
            run_id: Optional run identifier
            topic: Optional research topic
            metadata: Optional additional metadata
        """
        record = FailureRecord(
            prompt=prompt,
            response=response,
            errors=errors,
            eval_scores=eval_scores,
            stage=stage,
            model=model,
            run_id=run_id,
            topic=topic,
            metadata=metadata or {},
        )
        
        # Append to JSONL file
        with self._dataset_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record)) + "\n")
        
        logger.info(
            f"Recorded failure: stage={stage}, model={model}, "
            f"errors={len(errors)}, dataset_size={self._count_records()}"
        )
    
    async def load_test_cases(
        self,
        stage: str | None = None,
        model: str | None = None,
        limit: int | None = None,
    ) -> list[FailureRecord]:
        """Load test cases from dataset.
        
        Args:
            stage: Filter by stage (optional)
            model: Filter by model (optional)
            limit: Maximum number of records (optional)
            
        Returns:
            List of FailureRecord objects
        """
        if not self._dataset_path.exists():
            logger.warning(f"Dataset not found: {self._dataset_path}")
            return []
        
        records = []
        
        with self._dataset_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    record = FailureRecord(**data)
                    
                    # Apply filters
                    if stage and record.stage != stage:
                        continue
                    if model and record.model != model:
                        continue
                    
                    records.append(record)
                    
                    if limit and len(records) >= limit:
                        break
                        
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse dataset line: {e}")
        
        logger.info(f"Loaded {len(records)} test cases from dataset")
        return records
    
    async def get_statistics(self) -> dict[str, Any]:
        """Get dataset statistics.
        
        Returns:
            Dictionary with statistics
        """
        if not self._dataset_path.exists():
            return {
                "total_records": 0,
                "by_stage": {},
                "by_model": {},
                "avg_errors_per_record": 0.0,
            }
        
        records = await self.load_test_cases()
        
        # Count by stage
        by_stage: dict[str, int] = {}
        for record in records:
            by_stage[record.stage] = by_stage.get(record.stage, 0) + 1
        
        # Count by model
        by_model: dict[str, int] = {}
        for record in records:
            by_model[record.model] = by_model.get(record.model, 0) + 1
        
        # Average errors per record
        total_errors = sum(len(r.errors) for r in records)
        avg_errors = total_errors / len(records) if records else 0.0
        
        return {
            "total_records": len(records),
            "by_stage": by_stage,
            "by_model": by_model,
            "avg_errors_per_record": avg_errors,
            "dataset_path": str(self._dataset_path),
        }
    
    def _count_records(self) -> int:
        """Count records in dataset file."""
        if not self._dataset_path.exists():
            return 0
        
        count = 0
        with self._dataset_path.open("r", encoding="utf-8") as f:
            for _ in f:
                count += 1
        return count
    
    async def export_for_regression(
        self,
        output_path: str | Path,
        stage: str | None = None,
    ) -> int:
        """Export dataset for regression testing.
        
        Args:
            output_path: Path to export file
            stage: Filter by stage (optional)
            
        Returns:
            Number of records exported
        """
        records = await self.load_test_cases(stage=stage)
        
        export_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "total_cases": len(records),
            "test_cases": [asdict(r) for r in records],
        }
        
        with Path(output_path).open("w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2)
        
        logger.info(f"Exported {len(records)} test cases to {output_path}")
        return len(records)


# ─────────────────────────────────────────────────────────────────────────────
# Integration with Pipeline Runner
# ─────────────────────────────────────────────────────────────────────────────


class PipelineEvalIntegration:
    """Integrate evaluation dataset with pipeline execution."""
    
    def __init__(self, dataset_builder: EvalDatasetBuilder):
        self._builder = dataset_builder
        self._failure_thresholds = {
            "HYPOTHESIS_GEN": {"novelty": 0.5, "rigor": 0.6},
            "PEER_REVIEW": {"clarity": 0.7, "experiments": 0.6},
        }
    
    async def record_stage_failure(
        self,
        stage: str,
        prompt: str,
        response: str,
        errors: list[str],
        eval_scores: dict[str, float],
        model: str,
        run_id: str,
        topic: str,
    ) -> None:
        """Record a stage failure for later regression testing."""
        await self._builder.record_failure(
            prompt=prompt,
            response=response,
            errors=errors,
            eval_scores=eval_scores,
            stage=stage,
            model=model,
            run_id=run_id,
            topic=topic,
        )
    
    def should_flag_for_review(self, stage: str, eval_scores: dict[str, float]) -> bool:
        """Check if scores warrant human review.
        
        Args:
            stage: Pipeline stage
            eval_scores: Evaluation scores
            
        Returns:
            True if should flag for review
        """
        thresholds = self._failure_thresholds.get(stage, {})
        
        for dimension, threshold in thresholds.items():
            if dimension in eval_scores and eval_scores[dimension] < threshold:
                return True
        
        return False
    
    async def get_regression_tests(self, stage: str) -> list[FailureRecord]:
        """Get regression test cases for a stage.
        
        Args:
            stage: Pipeline stage
            
        Returns:
            List of failure records for regression testing
        """
        return await self._builder.load_test_cases(stage=stage, limit=50)
