# pyright: reportPrivateUsage=false
"""Comprehensive End-to-End Test Suite for Berb Autonomous Research Pipeline.

This test suite validates the complete 23-stage pipeline with mocked external
dependencies, testing all phases from research scoping to paper export.

Test Architecture:
- 8 Test Sets (one per pipeline phase A-H)
- 23 Stage Tests (one per pipeline stage)
- Integration Tests (cross-phase workflows)
- Regression Tests (bug fix verification)

Coverage:
- Phase A: Research Scoping (Stages 1-2)
- Phase B: Literature Discovery (Stages 3-6)
- Phase C: Knowledge Synthesis (Stages 7-8)
- Phase D: Experiment Design (Stages 9-11)
- Phase E: Experiment Execution (Stages 12-13)
- Phase F: Analysis & Decision (Stages 14-15)
- Phase G: Paper Writing (Stages 16-19)
- Phase H: Finalization (Stages 20-23)

# Author: Georgios-Chrysovalantis Chatzivantsidis
# Date: 2026-04-03
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.pipeline.contracts import CONTRACTS
from berb.pipeline.executor import execute_stage
from berb.pipeline.stages import Stage, StageStatus

# ============================================================================
# E2E Test Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def e2e_test_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create temporary directory for E2E test artifacts."""
    return tmp_path_factory.mktemp("e2e_full_pipeline")


@pytest.fixture(autouse=True)
def _no_network_literature_search():
    """Prevent any test in this module from touching real literature APIs.

    Several stages (LITERATURE_COLLECT, HYPOTHESIS_GEN via check_novelty) call
    berb.literature.search.search_papers_multi_query, which performs real
    network I/O (OpenAlex/Semantic Scholar/arXiv) with blocking time.sleep()
    retry loops. On Windows, pytest-timeout cannot interrupt a thread blocked
    in real socket I/O, so an unmocked call here would hang the whole pytest
    process. Mock at the source module so both direct and re-imported call
    sites are covered.
    """
    from berb.web.agent import WebSearchAgentResult

    with (
        patch("berb.literature.search.search_papers_multi_query", return_value=[]),
        patch(
            "berb.web.agent.WebSearchAgent.search_and_extract",
            return_value=WebSearchAgentResult(topic=""),
        ),
    ):
        yield


@pytest.fixture(scope="module")
def mock_config(e2e_test_dir: Path) -> RCConfig:
    """Create mock configuration for E2E tests."""
    data = {
        "project": {"name": "e2e-full-test", "mode": "full-auto"},
        "research": {
            "topic": "Machine Learning for Scientific Discovery",
            "domains": ["machine-learning", "science"],
            "daily_paper_count": 5,
            "quality_threshold": 4.0,
        },
        "runtime": {"timezone": "UTC", "max_parallel_tasks": 1},
        "notifications": {"channel": "console"},
        "knowledge_base": {
            "backend": "markdown",
            "root": str(e2e_test_dir / "kb"),
        },
        "openclaw_bridge": {"use_memory": False, "use_message": False},
        "llm": {
            "provider": "openai-compatible",
            "base_url": "http://localhost:1234/v1",
            "api_key_env": "E2E_TEST_KEY",
            "primary_model": "mock-model",
            "fallback_models": [],
        },
        "security": {"hitl_required_stages": []},  # No gates for E2E
        "experiment": {
            "mode": "sandbox",
            "time_budget_sec": 60,
            "max_iterations": 2,
            "metric_key": "accuracy",
            "metric_direction": "maximize",
        },
    }
    return RCConfig.from_dict(data, project_root=e2e_test_dir, check_paths=False)


@pytest.fixture(scope="module")
def adapters() -> AdapterBundle:
    """Create adapter bundle for E2E tests."""
    return AdapterBundle()


@pytest.fixture
def run_dir(e2e_test_dir: Path, request: pytest.FixtureRequest) -> Path:
    """Create run directory for each test."""
    test_name = request.node.name
    run_path = e2e_test_dir / "runs" / test_name
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path


# ============================================================================
# Mock LLM Client with Stage-Specific Responses
# ============================================================================


