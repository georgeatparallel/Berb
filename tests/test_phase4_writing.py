"""Tests for Phase 4: Writing Enhancements (Anti-AI, Citation Verification).

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from berb.writing.anti_ai import (
    AntiAIEncoder,
    EncoderConfig,
    AIPhrases,
    DetectionResult,
    create_encoder_from_env,
)
from berb.pipeline.citation_verification import (
    CitationVerifier,
    VerifierConfig,
    VerificationLayer,
    CitationVerificationResult,
    create_verifier_from_env,
)


# ============== Anti-AI Encoder Tests ==============

class TestEncoderConfig:
    """Test EncoderConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = EncoderConfig()
        assert config.language == ["en", "zh"]
        assert config.strictness == 0.7
        assert config.preserve_meaning is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = EncoderConfig(
            language=["en"],
            strictness=0.9,
            preserve_meaning=False,
        )
        assert config.language == ["en"]
        assert config.strictness == 0.9
        assert config.preserve_meaning is False


class TestAIPhrases:
    """Test AIPhrases dataclass."""

    def test_to_dict(self):
        """Test phrase to_dict method."""
        phrase = AIPhrases(
            phrase="delve into",
            position=10,
            confidence=0.8,
            category="cliche",
            suggestion="examine",
            reason="Common AI phrase",
        )
        d = phrase.to_dict()
        assert d["phrase"] == "delve into"
        assert d["category"] == "cliche"
        assert d["suggestion"] == "examine"


class TestDetectionResult:
    """Test DetectionResult dataclass."""

    def test_to_dict(self):
        """Test result to_dict method."""
        result = DetectionResult(
            text="Test text",
            ai_score=0.65,
            word_count=100,
            ai_word_percentage=15.0,
        )
        d = result.to_dict()
        assert d["text"] == "Test text"
        assert d["ai_score"] == 0.65
        assert d["word_count"] == 100


class TestAntiAIEncoder:
    """Test AntiAIEncoder."""

    def test_encoder_initialization(self):
        """Test encoder initialization."""
        encoder = AntiAIEncoder()
        assert encoder.config.strictness == 0.7

    def test_encoder_custom_config(self):
        """Test encoder with custom config."""
        config = EncoderConfig(strictness=0.9)
        encoder = AntiAIEncoder(config)
        assert encoder.config.strictness == 0.9

    def test_detect_english_ai_phrases(self):
        """Test English AI phrase detection."""
        encoder = AntiAIEncoder(EncoderConfig(language=["en"]))
        
        text = "This is a testament to the power of deep learning."
        result = encoder.detect(text)
        
        assert result.ai_score > 0
        assert len(result.phrases) > 0
        assert any("testament" in p.phrase.lower() for p in result.phrases)

    def test_detect_chinese_ai_phrases(self):
        """Test Chinese AI phrase detection."""
        encoder = AntiAIEncoder(EncoderConfig(language=["zh"]))
        
        text = "值得注意的是，这个发现很重要。"
        result = encoder.detect(text)
        
        assert result.ai_score > 0
        assert len(result.phrases) > 0
        assert any("值得" in p.phrase for p in result.phrases)

    def test_rewrite_english(self):
        """Test English AI phrase rewriting."""
        encoder = AntiAIEncoder(EncoderConfig(language=["en"]))
        
        text = "This is a testament to the power of deep learning."
        rewritten = encoder.rewrite(text)
        
        assert "testament" not in rewritten.lower()
        assert "evidence" in rewritten.lower() or "testament" not in rewritten

    def test_rewrite_chinese(self):
        """Test Chinese AI phrase rewriting."""
        encoder = AntiAIEncoder(EncoderConfig(language=["zh"]))
        
        text = "值得注意的是，这个发现很重要。"
        rewritten = encoder.rewrite(text)
        
        assert "值得" not in rewritten
        assert "重要" in rewritten

    def test_detect_batch(self):
        """Test batch detection."""
        encoder = AntiAIEncoder()
        
        texts = [
            "This is a testament to...",
            "值得注意的是...",
            "Normal human text.",
        ]
        
        results = encoder.detect_batch(texts)
        
        assert len(results) == 3
        assert results[0].ai_score > 0.5  # AI-like
        assert results[1].ai_score > 0.5  # AI-like

    def test_rewrite_batch(self):
        """Test batch rewriting."""
        encoder = AntiAIEncoder()
        
        texts = [
            "This is a testament to...",
            "值得注意的是...",
        ]
        
        rewritten = encoder.rewrite_batch(texts)
        
        assert len(rewritten) == 2
        assert "testament" not in rewritten[0].lower()

    def test_get_statistics(self):
        """Test writing statistics."""
        encoder = AntiAIEncoder()
        
        text = "This is a test. This is only a test. Testing one two three."
        stats = encoder.get_statistics(text)
        
        assert stats["word_count"] > 0
        assert stats["sentence_count"] > 0
        assert stats["avg_sentence_length"] > 0

    def test_categorize_en(self):
        """Test English phrase categorization."""
        encoder = AntiAIEncoder()
        
        category = encoder._categorize_en("delve into")
        assert category == "cliche"
        
        category = encoder._categorize_en("however")
        assert category == "transition"

    def test_categorize_zh(self):
        """Test Chinese phrase categorization."""
        encoder = AntiAIEncoder()
        
        category = encoder._categorize_zh("值得注意的是")
        assert category == "filler"
        
        category = encoder._categorize_zh("然而")
        assert category == "transition"

    def test_generate_recommendations(self):
        """Test recommendation generation."""
        encoder = AntiAIEncoder()
        
        phrases = [
            AIPhrases(phrase="test1", category="cliche", confidence=0.8),
            AIPhrases(phrase="test2", category="cliche", confidence=0.8),
            AIPhrases(phrase="test3", category="cliche", confidence=0.8),
        ]
        
        recommendations = encoder._generate_recommendations(phrases, 0.7)
        
        assert len(recommendations) > 0
        assert any("cliche" in r.lower() for r in recommendations)


