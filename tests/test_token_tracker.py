"""Unit tests for Token Tracker.

Paradigm: Functional testing with pure functions
Pattern: Repository pattern testing
"""

from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime, timezone

from berb.utils.token_tracker import (
    TokenTracker,
    TokenUsage,
    TokenSummary,
    DailyTokenStats,
)


@pytest.fixture
def tracker(tmp_path: Path) -> TokenTracker:
    """Create tracker with temporary database."""
    db_path = tmp_path / "test_tracking.db"
    tracker = TokenTracker(
        project_path=tmp_path / "test_project",
        db_path=db_path,
    )
    yield tracker
    tracker.close()


class TestTokenEstimation:
    """Test token estimation functionality."""

    def test_estimate_tokens_empty(self):
        """Test empty text returns 0 tokens."""
        assert TokenTracker.estimate_tokens("") == 0
        assert TokenTracker.estimate_tokens(None) == 0

    def test_estimate_tokens_short(self):
        """Test short text estimation."""
        assert TokenTracker.estimate_tokens("Hello") >= 1

    def test_estimate_tokens_long(self):
        """Test long text estimation."""
        text = "Hello " * 100  # 600 characters
        tokens = TokenTracker.estimate_tokens(text)
        assert tokens >= 100  # At least 100 tokens (600/4 = 150)

    def test_estimate_tokens_code(self):
        """Test code-like text estimation."""
        code = """
def hello():
    print("Hello, World!")
    return True
"""
        tokens = TokenTracker.estimate_tokens(code)
        assert tokens >= 1


class TestTokenTracking:
    """Test token tracking functionality."""

    def test_track_basic(self, tracker: TokenTracker):
        """Test basic token tracking."""
        usage = tracker.track(
            command="llm_call",
            input_text="What is 2+2?",
            output_text="2+2=4",
            execution_time_ms=150,
        )

        assert usage.command == "llm_call"
        assert usage.input_tokens > 0
        assert usage.output_tokens > 0
        assert usage.execution_time_ms == 150
        assert usage.project_path == str(tracker.project_path)

    def test_track_with_explicit_tokens(self, tracker: TokenTracker):
        """Test tracking with explicit token counts."""
        usage = tracker.track(
            command="llm_call",
            input_tokens=100,
            output_tokens=50,
            execution_time_ms=200,
        )

        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150
        assert usage.savings_pct == 50.0  # (100-50)/100 * 100

    def test_track_savings_calculation(self, tracker: TokenTracker):
        """Test token savings calculation."""
        usage = tracker.track(
            command="test",
            input_tokens=1000,
            output_tokens=200,
        )

        assert usage.savings_pct == 80.0  # (1000-200)/1000 * 100

    def test_track_persistence(self, tracker: TokenTracker):
        """Test that tracking persists to database."""
        tracker.track(
            command="test",
            input_tokens=100,
            output_tokens=50,
        )

        # Create new tracker with same DB
        new_tracker = TokenTracker(
            project_path=tracker.project_path,
            db_path=tracker.db_path,
        )
        summary = new_tracker.get_summary()

        assert summary.total_commands == 1
        assert summary.total_input_tokens == 100
        new_tracker.close()


class TestTokenSummary:
    """Test token summary functionality."""

    def test_get_summary_empty(self, tracker: TokenTracker):
        """Test summary with no data."""
        summary = tracker.get_summary()

        assert summary.total_commands == 0
        assert summary.total_input_tokens == 0
        assert summary.total_output_tokens == 0
        assert summary.total_saved_tokens == 0
        assert summary.avg_savings_pct == 0.0

    def test_get_summary_with_data(self, tracker: TokenTracker):
        """Test summary with tracked data."""
        # Track multiple commands
        for i in range(5):
            tracker.track(
                command=f"command_{i}",
                input_tokens=100,
                output_tokens=50,
                execution_time_ms=100,
            )

        summary = tracker.get_summary()

        assert summary.total_commands == 5
        assert summary.total_input_tokens == 500
        assert summary.total_output_tokens == 250
        assert summary.total_saved_tokens == 250
        assert summary.avg_savings_pct == 50.0
        assert summary.total_execution_time_ms == 500
        assert summary.avg_execution_time_ms == 100

    def test_get_summary_with_days_filter(self, tracker: TokenTracker):
        """Test summary with date filter."""
        # Track commands
        tracker.track(
            command="test",
            input_tokens=100,
            output_tokens=50,
        )

        # Get summary for last 7 days
        summary = tracker.get_summary(days=7)
        assert summary.total_commands == 1

        # Get summary for last 0 days (should be empty)
        summary = tracker.get_summary(days=0)
        assert summary.total_commands == 0