class MockLLMClient:
    """Mock LLM client for E2E tests with stage-specific responses."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls: list[dict] = []
        self.config = SimpleNamespace(base_url="http://mock", api_key="mock-key")

    def chat(
        self,
        messages: list[dict],
        model: str = "mock-model",
        **kwargs: Any,
    ) -> MagicMock:
        """Mock chat completion."""
        self.calls.append({"messages": messages, "model": model, "kwargs": kwargs})

        # Generate appropriate response based on stage
        response = self._generate_response(messages)

        result = MagicMock()
        result.content = response
        result.model = model
        result.usage = MagicMock()
        result.usage.prompt_tokens = 100
        result.usage.completion_tokens = 200
        return result

    def _generate_response(self, messages: list[dict]) -> str:
        """Generate mock response based on message content."""
        user_message = messages[-1]["content"].lower() if messages else ""

        # Stage-specific responses
        if "topic" in user_message and ("init" in user_message or "goal" in user_message):
            return self._topic_init_response()
        elif "problem decompose" in user_message or "sub-problems" in user_message:
            return self._problem_decompose_response()
        elif "search" in user_message and ("plan" in user_message or "strategy" in user_message):
            return self._search_strategy_response()
        elif "collect" in user_message and "literature" in user_message:
            return self._literature_collect_response()
        elif "screen" in user_message or "relevance" in user_message:
            return self._literature_screen_response()
        elif "extract" in user_message and "knowledge" in user_message:
            return self._knowledge_extract_response()
        elif "synthesis" in user_message or "synthesize" in user_message:
            return self._synthesis_response()
        elif "hypothesis" in user_message:
            return self._hypothesis_response()
        elif "experiment" in user_message and "design" in user_message:
            return self._experiment_design_response()
        elif "code" in user_message and "generate" in user_message:
            return self._code_generation_response()
        elif "resource" in user_message and "plan" in user_message:
            return self._resource_planning_response()
        elif "run" in user_message and "experiment" in user_message:
            return self._experiment_run_response()
        elif "refine" in user_message or "iterative" in user_message:
            return self._iterative_refine_response()
        elif "analyze" in user_message and "result" in user_message:
            return self._result_analysis_response()
        elif "decision" in user_message:
            return self._research_decision_response()
        elif "outline" in user_message and "paper" in user_message:
            return self._paper_outline_response()
        elif "draft" in user_message or "write paper" in user_message:
            return self._paper_draft_response()
        elif "review" in user_message and "peer" in user_message:
            return self._peer_review_response()
        elif "revision" in user_message:
            return self._paper_revision_response()
        elif "quality" in user_message and ("gate" in user_message or "assess" in user_message):
            return self._quality_gate_response()
        elif "archive" in user_message or "knowledge archive" in user_message:
            return self._knowledge_archive_response()
        elif "export" in user_message or "publish" in user_message:
            return self._export_publish_response()
        elif "citation" in user_message and "verify" in user_message:
            return self._citation_verify_response()
        else:
            return self._default_response()

    def _topic_init_response(self) -> str:
        return json.dumps(
            {
                "topic": "Machine Learning for Scientific Discovery",
                "research_questions": [
                    "How can ML accelerate scientific discovery?",
                    "What are the key challenges in ML-driven science?",
                ],
                "success_criteria": [
                    "Novel ML approach",
                    "Empirical validation",
                    "Scientific impact",
                ],
            }
        )

    def _problem_decompose_response(self) -> str:
        return """# Problem Decomposition

## Sub-problem 1: Data Collection
Automated data gathering from scientific sources

## Sub-problem 2: Model Development
ML model architecture design

## Sub-problem 3: Validation
Empirical testing and evaluation
"""

    def _search_strategy_response(self) -> str:
        return json.dumps(
            {
                "search_plan": {
                    "queries": ["ML for science", "automated discovery"],
                    "sources": ["arxiv", "semantic_scholar", "openalex"],
                },
                "sources": ["arxiv", "semantic_scholar", "openalex"],
                "queries": ["ML for science", "automated discovery"],
            }
        )

    def _literature_collect_response(self) -> str:
        papers = [
            {
                "title": f"Paper {i}",
                "authors": ["Author et al."],
                "year": 2025,
                "abstract": f"Abstract {i}",
            }
            for i in range(10)
        ]
        return "\n".join(json.dumps(p) for p in papers)

    def _literature_screen_response(self) -> str:
        papers = [
            {
                "title": f"Screened Paper {i}",
                "relevance_score": 0.9 - i * 0.1,
                "quality_score": 8.0 - i * 0.5,
            }
            for i in range(5)
        ]
        return "\n".join(json.dumps(p) for p in papers)

    def _knowledge_extract_response(self) -> str:
        return json.dumps(
            {
                "cards": [
                    {
                        "id": f"card-{i}",
                        "title": f"Paper {i}",
                        "key_findings": ["Finding 1", "Finding 2"],
                    }
                    for i in range(5)
                ]
            }
        )

    def _synthesis_response(self) -> str:
        return """# Knowledge Synthesis

## Topic Clusters
1. ML methods for science
2. Automated discovery systems
3. Evaluation frameworks

## Research Gaps
1. Lack of standardized benchmarks
2. Limited cross-domain transfer
3. Insufficient reproducibility studies
"""

    def _hypothesis_response(self) -> str:
        return """# Hypotheses

