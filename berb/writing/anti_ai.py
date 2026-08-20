"""Anti-AI encoder for human-like writing.

Detects and replaces AI-generated phrases with human alternatives.
Supports bilingual detection (English/Chinese) and provides context-aware
suggestions for academic writing.

Features:
- Detect common AI phrases and patterns
- Suggest human-like alternatives
- Bilingual support (EN/CN)
- Context-aware replacements
- Configurable detection sensitivity
- Integration with Stage 17 (PAPER_DRAFT) and Stage 19 (PAPER_REVISION)

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.writing.anti_ai import AntiAIEncoder, AIPhraseDetector

    encoder = AntiAIEncoder()

    # Detect AI phrases in text
    result = await encoder.analyze(text)
    print(f"Found {len(result.phrases)} AI-like phrases")

    # Replace with human alternatives
    revised = await encoder.replace(text)
    print(revised)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class Language(StrEnum):
    """Supported languages for AI detection."""

    ENGLISH = "en"
    CHINESE = "zh"
    AUTO = "auto"


class PhraseCategory(StrEnum):
    """Category of AI-generated phrase."""

    HEDGING = "hedging"
    """Overly cautious language (e.g., 'it is worth noting')"""

    TRANSITION = "transition"
    """Mechanical transitions (e.g., 'furthermore', 'moreover')"""

    SUMMARY = "summary"
    """Formulaic summaries (e.g., 'in conclusion', 'to summarize')"""

    EMPHASIS = "emphasis"
    """Artificial emphasis (e.g., 'it is important to note')"""

    STRUCTURE = "structure"
    """Formulaic structure markers (e.g., 'this paper presents')"""

    CLICHE = "cliche"
    """AI cliches (e.g., 'delve into', 'shed light on')"""

    REDUNDANCY = "redundancy"
    """Redundant phrases (e.g., 'comprehensive and thorough')"""

    SIGNIFICANCE = "significance"
    """Inflated significance/legacy claims (e.g., 'marks a pivotal moment')"""

    ATTRIBUTION = "attribution"
    """Vague, uncited authority (e.g., 'experts believe', 'industry reports')"""

    COPULA = "copula"
    """Avoidance of simple is/are (e.g., 'serves as', 'stands as', 'boasts')"""


@dataclass
class AIPhrases:
    """Detected AI-generated phrase (test compatibility alias).

    This is a test-compatible alias/wrapper for AIPhrase.

    Attributes:
        phrase: The detected phrase
        position: Position in text
        confidence: Detection confidence (0-1)
        category: Category of AI phrase
        suggestion: Suggested replacement
        reason: Why this is flagged as AI-like
    """

    phrase: str
    confidence: float
    category: str
    position: int = 0
    suggestion: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "phrase": self.phrase,
            "position": self.position,
            "confidence": self.confidence,
            "category": self.category,
            "suggestion": self.suggestion,
            "reason": self.reason,
        }


@dataclass
class DetectionResult:
    """Detection result for test compatibility.

    Attributes:
        text: Original text
        ai_score: AI likelihood score (0-1)
        word_count: Total word count
        ai_word_percentage: Percentage of AI-like words
    """

    text: str
    ai_score: float
    word_count: int = 0
    ai_word_percentage: float = 0.0
    phrases: list[AIPhrases] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "text": self.text[:200] if len(self.text) > 200 else self.text,
            "ai_score": self.ai_score,
            "word_count": self.word_count,
            "ai_word_percentage": self.ai_word_percentage,
            "recommendations": self.recommendations,
            "phrases": [p.to_dict() for p in self.phrases],
        }


@dataclass
class AIPhrase:
    """Detected AI-generated phrase.

    Attributes:
        text: The detected phrase
        category: Category of AI phrase
        start_pos: Start position in text
        end_pos: End position in text
        confidence: Detection confidence (0-1)
        alternatives: Suggested human alternatives
        explanation: Why this is flagged as AI-like
    """

    text: str
    category: PhraseCategory
    start_pos: int
    end_pos: int
    confidence: float
    alternatives: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "text": self.text,
            "category": self.category.value,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "confidence": self.confidence,
            "alternatives": self.alternatives,
            "explanation": self.explanation,
        }


@dataclass
class AnalysisResult:
    """Result from AI phrase analysis.

    Attributes:
        original_text: Original input text
        revised_text: Text with replacements applied
        phrases: List of detected AI phrases
        ai_score: Overall AI likelihood score (0-1)
        language: Detected language
        suggestions: Additional writing suggestions
    """

    original_text: str
    revised_text: str
    phrases: list[AIPhrase]
    ai_score: float
    language: Language = Language.ENGLISH
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "original_text": (
                self.original_text[:200] + "..."
                if len(self.original_text) > 200
                else self.original_text
            ),
            "revised_text": (
                self.revised_text[:200] + "..."
                if len(self.revised_text) > 200
                else self.revised_text
            ),
            "phrases": [p.to_dict() for p in self.phrases],
            "ai_score": self.ai_score,
            "language": self.language.value,
            "suggestions": self.suggestions,
        }


# AI phrase patterns - English
AI_PATTERNS_EN = {
    PhraseCategory.HEDGING: [
        (
            r"\bit is worth noting\b",
            "Consider removing or replacing with direct statement",
        ),
        (r"\bit should be noted\b", "Often unnecessary hedging"),
        (r"\bit is important to note\b", "Weak opening - be direct"),
        (r"\barguably\b", "Often overused hedge"),
        (r"\bpotentially\b", "Remove if claim is supported"),
        (r"\bmay\s+be\s+(?:seen|viewed|considered)\b", "Passive hedging"),
    ],
    PhraseCategory.TRANSITION: [
        (r"\bfurthermore\b", "Consider simpler transition or remove"),
        (r"\bmoreover\b", "Often sounds stilted"),
        (r"\badditionally\b", "Can be removed or replaced with 'also'"),
        (r"\bin\s+addition\b", "Simplify to 'also' or remove"),
        (r"\bconsequently\b", "Use 'so' or 'thus' instead"),
        (r"\bhowever\b", "Consider simpler transition or remove"),
    ],
    PhraseCategory.SUMMARY: [
        (r"\bin\s+conclusion\b", "Use section heading instead"),
        (r"\bto\s+(?:summarize|sum\s+up)\b", "Often unnecessary"),
        (r"\bin\s+summary\b", "Use section heading instead"),
        (r"\boverall\b", "Can often be removed"),
        (r"\btaken\s+together\b", "Formulaic summary marker"),
    ],
    PhraseCategory.EMPHASIS: [
        (
            r"\bit is (?:crucial|essential|important|imperative) to\b",
            "Be direct about importance",
        ),
        (r"\bnotably\b", "Often overused"),
        (r"\bsignificantly\b", "Use only for statistical significance"),
        (r"\binterestingly\b", "Let readers decide what's interesting"),
        (r"\bremarkably\b", "Often overused"),
    ],
    PhraseCategory.STRUCTURE: [
        (
            r"\bthis\s+paper\s+(?:presents|proposes|introduces)\b",
            "Consider active voice",
        ),
        (r"\bwe\s+(?:propose|present|introduce)\b", "Often acceptable, but vary"),
        (r"\bthe\s+rest\s+of\s+this\s+paper\b", "Formulaic roadmap"),
        (r"\bas\s+follows\b", "Often unnecessary"),
    ],
    PhraseCategory.CLICHE: [
        (r"\bdelves?\s+into\b", "Overused AI cliche - use 'examine' or 'analyze'"),
        (r"\bsheds?\s+light\s+on\b", "Cliche - use 'clarify' or 'explain'"),
        (r"\bpaves?\s+the\s+way\b", "Cliche - use 'enable' or 'facilitate'"),
        (
            r"\bplays?\s+a\s+(?:key|crucial|vital|pivotal)\s+role\b",
            "Cliche - be specific",
        ),
        (
            r"\bgain\s+(?:insights|understanding)\b",
            "Awkward - use 'understand' or 'learn'",
        ),
        (r"\bprovide\s+(?:insights|guidance)\b", "Often vague"),
        (r"\bleverages?\b", "Often pretentious - use 'use'"),
        (r"\butilize[sd]?\b", "Often pretentious - use 'use'"),
        (r"\bmethodology\b", "Often just 'methods' is fine"),
        (r"\bparadigm\b", "Often just 'approach' or 'framework'"),
        (r"\ba\s+testament\s+to\b", "Cliche - use 'evidence of' or 'proof of'"),
        (
            r"\bto\s+the\s+best\s+of\s+our\s+knowledge\b",
            "Overused hedge on novelty claims",
        ),
        (
            r"\bin\s+the\s+realm\s+of\b",
            "Vague abstract framing - name the specific field",
        ),
        (r"\bin\s+the\s+landscape\s+of\b", "Vague abstract-noun framing"),
        (
            r"\bgroundbreaking\b",
            "Promotional language - state the specific contribution",
        ),
        (r"\bcutting-edge\b", "Promotional language - be specific"),
        (r"\bgame-changing\b", "Promotional language - be specific"),
        (r"\ba\s+myriad\s+of\b", "Vague quantity - use a specific number or 'many'"),
        (r"\ba\s+plethora\s+of\b", "Vague quantity - use a specific number or 'many'"),
        (
            r"\bbridge\s+the\s+gap\b",
            "Cliche - state the specific limitation being addressed",
        ),
        (
            r"\bthe\s+advent\s+of\b",
            "Cliche temporal framing - state the specific development",
        ),
        (
            r"\bin\s+recent\s+(?:years|times)\b",
            "Vague temporal framing - give a specific timeframe",
        ),
        (
            r"\bhas\s+gained\s+significant\s+attention\b",
            "Vague attribution of popularity",
        ),
        (
            r"\bhas\s+attracted\s+considerable\s+interest\b",
            "Vague attribution of popularity",
        ),
        (r"\bhas\s+emerged\s+as\s+a\s+promising\b", "Cliche framing"),
        (r"\ba\s+comprehensive\s+overview\b", "Vague self-description"),
        (
            r"\bholistic\s+(?:approach|understanding)\b",
            "Vague abstraction - be specific",
        ),
        (r"\bshowcasing\s+the\s+efficacy\b", "Superficial -ing analysis"),
        (r"\bmultifaceted\b", "Vague abstraction"),
        (
            r"\bunderscores?\s+the\s+(?:importance|significance)\b",
            "Inflated significance",
        ),
        (r"\bnavigate\s+the\s+complexities\b", "Vague abstraction"),
        (r"\bharness(?:ing|es)?\s+the\s+(?:potential|power)\b", "Cliche - be specific"),
        (r"\bnuanced\s+(?:understanding|approach)\b", "Vague qualifier"),
        (
            r"\brobust\s+and\s+scalable\b",
            "Unsupported generic praise unless benchmarked",
        ),
        (r"\bseamlessly\s+integrates?\b", "Unsupported generic praise"),
        (r"\bthe\s+intricacies\s+of\b", "Vague abstraction"),
        (r"\bintricate\s+interplay\b", "Vague abstraction"),
        (r"\bfacilitate\s+a\s+deeper\s+understanding\b", "Vague filler"),
    ],
    PhraseCategory.REDUNDANCY: [
        (
            r"\b(?:comprehensive|thorough)\s+and\s+(?:comprehensive|thorough)\b",
            "Redundant pairing",
        ),
        (r"\b(?:various|different)\s+types\s+of\b", "Redundant - just 'various'"),
        (r"\b(?:each|every)\s+and\s+every\b", "Redundant pairing"),
        (r"\b(?:first|initial)\s+and\s+(?:foremost|primary)\b", "Cliche pairing"),
        (r"\b(?:end|final)\s+result\b", "Redundant - just 'result'"),
    ],
    PhraseCategory.SIGNIFICANCE: [
        (
            r"\bmarks?\s+a\s+pivotal\s+moment\b",
            "Inflated significance - state the fact plainly",
        ),
        (
            r"\bunderscores?\s+the\s+(?:importance|significance)\s+of\b",
            "Inflated significance",
        ),
        (
            r"\bsymboliz(?:es|ing)\s+its\s+(?:ongoing|enduring|lasting)\b",
            "Inflated significance",
        ),
        (r"\bsets?\s+the\s+stage\s+for\b", "Inflated significance cliche"),
        (r"\bevolving\s+landscape\b", "Vague abstract-noun inflation"),
        (r"\bindelible\s+mark\b", "Inflated significance cliche"),
        (r"\bdeeply\s+rooted\b", "Inflated significance cliche"),
    ],
    PhraseCategory.ATTRIBUTION: [
        (
            r"\bexperts?\s+believe\b",
            "Vague uncited authority - name the source or cite it",
        ),
        (r"\bindustry\s+reports?\b", "Vague uncited authority"),
        (r"\bobservers?\s+have\s+(?:noted|stated)\b", "Vague uncited authority"),
        (r"\bsome\s+critics?\s+argue\b", "Vague uncited authority"),
    ],
    PhraseCategory.COPULA: [
        (r"\bserves?\s+as\s+an?\b", "Copula avoidance - use 'is'/'are'"),
        (r"\bstands?\s+as\s+an?\b", "Copula avoidance - use 'is'/'are'"),
        (r"\bfunctions?\s+as\s+an?\b", "Copula avoidance - use 'is'/'are'"),
        (r"\bboasts?\s+(?:a|an|over)\b", "Copula avoidance - use 'has'"),
    ],
}

# AI phrase patterns - Chinese
AI_PATTERNS_ZH = {
    PhraseCategory.HEDGING: [
        (r"值得注意的是", "Often unnecessary hedging"),
        (r"需要注意的是", "Consider removing"),
        (r"可以说", "Overused hedge"),
        (r"可能", "Remove if claim is supported"),
    ],
    PhraseCategory.TRANSITION: [
        (r"此外", "Consider simpler transition"),
        (r"而且", "Can be removed"),
        (r"另外", "Simplify or remove"),
        (r"因此", "Use '所以' instead"),
        (r"然而", "Consider simpler transition"),
    ],
    PhraseCategory.SUMMARY: [
        (r"总之", "Use section heading instead"),
        (r"总而言之", "Often unnecessary"),
        (r"总的来说", "Formulaic"),
        (r"综上所述", "Cliche summary marker"),
    ],
    PhraseCategory.EMPHASIS: [
        (r"重要的是", "Be direct"),
        (r"关键的是", "Often overused"),
        (r"显著地", "Use only for statistical significance"),
        (r"有趣的是", "Let readers decide"),
    ],
    PhraseCategory.CLICHE: [
        (r"深入探讨", "Cliche - use '分析' or '研究'"),
        (r"揭示", "Often overused - use '显示'"),
        (r"提供见解", "Awkward - use '说明'"),
        (r"发挥作用", "Cliche - be specific"),
        (r"利用", "Often just '用' is fine"),
    ],
}


# Mechanical/formatting AI-tells that are not phrase-level (counted or
# substituted directly rather than matched as AIPhrase objects). Curly quotes
# are a correctness issue, not just style, for LaTeX output: LaTeX expects
# straight quotes (` ` / ' ') paired via `` and '', not literal U+201C/U+201D.
_CURLY_DOUBLE_QUOTES = str.maketrans({"“": '"', "”": '"'})
_CURLY_SINGLE_QUOTES = str.maketrans({"‘": "'", "’": "'"})
_EMOJI_RE = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff]+",
    flags=re.UNICODE,
)
_EM_DASH_RE = re.compile("—")

# Generic single-word hedges: legitimate in normal use ("very high accuracy",
# "many studies"), so these are density-gated (warn only above a whole-draft
# threshold) rather than flagged as individual AIPhrase matches, which would
# over-flag ordinary prose. Ported from the inline checker previously in
# _paper_writing.py._validate_draft_quality.
_WEASEL_WORDS_RE = re.compile(
    r"\b(various|many|several|quite|fairly|really|very|rather|"
    r"somewhat|relatively|arguably|interestingly|importantly|"
    r"it is well known that|it is obvious that|clearly)\b",
    re.IGNORECASE,
)
_DUPLICATE_WORDS_RE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)
_DUPLICATE_WORDS_ALLOWLIST = {"that", "had"}

# Common word pairs that LLMs hyphenate with unusual consistency; humans
# hyphenate these inconsistently or not at all. Deliberately a fixed list
# (not a general hyphen regex) so technical compounds like "ResNet-50" or
# domain-specific terms are never flagged.
_HYPHENATED_PAIRS_EN = (
    "third-party",
    "cross-functional",
    "client-facing",
    "data-driven",
    "decision-making",
    "well-known",
    "high-quality",
    "real-time",
    "long-term",
    "end-to-end",
)


class AntiAIEncoder:
    """Detect and replace AI-generated phrases.

    Provides bilingual (EN/CN) detection and replacement of common
    AI-generated phrases with human-like alternatives.

    Attributes:
        config: Encoder configuration
        sensitivity: Detection sensitivity (0.0-1.0, default: 0.7)
        auto_replace: Automatically replace detected phrases (default: False)
        language: Language to detect (default: auto-detect)
    """

    def __init__(
        self,
        config: EncoderConfig | None = None,
        sensitivity: float = 0.7,
        auto_replace: bool = False,
        language: Language = Language.AUTO,
    ):
        """
        Initialize anti-AI encoder.

        Args:
            config: Encoder configuration (optional, overrides other params)
            sensitivity: Detection sensitivity (0.0-1.0)
            auto_replace: Whether to auto-replace detected phrases
            language: Language to detect (auto, en, zh)
        """
        self.config = config or EncoderConfig()
        self.sensitivity = max(0.0, min(1.0, sensitivity))
        self.auto_replace = auto_replace
        self.language = language

        # Compile regex patterns
        self._patterns_en = self._compile_patterns(AI_PATTERNS_EN)
        self._patterns_zh = self._compile_patterns(AI_PATTERNS_ZH)

        logger.debug("AntiAIEncoder initialized with sensitivity=%.2f", sensitivity)

    def _compile_patterns(
        self,
        patterns: dict[PhraseCategory, list[tuple[str, str]]],
    ) -> list[tuple[re.Pattern, PhraseCategory, str]]:
        """Compile regex patterns for efficient matching."""
        compiled = []
        for category, pattern_list in patterns.items():
            for pattern, explanation in pattern_list:
                try:
                    compiled.append(
                        (re.compile(pattern, re.IGNORECASE), category, explanation)
                    )
                except re.error as e:
                    logger.warning("Invalid regex pattern '%s': %s", pattern, e)
        return compiled

    def _detect_language(self, text: str) -> Language:
        """Detect language of text."""
        # Count Chinese characters
        zh_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        # Count Latin characters
        en_chars = len(re.findall(r"[a-zA-Z]", text))

        if zh_chars > en_chars * 0.5:  # Some Chinese present
            return Language.CHINESE
        return Language.ENGLISH

    async def analyze(self, text: str) -> AnalysisResult:
        """
        Analyze text for AI-generated phrases.

        Args:
            text: Text to analyze

        Returns:
            AnalysisResult with detected phrases and suggestions
        """
        return self._analyze_sync(text)

    def _analyze_sync(self, text: str) -> AnalysisResult:
        """Synchronous core of analyze() — no actual I/O occurs, so the
        async wrapper above is purely for API compatibility. detect()/
        rewrite() and friends call this directly to avoid needless
        asyncio.run() nesting."""
        # Detect language
        lang = self.language
        if lang == Language.AUTO:
            lang = self._detect_language(text)

        # Select patterns
        patterns = self._patterns_en if lang == Language.ENGLISH else self._patterns_zh

        # Find matches
        phrases: list[AIPhrase] = []
        for pattern, category, explanation in patterns:
            for match in pattern.finditer(text):
                # Apply sensitivity threshold
                confidence = 0.8  # Base confidence
                if category in (
                    PhraseCategory.CLICHE,
                    PhraseCategory.REDUNDANCY,
                    PhraseCategory.SIGNIFICANCE,
                    PhraseCategory.ATTRIBUTION,
                ):
                    confidence = 0.9  # Higher confidence for obvious issues
                elif category in (PhraseCategory.STRUCTURE, PhraseCategory.TRANSITION):
                    confidence = 0.6  # Lower confidence for acceptable patterns

                if confidence >= self.sensitivity:
                    # Get alternatives
                    alternatives = self._get_alternatives(match.group(), category, lang)

                    phrases.append(
                        AIPhrase(
                            text=match.group(),
                            category=category,
                            start_pos=match.start(),
                            end_pos=match.end(),
                            confidence=confidence,
                            alternatives=alternatives,
                            explanation=explanation,
                        )
                    )

        # Sort by position
        phrases.sort(key=lambda p: p.start_pos)

        # Calculate AI score
        ai_score = self._calculate_ai_score(text, phrases)

        # Generate revised text
        revised_text = text
        if self.auto_replace or phrases:
            revised_text = self._apply_replacements(text, phrases)

        # Generate suggestions
        suggestions = self._generate_suggestions(phrases, lang)

        return AnalysisResult(
            original_text=text,
            revised_text=revised_text,
            phrases=phrases,
            ai_score=ai_score,
            language=lang,
            suggestions=suggestions,
        )

    def _get_alternatives(
        self,
        phrase: str,
        category: PhraseCategory,
        language: Language,
    ) -> list[str]:
        """Get human-like alternatives for detected phrase."""
        alternatives_map = {
            # English alternatives
            (PhraseCategory.HEDGING, Language.ENGLISH): {
                "it is worth noting": ["Note that", ""],
                "it should be noted": ["Note that", ""],
                "it is important to note": ["Importantly", ""],
                "arguably": [""],
                "potentially": [""],
            },
            (PhraseCategory.TRANSITION, Language.ENGLISH): {
                "furthermore": ["Additionally", "Also", ""],
                "moreover": ["Additionally", "Also", ""],
                "additionally": ["Also", ""],
                "in addition": ["Also", ""],
                "consequently": ["Thus", "So", ""],
            },
            (PhraseCategory.CLICHE, Language.ENGLISH): {
                "delve into": ["examine", "analyze", "investigate", "study"],
                "shed light on": ["clarify", "explain", "illuminate"],
                "pave the way": ["enable", "facilitate", "allow"],
                "play a key role": ["is key to", "is essential for", ""],
                "gain insights": ["understand", "learn"],
                "provide insights": ["show", "demonstrate"],
                "leverage": ["use", "utilize"],
                "utilize": ["use"],
                "methodology": ["method", "approach"],
                "paradigm": ["approach", "framework", "model"],
                "a testament to": ["evidence of", "proof of", "shows"],
            },
            (PhraseCategory.SIGNIFICANCE, Language.ENGLISH): {
                "marks a pivotal moment": ["[state the fact directly]"],
                "underscores the importance of": ["shows", "indicates"],
                "sets the stage for": ["enables", "leads to"],
                "evolving landscape": ["[name the specific field or trend]"],
                "indelible mark": ["[state the specific effect]"],
                "deeply rooted": ["[state the specific origin]"],
            },
            (PhraseCategory.ATTRIBUTION, Language.ENGLISH): {
                "experts believe": ["[cite the specific source]"],
                "industry reports": ["[cite the specific report]"],
                "observers have noted": ["[cite the specific source]"],
                "some critics argue": ["[cite the specific critic]"],
            },
            (PhraseCategory.COPULA, Language.ENGLISH): {
                "serves as a": ["is a"],
                "serves as an": ["is an"],
                "stands as a": ["is a"],
                "stands as an": ["is an"],
                "functions as a": ["is a"],
                "functions as an": ["is an"],
                "boasts a": ["has a"],
                "boasts an": ["has an"],
                "boasts over": ["has over"],
            },
            # Chinese alternatives
            (PhraseCategory.CLICHE, Language.CHINESE): {
                "深入探讨": ["分析", "研究", "探讨"],
                "揭示": ["显示", "表明"],
                "提供见解": ["说明", "展示"],
                "发挥作用": ["有助于", "促进"],
                "利用": ["用", "使用"],
            },
        }

        phrase_lower = phrase.lower().strip()
        key = (category, language)

        if key in alternatives_map:
            alts = alternatives_map[key].get(phrase_lower, [])
            if alts:
                return alts

        # Default: suggest removal or simplification
        if language == Language.ENGLISH:
            return ["[remove or rephrase]", "[simplify]"]
        return ["[删除或改写]", "[简化]"]

    def _calculate_ai_score(self, text: str, phrases: list[AIPhrase]) -> float:
        """Calculate overall AI likelihood score (0-1)."""
        if not phrases:
            return 0.0

        # Base score from phrase count
        word_count = len(text.split())
        phrase_density = len(phrases) / max(word_count, 1) * 100  # Per 100 words

        # Weighted by confidence
        avg_confidence = sum(p.confidence for p in phrases) / len(phrases)

        # Score formula
        score = min(1.0, phrase_density * avg_confidence * 0.3)

        return round(score, 2)

    def _apply_replacements(self, text: str, phrases: list[AIPhrase]) -> str:
        """Apply replacements to text."""
        # Process from end to start to preserve positions
        result = text
        for phrase in reversed(phrases):
            if phrase.alternatives:
                # Use first alternative (or empty string if first is "")
                replacement = phrase.alternatives[0]
                result = (
                    result[: phrase.start_pos] + replacement + result[phrase.end_pos :]
                )
        return result

    def _generate_suggestions(
        self,
        phrases: list[AIPhrase],
        language: Language,
    ) -> list[str]:
        """Generate writing improvement suggestions."""
        suggestions = []

        # Count categories
        category_counts: dict[PhraseCategory, int] = {}
        for phrase in phrases:
            category_counts[phrase.category] = (
                category_counts.get(phrase.category, 0) + 1
            )

        # Generate suggestions based on patterns
        if category_counts.get(PhraseCategory.HEDGING, 0) > 3:
            if language == Language.ENGLISH:
                suggestions.append("Reduce hedging - make stronger, more direct claims")
            else:
                suggestions.append("减少模糊表述 - 使用更直接、明确的陈述")

        if category_counts.get(PhraseCategory.CLICHE, 0) > 2:
            if language == Language.ENGLISH:
                suggestions.append("Replace cliches with specific, concrete language")
            else:
                suggestions.append("用具体、明确的语言替换陈词滥调")

        if category_counts.get(PhraseCategory.REDUNDANCY, 0) > 1:
            if language == Language.ENGLISH:
                suggestions.append("Remove redundant word pairings")
            else:
                suggestions.append("删除冗余的词语搭配")

        if category_counts.get(PhraseCategory.TRANSITION, 0) > 4:
            if language == Language.ENGLISH:
                suggestions.append(
                    "Reduce mechanical transitions - let ideas flow naturally"
                )
            else:
                suggestions.append("减少机械化的过渡词 - 让思路自然流畅")

        if category_counts.get(PhraseCategory.SIGNIFICANCE, 0) > 1:
            suggestions.append(
                "Remove inflated significance language - state facts plainly instead of "
                "claiming broader importance"
            )

        if category_counts.get(PhraseCategory.ATTRIBUTION, 0) > 0:
            suggestions.append(
                "Replace vague authority claims (e.g. 'experts believe') with a specific citation"
            )

        if category_counts.get(PhraseCategory.COPULA, 0) > 2:
            suggestions.append(
                "Replace 'serves as'/'stands as'/'boasts' with 'is'/'has'"
            )

        return suggestions

    async def replace(self, text: str) -> str:
        """
        Replace AI phrases with human alternatives.

        Args:
            text: Input text

        Returns:
            Text with AI phrases replaced
        """
        result = await self.analyze(text)
        return result.revised_text

    def detect(self, text: str) -> DetectionResult:
        """
        Detect AI phrases without replacement (sync).

        Args:
            text: Input text

        Returns:
            DetectionResult with detected phrases and AI score
        """
        result = self._analyze_sync(text)
        word_count = len(text.split())
        ai_word_percentage = round(len(result.phrases) / max(word_count, 1) * 100, 2)
        phrases = [
            AIPhrases(
                phrase=p.text,
                confidence=p.confidence,
                category=p.category.value,
                position=p.start_pos,
                suggestion=p.alternatives[0] if p.alternatives else "",
                reason=p.explanation,
            )
            for p in result.phrases
        ]
        recommendations = self._generate_recommendations(phrases, self.sensitivity)
        return DetectionResult(
            text=text,
            ai_score=result.ai_score,
            word_count=word_count,
            ai_word_percentage=ai_word_percentage,
            phrases=phrases,
            recommendations=recommendations,
        )

    def rewrite(self, text: str) -> str:
        """Replace AI phrases with human alternatives (sync)."""
        return self._analyze_sync(text).revised_text

    def detect_batch(self, texts: list[str]) -> list[DetectionResult]:
        """Detect AI phrases across multiple texts (sync)."""
        return [self.detect(t) for t in texts]

    def rewrite_batch(self, texts: list[str]) -> list[str]:
        """Rewrite multiple texts to remove AI phrases (sync)."""
        return [self.rewrite(t) for t in texts]

    def get_statistics(self, text: str) -> dict[str, Any]:
        """Basic writing statistics (word/sentence counts)."""
        word_count = len(text.split())
        sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
        sentence_count = len(sentences)
        avg_sentence_length = (
            round(word_count / sentence_count, 2) if sentence_count else 0.0
        )
        return {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "avg_sentence_length": avg_sentence_length,
        }

    def detect_mechanical(self, text: str) -> list[str]:
        """Detect formatting/density-level AI tells that aren't phrase matches.

        Covers curly quotes (a LaTeX correctness issue), emoji, em-dash
        overuse, mechanically-consistent hyphenated word pairs, whole-draft
        weasel-word density, and duplicate adjacent words. These are
        density/threshold-gated rather than per-match AIPhrase objects
        because the underlying words (very, many, several, ...) are normal
        in legitimate prose and only become a signal in aggregate.
        Returns human-readable warnings.
        """
        warnings: list[str] = []
        word_count = max(len(text.split()), 1)

        curly_count = sum(text.count(c) for c in "“”‘’")
        if curly_count:
            warnings.append(
                f"{curly_count} curly quote character(s) found — LaTeX expects straight "
                "quotes (use fix_mechanical() to normalize)"
            )

        emoji_count = len(_EMOJI_RE.findall(text))
        if emoji_count:
            warnings.append(f"{emoji_count} emoji found — remove from academic prose")

        em_dash_count = len(_EM_DASH_RE.findall(text))
        em_dash_density = em_dash_count / word_count * 1000
        if em_dash_count >= 3 and em_dash_density > 2.0:
            warnings.append(
                f"Em dash overuse: {em_dash_count} instance(s) "
                f"({em_dash_density:.1f} per 1000 words) — prefer commas or periods"
            )

        hyphen_hits = [p for p in _HYPHENATED_PAIRS_EN if p in text.lower()]
        if len(hyphen_hits) >= 3:
            warnings.append(
                f"Mechanically consistent hyphenation of common word pairs "
                f"({', '.join(hyphen_hits[:5])}) — humans hyphenate these inconsistently"
            )

        weasel_count = len(_WEASEL_WORDS_RE.findall(text))
        if weasel_count > 20:
            warnings.append(
                f"High weasel-word count: {weasel_count} instances "
                "(various, several, quite, fairly, rather, somewhat) — "
                "replace with precise quantities or remove"
            )

        dup_matches = _DUPLICATE_WORDS_RE.findall(text)
        dup_count = len(
            [d for d in dup_matches if d.lower() not in _DUPLICATE_WORDS_ALLOWLIST]
        )
        if dup_count > 0:
            warnings.append(
                f"Duplicate adjacent words found: {dup_count} instance(s) "
                "(e.g., 'the the', 'is is') — likely typos"
            )

        return warnings

    def fix_mechanical(self, text: str) -> str:
        """Apply unambiguous, context-free mechanical fixes.

        Only normalizes curly quotes to straight quotes and strips emoji —
        both are safe character-level substitutions with no judgment call.
        Em-dash density and hyphenation are reported by detect_mechanical()
        but not auto-fixed, since blind substitution risks breaking sentences.
        """
        result = text.translate(_CURLY_DOUBLE_QUOTES).translate(_CURLY_SINGLE_QUOTES)
        result = _EMOJI_RE.sub("", result)
        return result

    def _categorize_en(self, phrase: str) -> str:
        """Categorize an English phrase by matching against known patterns."""
        for pattern, category, _ in self._patterns_en:
            if pattern.search(phrase):
                return category.value
        return "unknown"

    # Chinese phrases use distinct category labels from the English
    # PhraseCategory enum (e.g. "filler" instead of "hedging") — kept as
    # its own lookup rather than forcing a shared taxonomy across languages.
    _ZH_CATEGORIES: dict[str, str] = {
        "值得注意的是": "filler",
        "需要注意的是": "filler",
        "可以说": "filler",
        "可能": "filler",
        "此外": "transition",
        "而且": "transition",
        "另外": "transition",
        "因此": "transition",
        "然而": "transition",
        "总之": "summary",
        "总而言之": "summary",
        "总的来说": "summary",
        "综上所述": "summary",
        "重要的是": "emphasis",
        "关键的是": "emphasis",
        "显著地": "emphasis",
        "有趣的是": "emphasis",
        "深入探讨": "cliche",
        "揭示": "cliche",
        "提供见解": "cliche",
        "发挥作用": "cliche",
        "利用": "cliche",
    }

    def _categorize_zh(self, phrase: str) -> str:
        """Categorize a Chinese phrase by matching against known phrases."""
        if phrase in self._ZH_CATEGORIES:
            return self._ZH_CATEGORIES[phrase]
        for key, category in self._ZH_CATEGORIES.items():
            if key in phrase:
                return category
        return "unknown"

    def _generate_recommendations(
        self, phrases: list[AIPhrases], threshold: float
    ) -> list[str]:
        """Generate human-readable recommendations from detected phrases."""
        _ = threshold
        counts: dict[str, int] = {}
        for p in phrases:
            counts[p.category] = counts.get(p.category, 0) + 1

        recommendations: list[str] = []
        if counts.get("cliche", 0) >= 2:
            recommendations.append(
                "Replace cliche phrases with specific, concrete language"
            )
        if counts.get("hedging", 0) >= 3 or counts.get("filler", 0) >= 3:
            recommendations.append("Reduce hedging/filler language")
        if counts.get("redundancy", 0) >= 1:
            recommendations.append("Remove redundant word pairings")
        if counts.get("transition", 0) >= 4:
            recommendations.append("Reduce mechanical transitions")
        if counts.get("significance", 0) >= 2:
            recommendations.append("Remove inflated significance/legacy language")
        if counts.get("attribution", 0) >= 1:
            recommendations.append(
                "Replace vague authority claims with specific citations"
            )
        if counts.get("copula", 0) >= 3:
            recommendations.append(
                "Replace 'serves as'/'stands as'/'boasts' with 'is'/'has'"
            )
        if not recommendations and phrases:
            recommendations.append(
                f"Review {len(phrases)} flagged phrase(s) for clarity"
            )
        return recommendations


# Convenience functions
async def analyze_for_ai(text: str, sensitivity: float = 0.7) -> AnalysisResult:
    """
    Analyze text for AI-generated phrases.

    Args:
        text: Text to analyze
        sensitivity: Detection sensitivity (0.0-1.0)

    Returns:
        AnalysisResult with detected phrases

    Example:
        >>> result = await analyze_for_ai("This paper delves into...")
        >>> print(f"AI score: {result.ai_score}")
        >>> print(f"Found {len(result.phrases)} AI-like phrases")
    """
    encoder = AntiAIEncoder(sensitivity=sensitivity)
    return await encoder.analyze(text)


async def replace_ai_phrases(text: str) -> str:
    """
    Replace AI phrases with human alternatives.

    Args:
        text: Input text

    Returns:
        Humanized text

    Example:
        >>> text = "This paper delves into the methodology..."
        >>> revised = await replace_ai_phrases(text)
        >>> print(revised)
        "This paper examines the method..."
    """
    encoder = AntiAIEncoder(auto_replace=True)
    result = await encoder.analyze(text)
    return result.revised_text


@dataclass
class EncoderConfig:
    """Configuration for AntiAIEncoder.

    Attributes:
        language: Languages to detect (default: ["en", "zh"])
        strictness: Detection strictness 0.0-1.0 (default: 0.7)
        preserve_meaning: Preserve original meaning when replacing (default: True)
    """

    language: list[str] = field(default_factory=lambda: ["en", "zh"])
    strictness: float = 0.7
    preserve_meaning: bool = True


def create_encoder_from_env() -> AntiAIEncoder:
    """Create AntiAIEncoder from environment variables.

    Returns:
        AntiAIEncoder configured from environment

    Example:
        >>> encoder = create_encoder_from_env()
    """
    import os

    language = os.environ.get("ANTI_AI_LANGUAGE", "en,zh").split(",")
    strictness = float(os.environ.get("ANTI_AI_STRICTNESS", 0.7))
    preserve_meaning = (
        os.environ.get("ANTI_AI_PRESERVE_MEANING", "true").lower() == "true"
    )
    config = EncoderConfig(
        language=language, strictness=strictness, preserve_meaning=preserve_meaning
    )
    return AntiAIEncoder(config=config, sensitivity=strictness, auto_replace=False)
