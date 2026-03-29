"""Persistent Memory for HyperAgent.

Stores improvements, performance history, and knowledge across runs.
Enables transfer of improvements between domains.

Based on Facebook AI Research paper (arXiv:2603.19461v1).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from berb.hyperagent.base import Improvement, TaskResult

logger = logging.getLogger(__name__)


@dataclass
class PerformanceRecord:
    """Record of task performance."""
    
    variant_id: str
    task_id: str
    success: bool
    metrics: dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "variant_id": self.variant_id,
            "task_id": self.task_id,
            "success": self.success,
            "metrics": self.metrics,
            "timestamp": self.timestamp.isoformat(),
        }


class PersistentMemory:
    """Persistent memory for Hyperagent.
    
    Stores:
    1. Improvements (code modifications with metadata)
    2. Performance history (task results across variants)
    3. Cross-domain knowledge (transferable improvements)
    
    Attributes:
        storage_path: Path to persistent storage
        improvements: List of all improvements
        performance_history: List of performance records
    """
    
    def __init__(self, storage_path: Path):
        """
        Initialize Persistent Memory.
        
        Args:
            storage_path: Path to storage directory
        """
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # In-memory caches
        self.improvements: list[Improvement] = []
        self.performance_history: list[PerformanceRecord] = []
        
        # Load existing data
        self._load_from_disk()
        
        logger.info("Persistent Memory initialized (storage: %s)", storage_path)
    
    def _load_from_disk(self) -> None:
        """Load data from disk."""
        # Load improvements
        improvements_path = self.storage_path / "improvements.jsonl"
        if improvements_path.exists():
            with open(improvements_path, "r", encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line)
                    improvement = self._dict_to_improvement(data)
                    self.improvements.append(improvement)
            logger.info("Loaded %d improvements from disk", len(self.improvements))
        
        # Load performance history
        performance_path = self.storage_path / "performance.jsonl"
        if performance_path.exists():
            with open(performance_path, "r", encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line)
                    record = self._dict_to_performance_record(data)
                    self.performance_history.append(record)
            logger.info("Loaded %d performance records from disk", len(self.performance_history))
    
    def _save_to_disk(self) -> None:
        """Save data to disk."""
        # Save improvements
        improvements_path = self.storage_path / "improvements.jsonl"
        with open(improvements_path, "w", encoding="utf-8") as f:
            for improvement in self.improvements:
                f.write(json.dumps(improvement.to_dict()) + "\n")
        
        # Save performance history
        performance_path = self.storage_path / "performance.jsonl"
        with open(performance_path, "w", encoding="utf-8") as f:
            for record in self.performance_history:
                f.write(json.dumps(record.to_dict()) + "\n")
        
        logger.debug("Saved memory to disk")
    
    def _dict_to_improvement(self, data: dict[str, Any]) -> Improvement:
        """Convert dictionary to Improvement."""
        return Improvement(
            improvement_id=data["improvement_id"],
            description=data["description"],
            code_diff=data["code_diff"],
            affected_component=data["affected_component"],
            expected_benefit=data["expected_benefit"],
            actual_benefit=data.get("actual_benefit"),
            confidence=data.get("confidence", 0.0),
            transferable=data.get("transferable", True),
            source_domain=data.get("source_domain", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )
    
    def _dict_to_performance_record(self, data: dict[str, Any]) -> PerformanceRecord:
        """Convert dictionary to PerformanceRecord."""
        return PerformanceRecord(
            variant_id=data["variant_id"],
            task_id=data["task_id"],
            success=data["success"],
            metrics=data.get("metrics", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )
    
    async def store_improvement(self, improvement: Improvement) -> None:
        """
        Store an improvement.
        
        Args:
            improvement: Improvement to store
        """
        self.improvements.append(improvement)
        self._save_to_disk()
        
        logger.info(
            "Stored improvement %s: %s",
            improvement.improvement_id,
            improvement.description,
        )
    
    async def store_performance(
        self,
        variant_id: str,
        task_id: str,
        metrics: dict[str, float],
        success: bool,
    ) -> None:
        """
        Store task performance.
        
        Args:
            variant_id: Agent variant ID
            task_id: Task identifier
            metrics: Performance metrics
            success: Whether task succeeded
        """
        record = PerformanceRecord(
            variant_id=variant_id,
            task_id=task_id,
            success=success,
            metrics=metrics,
        )
        self.performance_history.append(record)
        
        # Periodically save to disk
        if len(self.performance_history) % 10 == 0:
            self._save_to_disk()
    
    def get_all_improvements(self) -> list[Improvement]:
        """Get all stored improvements."""
        return self.improvements
    
    def get_improvements_for_domain(self, domain: str) -> list[Improvement]:
        """
        Get improvements relevant to a specific domain.
        
        Args:
            domain: Domain name
        
        Returns:
            List of relevant improvements
        """
        # Filter by source domain and transferable flag
        return [
            imp for imp in self.improvements
            if imp.source_domain == domain or imp.transferable
        ]
    
    def transfer_improvements(
        self,
        source_domain: str,
        target_domain: str,
    ) -> list[Improvement]:
        """
        Transfer improvements from source to target domain.
        
        Args:
            source_domain: Source domain
            target_domain: Target domain
        
        Returns:
            List of transferred improvements
        """
        transferred = []
        for improvement in self.improvements:
            if improvement.transferable:
                # Create copy with new source domain
                transferred_improvement = Improvement(
                    improvement_id=f"{improvement.improvement_id}_transfer_{target_domain}",
                    description=f"[Transferred from {source_domain}] {improvement.description}",
                    code_diff=improvement.code_diff,
                    affected_component=improvement.affected_component,
                    expected_benefit=improvement.expected_benefit,
                    actual_benefit=improvement.actual_benefit,
                    confidence=improvement.confidence * 0.9,  # Slight confidence reduction for transfer
                    transferable=improvement.transferable,
                    source_domain=target_domain,
                    timestamp=datetime.now(timezone.utc),
                )
                transferred.append(transferred_improvement)
        
        logger.info(
            "Transferred %d improvements from %s to %s",
            len(transferred),
            source_domain,
            target_domain,
        )
        
        return transferred
    
    def get_performance_by_variant(self, variant_id: str) -> list[PerformanceRecord]:
        """
        Get performance records for a specific variant.
        
        Args:
            variant_id: Variant identifier
        
        Returns:
            List of performance records
        """
        return [
            record for record in self.performance_history
            if record.variant_id == variant_id
        ]
    
    def calculate_variant_performance(self, variant_id: str) -> float:
        """
        Calculate average performance for a variant.
        
        Args:
            variant_id: Variant identifier
        
        Returns:
            Average performance score (0-1)
        """
        records = self.get_performance_by_variant(variant_id)
        if not records:
            return 0.0
        
        success_count = sum(1 for r in records if r.success)
        return success_count / len(records)
    
    def get_best_variant(self) -> str | None:
        """
        Get the best performing variant.
        
        Returns:
            Variant ID of best performer, or None if no data
        """
        if not self.performance_history:
            return None
        
        # Group by variant
        variants = {}
        for record in self.performance_history:
            if record.variant_id not in variants:
                variants[record.variant_id] = []
            variants[record.variant_id].append(record)
        
        # Calculate success rate for each variant
        best_variant = None
        best_rate = 0.0
        
        for variant_id, records in variants.items():
            success_rate = sum(1 for r in records if r.success) / len(records)
            if success_rate > best_rate:
                best_rate = success_rate
                best_variant = variant_id
        
        return best_variant
    
    def get_improvement_history(self) -> list[dict[str, Any]]:
        """
        Get history of all improvements with outcomes.
        
        Returns:
            List of improvement history entries
        """
        history = []
        for improvement in self.improvements:
            entry = improvement.to_dict()
            
            # Find performance before/after improvement
            # (simplified - in production would track more precisely)
            entry["outcome"] = "pending"
            
            history.append(entry)
        
        return history
    
    def clear(self) -> None:
        """Clear all memory."""
        self.improvements.clear()
        self.performance_history.clear()
        
        # Clear disk storage
        improvements_path = self.storage_path / "improvements.jsonl"
        performance_path = self.storage_path / "performance.jsonl"
        
        if improvements_path.exists():
            improvements_path.unlink()
        if performance_path.exists():
            performance_path.unlink()
        
        logger.info("Persistent Memory cleared")
    
    async def close(self) -> None:
        """Clean up and save to disk."""
        self._save_to_disk()
        logger.info("Persistent Memory closed")
    
    def __len__(self) -> int:
        """Get total number of stored items."""
        return len(self.improvements) + len(self.performance_history)
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"PersistentMemory(improvements={len(self.improvements)}, "
            f"performance_records={len(self.performance_history)})"
        )