## H1
ML-accelerated discovery reduces time-to-insight by 50%

## H2
Automated feature engineering improves model accuracy by 15%

## H3
Cross-domain transfer learning enables rapid adaptation with 80% less data
"""

    def _experiment_design_response(self) -> str:
        return json.dumps(
            {
                "experiment_plan": {
                    "objective": "Validate ML acceleration hypothesis",
                    "method": "Comparative study with baseline",
                    "metrics": ["time-to-insight", "accuracy", "resource_usage"],
                    "conditions": [
                        {"name": "control", "description": "Traditional method"},
                        {"name": "treatment", "description": "ML-accelerated method"},
                    ],
                }
            }
        )

    def _code_generation_response(self) -> str:
        return """```python
# main.py - ML Experiment
import numpy as np

def run_experiment():
    '''Run ML experiment'''
    # Generate synthetic data
    X = np.random.randn(100, 10)
    y = np.random.randint(0, 2, 100)

    # Train model
    from sklearn.ensemble import RandomForestClassifier
    model = RandomForestClassifier(n_estimators=10)
    model.fit(X, y)

    # Evaluate
    accuracy = model.score(X, y)
    print(f'accuracy: {accuracy:.4f}')
    return accuracy

if __name__ == '__main__':
    run_experiment()
```
"""

    def _resource_planning_response(self) -> str:
        return json.dumps(
            {
                "schedule": {
                    "total_time_estimate": "2 hours",
                    "gpu_required": False,
                    "memory_required_gb": 4,
                    "trials": [
                        {"condition": "control", "repeats": 5},
                        {"condition": "treatment", "repeats": 5},
                    ],
                }
            }
        )

    def _experiment_run_response(self) -> str:
        return json.dumps(
            {
                "runs": [
                    {
                        "run_id": f"run-{i}",
                        "condition": "control" if i < 5 else "treatment",
                        "accuracy": 0.7 + i * 0.02,
                    }
                    for i in range(10)
                ]
            }
        )

    def _iterative_refine_response(self) -> str:
        return json.dumps(
            {
                "refinement_log": {
                    "iterations": 3,
                    "final_metrics": {"accuracy": 0.85},
                    "improvements": ["Hyperparameter tuning", "Feature engineering"],
                }
            }
        )

    def _result_analysis_response(self) -> str:
        return """# Result Analysis

## Key Findings

1. ML approach reduced time-to-insight by 45%
2. Accuracy improved by 12%
3. Resource usage comparable to baseline

## Statistical Significance

p-value < 0.05 for primary metric

## Limitations

- Synthetic data only
- Limited domain scope
"""

    def _research_decision_response(self) -> str:
        return json.dumps(
            {
                "decision": "PROCEED",
                "justification": "Results support hypothesis with statistical significance",
                "confidence": 0.85,
            }
        )

    def _paper_outline_response(self) -> str:
        return """# Paper Outline

## 1. Introduction
- Problem statement
- Contributions

## 2. Related Work
- ML for science
- Automated discovery

## 3. Method
- Approach
- Implementation

## 4. Experiments
- Setup
- Results

## 5. Discussion
- Implications
- Limitations

## 6. Conclusion
"""

    def _paper_draft_response(self) -> str:
        return """# Machine Learning for Scientific Discovery

## Abstract

We present a novel ML approach for accelerating scientific discovery...

## 1. Introduction

Scientific discovery is time-consuming...

## 2. Related Work

Previous work has explored...

## 3. Method

Our approach uses...

## 4. Experiments

We conducted experiments...

## 5. Discussion

Results show significant improvement...

## 6. Conclusion

We demonstrated ML acceleration...

## References

[1] Smith et al. (2025)
"""

    def _peer_review_response(self) -> str:
        return """# Peer Review

## Reviewer 1
Score: 8/10
Comments: Strong contribution, minor revisions needed

## Reviewer 2
Score: 7/10
Comments: Good work, clarify methodology

## Reviewer 3
Score: 9/10
Comments: Excellent contribution

## Area Chair
Decision: Accept with minor revisions
"""

    def _paper_revision_response(self) -> str:
        return """# Revised Paper

## Abstract

We present a novel ML approach for accelerating scientific discovery...

[Revisions based on reviewer feedback]

## Changes Made

1. Clarified methodology section
2. Added ablation study
3. Improved figure captions
"""

    def _quality_gate_response(self) -> str:
        return json.dumps(
            {
                "quality_report": {
                    "score_1_to_10": 8.5,
                    "verdict": "accept",
                    "criteria": {
                        "novelty": 8.0,
                        "methodological_rigor": 9.0,
                        "clarity": 8.5,
                        "reproducibility": 8.5,
                    },
                }
            }
        )

    def _knowledge_archive_response(self) -> str:
        return json.dumps(
            {
                "archive": {
                    "retrospective": "Research completed successfully",
                    "bundle_index": ["paper", "code", "data", "experiments"],
                }
            }
        )

    def _export_publish_response(self) -> str:
        return """# Final Paper

