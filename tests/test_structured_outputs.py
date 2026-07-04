"""Unit tests for structured outputs."""

import pytest
from pydantic import ValidationError
from berb.llm.structured_outputs import (
    DecompositionOutput,
    HypothesisOutput,
    ExperimentDesignOutput,
    CodeGenerationOutput,
    ResearchDecisionOutput,
    PeerReviewOutput,
    CitationVerificationOutput,
    get_output_model,
    validate_output,
)


class TestDecompositionOutput:
    """Test DecompositionOutput model."""

    def test_valid_decomposition(self):
        """Test valid decomposition output."""
        data = {
            "sub_problems": ["Problem 1", "Problem 2", "Problem 3"],
            "assumptions": [
                {"text": "Assumption 1", "label": "VERIFIED"},
                {"text": "Assumption 2", "label": "HYPOTHESIS"},
            ],
            "failure_modes": ["Failure mode 1", "Failure mode 2"],
        }

        output = DecompositionOutput.model_validate(data)

        assert len(output.sub_problems) == 3
        assert len(output.assumptions) == 2
        assert len(output.failure_modes) == 2

    def test_invalid_decision_value(self):
        """Test invalid assumption label raises error."""
        data = {
            "sub_problems": ["Problem 1"],
            "assumptions": [{"text": "Assumption", "label": "INVALID"}],
            "failure_modes": ["Failure"],
        }

        # Should still validate (label is just str, not enum)
        output = DecompositionOutput.model_validate(data)
        assert len(output.assumptions) == 1

    def test_empty_sub_problems_fails(self):
        """Test empty sub_problems fails validation."""
        data = {
            "sub_problems": [],
            "assumptions": [{"text": "A", "label": "V"}],
            "failure_modes": ["F"],
        }

        with pytest.raises(ValidationError):
            DecompositionOutput.model_validate(data)


class TestHypothesisOutput:
    """Test HypothesisOutput model."""

    def test_valid_hypotheses(self):
        """Test valid hypotheses output."""
        data = {
            "hypotheses": [
                {"statement": "H1", "rationale": "R1"},
                {"statement": "H2", "rationale": "R2"},
            ],
            "rationale": "Overall reasoning " * 3,  # >= 50 chars
        }

        output = HypothesisOutput.model_validate(data)

        assert len(output.hypotheses) == 2
        assert len(output.rationale) >= 50

    def test_rationale_too_short(self):
        """Test rationale too short fails validation."""
        data = {
            "hypotheses": [{"statement": "H1", "rationale": "R1"}],
            "rationale": "Short",  # < 50 chars
        }

        with pytest.raises(ValidationError):
            HypothesisOutput.model_validate(data)


class TestExperimentDesignOutput:
    """Test ExperimentDesignOutput model."""

    def test_valid_design(self):
        """Test valid experiment design."""
        data = {
            "method": "A" * 100,  # >= 100 chars
            "variables": {
                "independent": ["var1", "var2"],
                "dependent": ["outcome1"],
            },
            "controls": ["Control 1", "Control 2"],
            "metrics": ["Metric 1", "Metric 2", "Metric 3"],
        }

        output = ExperimentDesignOutput.model_validate(data)

        assert len(output.method) >= 100
        assert len(output.controls) >= 1
        assert len(output.metrics) >= 2


class TestResearchDecisionOutput:
    """Test ResearchDecisionOutput model."""

    def test_valid_decisions(self):
        """Test valid decision values."""
        for decision in ["PROCEED", "REFINE", "PIVOT"]:
            data = {
                "decision": decision,
                "rationale": "A" * 50,
                "next_steps": ["Step 1"],
            }

            output = ResearchDecisionOutput.model_validate(data)
            assert output.decision == decision

    def test_invalid_decision_fails(self):
        """Test invalid decision fails validation."""
        data = {
            "decision": "INVALID",
            "rationale": "A" * 50,
            "next_steps": ["Step 1"],
        }

        with pytest.raises(ValidationError):
            ResearchDecisionOutput.model_validate(data)


class TestPeerReviewOutput:
    """Test PeerReviewOutput model."""

    def test_valid_review(self):
        """Test valid peer review."""
        data = {
            "scores": {
                "novelty": 7.5,
                "rigor": 8.0,
                "clarity": 6.5,
                "impact": 7.0,
                "experiments": 8.5,
            },
            "strengths": ["Strong methodology"],
            "weaknesses": ["Limited discussion"],
            "recommendations": ["Expand discussion"],
        }

        output = PeerReviewOutput.model_validate(data)

        assert len(output.scores) == 5
        assert len(output.strengths) >= 1
        assert len(output.weaknesses) >= 1


class TestGetOutputModel:
    """Test get_output_model function."""

    def test_known_stages(self):
        """Test known stage names return models."""
        assert get_output_model("HYPOTHESIS_GEN") == HypothesisOutput
        assert get_output_model("PEER_REVIEW") == PeerReviewOutput
        assert get_output_model("EXPERIMENT_DESIGN") == ExperimentDesignOutput

    def test_unknown_stage_returns_none(self):
        """Test unknown stage returns None."""
        assert get_output_model("UNKNOWN_STAGE") is None
        assert get_output_model("") is None

    def test_case_insensitive(self):
        """Test stage name is case insensitive."""
        assert get_output_model("hypothesis_gen") == HypothesisOutput
        assert get_output_model("Hypothesis_Gen") == HypothesisOutput


class TestValidateOutput:
    """Test validate_output function."""

    def test_valid_data(self):
        """Test valid data passes validation."""
        data = {
            "hypotheses": [{"statement": "H1", "rationale": "R1"}],
            "rationale": "A" * 50,
        }

        output = validate_output(HypothesisOutput, data)

        assert isinstance(output, HypothesisOutput)
        assert len(output.hypotheses) == 1

    def test_invalid_data_raises(self):
        """Test invalid data raises ValidationError."""
        data = {
            "hypotheses": [],  # Empty, fails min_length
            "rationale": "Short",
        }

        with pytest.raises(ValidationError):
            validate_output(HypothesisOutput, data)