class TestDailyStats:
    """Test daily statistics functionality."""

    def test_get_daily_stats(self, tracker: TokenTracker):
        """Test daily statistics retrieval."""
        # Track commands
        for _ in range(3):
            tracker.track(
                command="test",
                input_tokens=100,
                output_tokens=50,
            )

        stats = tracker.get_daily_stats(days=7)

        assert len(stats) >= 1
        today_stats = stats[0]  # Most recent day
        assert today_stats.commands == 3
        assert today_stats.input_tokens == 300
        assert today_stats.output_tokens == 150
        assert today_stats.saved_tokens == 150

    def test_get_daily_stats_empty(self, tracker: TokenTracker):
        """Test daily stats with no data."""
        stats = tracker.get_daily_stats(days=7)
        assert len(stats) == 0


class TestCommandsByType:
    """Test command type grouping."""

    def test_get_commands_by_type(self, tracker: TokenTracker):
        """Test grouping by command type."""
        # Track different command types
        tracker.track(command="llm_call", input_tokens=100, output_tokens=50)
        tracker.track(command="llm_call", input_tokens=200, output_tokens=100)
        tracker.track(command="search", input_tokens=50, output_tokens=25)

        by_type = tracker.get_commands_by_type()

        assert "llm_call" in by_type
        assert "search" in by_type
        assert by_type["llm_call"].total_commands == 2
        assert by_type["search"].total_commands == 1


class TestCostEstimation:
    """Test cost estimation functionality."""

    def test_estimate_cost(self, tracker: TokenTracker):
        """Test cost estimation."""
        # Track commands
        tracker.track(
            command="test",
            input_tokens=1_000_000,
            output_tokens=500_000,
        )

        costs = tracker.estimate_cost(
            input_rate=5.0,  # $5 per 1M tokens
            output_rate=15.0,  # $15 per 1M tokens
        )

        assert costs["input_cost"] == 5.0
        assert costs["output_cost"] == 7.5
        assert costs["total_cost"] == 12.5
        assert costs["avg_cost_per_command"] == 12.5

    def test_estimate_cost_empty(self, tracker: TokenTracker):
        """Test cost estimation with no data."""
        costs = tracker.estimate_cost()

        assert costs["total_cost"] == 0.0
        assert costs["avg_cost_per_command"] == 0.0


class TestContextManager:
    """Test context manager functionality."""

    def test_context_manager(self, tmp_path: Path):
        """Test context manager usage."""
        db_path = tmp_path / "test.db"

        with TokenTracker(db_path=db_path) as tracker:
            tracker.track(
                command="test",
                input_tokens=100,
                output_tokens=50,
            )
            summary = tracker.get_summary()
            assert summary.total_commands == 1

        # Connection should be closed
        assert tracker._conn is None


class TestTokenUsageDataclass:
    """Test TokenUsage dataclass."""

    def test_total_tokens(self):
        """Test total tokens calculation."""
        usage = TokenUsage(
            command="test",
            input_tokens=100,
            output_tokens=50,
            execution_time_ms=100,
            project_path="/test",
        )

        assert usage.total_tokens == 150

    def test_savings_pct(self):
        """Test savings percentage calculation."""
        usage = TokenUsage(
            command="test",
            input_tokens=1000,
            output_tokens=200,
            execution_time_ms=100,
            project_path="/test",
        )

        assert usage.savings_pct == 80.0

    def test_savings_pct_zero_input(self):
        """Test savings percentage with zero input."""
        usage = TokenUsage(
            command="test",
            input_tokens=0,
            output_tokens=0,
            execution_time_ms=100,
            project_path="/test",
        )

        assert usage.savings_pct == 0.0

    def test_immutability(self):
        """Test that TokenUsage is immutable."""
        usage = TokenUsage(
            command="test",
            input_tokens=100,
            output_tokens=50,
            execution_time_ms=100,
            project_path="/test",
        )

        with pytest.raises(Exception):  # frozen=True
            usage.command = "modified"


class TestProjectScoping:
    """Test project-scoped tracking."""

    def test_project_isolation(self, tmp_path: Path):
        """Test that different projects have isolated tracking."""
        project1 = tmp_path / "project1"
        project2 = tmp_path / "project2"
        db_path = tmp_path / "test.db"

        tracker1 = TokenTracker(project_path=project1, db_path=db_path)
        tracker2 = TokenTracker(project_path=project2, db_path=db_path)

        # Track in both projects
        tracker1.track(command="test", input_tokens=100, output_tokens=50)
        tracker2.track(command="test", input_tokens=200, output_tokens=100)

        # Verify isolation
        summary1 = tracker1.get_summary()
        summary2 = tracker2.get_summary()

        assert summary1.total_commands == 1
        assert summary1.total_input_tokens == 100

        assert summary2.total_commands == 1
        assert summary2.total_input_tokens == 200

        tracker1.close()
        tracker2.close()