## Machine Learning for Scientific Discovery

[Final formatted paper ready for submission]
"""

    def _citation_verify_response(self) -> str:
        return json.dumps(
            {
                "verification_report": {
                    "total_citations": 15,
                    "verified_citations": 15,
                    "hallucinated_citations": 0,
                    "status": "all_verified",
                }
            }
        )

    def _default_response(self) -> str:
        return "Mock response for pipeline stage"


# ============================================================================
# Test Set 1: Phase A - Research Scoping (Stages 1-2)
# ============================================================================


class TestPhaseA_ResearchScoping:
    """Test Phase A: Research Scoping (Stages 1-2).

    Validates:
    - Topic initialization
    - Problem decomposition
    - Goal formulation
    """

    def test_stage_01_topic_init(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 1: Initialize research topic."""
        stage_dir = run_dir / f"stage-{Stage.TOPIC_INIT:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.TOPIC_INIT,
                run_dir=run_dir,
                run_id="e2e-full-001",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        # Verify
        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "goal.md" in result.artifacts
        assert (stage_dir / "goal.md").exists()
        assert (stage_dir / "hardware_profile.json").exists()

    def test_stage_02_problem_decompose(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 2: Decompose problem into sub-problems."""
        # Setup: Create prior artifact from Stage 1
        stage1_dir = run_dir / f"stage-{Stage.TOPIC_INIT:02d}"
        stage1_dir.mkdir(parents=True, exist_ok=True)
        (stage1_dir / "goal.md").write_text("# Research Goal\n\nTest goal", encoding="utf-8")

        stage_dir = run_dir / f"stage-{Stage.PROBLEM_DECOMPOSE:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.PROBLEM_DECOMPOSE,
                run_dir=run_dir,
                run_id="e2e-full-002",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        # Verify
        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "problem_tree.md" in result.artifacts
        assert (stage_dir / "problem_tree.md").exists()


# ============================================================================
# Test Set 2: Phase B - Literature Discovery (Stages 3-6)
# ============================================================================


class TestPhaseB_LiteratureDiscovery:
    """Test Phase B: Literature Discovery (Stages 3-6).

    Validates:
    - Search strategy formulation
    - Literature collection
    - Screening process
    - Knowledge extraction
    """

    def _setup_prior_stages(self, run_dir: Path, up_to_stage: int) -> None:
        """Setup artifacts from prior stages."""
        artifacts = {
            1: ("stage-01", "goal.md", "# Goal"),
            2: ("stage-02", "problem_tree.md", "# Problem Tree"),
        }
        for stage_num in range(1, min(up_to_stage, 3)):
            if stage_num in artifacts:
                dir_name, file_name, content = artifacts[stage_num]
                stage_dir = run_dir / dir_name
                stage_dir.mkdir(parents=True, exist_ok=True)
                (stage_dir / file_name).write_text(content, encoding="utf-8")

    def test_stage_03_search_strategy(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 3: Formulate search strategy."""
        self._setup_prior_stages(run_dir, 3)

        stage_dir = run_dir / f"stage-{Stage.SEARCH_STRATEGY:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.SEARCH_STRATEGY,
                run_dir=run_dir,
                run_id="e2e-full-003",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "search_plan.yaml" in result.artifacts
        assert "sources.json" in result.artifacts
        assert "queries.json" in result.artifacts

    def test_stage_04_literature_collect(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 4: Collect literature."""
        self._setup_prior_stages(run_dir, 4)
        stage3_dir = run_dir / "stage-03"
        stage3_dir.mkdir(parents=True, exist_ok=True)
        (stage3_dir / "search_plan.yaml").write_text("queries: [test]", encoding="utf-8")

        stage_dir = run_dir / f"stage-{Stage.LITERATURE_COLLECT:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with (
            patch("berb.pipeline.executor.create_llm_client", return_value=llm),
            patch("berb.literature.search.search_papers_multi_query", return_value=[]),
        ):
            result = execute_stage(
                Stage.LITERATURE_COLLECT,
                run_dir=run_dir,
                run_id="e2e-full-004",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "candidates.jsonl" in result.artifacts

    def test_stage_05_literature_screen(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 5: Screen literature (GATE)."""
        self._setup_prior_stages(run_dir, 5)
        stage4_dir = run_dir / "stage-04"
        stage4_dir.mkdir(parents=True, exist_ok=True)
        (stage4_dir / "candidates.jsonl").write_text('{"title": "test"}\n', encoding="utf-8")

        stage_dir = run_dir / f"stage-{Stage.LITERATURE_SCREEN:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.LITERATURE_SCREEN,
                run_dir=run_dir,
                run_id="e2e-full-005",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "shortlist.jsonl" in result.artifacts

    def test_stage_06_knowledge_extract(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 6: Extract knowledge from papers."""
        self._setup_prior_stages(run_dir, 6)
        stage5_dir = run_dir / "stage-05"
        stage5_dir.mkdir(parents=True, exist_ok=True)
        (stage5_dir / "shortlist.jsonl").write_text('{"title": "test"}\n', encoding="utf-8")

        stage_dir = run_dir / f"stage-{Stage.KNOWLEDGE_EXTRACT:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.KNOWLEDGE_EXTRACT,
                run_dir=run_dir,
                run_id="e2e-full-006",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert (stage_dir / "cards").exists()


# ============================================================================
# Test Set 3: Phase C - Knowledge Synthesis (Stages 7-8)
# ============================================================================


class TestPhaseC_KnowledgeSynthesis:
    """Test Phase C: Knowledge Synthesis (Stages 7-8).

    Validates:
    - Synthesis of extracted knowledge
    - Hypothesis generation
    """

    def _setup_prior_stages(self, run_dir: Path) -> None:
        """Setup artifacts from stages 1-6."""
        for i in range(1, 7):
            stage_dir = run_dir / f"stage-{i:02d}"
            stage_dir.mkdir(parents=True, exist_ok=True)
            if i == 6:
                cards_dir = stage_dir / "cards"
                cards_dir.mkdir(parents=True, exist_ok=True)
                (cards_dir / "card-1.json").write_text('{"title": "test"}', encoding="utf-8")
            else:
                (stage_dir / f"artifact-{i}.md").write_text(f"# Artifact {i}", encoding="utf-8")

    def test_stage_07_synthesis(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 7: Synthesize knowledge."""
        self._setup_prior_stages(run_dir)

        stage_dir = run_dir / f"stage-{Stage.SYNTHESIS:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.SYNTHESIS,
                run_dir=run_dir,
                run_id="e2e-full-007",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "synthesis.md" in result.artifacts

    def test_stage_08_hypothesis_gen(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 8: Generate hypotheses."""
        self._setup_prior_stages(run_dir)
        stage7_dir = run_dir / "stage-07"
        stage7_dir.mkdir(parents=True, exist_ok=True)
        (stage7_dir / "synthesis.md").write_text("# Synthesis", encoding="utf-8")

        stage_dir = run_dir / f"stage-{Stage.HYPOTHESIS_GEN:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.HYPOTHESIS_GEN,
                run_dir=run_dir,
                run_id="e2e-full-008",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "hypotheses.md" in result.artifacts


# ============================================================================
# Test Set 4: Phase D - Experiment Design (Stages 9-11)
# ============================================================================


class TestPhaseD_ExperimentDesign:
    """Test Phase D: Experiment Design (Stages 9-11).

    Validates:
    - Experiment design
    - Code generation
    - Resource planning
    """

    def _setup_prior_stages(self, run_dir: Path) -> None:
        """Setup artifacts from stages 1-8."""
        for i in range(1, 9):
            stage_dir = run_dir / f"stage-{i:02d}"
            stage_dir.mkdir(parents=True, exist_ok=True)
            if i == 8:
                (stage_dir / "hypotheses.md").write_text("# Hypotheses", encoding="utf-8")
            else:
                (stage_dir / f"artifact-{i}.md").write_text(f"# Artifact {i}", encoding="utf-8")

    def test_stage_09_experiment_design(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 9: Design experiment (GATE)."""
        self._setup_prior_stages(run_dir)

        stage_dir = run_dir / f"stage-{Stage.EXPERIMENT_DESIGN:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.EXPERIMENT_DESIGN,
                run_dir=run_dir,
                run_id="e2e-full-009",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "exp_plan.yaml" in result.artifacts

    def test_stage_10_code_generation(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 10: Generate experiment code."""
        self._setup_prior_stages(run_dir)
        stage9_dir = run_dir / "stage-09"
        stage9_dir.mkdir(parents=True, exist_ok=True)
        (stage9_dir / "exp_plan.yaml").write_text("conditions: []", encoding="utf-8")

        stage_dir = run_dir / f"stage-{Stage.CODE_GENERATION:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.CODE_GENERATION,
                run_dir=run_dir,
                run_id="e2e-full-010",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "experiment/" in result.artifacts or "main.py" in result.artifacts

    def test_stage_11_resource_planning(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 11: Plan resources."""
        self._setup_prior_stages(run_dir)
        stage9_dir = run_dir / "stage-09"
        stage10_dir = run_dir / "stage-10"
        stage9_dir.mkdir(parents=True, exist_ok=True)
        stage10_dir.mkdir(parents=True, exist_ok=True)
        (stage9_dir / "exp_plan.yaml").write_text("conditions: []", encoding="utf-8")
        (stage10_dir / "main.py").write_text("print('test')", encoding="utf-8")

        stage_dir = run_dir / f"stage-{Stage.RESOURCE_PLANNING:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.RESOURCE_PLANNING,
                run_dir=run_dir,
                run_id="e2e-full-011",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "schedule.json" in result.artifacts


# ============================================================================
# Test Set 5: Phase E - Experiment Execution (Stages 12-13)
# ============================================================================


class TestPhaseE_ExperimentExecution:
    """Test Phase E: Experiment Execution (Stages 12-13).

    Validates:
    - Experiment run
    - Iterative refinement
    """

    def _setup_prior_stages(self, run_dir: Path) -> None:
        """Setup artifacts from stages 1-11."""
        for i in range(1, 12):
            stage_dir = run_dir / f"stage-{i:02d}"
            stage_dir.mkdir(parents=True, exist_ok=True)
            if i == 11:
                (stage_dir / "schedule.json").write_text('{"trials": []}', encoding="utf-8")
                exp_dir = stage_dir / "experiment"
                exp_dir.mkdir(parents=True, exist_ok=True)
                (exp_dir / "main.py").write_text("print('test')", encoding="utf-8")
            else:
                (stage_dir / f"artifact-{i}.md").write_text(f"# Artifact {i}", encoding="utf-8")

    def test_stage_12_experiment_run(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 12: Run experiment."""
        self._setup_prior_stages(run_dir)

        stage_dir = run_dir / f"stage-{Stage.EXPERIMENT_RUN:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.EXPERIMENT_RUN,
                run_dir=run_dir,
                run_id="e2e-full-012",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        # Stage 12 may succeed or need refinement
        assert result.status in [StageStatus.DONE, StageStatus.BLOCKED_APPROVAL], (
            f"Stage failed: {result.error}"
        )

    def test_stage_13_iterative_refine(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 13: Iterative refinement."""
        self._setup_prior_stages(run_dir)
        stage12_dir = run_dir / "stage-12"
        stage12_dir.mkdir(parents=True, exist_ok=True)
        runs_dir = stage12_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text('{"status": "completed"}', encoding="utf-8")

        stage_dir = run_dir / f"stage-{Stage.ITERATIVE_REFINE:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.ITERATIVE_REFINE,
                run_dir=run_dir,
                run_id="e2e-full-013",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"


# ============================================================================
# Test Set 6: Phase F - Analysis & Decision (Stages 14-15)
# ============================================================================


class TestPhaseF_AnalysisDecision:
    """Test Phase F: Analysis & Decision (Stages 14-15).

    Validates:
    - Result analysis
    - Research decision
    """

    def _setup_prior_stages(self, run_dir: Path) -> None:
        """Setup artifacts from stages 1-13."""
        for i in range(1, 14):
            stage_dir = run_dir / f"stage-{i:02d}"
            stage_dir.mkdir(parents=True, exist_ok=True)
            if i == 12:
                runs_dir = stage_dir / "runs"
                runs_dir.mkdir(parents=True, exist_ok=True)
                (runs_dir / "run-1.json").write_text('{"status": "completed"}', encoding="utf-8")
            else:
                (stage_dir / f"artifact-{i}.md").write_text(f"# Artifact {i}", encoding="utf-8")

    def test_stage_14_result_analysis(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 14: Analyze results."""
        self._setup_prior_stages(run_dir)

        stage_dir = run_dir / f"stage-{Stage.RESULT_ANALYSIS:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.RESULT_ANALYSIS,
                run_dir=run_dir,
                run_id="e2e-full-014",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "analysis.md" in result.artifacts

    def test_stage_15_research_decision(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 15: Make research decision."""
        self._setup_prior_stages(run_dir)
        stage14_dir = run_dir / "stage-14"
        stage14_dir.mkdir(parents=True, exist_ok=True)
        (stage14_dir / "analysis.md").write_text("# Analysis", encoding="utf-8")

        stage_dir = run_dir / f"stage-{Stage.RESEARCH_DECISION:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.RESEARCH_DECISION,
                run_dir=run_dir,
                run_id="e2e-full-015",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "decision.md" in result.artifacts


# ============================================================================
# Test Set 7: Phase G - Paper Writing (Stages 16-19)
# ============================================================================


class TestPhaseG_PaperWriting:
    """Test Phase G: Paper Writing (Stages 16-19).

    Validates:
    - Paper outline
    - Paper draft
    - Peer review
    - Paper revision
    """

    def _setup_prior_stages(self, run_dir: Path) -> None:
        """Setup artifacts from stages 1-15."""
        for i in range(1, 16):
            stage_dir = run_dir / f"stage-{i:02d}"
            stage_dir.mkdir(parents=True, exist_ok=True)
            if i == 12:
                # Create experiment run data
                runs_dir = stage_dir / "runs"
                runs_dir.mkdir(parents=True, exist_ok=True)
                (runs_dir / "run-1.json").write_text(
                    '{"status": "completed", "metrics": {"accuracy": 0.85}}', encoding="utf-8"
                )
            elif i == 15:
                (stage_dir / "decision.md").write_text("# Decision: PROCEED", encoding="utf-8")
                (stage_dir / "analysis.md").write_text("# Analysis", encoding="utf-8")
            else:
                (stage_dir / f"artifact-{i}.md").write_text(f"# Artifact {i}", encoding="utf-8")

    def test_stage_16_paper_outline(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 16: Create paper outline."""
        self._setup_prior_stages(run_dir)

        stage_dir = run_dir / f"stage-{Stage.PAPER_OUTLINE:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.PAPER_OUTLINE,
                run_dir=run_dir,
                run_id="e2e-full-016",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "outline.md" in result.artifacts

    def test_stage_17_paper_draft(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 17: Write paper draft."""
        self._setup_prior_stages(run_dir)
        stage16_dir = run_dir / "stage-16"
        stage16_dir.mkdir(parents=True, exist_ok=True)
        (stage16_dir / "outline.md").write_text("# Outline", encoding="utf-8")

        stage_dir = run_dir / f"stage-{Stage.PAPER_DRAFT:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.PAPER_DRAFT,
                run_dir=run_dir,
                run_id="e2e-full-017",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "paper_draft.md" in result.artifacts

    def test_stage_18_peer_review(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 18: Peer review."""
        self._setup_prior_stages(run_dir)
        stage17_dir = run_dir / "stage-17"
        stage17_dir.mkdir(parents=True, exist_ok=True)
        (stage17_dir / "paper_draft.md").write_text("# Paper Draft", encoding="utf-8")

        stage_dir = run_dir / f"stage-{Stage.PEER_REVIEW:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.PEER_REVIEW,
                run_dir=run_dir,
                run_id="e2e-full-018",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "reviews.md" in result.artifacts

    def test_stage_19_paper_revision(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 19: Revise paper."""
        self._setup_prior_stages(run_dir)
        stage17_dir = run_dir / "stage-17"
        stage18_dir = run_dir / "stage-18"
        stage17_dir.mkdir(parents=True, exist_ok=True)
        stage18_dir.mkdir(parents=True, exist_ok=True)
        (stage17_dir / "paper_draft.md").write_text("# Paper Draft", encoding="utf-8")
        (stage18_dir / "reviews.md").write_text("# Reviews", encoding="utf-8")

        stage_dir = run_dir / f"stage-{Stage.PAPER_REVISION:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.PAPER_REVISION,
                run_dir=run_dir,
                run_id="e2e-full-019",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "paper_revised.md" in result.artifacts


# ============================================================================
# Test Set 8: Phase H - Finalization (Stages 20-23)
# ============================================================================


class TestPhaseH_Finalization:
    """Test Phase H: Finalization (Stages 20-23).

    Validates:
    - Quality gate
    - Knowledge archive
    - Export publish
    - Citation verify
    """

    def _setup_prior_stages(self, run_dir: Path) -> None:
        """Setup artifacts from stages 1-19."""
        for i in range(1, 20):
            stage_dir = run_dir / f"stage-{i:02d}"
            stage_dir.mkdir(parents=True, exist_ok=True)
            if i == 10:
                # Create code directory for stage 10
                code_dir = stage_dir / "code"
                code_dir.mkdir(parents=True, exist_ok=True)
                (code_dir / "main.py").write_text("print('test')", encoding="utf-8")
            elif i == 12:
                # Create experiment run data
                runs_dir = stage_dir / "runs"
                runs_dir.mkdir(parents=True, exist_ok=True)
                (runs_dir / "run-1.json").write_text(
                    '{"status": "completed", "metrics": {"accuracy": 0.85}}', encoding="utf-8"
                )
            elif i == 19:
                (stage_dir / "paper_revised.md").write_text("# Revised Paper", encoding="utf-8")
            else:
                (stage_dir / f"artifact-{i}.md").write_text(f"# Artifact {i}", encoding="utf-8")

    def test_stage_20_quality_gate(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 20: Quality gate."""
        self._setup_prior_stages(run_dir)

        stage_dir = run_dir / f"stage-{Stage.QUALITY_GATE:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.QUALITY_GATE,
                run_dir=run_dir,
                run_id="e2e-full-020",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "quality_report.json" in result.artifacts

    def test_stage_21_knowledge_archive(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 21: Knowledge archive."""
        self._setup_prior_stages(run_dir)

        stage_dir = run_dir / f"stage-{Stage.KNOWLEDGE_ARCHIVE:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.KNOWLEDGE_ARCHIVE,
                run_dir=run_dir,
                run_id="e2e-full-021",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "archive.md" in result.artifacts

    def test_stage_22_export_publish(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 22: Export and publish."""
        self._setup_prior_stages(run_dir)
        stage19_dir = run_dir / "stage-19"
        stage19_dir.mkdir(parents=True, exist_ok=True)
        (stage19_dir / "paper_revised.md").write_text("# Revised Paper", encoding="utf-8")

        stage_dir = run_dir / f"stage-{Stage.EXPORT_PUBLISH:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)
        # Create required code/ output directory
        code_dir = stage_dir / "code"
        code_dir.mkdir(parents=True, exist_ok=True)
        (code_dir / "main.py").write_text("print('test')", encoding="utf-8")

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.EXPORT_PUBLISH,
                run_dir=run_dir,
                run_id="e2e-full-022",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "paper_final.md" in result.artifacts

    def test_stage_23_citation_verify(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Stage 23: Citation verification."""
        self._setup_prior_stages(run_dir)
        stage22_dir = run_dir / "stage-22"
        stage22_dir.mkdir(parents=True, exist_ok=True)
        (stage22_dir / "paper_final.md").write_text(
            "# Final Paper\n\n[1] Smith et al.", encoding="utf-8"
        )

        stage_dir = run_dir / f"stage-{Stage.CITATION_VERIFY:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.CITATION_VERIFY,
                run_dir=run_dir,
                run_id="e2e-full-023",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        assert result.status == StageStatus.DONE, f"Stage failed: {result.error}"
        assert "verification_report.json" in result.artifacts


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for cross-stage workflows."""

    def test_pipeline_contract_completeness(self) -> None:
        """Test that all 23 stages have contracts defined."""
        assert len(CONTRACTS) == 23, "Expected 23 stage contracts"
        for stage in Stage:
            assert stage in CONTRACTS, f"Missing contract for stage {stage.name}"

    def test_stage_sequence_integrity(self) -> None:
        """Test that stage sequence is continuous."""
        for i in range(1, 23):
            assert Stage(i) is not None, f"Missing stage {i}"
            assert Stage(i).name is not None, f"Stage {i} missing name"

    def test_all_stages_executable(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Test that all stages can be executed without crashing."""
        # Setup minimal prior artifacts
        for i in range(1, 24):
            stage_dir = run_dir / f"stage-{i:02d}"
            stage_dir.mkdir(parents=True, exist_ok=True)
            # Create minimal required artifacts for each stage
            if i > 1:
                prior_dir = run_dir / f"stage-{i - 1:02d}"
                prior_dir.mkdir(parents=True, exist_ok=True)
                (prior_dir / f"artifact-{i - 1}.md").write_text(
                    f"# Artifact {i - 1}", encoding="utf-8"
                )

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            for stage in Stage:
                result = execute_stage(
                    stage,
                    run_dir=run_dir,
                    run_id=f"e2e-integration-{int(stage):02d}",
                    config=mock_config,
                    adapters=adapters,
                    auto_approve_gates=True,
                )
                # All stages should complete without exception
                assert result is not None, f"Stage {stage.name} returned None"


# ============================================================================
# Regression Tests
# ============================================================================


class TestRegression:
    """Regression tests for bug fixes."""

    def test_missing_input_artifact_handling(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Test that missing input artifacts are handled gracefully."""
        stage_dir = run_dir / f"stage-{Stage.PROBLEM_DECOMPOSE:02d}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = MockLLMClient()

        with patch("berb.pipeline.executor.create_llm_client", return_value=llm):
            result = execute_stage(
                Stage.PROBLEM_DECOMPOSE,
                run_dir=run_dir,
                run_id="e2e-regression-001",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        # Should fail gracefully with appropriate error
        assert result.status == StageStatus.FAILED
        assert "Missing input" in (result.error or "")

    def test_llm_unavailable_fallback(
        self, run_dir: Path, mock_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        """Test that stages handle LLM unavailability gracefully."""
        stage1_dir = run_dir / "stage-01"
        stage1_dir.mkdir(parents=True, exist_ok=True)

        with patch(
            "berb.pipeline.executor.create_llm_client", side_effect=Exception("LLM unavailable")
        ):
            result = execute_stage(
                Stage.TOPIC_INIT,
                run_dir=run_dir,
                run_id="e2e-regression-002",
                config=mock_config,
                adapters=adapters,
                auto_approve_gates=True,
            )

        # Should not crash, may produce default output
        assert result is not None
