"""Unit tests for automated evaluation dataset."""

import json
import tempfile
from pathlib import Path

import pytest

from berb.llm.eval_dataset import (
    EvalDatasetBuilder,
    FailureRecord,
    PipelineEvalIntegration,
)


class TestFailureRecord:
    """Test FailureRecord dataclass."""

    def test_create_record(self):
        """Test creating a failure record."""
        record = FailureRecord(
            prompt="Test prompt",
            response="Bad response",
            errors=["Error 1", "Error 2"],
            eval_scores={"novelty": 0.3, "rigor": 0.4},
            stage="HYPOTHESIS_GEN",
            model="gpt-4o",
        )

        assert record.prompt == "Test prompt"
        assert len(record.errors) == 2
        assert record.stage == "HYPOTHESIS_GEN"


class TestEvalDatasetBuilder:
    """Test EvalDatasetBuilder class."""

    @pytest.mark.asyncio
    async def test_record_failure(self):
        """Test recording a failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "eval_dataset.jsonl"
            builder = EvalDatasetBuilder(dataset_path=dataset_path)

            await builder.record_failure(
                prompt="Test prompt",
                response="Bad response",
                errors=["Error 1"],
                eval_scores={"novelty": 0.3},
                stage="HYPOTHESIS_GEN",
                model="gpt-4o",
            )

            # Verify file was created
            assert dataset_path.exists()

            # Verify content
            with dataset_path.open() as f:
                line = f.readline()
                data = json.loads(line)
                assert data["prompt"] == "Test prompt"
                assert data["stage"] == "HYPOTHESIS_GEN"

    @pytest.mark.asyncio
    async def test_load_test_cases(self):
        """Test loading test cases."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "eval_dataset.jsonl"
            builder = EvalDatasetBuilder(dataset_path=dataset_path)

            # Record some failures
            await builder.record_failure(
                prompt="Prompt 1",
                response="Response 1",
                errors=["Error"],
                eval_scores={"novelty": 0.3},
                stage="HYPOTHESIS_GEN",
                model="gpt-4o",
            )

            await builder.record_failure(
                prompt="Prompt 2",
                response="Response 2",
                errors=["Error"],
                eval_scores={"novelty": 0.4},
                stage="PEER_REVIEW",
                model="claude-sonnet",
            )

            # Load all
            records = await builder.load_test_cases()
            assert len(records) == 2

            # Load by stage
            records = await builder.load_test_cases(stage="HYPOTHESIS_GEN")
            assert len(records) == 1
            assert records[0].stage == "HYPOTHESIS_GEN"

            # Load by model
            records = await builder.load_test_cases(model="claude-sonnet")
            assert len(records) == 1
            assert records[0].model == "claude-sonnet"

    @pytest.mark.asyncio
    async def test_load_nonexistent_dataset(self):
        """Test loading from nonexistent dataset."""
        builder = EvalDatasetBuilder(
            dataset_path="/nonexistent/path.jsonl", auto_create=False
        )

        records = await builder.load_test_cases()
        assert records == []

    @pytest.mark.asyncio
    async def test_get_statistics(self):
        """Test getting dataset statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "eval_dataset.jsonl"
            builder = EvalDatasetBuilder(dataset_path=dataset_path)

            # Record failures for different stages
            await builder.record_failure(
                prompt="P1",
                response="R1",
                errors=["E1", "E2"],
                eval_scores={"novelty": 0.3},
                stage="HYPOTHESIS_GEN",
                model="gpt-4o",
            )

            await builder.record_failure(
                prompt="P2",
                response="R2",
                errors=["E1"],
                eval_scores={"novelty": 0.4},
                stage="HYPOTHESIS_GEN",
                model="gpt-4o",
            )

            await builder.record_failure(
                prompt="P3",
                response="R3",
                errors=["E1", "E2", "E3"],
                eval_scores={"clarity": 0.5},
                stage="PEER_REVIEW",
                model="claude-sonnet",
            )

            stats = await builder.get_statistics()

            assert stats["total_records"] == 3
            assert stats["by_stage"]["HYPOTHESIS_GEN"] == 2
            assert stats["by_stage"]["PEER_REVIEW"] == 1
            assert stats["by_model"]["gpt-4o"] == 2
            assert abs(stats["avg_errors_per_record"] - 2.0) < 0.01

    @pytest.mark.asyncio
    async def test_export_for_regression(self):
        """Test exporting for regression testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "eval_dataset.jsonl"
            export_path = Path(tmpdir) / "export.json"
            builder = EvalDatasetBuilder(dataset_path=dataset_path)

            # Record failures
            await builder.record_failure(
                prompt="P1",
                response="R1",
                errors=["E1"],
                eval_scores={"novelty": 0.3},
                stage="HYPOTHESIS_GEN",
                model="gpt-4o",
            )

            # Export
            count = await builder.export_for_regression(
                output_path=export_path,
                stage="HYPOTHESIS_GEN",
            )

            assert count == 1
            assert export_path.exists()

            # Verify export content
            with export_path.open() as f:
                data = json.load(f)
                assert data["total_cases"] == 1
                assert data["stage"] == "HYPOTHESIS_GEN"


class TestPipelineEvalIntegration:
    """Test PipelineEvalIntegration class."""

    @pytest.mark.asyncio
    async def test_record_stage_failure(self):
        """Test recording stage failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "eval_dataset.jsonl"
            builder = EvalDatasetBuilder(dataset_path=dataset_path)
            integration = PipelineEvalIntegration(builder)

            await integration.record_stage_failure(
                stage="HYPOTHESIS_GEN",
                prompt="Test",
                response="Bad",
                errors=["Error"],
                eval_scores={"novelty": 0.3},
                model="gpt-4o",
                run_id="run_123",
                topic="Test topic",
            )

            records = await builder.load_test_cases()
            assert len(records) == 1
            assert records[0].run_id == "run_123"
            assert records[0].topic == "Test topic"

    def test_should_flag_for_review(self):
        """Test flagging for review."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "eval_dataset.jsonl"
            builder = EvalDatasetBuilder(dataset_path=dataset_path)
            integration = PipelineEvalIntegration(builder)

            # Below threshold - should flag
            should_flag = integration.should_flag_for_review(
                stage="HYPOTHESIS_GEN",
                eval_scores={"novelty": 0.3},  # Below 0.5 threshold
            )
            assert should_flag is True

            # Above threshold - should not flag
            should_flag = integration.should_flag_for_review(
                stage="HYPOTHESIS_GEN",
                eval_scores={"novelty": 0.7},  # Above 0.5 threshold
            )
            assert should_flag is False

    @pytest.mark.asyncio
    async def test_get_regression_tests(self):
        """Test getting regression tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "eval_dataset.jsonl"
            builder = EvalDatasetBuilder(dataset_path=dataset_path)
            integration = PipelineEvalIntegration(builder)

            # Record failures
            for i in range(5):
                await builder.record_failure(
                    prompt=f"P{i}",
                    response=f"R{i}",
                    errors=["E"],
                    eval_scores={"novelty": 0.3},
                    stage="HYPOTHESIS_GEN",
                    model="gpt-4o",
                )

            # Get regression tests
            tests = await integration.get_regression_tests("HYPOTHESIS_GEN")

            assert len(tests) == 5
