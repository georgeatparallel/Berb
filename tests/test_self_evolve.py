"""Unit tests for SelfEvolve self-improving system."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from berb.self_evolve import (
    Experience,
    ExperienceAnalyzer,
    ExperienceCollector,
    ExperienceType,
    PolicyUpdater,
    SelfEvolveOrchestrator,
)


class TestExperience:
    """Test Experience dataclass."""

    def test_create_experience(self):
        """Test creating an experience."""
        exp = Experience(
            run_id="run_123",
            topic="Test topic",
            stage="HYPOTHESIS_GEN",
            experience_type=ExperienceType.SUCCESS,
            timestamp="2024-01-01T00:00:00",
            input_prompt="Test prompt",
            output_response="Test response",
            quality_score=9.5,
            time_taken_sec=10.5,
            tokens_used=1000,
            cost_usd=0.05,
        )

        assert exp.run_id == "run_123"
        assert exp.experience_type == ExperienceType.SUCCESS
        assert exp.quality_score == 9.5


class TestExperienceCollector:
    """Test ExperienceCollector class."""

    def test_record_experience(self, tmp_path):
        """Test recording an experience."""
        collector = ExperienceCollector(storage_path=str(tmp_path))

        collector.record_experience(
            run_id="run_123",
            topic="Test",
            stage="TEST_STAGE",
            experience_type=ExperienceType.SUCCESS,
            input_prompt="prompt",
            output_response="response",
            quality_score=9.0,
            time_taken_sec=10.0,
            tokens_used=1000,
            cost_usd=0.05,
        )

        # Should be in buffer
        assert len(collector._buffer) == 1

    def test_flush_experiences(self, tmp_path):
        """Test flushing experiences to storage."""
        collector = ExperienceCollector(storage_path=str(tmp_path))
        collector._flush_size = 1  # Force flush

        collector.record_experience(
            run_id="run_123",
            topic="Test",
            stage="TEST",
            experience_type=ExperienceType.SUCCESS,
            input_prompt="p",
            output_response="r",
            quality_score=9.0,
            time_taken_sec=10.0,
            tokens_used=1000,
            cost_usd=0.05,
        )

        # Should be flushed
        assert len(collector._buffer) == 0

        # File should exist
        files = list(tmp_path.glob("experiences_*.jsonl"))
        assert len(files) > 0

    def test_get_experiences(self, tmp_path):
        """Test retrieving experiences."""
        collector = ExperienceCollector(storage_path=str(tmp_path))
        collector._flush_size = 1

        # Record and flush
        collector.record_experience(
            run_id="run_123",
            topic="Test",
            stage="STAGE_A",
            experience_type=ExperienceType.SUCCESS,
            input_prompt="p",
            output_response="r",
            quality_score=9.0,
            time_taken_sec=10.0,
            tokens_used=1000,
            cost_usd=0.05,
        )

        # Retrieve
        experiences = collector.get_experiences(stage="STAGE_A")

        assert len(experiences) == 1
        assert experiences[0].run_id == "run_123"

    def test_get_experiences_filter_by_type(self, tmp_path):
        """Test filtering experiences by type."""
        collector = ExperienceCollector(storage_path=str(tmp_path))
        collector._flush_size = 1

        # Record success
        collector.record_experience(
            run_id="run_1",
            topic="Test",
            stage="STAGE",
            experience_type=ExperienceType.SUCCESS,
            input_prompt="p",
            output_response="r",
            quality_score=9.0,
            time_taken_sec=10.0,
            tokens_used=1000,
            cost_usd=0.05,
        )

        # Record failure
        collector.record_experience(
            run_id="run_2",
            topic="Test",
            stage="STAGE",
            experience_type=ExperienceType.FAILURE,
            input_prompt="p",
            output_response="r",
            quality_score=3.0,
            time_taken_sec=10.0,
            tokens_used=1000,
            cost_usd=0.05,
            errors=["Error occurred"],
        )

        # Filter by success
        successes = collector.get_experiences(experience_type=ExperienceType.SUCCESS)
        assert len(successes) == 1
        assert successes[0].experience_type == ExperienceType.SUCCESS

        # Filter by failure
        failures = collector.get_experiences(experience_type=ExperienceType.FAILURE)
        assert len(failures) == 1
        assert failures[0].experience_type == ExperienceType.FAILURE

    def test_get_statistics(self, tmp_path):
        """Test getting statistics."""
        collector = ExperienceCollector(storage_path=str(tmp_path))
        collector._flush_size = 1

        # Record some experiences
        for i in range(5):
            collector.record_experience(
                run_id=f"run_{i}",
                topic="Test",
                stage="STAGE",
                experience_type=(ExperienceType.SUCCESS if i < 3 else ExperienceType.FAILURE),
                input_prompt="p",
                output_response="r",
                quality_score=9.0 if i < 3 else 3.0,
                time_taken_sec=10.0,
                tokens_used=1000,
                cost_usd=0.05,
            )

        stats = collector.get_statistics()

        assert stats["total_experiences"] > 0
        assert "by_type" in stats
        assert "avg_quality" in stats


class TestExperienceAnalyzer:
    """Test ExperienceAnalyzer class."""

    def test_analyze_failures(self, tmp_path):
        """Test analyzing failure patterns."""
        collector = ExperienceCollector(storage_path=str(tmp_path))
        collector._flush_size = 1

        # Record failures with common error
        for i in range(3):
            collector.record_experience(
                run_id=f"fail_{i}",
                topic="Test",
                stage="STAGE_A",
                experience_type=ExperienceType.FAILURE,
                input_prompt="p",
                output_response="r",
                quality_score=3.0,
                time_taken_sec=10.0,
                tokens_used=1000,
                cost_usd=0.05,
                errors=["JSON parse error: invalid format"],
            )

        analyzer = ExperienceAnalyzer(collector)
        analysis = analyzer.analyze_failures()

        assert analysis["total_failures"] == 3
        assert len(analysis["common_errors"]) > 0
        assert len(analysis["recommendations"]) > 0

    def test_analyze_successes(self, tmp_path):
        """Test analyzing success patterns."""
        collector = ExperienceCollector(storage_path=str(tmp_path))
        collector._flush_size = 1

        # Record high-quality successes
        for i in range(3):
            collector.record_experience(
                run_id=f"success_{i}",
                topic="Test",
                stage="STAGE_A",
                experience_type=ExperienceType.SUCCESS,
                input_prompt="Detailed prompt with step-by-step instructions and examples",
                output_response="Excellent response",
                quality_score=9.5,
                time_taken_sec=10.0,
                tokens_used=1000,
                cost_usd=0.05,
            )

        analyzer = ExperienceAnalyzer(collector)
        analysis = analyzer.analyze_successes()

        assert analysis["total_successes"] == 3
        assert analysis["high_quality_count"] == 3
        assert len(analysis["best_practices"]) > 0

    def test_analyze_empty_data(self, tmp_path):
        """Test analyzing with no data."""
        collector = ExperienceCollector(storage_path=str(tmp_path))
        analyzer = ExperienceAnalyzer(collector)

        failure_analysis = analyzer.analyze_failures()
        assert failure_analysis["total_failures"] == 0

        success_analysis = analyzer.analyze_successes()
        assert success_analysis["total_successes"] == 0


class TestPolicyUpdater:
    """Test PolicyUpdater class."""

    def test_update_prompts(self, tmp_path):
        """Test updating prompts."""
        updater = PolicyUpdater(config_path=str(tmp_path))

        improvements = [
            "Add more examples",
            "Include step-by-step instructions",
        ]
        examples = ["Example 1", "Example 2"]

        file_path = updater.update_prompts(
            stage="HYPOTHESIS_GEN",
            improvements=improvements,
            examples=examples,
        )

        assert Path(file_path).exists()

        # Verify content
        content = Path(file_path).read_text()
        assert "HYPOTHESIS_GEN" in content
        assert "Add more examples" in content

    def test_update_routing_rules(self, tmp_path):
        """Test updating routing rules."""
        updater = PolicyUpdater(config_path=str(tmp_path))

        file_path = updater.update_routing_rules(
            stage="PEER_REVIEW",
            recommended_model="claude-sonnet",
            reasoning="Higher quality for critical evaluation",
        )

        assert Path(file_path).exists()

        content = Path(file_path).read_text()
        assert "PEER_REVIEW" in content
        assert "claude-sonnet" in content


class TestSelfEvolveOrchestrator:
    """Test SelfEvolveOrchestrator class."""

    def test_record_research_run(self, tmp_path):
        """Test recording a research run."""
        with patch("berb.self_evolve.ExperienceCollector") as MockCollector:
            mock_collector = MagicMock()
            MockCollector.return_value = mock_collector

            orchestrator = SelfEvolveOrchestrator()
            orchestrator._collector = mock_collector

            orchestrator.record_research_run(
                run_id="run_123",
                topic="Test topic",
                stage="HYPOTHESIS_GEN",
                success=True,
                quality_score=9.0,
                input_prompt="test",
                output_response="response",
            )

            # Verify experience was recorded
            assert mock_collector.record_experience.called

    @pytest.mark.asyncio
    async def test_start_improvement_cycle(self, tmp_path):
        """Test starting improvement cycle."""
        with (
            patch("berb.self_evolve.ExperienceCollector") as MockCollector,
            patch("berb.self_evolve.ExperienceAnalyzer") as MockAnalyzer,
            patch("berb.self_evolve.PolicyUpdater") as MockUpdater,
        ):
            mock_collector = MagicMock()
            mock_analyzer = MagicMock()
            mock_updater = MagicMock()

            MockCollector.return_value = mock_collector
            MockAnalyzer.return_value = mock_analyzer
            MockUpdater.return_value = mock_updater

            # Mock analyzer results
            mock_analyzer.analyze_failures.return_value = {
                "total_failures": 5,
                "recommendations": ["Fix JSON parsing"],
            }
            mock_analyzer.analyze_successes.return_value = {
                "total_successes": 10,
                "best_practices": ["Use detailed prompts"],
            }

            orchestrator = SelfEvolveOrchestrator()
            orchestrator._collector = mock_collector
            orchestrator._analyzer = mock_analyzer
            orchestrator._updater = mock_updater

            result = await orchestrator.start_improvement_cycle()

            assert result["status"] == "complete"
            assert "improvements_generated" in result
            assert "improvements_applied" in result

    def test_get_statistics(self, tmp_path):
        """Test getting statistics."""
        with patch("berb.self_evolve.ExperienceCollector") as MockCollector:
            mock_collector = MagicMock()
            mock_collector.get_statistics.return_value = {
                "total_experiences": 100,
                "by_type": {"success": 80, "failure": 20},
            }
            MockCollector.return_value = mock_collector

            orchestrator = SelfEvolveOrchestrator()
            orchestrator._collector = mock_collector
            orchestrator._improvement_count = 5

            stats = orchestrator.get_statistics()

            assert "collector" in stats
            assert stats["improvement_cycles"] == 5
            assert stats["status"] == "active"