# ============== Citation Verification Tests ==============

class TestVerifierConfig:
    """Test VerifierConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = VerifierConfig()
        assert config.enable_format_check is True
        assert config.enable_api_check is True
        assert config.min_confidence == 0.6

    def test_custom_config(self):
        """Test custom configuration."""
        config = VerifierConfig(
            enable_format_check=False,
            enable_content_check=False,
            min_confidence=0.8,
        )
        assert config.enable_format_check is False
        assert config.enable_content_check is False
        assert config.min_confidence == 0.8


class TestVerificationLayer:
    """Test VerificationLayer enum."""

    def test_layer_values(self):
        """Test layer enum values."""
        assert VerificationLayer.FORMAT.value == "format"
        assert VerificationLayer.API.value == "api"
        assert VerificationLayer.INFO.value == "info"
        assert VerificationLayer.CONTENT.value == "content"


class TestCitationVerificationResult:
    """Test CitationVerificationResult dataclass."""

    def test_to_dict(self):
        """Test result to_dict method."""
        result = CitationVerificationResult(
            is_valid=True,
            confidence=0.85,
            layers_passed=[VerificationLayer.FORMAT, VerificationLayer.API],
        )
        d = result.to_dict()
        assert d["is_valid"] is True
        assert d["confidence"] == 0.85
        assert "format" in d["layers_passed"]


class TestCitationVerifier:
    """Test CitationVerifier."""

    def test_verifier_initialization(self):
        """Test verifier initialization."""
        verifier = CitationVerifier()
        assert verifier.config.enable_format_check is True

    def test_verifier_custom_config(self):
        """Test verifier with custom config."""
        config = VerifierConfig(enable_api_check=False)
        verifier = CitationVerifier(config)
        assert verifier.config.enable_api_check is False

    def test_check_format_valid_doi(self):
        """Test DOI format validation."""
        verifier = CitationVerifier()
        
        citation = {"doi": "10.1038/s41586-021-03819-2"}
        # Note: This is async, but we'll test the pattern directly
        import re
        pattern = verifier.DOI_PATTERN
        assert pattern.match("10.1038/s41586-021-03819-2")

    def test_check_format_invalid_doi(self):
        """Test invalid DOI format."""
        verifier = CitationVerifier()
        
        pattern = verifier.DOI_PATTERN
        assert not pattern.match("invalid-doi")
        assert not pattern.match("10.100")  # Too short

    def test_check_format_valid_arxiv(self):
        """Test arXiv ID format validation."""
        verifier = CitationVerifier()
        
        pattern = verifier.ARXIV_PATTERN
        assert pattern.match("2103.12345")
        assert pattern.match("2103.12345v2")

    def test_check_format_invalid_arxiv(self):
        """Test invalid arXiv ID format."""
        verifier = CitationVerifier()
        
        pattern = verifier.ARXIV_PATTERN
        assert not pattern.match("invalid-arxiv")
        assert not pattern.match("1234")  # Too short

    @pytest.mark.asyncio
    async def test_verify_format_only(self):
        """Test verification with format check only."""
        config = VerifierConfig(
            enable_format_check=True,
            enable_api_check=False,
            enable_info_check=False,
            enable_content_check=False,
        )
        verifier = CitationVerifier(config)
        
        citation = {"doi": "10.1038/s41586-021-03819-2"}
        result = await verifier.verify(citation)
        
        assert VerificationLayer.FORMAT in result.layers_passed
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_verify_invalid_format(self):
        """Test verification with invalid format."""
        config = VerifierConfig(
            enable_format_check=True,
            enable_api_check=False,
            enable_info_check=False,
            enable_content_check=False,
        )
        verifier = CitationVerifier(config)
        
        citation = {"doi": "invalid-doi"}
        result = await verifier.verify(citation)
        
        assert VerificationLayer.FORMAT in result.layers_failed
        assert result.is_valid is False

    def test_fuzzy_match(self):
        """Test fuzzy string matching."""
        verifier = CitationVerifier()
        
        # High similarity (same words)
        assert verifier._fuzzy_match("Deep Learning", "deep learning") is True
        
        # Partial similarity (some overlap, but below 0.7 threshold)
        # "Deep Learning" vs "deep neural networks" = 1/4 = 25% overlap
        assert verifier._fuzzy_match("Deep Learning", "deep neural networks") is False
        
        # Good overlap test (2/3 = 67% - still below 0.7)
        assert verifier._fuzzy_match("Deep Learning Methods", "deep learning approaches") is False
        
        # Very high overlap (3/4 = 75% - above 0.7)
        assert verifier._fuzzy_match("Deep Learning Methods", "deep learning methods are") is True
        
        # Low similarity
        assert verifier._fuzzy_match("Deep Learning", "quantum physics") is False

    def test_keyword_alignment(self):
        """Test keyword-based alignment."""
        verifier = CitationVerifier()
        
        citation = {"title": "Deep Learning for Natural Language Processing"}
        claim = "This paper presents deep learning methods for NLP tasks."
        
        alignment = verifier._keyword_alignment(citation, claim)
        assert alignment > 0.5  # Should have good overlap

    def test_calculate_confidence(self):
        """Test confidence calculation."""
        verifier = CitationVerifier()
        
        # All layers passed
        result = CitationVerificationResult(
            layers_passed=[
                VerificationLayer.FORMAT,
                VerificationLayer.API,
                VerificationLayer.INFO,
                VerificationLayer.CONTENT,
            ],
            claim_alignment=0.9,
        )
        confidence = verifier._calculate_confidence(result)
        assert confidence > 0.8

        # Some layers failed
        result = CitationVerificationResult(
            layers_passed=[VerificationLayer.FORMAT],
            layers_failed=[VerificationLayer.API],
        )
        confidence = verifier._calculate_confidence(result)
        assert confidence < 0.5


# ============== Environment Configuration Tests ==============

class TestEnvironmentConfig:
    """Test environment-based configuration."""

    def test_create_encoder_from_env(self):
        """Test creating AntiAIEncoder from environment."""
        with patch.dict('os.environ', {
            'ANTI_AI_LANGUAGE': 'en',
            'ANTI_AI_STRICTNESS': '0.9',
        }, clear=False):
            encoder = create_encoder_from_env()
            assert encoder.config.language == ["en"]
            assert encoder.config.strictness == 0.9

    def test_create_verifier_from_env(self):
        """Test creating CitationVerifier from environment."""
        with patch.dict('os.environ', {
            'CITATION_ENABLE_API': 'false',
            'CITATION_TIMEOUT': '60',
        }, clear=False):
            verifier = create_verifier_from_env()
            assert verifier.config.enable_api_check is False
            assert verifier.config.timeout == 60


# ============== Integration Tests ==============

class TestWritingIntegration:
    """Test writing module integration."""

    def test_import_anti_ai_encoder(self):
        """Test AntiAIEncoder can be imported."""
        from berb.writing.anti_ai import AntiAIEncoder
        assert AntiAIEncoder is not None

    def test_import_citation_verifier(self):
        """Test CitationVerifier can be imported."""
        from berb.pipeline.citation_verification import CitationVerifier
        assert CitationVerifier is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
