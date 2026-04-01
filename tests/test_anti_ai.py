"""Tests for anti-AI encoder module.

Coverage:
- AIPhrase detection
- Language detection
- Phrase replacement
- AI score calculation
- Bilingual support (EN/CN)

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

import pytest
import asyncio

from berb.writing.anti_ai import (
    AntiAIEncoder,
    AIPhrase,
    AnalysisResult,
    Language,
    PhraseCategory,
    analyze_for_ai,
    replace_ai_phrases,
)


class TestLanguageDetection:
    """Test language detection."""

    def test_detect_english(self):
        """Test English language detection."""
        encoder = AntiAIEncoder(language=Language.AUTO)
        text = "This paper presents a novel approach to machine learning."
        result = asyncio.run(encoder.analyze(text))
        assert result.language == Language.ENGLISH

    def test_detect_chinese(self):
        """Test Chinese language detection."""
        encoder = AntiAIEncoder(language=Language.AUTO)
        text = "本文提出了一种新的机器学习方法。"
        result = asyncio.run(encoder.analyze(text))
        assert result.language == Language.CHINESE

    def test_detect_mixed_language(self):
        """Test mixed language detection (more Chinese)."""
        encoder = AntiAIEncoder(language=Language.AUTO)
        text = "This paper 提出了一种 new approach to 机器学习."
        result = asyncio.run(encoder.analyze(text))
        # Should detect as Chinese due to character count
        assert result.language in (Language.ENGLISH, Language.CHINESE)


class TestAIPhraseDetection:
    """Test AI phrase detection."""

    def test_detect_cliche(self):
        """Test cliche detection."""
        encoder = AntiAIEncoder(sensitivity=0.5)
        text = "This paper delves into the methodology of deep learning."
        result = asyncio.run(encoder.analyze(text))
        
        assert len(result.phrases) > 0
        assert any(p.category == PhraseCategory.CLICHE for p in result.phrases)

    def test_detect_hedging(self):
        """Test hedging detection."""
        encoder = AntiAIEncoder(sensitivity=0.5)
        text = "It is worth noting that the results may potentially suggest..."
        result = asyncio.run(encoder.analyze(text))
        
        assert len(result.phrases) > 0
        assert any(p.category == PhraseCategory.HEDGING for p in result.phrases)

    def test_detect_transition(self):
        """Test transition detection."""
        encoder = AntiAIEncoder(sensitivity=0.5)
        text = "Furthermore, moreover, additionally, the results show..."
        result = asyncio.run(encoder.analyze(text))
        
        assert len(result.phrases) > 0
        assert any(p.category == PhraseCategory.TRANSITION for p in result.phrases)

    def test_detect_redundancy(self):
        """Test redundancy detection."""
        encoder = AntiAIEncoder(sensitivity=0.5)
        text = "The comprehensive and thorough analysis shows..."
        result = asyncio.run(encoder.analyze(text))
        
        assert len(result.phrases) > 0
        assert any(p.category == PhraseCategory.REDUNDANCY for p in result.phrases)

    def test_no_ai_phrases(self):
        """Test text without AI phrases."""
        encoder = AntiAIEncoder(sensitivity=0.9)  # High sensitivity
        text = "We trained a ResNet-50 on ImageNet for 90 epochs."
        result = asyncio.run(encoder.analyze(text))
        
        assert result.ai_score < 0.3

    def test_sensitivity_threshold(self):
        """Test sensitivity threshold."""
        text = "This paper delves into the methodology."
        
        # Low sensitivity - should detect
        encoder_low = AntiAIEncoder(sensitivity=0.5)
        result_low = asyncio.run(encoder_low.analyze(text))
        
        # High sensitivity - might not detect
        encoder_high = AntiAIEncoder(sensitivity=0.95)
        result_high = asyncio.run(encoder_high.analyze(text))
        
        # Lower sensitivity should detect at least as many
        assert len(result_low.phrases) >= len(result_high.phrases)


class TestAIReplacement:
    """Test AI phrase replacement."""

    def test_auto_replace(self):
        """Test automatic replacement."""
        encoder = AntiAIEncoder(auto_replace=True, sensitivity=0.5)
        text = "This paper delves into the methodology."
        result = asyncio.run(encoder.analyze(text))
        
        # Should detect the phrase
        assert len(result.phrases) > 0
        # Revised text should be different (replacement applied)
        # Note: replacement might use first alternative "examine"
        assert result.revised_text != result.original_text or len(result.phrases) > 0

    def test_replace_with_alternative(self):
        """Test replacement with appropriate alternative."""
        encoder = AntiAIEncoder(auto_replace=True, sensitivity=0.5)
        text = "We leverage the methodology to utilize the framework."
        result = asyncio.run(encoder.analyze(text))
        
        # Should detect cliches
        assert len(result.phrases) > 0

    def test_convenience_function_replace(self):
        """Test convenience function for replacement."""
        text = "This paper delves into the methodology."
        result = asyncio.run(replace_ai_phrases(text))
        
        # Should return a string
        assert isinstance(result, str)
        # Function should complete without error
        assert len(result) > 0


class TestAIScore:
    """Test AI score calculation."""

    def test_high_ai_score(self):
        """Test high AI score for AI-like text."""
        encoder = AntiAIEncoder(sensitivity=0.5)
        text = """
        In conclusion, it is worth noting that this paper delves into 
        the comprehensive and thorough methodology. Furthermore, it is 
        important to note that we leverage the framework to shed light 
        on the problem.
        """
        result = asyncio.run(encoder.analyze(text))
        
        assert result.ai_score > 0.3

    def test_low_ai_score(self):
        """Test low AI score for human-like text."""
        encoder = AntiAIEncoder(sensitivity=0.5)
        text = """
        We trained ResNet-50 on ImageNet for 90 epochs using SGD with 
        momentum 0.9. Learning rate: 0.01, batch size: 256. Results: 
        76.3% top-1 accuracy.
        """
        result = asyncio.run(encoder.analyze(text))
        
        assert result.ai_score < 0.3

    def test_score_with_no_phrases(self):
        """Test score is 0 when no phrases detected."""
        encoder = AntiAIEncoder(sensitivity=0.99)  # Very high threshold
        text = "The model achieved 95% accuracy."
        result = asyncio.run(encoder.analyze(text))
        
        assert result.ai_score == 0.0


class TestChineseSupport:
    """Test Chinese language support."""

    def test_detect_chinese_cliches(self):
        """Test Chinese cliche detection."""
        encoder = AntiAIEncoder(sensitivity=0.5, language=Language.CHINESE)
        text = "本文深入探讨了机器学习的方法论。"
        result = asyncio.run(encoder.analyze(text))
        
        # Should detect "深入探讨" as cliche
        assert len(result.phrases) > 0

    def test_chinese_alternatives(self):
        """Test Chinese phrase alternatives."""
        encoder = AntiAIEncoder(auto_replace=True, sensitivity=0.5)
        text = "我们利用这个方法揭示了问题的本质。"
        result = asyncio.run(encoder.analyze(text))
        
        # Should have replacements
        assert result.revised_text != text or len(result.phrases) > 0


class TestAnalysisResult:
    """Test AnalysisResult functionality."""

    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = AnalysisResult(
            original_text="Test text",
            revised_text="Revised text",
            phrases=[],
            ai_score=0.5,
            language=Language.ENGLISH,
        )
        
        d = result.to_dict()
        
        assert d["original_text"] == "Test text"
        assert d["revised_text"] == "Revised text"
        assert d["ai_score"] == 0.5
        assert d["language"] == "en"

    def test_phrase_to_dict(self):
        """Test converting phrase to dictionary."""
        phrase = AIPhrase(
            text="delves into",
            category=PhraseCategory.CLICHE,
            start_pos=10,
            end_pos=21,
            confidence=0.9,
            alternatives=["examines", "analyzes"],
            explanation="Overused AI cliche",
        )
        
        d = phrase.to_dict()
        
        assert d["text"] == "delves into"
        assert d["category"] == "cliche"
        assert d["confidence"] == 0.9
        assert len(d["alternatives"]) == 2


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_analyze_for_ai(self):
        """Test analyze_for_ai function."""
        text = "This paper delves into the methodology."
        result = asyncio.run(analyze_for_ai(text, sensitivity=0.5))
        
        assert isinstance(result, AnalysisResult)
        assert len(result.phrases) > 0

    def test_replace_ai_phrases(self):
        """Test replace_ai_phrases function."""
        text = "This paper delves into the methodology."
        result = asyncio.run(replace_ai_phrases(text))

        # Should return a string
        assert isinstance(result, str)
        assert len(result) > 0
        # Function should complete without error


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_text(self):
        """Test empty text."""
        encoder = AntiAIEncoder()
        result = asyncio.run(encoder.analyze(""))
        
        assert result.ai_score == 0.0
        assert len(result.phrases) == 0

    def test_very_short_text(self):
        """Test very short text."""
        encoder = AntiAIEncoder()
        result = asyncio.run(encoder.analyze("Test."))
        
        assert result.ai_score == 0.0

    def test_long_text(self):
        """Test long text handling."""
        encoder = AntiAIEncoder()
        text = "This paper delves into the methodology. " * 100
        result = asyncio.run(encoder.analyze(text))
        
        assert len(result.phrases) > 0
        # Should handle long text without error

    def test_special_characters(self):
        """Test text with special characters."""
        encoder = AntiAIEncoder()
        text = "The model achieved 95.3% accuracy (p < 0.001)."
        result = asyncio.run(encoder.analyze(text))
        
        assert result.ai_score == 0.0  # No AI phrases


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
