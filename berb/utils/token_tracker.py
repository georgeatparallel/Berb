"""Token consumption tracking and analytics system.

This module provides comprehensive tracking of token usage across Berb,
recording input/output tokens, execution times, and providing aggregation APIs
for daily/weekly/monthly statistics.

Architecture: Repository + Unit of Work pattern
Paradigm: Functional + Event-Driven

Example:
    >>> tracker = TokenTracker(project_path=Path.cwd())
    >>> usage = tracker.track(
    ...     command="llm_call",
    ...     input_text=prompt,
    ...     output_text=response,
    ...     execution_time_ms=150,
    ... )
    >>> summary = tracker.get_summary()
    >>> print(f"Saved {summary['total_saved_tokens']:,} tokens")

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TokenUsage:
    """Individual token usage record.
    
    Attributes:
        command: Command name (e.g., "llm_call", "literature_search")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        execution_time_ms: Execution time in milliseconds
        project_path: Project path for scoping
        timestamp: UTC timestamp when recorded
    """
    command: str
    input_tokens: int
    output_tokens: int
    execution_time_ms: int
    project_path: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def total_tokens(self) -> int:
        """Total tokens consumed."""
        return self.input_tokens + self.output_tokens
    
    @property
    def savings_pct(self) -> float:
        """Estimated savings percentage (vs baseline)."""
        if self.input_tokens == 0:
            return 0.0
        return ((self.input_tokens - self.output_tokens) / self.input_tokens) * 100


@dataclass(frozen=True)
class TokenSummary:
    """Aggregated token usage statistics.
    
    Attributes:
        total_commands: Total number of commands recorded
        total_input_tokens: Total input tokens
        total_output_tokens: Total output tokens
        total_saved_tokens: Total tokens saved
        avg_savings_pct: Average savings percentage
        total_execution_time_ms: Total execution time
        avg_execution_time_ms: Average execution time per command
    """
    total_commands: int
    total_input_tokens: int
    total_output_tokens: int
    total_saved_tokens: int
    avg_savings_pct: float
    total_execution_time_ms: int
    avg_execution_time_ms: int


@dataclass(frozen=True)
class DailyTokenStats:
    """Daily token usage statistics.
    
    Attributes:
        date: Date string (YYYY-MM-DD)
        commands: Number of commands
        input_tokens: Total input tokens
        output_tokens: Total output tokens
        saved_tokens: Total tokens saved
        savings_pct: Average savings percentage
    """
    date: str
    commands: int
    input_tokens: int
    output_tokens: int
    saved_tokens: int
    savings_pct: float


# ─────────────────────────────────────────────────────────────────────────────
# Token Tracker
# ─────────────────────────────────────────────────────────────────────────────

class TokenTracker:
    """Token consumption tracker with SQLite persistence.
    
    Provides comprehensive tracking of token usage with:
    - Project-scoped tracking
    - Daily/weekly/monthly analytics
    - Cost estimation
    - Budget alerts
    
    Database Location:
        - Windows: %APPDATA%\\berb\\tracking.db
        - macOS: ~/Library/Application Support/berb/tracking.db
        - Linux: ~/.local/share/berb/tracking.db
    
    Example:
        >>> tracker = TokenTracker(project_path=Path.cwd())
        >>> usage = tracker.track(
        ...     command="llm_call",
        ...     input_text=prompt,
        ...     output_text=response,
        ...     execution_time_ms=150,
        ... )
        >>> summary = tracker.get_summary()
    """
    
    def __init__(
        self,
        project_path: Optional[Path] = None,
        db_path: Optional[Path] = None,
    ):
        """Initialize token tracker.
        
        Args:
            project_path: Project path for scoping (default: current directory)
            db_path: Custom database path (default: platform-specific location)
        """
        self.project_path = project_path or Path.cwd()
        self.db_path = db_path or self._get_default_db_path()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()
    
    @staticmethod
    def _get_default_db_path() -> Path:
        """Get platform-specific default database path."""
        import sys
        
        if sys.platform == "win32":
            base = Path.home() / "AppData" / "Roaming"
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:  # Linux
            base = Path.home() / ".local" / "share"
        
        db_dir = base / "berb"
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir / "tracking.db"
    
    @property
    def connection(self) -> sqlite3.Connection:
        """Get database connection (lazy initialization)."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self.connection
        conn.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                project_path TEXT NOT NULL,
                command TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                saved_tokens INTEGER NOT NULL,
                savings_pct REAL NOT NULL,
                execution_time_ms INTEGER NOT NULL
            )
        """)
        
        # Create indexes for common queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON token_usage(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_project 
            ON token_usage(project_path)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_command 
            ON token_usage(command)
        """)
        
        conn.commit()
        logger.debug(f"Token tracker initialized at {self.db_path}")
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def __enter__(self) -> TokenTracker:
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
    
    # ─────────────────────────────────────────────────────────────────────────
    # Token Estimation
    # ─────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count from text.
        
        Rule of thumb: 1 token ≈ 4 characters (English text)
        For code: 1 token ≈ 3-4 characters
        
        Args:
            text: Text to estimate tokens for
        
        Returns:
            Estimated token count
        """
        if not text:
            return 0
        
        # Simple estimation: characters / 4
        # For more accuracy, use tiktoken library
        return max(1, len(text) // 4)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Tracking
    # ─────────────────────────────────────────────────────────────────────────
    
    def track(
        self,
        command: str,
        input_text: str = "",
        output_text: str = "",
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        execution_time_ms: int = 0,
    ) -> TokenUsage:
        """Track token usage for a command execution.
        
        Args:
            command: Command name (e.g., "llm_call", "literature_search")
            input_text: Input text (used if input_tokens not provided)
            output_text: Output text (used if output_tokens not provided)
            input_tokens: Input token count (estimated from text if not provided)
            output_tokens: Output token count (estimated from text if not provided)
            execution_time_ms: Execution time in milliseconds
        
        Returns:
            TokenUsage record
        
        Example:
            >>> usage = tracker.track(
            ...     command="llm_call",
            ...     input_text=prompt,
            ...     output_text=response,
            ...     execution_time_ms=150,
            ... )
        """
        # Estimate tokens if not provided
        if input_tokens is None:
            input_tokens = self.estimate_tokens(input_text)
        if output_tokens is None:
            output_tokens = self.estimate_tokens(output_text)
        
        saved_tokens = input_tokens - output_tokens
        savings_pct = (saved_tokens / input_tokens * 100) if input_tokens > 0 else 0.0
        
        usage = TokenUsage(
            command=command,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            execution_time_ms=execution_time_ms,
            project_path=str(self.project_path),
        )
        
        # Persist to database
        self.connection.execute(
            """
            INSERT INTO token_usage
            (timestamp, project_path, command, input_tokens, output_tokens,
             saved_tokens, savings_pct, execution_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usage.timestamp.isoformat(),
                usage.project_path,
                usage.command,
                usage.input_tokens,
                usage.output_tokens,
                saved_tokens,
                savings_pct,
                execution_time_ms,
            ),
        )
        self.connection.commit()
        
        logger.debug(
            f"Tracked {command}: {input_tokens}→{output_tokens} tokens "
            f"(saved {saved_tokens}, {savings_pct:.1f}%)"
        )
        
        return usage
    
    # ─────────────────────────────────────────────────────────────────────────
    # Analytics
    # ─────────────────────────────────────────────────────────────────────────
    
    def get_summary(
        self,
        days: Optional[int] = None,
    ) -> TokenSummary:
        """Get token usage summary.
        
        Args:
            days: Number of days to include (None for all time)
        
        Returns:
            TokenSummary with aggregated statistics
        
        Example:
            >>> summary = tracker.get_summary(days=7)
            >>> print(f"Saved {summary.total_saved_tokens:,} tokens")
        """
        # days=0 means "last 0 days" → always empty.  Short-circuit before querying
        # because SQLite's datetime('now', '-0 days') = now, so a >= comparison
        # would still match records inserted in the same moment.
        if days == 0:
            return TokenSummary(
                total_commands=0,
                total_input_tokens=0,
                total_output_tokens=0,
                total_saved_tokens=0,
                avg_savings_pct=0.0,
                total_execution_time_ms=0,
                avg_execution_time_ms=0,
            )

        conn = self.connection

        # Build query with optional date filter
        where_clause = ""
        params: list[Any] = [str(self.project_path)]

        # Use `is not None` not truthiness: days=0 is handled above; negative or
        # positive integers are valid filters.
        if days is not None:
            where_clause = "AND timestamp >= datetime('now', ?)"
            params.append(f"-{days} days")

        query = f"""
        SELECT
            COUNT(*) as total_commands,
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            SUM(saved_tokens) as total_saved,
            AVG(savings_pct) as avg_savings_pct,
            SUM(execution_time_ms) as total_time_ms
        FROM token_usage
        WHERE project_path = ? {where_clause}
        """
        
        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        
        if row is None or row["total_commands"] == 0:
            return TokenSummary(
                total_commands=0,
                total_input_tokens=0,
                total_output_tokens=0,
                total_saved_tokens=0,
                avg_savings_pct=0.0,
                total_execution_time_ms=0,
                avg_execution_time_ms=0,
            )
        
        total_commands = row["total_commands"] or 0
        total_time_ms = row["total_time_ms"] or 0
        
        return TokenSummary(
            total_commands=total_commands,
            total_input_tokens=row["total_input"] or 0,
            total_output_tokens=row["total_output"] or 0,
            total_saved_tokens=row["total_saved"] or 0,
            avg_savings_pct=row["avg_savings_pct"] or 0.0,
            total_execution_time_ms=total_time_ms,
            avg_execution_time_ms=total_time_ms // total_commands if total_commands > 0 else 0,
        )
    
    def get_daily_stats(
        self,
        days: int = 7,
    ) -> list[DailyTokenStats]:
        """Get daily token usage statistics.
        
        Args:
            days: Number of days to include
        
        Returns:
            List of DailyTokenStats, ordered by date descending
        
        Example:
            >>> stats = tracker.get_daily_stats(days=7)
            >>> for day in stats:
            ...     print(f"{day.date}: {day.saved_tokens:,} tokens saved")
        """
        conn = self.connection
        
        query = f"""
        SELECT
            DATE(timestamp) as date,
            COUNT(*) as commands,
            SUM(input_tokens) as input_tokens,
            SUM(output_tokens) as output_tokens,
            SUM(saved_tokens) as saved_tokens,
            AVG(savings_pct) as savings_pct
        FROM token_usage
        WHERE project_path = ?
          AND timestamp >= datetime('now', ?)
        GROUP BY DATE(timestamp)
        ORDER BY date DESC
        """
        
        cursor = conn.execute(query, [str(self.project_path), f"-{days} days"])
        
        return [
            DailyTokenStats(
                date=row["date"],
                commands=row["commands"],
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                saved_tokens=row["saved_tokens"],
                savings_pct=row["savings_pct"],
            )
            for row in cursor.fetchall()
        ]
    
    def get_commands_by_type(
        self,
        days: Optional[int] = None,
    ) -> dict[str, TokenSummary]:
        """Get token usage summary grouped by command type.
        
        Args:
            days: Number of days to include (None for all time)
        
        Returns:
            Dictionary mapping command names to TokenSummary
        """
        conn = self.connection
        
        # Build query with optional date filter
        where_clause = ""
        params: list[Any] = [str(self.project_path)]
        
        # Use `is not None` not truthiness: days=0 is a valid filter (last 0 days →
        # empty result) but `if days:` treats 0 as False, bypassing the WHERE clause
        # and returning all rows instead.
        if days is not None:
            where_clause = "AND timestamp >= datetime('now', ?)"
            params.append(f"-{days} days")
        
        query = f"""
        SELECT
            command,
            COUNT(*) as total_commands,
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            SUM(saved_tokens) as total_saved,
            AVG(savings_pct) as avg_savings_pct,
            SUM(execution_time_ms) as total_time_ms
        FROM token_usage
        WHERE project_path = ? {where_clause}
        GROUP BY command
        ORDER BY total_saved DESC
        """
        
        cursor = conn.execute(query, params)
        
        result = {}
        for row in cursor.fetchall():
            total_commands = row["total_commands"]
            total_time_ms = row["total_time_ms"] or 0
            
            result[row["command"]] = TokenSummary(
                total_commands=total_commands,
                total_input_tokens=row["total_input"] or 0,
                total_output_tokens=row["total_output"] or 0,
                total_saved_tokens=row["total_saved"] or 0,
                avg_savings_pct=row["avg_savings_pct"] or 0.0,
                total_execution_time_ms=total_time_ms,
                avg_execution_time_ms=total_time_ms // total_commands if total_commands > 0 else 0,
            )
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Cost Estimation
    # ─────────────────────────────────────────────────────────────────────────
    
    def estimate_cost(
        self,
        input_rate: float = 0.000005,
        output_rate: float = 0.000015,
        days: Optional[int] = None,
    ) -> dict[str, float]:
        """Estimate API costs based on token usage.
        
        Args:
            input_rate: Cost per input token (USD)
            output_rate: Cost per output token (USD)
            days: Number of days to include (None for all time)
        
        Returns:
            Dictionary with cost breakdown
        
        Example:
            >>> costs = tracker.estimate_cost(
            ...     input_rate=0.000005,  # GPT-4 input
            ...     output_rate=0.000015,  # GPT-4 output
            ... )
            >>> print(f"Total cost: ${costs['total']:.4f}")
        """
        summary = self.get_summary(days=days)
        
        input_cost = summary.total_input_tokens * input_rate / 1_000_000
        output_cost = summary.total_output_tokens * output_rate / 1_000_000
        total_cost = input_cost + output_cost
        
        return {
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost,
            "avg_cost_per_command": total_cost / summary.total_commands if summary.total_commands > 0 else 0,
        }
