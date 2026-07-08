"""Extended cost tracking for all 11 providers.

This module provides comprehensive cost tracking for reasoning method
executions across all 11 LLM providers, with support for:
- Per-model pricing (100+ models)
- Provider diversity tracking
- Cost budget enforcement
- Quality-adjusted cost metrics

Usage:
    from berb.metrics.reasoning_cost_tracker import ExtendedReasoningCostTracker

    tracker = ExtendedReasoningCostTracker()

    # Track a reasoning execution
    record = tracker.track(
        method="multi_perspective",
        phase="constructive",
        model="xiaomi/mimo-v2-pro",
        input_tokens=1000,
        output_tokens=500,
        duration_ms=1500,
        run_id="run-123",
    )

    # Get summary
    summary = tracker.get_summary(days=7)
    print(f"Total cost: ${summary['total_cost_usd']:.4f}")

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Provider(StrEnum):
    """LLM providers supported by extended cost tracking."""

    MINIMAX = "minimax"
    QWEN = "qwen"
    GLM = "glm"  # Z.ai
    MIMO = "mimo"  # Xiaomi
    KIMI = "kimi"  # Moonshot
    PERPLEXITY = "perplexity"
    XAI = "xai"  # Grok
    DEEPSEEK = "deepseek"
    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    UNKNOWN = "unknown"


@dataclass
class ReasoningCostRecord:
    """Single cost record for reasoning execution.

    Attributes:
        method: Reasoning method name (e.g., "multi_perspective")
        phase: Phase within method (e.g., "constructive")
        model: Full model identifier (e.g., "xiaomi/mimo-v2-pro")
        provider: Provider enum
        input_tokens: Input token count
        output_tokens: Output token count
        cost_usd: Calculated cost in USD
        duration_ms: Execution duration in milliseconds
        timestamp: UTC timestamp when recorded
        run_id: Optional run identifier for grouping
        quality_score: Optional post-execution quality rating (0-10)
    """

    method: str
    phase: str
    model: str
    provider: Provider
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    run_id: str | None = None
    quality_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "method": self.method,
            "phase": self.phase,
            "model": self.model,
            "provider": self.provider.value,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
            "run_id": self.run_id,
            "quality_score": self.quality_score,
        }


class ExtendedReasoningCostTracker:
    """Track and analyze reasoning method costs across all 11 providers.

    Features:
    - Complete pricing for 100+ models
    - Provider diversity tracking (target: no provider >40%)
    - Cost budget enforcement
    - Quality-adjusted cost metrics
    - SQLite persistence
    - Daily/weekly/monthly analytics

    Database Location:
        - Windows: %APPDATA%\berb\\cost_tracking.db
        - macOS: ~/Library/Application Support/berb/cost_tracking.db
        - Linux: ~/.local/share/berb/cost_tracking.db
    """

    # Complete pricing for all recommended models (per 1M tokens)
    # Source: OpenRouter API /models endpoint (June 2026)
    MODEL_PRICING: dict[str, tuple[float, float]] = {
        # =====================================================================
        # ANTHROPIC
        # =====================================================================
        "anthropic/claude-sonnet-4.6": (3.00, 15.00),
        "anthropic/claude-sonnet-4.5": (3.00, 15.00),
        "anthropic/claude-opus-4.6": (5.00, 25.00),
        "anthropic/claude-opus-4.7": (5.00, 25.00),
        "anthropic/claude-opus-4.7-fast": (30.00, 150.00),
        "anthropic/claude-opus-4.8": (5.00, 25.00),
        "anthropic/claude-opus-4.8-fast": (10.00, 50.00),
        "anthropic/claude-opus-4.5": (5.00, 25.00),
        "anthropic/claude-opus-4.1": (15.00, 75.00),
        "anthropic/claude-haiku-4.5": (1.00, 5.00),
        "anthropic/claude-fable-5": (0.01, 0.05),
        # =====================================================================
        # OPENAI
        # =====================================================================
        "openai/gpt-5.5": (5.00, 30.00),
        "openai/gpt-5.5-pro": (30.00, 180.00),
        "openai/gpt-5.4": (2.50, 15.00),
        "openai/gpt-5.4-pro": (30.00, 180.00),
        "openai/gpt-5.4-mini": (0.75, 4.50),
        "openai/gpt-5.4-nano": (0.20, 1.25),
        "openai/gpt-5.2": (1.75, 14.00),
        "openai/gpt-5.2-codex": (1.75, 14.00),
        "openai/gpt-5.1": (1.25, 10.00),
        "openai/gpt-5": (1.25, 10.00),
        "openai/gpt-5-mini": (0.25, 2.00),
        "openai/gpt-5-nano": (0.05, 0.40),
        "openai/gpt-4o": (2.50, 10.00),
        "openai/gpt-4o-mini": (0.15, 0.60),
        "openai/gpt-4.1": (2.00, 8.00),
        "openai/gpt-4.1-mini": (0.40, 1.60),
        "openai/gpt-4.1-nano": (0.10, 0.40),
        "openai/o3-pro": (20.00, 80.00),
        "openai/o3": (2.00, 8.00),
        "openai/o3-mini": (1.10, 4.40),
        "openai/o4-mini": (1.10, 4.40),
        "openai/o1": (15.00, 60.00),
        # =====================================================================
        # GOOGLE
        # =====================================================================
        "google/gemini-2.5-pro": (1.25, 10.00),
        "google/gemini-2.5-flash": (0.30, 2.50),
        "google/gemini-2.5-flash-lite": (0.10, 0.40),
        "google/gemini-3-flash-preview": (0.50, 3.00),
        "google/gemini-3.5-flash": (1.50, 9.00),
        "google/gemini-3.1-flash-lite": (0.25, 1.50),
        "google/gemma-4-26b-a4b-it": (0.06, 0.33),
        "google/gemma-4-31b-it": (0.12, 0.35),
        # =====================================================================
        # DEEPSEEK
        # =====================================================================
        "deepseek/deepseek-v3.2": (0.23, 0.34),
        "deepseek/deepseek-chat-v3.1": (0.21, 0.79),
        "deepseek/deepseek-v4-pro": (0.44, 0.87),
        "deepseek/deepseek-v4-flash": (0.09, 0.18),
        "deepseek/deepseek-r1": (0.70, 2.50),
        # =====================================================================
        # QWEN
        # =====================================================================
        "qwen/qwen3-max": (0.78, 3.90),
        "qwen/qwen3-max-thinking": (0.78, 3.90),
        "qwen/qwen3.5-plus-20260420": (0.30, 1.80),
        "qwen/qwen3.5-flash-02-23": (0.065, 0.26),
        "qwen/qwen3.5-9b": (0.10, 0.15),
        "qwen/qwen3.5-27b": (0.20, 1.56),
        "qwen/qwen3.5-35b-a3b": (0.14, 1.00),
        "qwen/qwen3.5-122b-a10b": (0.26, 2.08),
        "qwen/qwen3.5-397b-a17b": (0.39, 2.45),
        "qwen/qwen3.6-plus": (0.33, 1.95),
        "qwen/qwen3.6-flash": (0.19, 1.13),
        "qwen/qwen3.7-plus": (0.32, 1.28),
        "qwen/qwen3.7-max": (1.25, 3.75),
        "qwen/qwen3-coder": (0.22, 1.80),
        "qwen/qwen3-coder-plus": (0.65, 3.25),
        "qwen/qwen3-coder-flash": (0.20, 0.98),
        # =====================================================================
        # XAI (Grok)
        # =====================================================================
        "x-ai/grok-4.5": (2.00, 4.00),
        "x-ai/grok-4.3": (1.25, 2.50),
        # =====================================================================
        # XIAOMI (MIMO)
        # =====================================================================
        "xiaomi/mimo-v2.5": (0.14, 0.28),
        "xiaomi/mimo-v2.5-pro": (0.44, 0.87),
        # =====================================================================
        # MOONSHOTAI (KIMI)
        # =====================================================================
        "moonshotai/kimi-k2": (0.57, 2.30),
        "moonshotai/kimi-k2.5": (0.38, 2.03),
        "moonshotai/kimi-k2.6": (0.66, 3.41),
        "moonshotai/kimi-k2.7-code": (0.61, 3.07),
        # =====================================================================
        # MINIMAX
        # =====================================================================
        "minimax/minimax-m2.5": (0.15, 0.90),
        "minimax/minimax-m2.7": (0.25, 1.00),
        "minimax/minimax-m3": (0.30, 1.20),
        "minimax/minimax-m1": (0.20, 1.10),
        # =====================================================================
        # Z-AI (GLM)
        # =====================================================================
        "z-ai/glm-4.5": (0.60, 2.20),
        "z-ai/glm-4.5-air": (0.13, 0.85),
        "z-ai/glm-4.7": (0.40, 1.75),
        "z-ai/glm-4.7-flash": (0.06, 0.40),
        "z-ai/glm-5": (0.60, 1.92),
        "z-ai/glm-5.1": (0.98, 3.08),
        "z-ai/glm-5.2": (0.98, 3.08),
        # =====================================================================
        # PERPLEXITY (Sonar; per-search cost added separately)
        # =====================================================================
        "perplexity/sonar": (1.00, 1.00),
        "perplexity/sonar-pro": (3.00, 15.00),
        "perplexity/sonar-pro-search": (3.00, 15.00),  # +$0.018 per search
        "perplexity/sonar-reasoning-pro": (2.00, 8.00),
        "perplexity/sonar-deep-research": (2.00, 8.00),
        # =====================================================================
        # META (Llama)
        # =====================================================================
        "meta-llama/llama-4-maverick": (0.15, 0.60),
        "meta-llama/llama-4-scout": (0.10, 0.30),
        # =====================================================================
        # AMAZON (Nova)
        # =====================================================================
        "amazon/nova-2-lite-v1": (0.30, 2.50),
        "amazon/nova-pro-v1": (0.80, 3.20),
        "amazon/nova-premier-v1": (2.50, 12.50),
        # =====================================================================
        # MISTRAL
        # =====================================================================
        "mistralai/mistral-large": (2.00, 6.00),
        "mistralai/mistral-medium-3-5": (1.50, 7.50),
        "mistralai/mistral-small-3.2-24b-instruct": (0.08, 0.20),
        # =====================================================================
        # OTHER NOTABLE PROVIDERS
        # =====================================================================
        "nvidia/nemotron-3-super-120b-a12b": (0.09, 0.45),
        "microsoft/phi-4-mini-instruct": (0.08, 0.35),
        "cohere/command-a": (2.50, 10.00),
        "bytedance-seed/seed-2.0-mini": (0.10, 0.40),
    }

    # Perplexity search cost (per search)
    PERPLEXITY_SEARCH_COST = 0.018  # $18 per 1000 searches

    # Schema version for migrations
    _SCHEMA_VERSION: int = 1

    def __init__(
        self,
        project_path: Path | None = None,
        db_path: Path | None = None,
        cost_budget_usd: float | None = 6.00,
    ):
        """Initialize cost tracker.

        Args:
            project_path: Project path for scoping (default: current directory)
            db_path: Custom database path (default: platform-specific location)
            cost_budget_usd: Cost budget per reasoning run (default: $6.00)
        """
        self.project_path = project_path or Path.cwd()
        self.db_path = db_path or self._get_default_db_path()
        self.cost_budget_usd = cost_budget_usd
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @staticmethod
    def _get_default_db_path() -> Path:
        """Get platform-specific default database path."""
        import sys

        if sys.platform == "win32":
            base = Path.home() / "AppData" / "Roaming"
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path.home() / ".local" / "share"

        db_dir = base / "berb"
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir / "cost_tracking.db"

    @property
    def connection(self) -> sqlite3.Connection:
        """Get database connection (lazy initialization)."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        """Initialize database schema with version tracking."""
        conn = self.connection

        # Schema version table
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        row = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
        current_version = int(row[0]) if row else 0
        if current_version < self._SCHEMA_VERSION:
            self._migrate(conn, current_version, self._SCHEMA_VERSION)
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
                (str(self._SCHEMA_VERSION),),
            )

        # Cost tracking table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reasoning_costs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                project_path TEXT NOT NULL,
                method TEXT NOT NULL,
                phase TEXT NOT NULL,
                model TEXT NOT NULL,
                provider TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cost_usd REAL NOT NULL,
                duration_ms INTEGER NOT NULL,
                run_id TEXT,
                quality_score REAL
            )
        """)

        # Create indexes for common queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON reasoning_costs(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_method
            ON reasoning_costs(method)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_provider
            ON reasoning_costs(provider)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_run_id
            ON reasoning_costs(run_id)
        """)

        conn.commit()
        logger.debug(f"Cost tracker initialized at {self.db_path}")

    @staticmethod
    def _migrate(conn: sqlite3.Connection, from_version: int, to_version: int) -> None:
        """Apply incremental schema migrations."""
        if from_version < 1:
            logger.debug("Schema migration: 0 → 1 (initial schema)")
        logger.debug("Schema migrated from v%d to v%d", from_version, to_version)

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> ExtendedReasoningCostTracker:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    # =====================================================================
    # Provider Extraction
    # =====================================================================

    @classmethod
    def _extract_provider(cls, model: str) -> Provider:
        """Extract provider from model string."""
        model_lower = model.lower()

        provider_map = {
            "minimax": Provider.MINIMAX,
            "qwen": Provider.QWEN,
            "z-ai": Provider.GLM,
            "glm": Provider.GLM,
            "xiaomi": Provider.MIMO,
            "mimo": Provider.MIMO,
            "moonshotai": Provider.KIMI,
            "kimi": Provider.KIMI,
            "perplexity": Provider.PERPLEXITY,
            "x-ai": Provider.XAI,
            "grok": Provider.XAI,
            "deepseek": Provider.DEEPSEEK,
            "google": Provider.GOOGLE,
            "gemini": Provider.GOOGLE,
            "anthropic": Provider.ANTHROPIC,
            "claude": Provider.ANTHROPIC,
            "openai": Provider.OPENAI,
            "gpt": Provider.OPENAI,
        }

        for prefix, provider in provider_map.items():
            if model_lower.startswith(prefix):
                return provider

        return Provider.UNKNOWN

    # =====================================================================
    # Cost Calculation
    # =====================================================================

    def _calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        search_count: int = 0,
    ) -> float:
        """Calculate cost for model execution.

        Args:
            model: Model identifier
            input_tokens: Input token count
            output_tokens: Output token count
            search_count: Number of searches (for Perplexity)

        Returns:
            Cost in USD
        """
        input_price, output_price = self.MODEL_PRICING.get(model, (0, 0))

        # Calculate token cost
        cost_usd = (input_tokens * input_price + output_tokens * output_price) / 1_000_000

        # Add search cost for Perplexity
        if "perplexity" in model.lower() and search_count > 0:
            cost_usd += search_count * self.PERPLEXITY_SEARCH_COST

        return cost_usd

    # =====================================================================
    # Tracking
    # =====================================================================

    def track(
        self,
        method: str,
        phase: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
        run_id: str | None = None,
        quality_score: float | None = None,
        search_count: int = 0,
    ) -> ReasoningCostRecord:
        """Track a reasoning execution.

        Args:
            method: Reasoning method name
            phase: Phase within method
            model: Model identifier
            input_tokens: Input token count
            output_tokens: Output token count
            duration_ms: Execution duration
            run_id: Optional run identifier
            quality_score: Optional quality rating (0-10)
            search_count: Number of searches (for Perplexity)

        Returns:
            ReasoningCostRecord
        """
        provider = self._extract_provider(model)
        cost_usd = self._calculate_cost(model, input_tokens, output_tokens, search_count)

        record = ReasoningCostRecord(
            method=method,
            phase=phase,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            timestamp=datetime.now(UTC),
            run_id=run_id,
            quality_score=quality_score,
        )

        # Persist to database
        self._persist(record)

        # Check budget
        if self.cost_budget_usd:
            run_cost = self._get_run_cost(run_id) if run_id else 0
            if run_cost > self.cost_budget_usd:
                logger.warning(
                    f"Cost budget exceeded: ${run_cost:.4f} > ${self.cost_budget_usd:.2f} "
                    f"for run {run_id}"
                )

        return record

    def _persist(self, record: ReasoningCostRecord) -> None:
        """Persist record to database."""
        conn = self.connection
        conn.execute(
            """
            INSERT INTO reasoning_costs
            (timestamp, project_path, method, phase, model, provider,
             input_tokens, output_tokens, cost_usd, duration_ms, run_id, quality_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.timestamp.isoformat(),
                str(self.project_path),
                record.method,
                record.phase,
                record.model,
                record.provider.value,
                record.input_tokens,
                record.output_tokens,
                record.cost_usd,
                record.duration_ms,
                record.run_id,
                record.quality_score,
            ),
        )
        conn.commit()

    # =====================================================================
    # Analytics
    # =====================================================================

    def get_summary(self, days: int | None = 7) -> dict[str, Any]:
        """Get cost summary for last N days.

        Args:
            days: Number of days (None for all time)

        Returns:
            Summary dictionary with totals and breakdowns
        """
        conn = self.connection

        # Build query
        where_clause = ""
        params: list[Any] = [str(self.project_path)]

        if days is not None:
            where_clause = "AND timestamp >= datetime('now', ?)"
            params.append(f"-{days} days")

        # Get totals
        query = f"""
        SELECT
            COUNT(*) as total_executions,
            SUM(cost_usd) as total_cost_usd,
            SUM(input_tokens) as total_input_tokens,
            SUM(output_tokens) as total_output_tokens,
            AVG(cost_usd) as avg_cost_per_execution,
            AVG(duration_ms) as avg_duration_ms
        FROM reasoning_costs
        WHERE project_path = ? {where_clause}
        """

        cursor = conn.execute(query, params)
        row = cursor.fetchone()

        # Get cost by method
        method_query = f"""
        SELECT method, SUM(cost_usd) as cost
        FROM reasoning_costs
        WHERE project_path = ? {where_clause}
        GROUP BY method
        ORDER BY cost DESC
        """
        method_cursor = conn.execute(method_query, params)
        cost_by_method = {row["method"]: row["cost"] for row in method_cursor}

        # Get cost by provider
        provider_query = f"""
        SELECT provider, SUM(cost_usd) as cost
        FROM reasoning_costs
        WHERE project_path = ? {where_clause}
        GROUP BY provider
        ORDER BY cost DESC
        """
        provider_cursor = conn.execute(provider_query, params)
        cost_by_provider = {row["provider"]: row["cost"] for row in provider_cursor}

        # Calculate provider distribution
        total_cost = row["total_cost_usd"] or 0
        provider_distribution = {}
        if total_cost > 0:
            for provider, cost in cost_by_provider.items():
                provider_distribution[provider] = cost / total_cost

        return {
            "total_executions": row["total_executions"] or 0,
            "total_cost_usd": row["total_cost_usd"] or 0,
            "total_input_tokens": row["total_input_tokens"] or 0,
            "total_output_tokens": row["total_output_tokens"] or 0,
            "avg_cost_per_execution": row["avg_cost_per_execution"] or 0,
            "avg_duration_ms": row["avg_duration_ms"] or 0,
            "cost_by_method": cost_by_method,
            "cost_by_provider": cost_by_provider,
            "provider_distribution": provider_distribution,
            "max_provider_pct": max(provider_distribution.values()) if provider_distribution else 0,
            "budget_status": "over"
            if (row["total_cost_usd"] or 0) > (self.cost_budget_usd or float("inf"))
            else "under",
        }

    def _get_run_cost(self, run_id: str) -> float:
        """Get total cost for a specific run."""
        conn = self.connection
        cursor = conn.execute(
            "SELECT SUM(cost_usd) as total FROM reasoning_costs WHERE run_id = ?",
            (run_id,),
        )
        row = cursor.fetchone()
        return row["total"] or 0

    def get_provider_distribution(self) -> dict[str, float]:
        """Get cost distribution by provider (last 7 days).

        Returns:
            Dictionary mapping provider to percentage (0-1)
        """
        summary = self.get_summary(days=7)
        return summary["provider_distribution"]

    def get_alerts(self) -> list[str]:
        """Get cost-related alerts.

        Returns:
            List of alert messages
        """
        alerts = []
        summary = self.get_summary(days=1)

        # Check total cost
        if summary["total_cost_usd"] > 10:
            alerts.append(f"🔴 HIGH_COST: ${summary['total_cost_usd']:.2f} today (target: <$6)")
        elif summary["total_cost_usd"] > 8:
            alerts.append(f"🟡 WARNING: ${summary['total_cost_usd']:.2f} today")

        # Check provider concentration
        if summary["max_provider_pct"] > 0.60:
            max_provider = max(summary["provider_distribution"].items(), key=lambda x: x[1])
            alerts.append(
                f"🔴 HIGH_CONCENTRATION: {max_provider[0]} at {max_provider[1] * 100:.1f}% (max: 40%)"
            )
        elif summary["max_provider_pct"] > 0.40:
            max_provider = max(summary["provider_distribution"].items(), key=lambda x: x[1])
            alerts.append(f"🟡 WARNING: {max_provider[0]} at {max_provider[1] * 100:.1f}%")

        # Check budget
        if summary["budget_status"] == "over":
            alerts.append(
                f"🔴 BUDGET_EXCEEDED: ${summary['total_cost_usd']:.2f} > ${self.cost_budget_usd:.2f}"
            )

        return alerts

    def export_report(self, output_path: Path, days: int = 7) -> None:
        """Export cost report to JSON file.

        Args:
            output_path: Output file path
            days: Number of days to include
        """
        summary = self.get_summary(days=days)
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "period_days": days,
            "budget_usd": self.cost_budget_usd,
            "summary": summary,
            "alerts": self.get_alerts(),
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2))
        logger.info(f"Cost report exported to {output_path}")


# Global tracker instance
_tracker: ExtendedReasoningCostTracker | None = None

# Lock for thread-safe singleton creation (BUG-001 fix)
_tracker_lock = threading.Lock()


def get_cost_tracker(
    project_path: Path | None = None,
    cost_budget_usd: float | None = 6.00,
) -> ExtendedReasoningCostTracker:
    """Get global cost tracker instance.

    Args:
        project_path: Project path for scoping
        cost_budget_usd: Cost budget per run

    Returns:
        ExtendedReasoningCostTracker instance
    """
    global _tracker
    with _tracker_lock:
        if _tracker is None or _tracker.project_path != (project_path or Path.cwd()):
            _tracker = ExtendedReasoningCostTracker(
                project_path=project_path,
                cost_budget_usd=cost_budget_usd,
            )
        return _tracker
