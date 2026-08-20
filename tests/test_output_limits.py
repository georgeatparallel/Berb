"""Unit tests for output token limits."""

from berb.llm.output_limits import (
    DEFAULT_TOKEN_LIMIT,
    OUTPUT_TOKEN_LIMITS,
    Stage,
    get_all_limits,
    get_stage_token_limit,
    validate_response_length,
)


class TestStageEnum:
    """Test Stage enumeration."""

    def test_all_stages_defined(self):
        """Verify all 23 stages are defined."""
        assert len(Stage) == 23
        assert Stage.TOPIC_INIT == 1
        assert Stage.CITATION_VERIFY == 23

    def test_stage_names(self):
        """Verify stage names match pipeline."""
        assert Stage.HYPOTHESIS_GEN.name == "HYPOTHESIS_GEN"
        assert Stage.PAPER_DRAFT.name == "PAPER_DRAFT"


class TestOutputTokenLimits:
    """Test output token limits configuration."""

    def test_all_stages_have_limits(self):
        """Verify every stage has a token limit defined."""
        for stage in Stage:
            assert stage in OUTPUT_TOKEN_LIMITS, f"Missing limit for {stage.name}"

    def test_limits_are_reasonable(self):
        """Verify token limits are within reasonable ranges."""
        for stage, limit in OUTPUT_TOKEN_LIMITS.items():
            assert 500 <= limit <= 10000, f"Unusual limit {limit} for {stage.name}"

    def test_specific_limits(self):
        """Verify specific stage limits match expected values."""
        assert OUTPUT_TOKEN_LIMITS[Stage.HYPOTHESIS_GEN] == 2000
        assert OUTPUT_TOKEN_LIMITS[Stage.PAPER_DRAFT] == 8000
        assert OUTPUT_TOKEN_LIMITS[Stage.PEER_REVIEW] == 800  # Concise reviews!
        assert OUTPUT_TOKEN_LIMITS[Stage.QUALITY_GATE] == 500  # Very concise


class TestGetStageTokenLimit:
    """Test get_stage_token_limit function."""

    def test_stage_enum_input(self):
        """Test with Stage enum input."""
        assert get_stage_token_limit(Stage.HYPOTHESIS_GEN) == 2000
        assert get_stage_token_limit(Stage.PAPER_DRAFT) == 8000

    def test_int_input(self):
        """Test with integer stage number."""
        assert get_stage_token_limit(8) == 2000
        assert get_stage_token_limit(17) == 8000

    def test_string_input(self):
        """Test with string stage name."""
        assert get_stage_token_limit("HYPOTHESIS_GEN") == 2000
        assert get_stage_token_limit("paper_draft") == 8000

    def test_invalid_stage_returns_default(self):
        """Test invalid stage returns default limit."""
        assert get_stage_token_limit(999) == DEFAULT_TOKEN_LIMIT
        assert get_stage_token_limit("INVALID_STAGE") == DEFAULT_TOKEN_LIMIT
        assert get_stage_token_limit(-1) == DEFAULT_TOKEN_LIMIT


class TestGetAllLimits:
    """Test get_all_limits function."""

    def test_returns_dict(self):
        """Verify returns dictionary."""
        limits = get_all_limits()
        assert isinstance(limits, dict)

    def test_all_stages_included(self):
        """Verify all stages are included."""
        limits = get_all_limits()
        assert len(limits) == 23
        assert "HYPOTHESIS_GEN" in limits
        assert "PAPER_DRAFT" in limits

    def test_values_match(self):
        """Verify values match OUTPUT_TOKEN_LIMITS."""
        limits = get_all_limits()
        for stage, expected_limit in OUTPUT_TOKEN_LIMITS.items():
            assert limits[stage.name] == expected_limit


class TestValidateResponseLength:
    """Test validate_response_length function."""

    def test_valid_short_response(self):
        """Test valid short response."""
        content = "This is a short response."  # ~7 tokens
        is_valid, estimated, limit = validate_response_length(
            content, Stage.QUALITY_GATE
        )

        assert is_valid is True
        assert estimated <= limit

    def test_invalid_long_response(self):
        """Test invalid long response."""
        # Generate content exceeding limit
        content = "test " * 3000  # ~1500 tokens, exceeds 500 limit
        is_valid, estimated, limit = validate_response_length(
            content, Stage.QUALITY_GATE
        )

        assert is_valid is False
        assert estimated > limit

    def test_token_estimation(self):
        """Test token estimation accuracy."""
        # 100 characters ≈ 25 tokens
        content = "a" * 100
        is_valid, estimated, limit = validate_response_length(content, Stage.TOPIC_INIT)

        assert estimated == 25  # 100 // 4 = 25

    def test_returns_limit_info(self):
        """Test returns limit information."""
        content = "test"
        is_valid, estimated, limit = validate_response_length(
            content, Stage.PAPER_DRAFT
        )

        assert limit == 8000  # PAPER_DRAFT limit


class TestTokenLimitRationale:
    """Test token limit rationale (documentation tests)."""

    def test_simple_stages_have_low_limits(self):
        """Verify simple stages have lower limits."""
        # Screening and verification should be concise
        assert OUTPUT_TOKEN_LIMITS[Stage.LITERATURE_SCREEN] <= 2500
        assert OUTPUT_TOKEN_LIMITS[Stage.QUALITY_GATE] <= 1000
        assert OUTPUT_TOKEN_LIMITS[Stage.CITATION_VERIFY] <= 3000

    def test_complex_stages_have_high_limits(self):
        """Verify complex stages have higher limits."""
        # Drafting and code generation need more tokens
        assert OUTPUT_TOKEN_LIMITS[Stage.PAPER_DRAFT] >= 6000
        assert OUTPUT_TOKEN_LIMITS[Stage.CODE_GENERATION] >= 4000
        assert OUTPUT_TOKEN_LIMITS[Stage.PAPER_REVISION] >= 4000

    def test_peer_review_concise(self):
        """Verify peer review is intentionally concise (score + brief reasoning)."""
        # Peer review should be concise - just scores and key points
        assert OUTPUT_TOKEN_LIMITS[Stage.PEER_REVIEW] == 800
