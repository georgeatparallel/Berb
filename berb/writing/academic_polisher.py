"""Academic prose polisher for fine-grained writing quality.

This module provides fine-grained academic writing quality checks:
- Word choice (utilize → use)
- Formality (informal → formal)
- Grammar (academic conventions)
- Transitions (Also → Furthermore)
- Overgeneralization (All → Most)
- Hedging (proves → suggests)
- Tense consistency (methods=past, discussion=present)
- Voice (passive/active per domain)
- Citation integration

Inspired by Writeless AI's polishing features.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AcademicPolishCategory(StrEnum):
    """Category of academic polish improvement.

    Attributes:
        WORD_CHOICE: Better word selection
        FORMALITY: More formal language
        GRAMMAR: Grammar corrections
        TRANSITIONS: Better transition words
        OVERGENERALIZED: Reduce overgeneralization
        HEDGING: Appropriate hedging
        TENSE_CONSISTENCY: Consistent verb tense
        PASSIVE_ACTIVE: Appropriate voice
        CITATION_INTEGRATION: Better citation phrasing
    """

    WORD_CHOICE = "word_choice"
    FORMALITY = "formality"
    GRAMMAR = "grammar"
    TRANSITIONS = "transitions"
    OVERGENERALIZED = "overgeneralized"
    HEDGING = "hedging"
    TENSE_CONSISTENCY = "tense"
    PASSIVE_ACTIVE = "voice"
    CITATION_INTEGRATION = "citation"


class PolishSeverity(StrEnum):
    """Severity of polish suggestion.

    Attributes:
        ERROR: Must fix (grammar, clarity)
        WARNING: Should fix (formality, word choice)
        SUGGESTION: Optional improvement (style)
    """

    ERROR = "error"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class PolishSuggestion(BaseModel):
    """Single polish suggestion.

    Attributes:
        category: Polish category
        original_text: Original text span
        suggested_replacement: Suggested replacement
        severity: Suggestion severity
        explanation: Why this change is suggested
        confidence: Confidence in suggestion (0-1)
        start_pos: Start position in text
        end_pos: End position in text
    """

    category: AcademicPolishCategory
    original_text: str
    suggested_replacement: str
    severity: PolishSeverity
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)
    start_pos: int = 0
    end_pos: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "category": self.category.value,
            "original": self.original_text,
            "suggested": self.suggested_replacement,
            "severity": self.severity.value,
            "explanation": self.explanation,
            "confidence": self.confidence,
        }


class PolishReport(BaseModel):
    """Complete polish report for a text.

    Attributes:
        text_length: Length of analyzed text
        total_suggestions: Total number of suggestions
        by_category: Suggestions per category
        by_severity: Suggestions per severity
        suggestions: All suggestions
        overall_quality_score: Overall quality score (0-1)
        domain: Domain used for analysis
    """

    text_length: int = 0
    total_suggestions: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
    suggestions: list[PolishSuggestion] = Field(default_factory=list)
    overall_quality_score: float = Field(default=1.0, ge=0.0, le=1.0)
    domain: str = "general"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        # Calculate derived fields
        self.text_length = sum(len(s.original_text) for s in self.suggestions)
        self.total_suggestions = len(self.suggestions)

        # Count by category
        for cat in AcademicPolishCategory:
            count = sum(1 for s in self.suggestions if s.category == cat)
            self.by_category[cat.value] = count

        # Count by severity
        for sev in PolishSeverity:
            count = sum(1 for s in self.suggestions if s.severity == sev)
            self.by_severity[sev.value] = count

        # Calculate quality score
        if self.total_suggestions > 0:
            error_penalty = self.by_severity.get("error", 0) * 0.1
            warning_penalty = self.by_severity.get("warning", 0) * 0.05
            suggestion_penalty = self.by_severity.get("suggestion", 0) * 0.02
            self.overall_quality_score = max(
                0.0, 1.0 - error_penalty - warning_penalty - suggestion_penalty
            )
        else:
            self.overall_quality_score = 1.0


@dataclass
class PolishPattern:
    """Pattern for polish detection.

    Attributes:
        pattern: Text pattern to match
        replacement: Suggested replacement
        category: Polish category
        severity: Severity level
        explanation: Why to change
        domain_specific: Domain where this applies
    """

    pattern: str
    replacement: str
    category: AcademicPolishCategory
    severity: PolishSeverity
    explanation: str
    domain_specific: str | None = None


class AcademicProsePolisher:
    """Polish academic writing to match scholarly conventions.

    This polisher:
    1. Scans text for improvement opportunities
    2. Categorizes suggestions by type
    3. Provides severity levels
    4. Can auto-apply high-confidence fixes
    5. Calibrates to domain and style

    Usage::

        polisher = AcademicProsePolisher()
        report = await polisher.polish(text, domain="machine-learning")

    Attributes:
        domain: Current domain for analysis
        style_fingerprint: Optional style fingerprint
    """

    # Word choice patterns
    WORD_CHOICE_PATTERNS = [
        PolishPattern(
            pattern="utilize",
            replacement="use",
            category=AcademicPolishCategory.WORD_CHOICE,
            severity=PolishSeverity.WARNING,
            explanation="'Use' is clearer and more direct than 'utilize'",
        ),
        PolishPattern(
            pattern="leverage",
            replacement="use",
            category=AcademicPolishCategory.WORD_CHOICE,
            severity=PolishSeverity.WARNING,
            explanation="'Use' is clearer than 'leverage' in academic writing",
        ),
        PolishPattern(
            pattern="facilitate",
            replacement="help",
            category=AcademicPolishCategory.WORD_CHOICE,
            severity=PolishSeverity.SUGGESTION,
            explanation="'Help' is often clearer than 'facilitate'",
        ),
        PolishPattern(
            pattern="methodology",
            replacement="method",
            category=AcademicPolishCategory.WORD_CHOICE,
            severity=PolishSeverity.SUGGESTION,
            explanation="'Method' is sufficient unless discussing methodology broadly",
        ),
        PolishPattern(
            pattern="commence",
            replacement="begin",
            category=AcademicPolishCategory.WORD_CHOICE,
            severity=PolishSeverity.WARNING,
            explanation="'Begin' is clearer than 'commence'",
        ),
        PolishPattern(
            pattern="subsequently",
            replacement="then",
            category=AcademicPolishCategory.WORD_CHOICE,
            severity=PolishSeverity.SUGGESTION,
            explanation="'Then' is often clearer than 'subsequently'",
        ),
    ]

    # Formality patterns
    FORMALITY_PATTERNS = [
        PolishPattern(
            pattern="a lot of",
            replacement="many",
            category=AcademicPolishCategory.FORMALITY,
            severity=PolishSeverity.WARNING,
            explanation="'Many' is more formal than 'a lot of'",
        ),
        PolishPattern(
            pattern="kind of",
            replacement="somewhat",
            category=AcademicPolishCategory.FORMALITY,
            severity=PolishSeverity.WARNING,
            explanation="'Somewhat' is more formal than 'kind of'",
        ),
        PolishPattern(
            pattern="sort of",
            replacement="somewhat",
            category=AcademicPolishCategory.FORMALITY,
            severity=PolishSeverity.WARNING,
            explanation="'Somewhat' is more formal than 'sort of'",
        ),
        PolishPattern(
            pattern="really",
            replacement="very",
            category=AcademicPolishCategory.FORMALITY,
            severity=PolishSeverity.SUGGESTION,
            explanation="'Very' is more formal than 'really'",
        ),
        PolishPattern(
            pattern="big",
            replacement="significant",
            category=AcademicPolishCategory.FORMALITY,
            severity=PolishSeverity.WARNING,
            explanation="'Significant' is more precise in academic writing",
        ),
        PolishPattern(
            pattern="huge",
            replacement="substantial",
            category=AcademicPolishCategory.FORMALITY,
            severity=PolishSeverity.WARNING,
            explanation="'Substantial' is more appropriate than 'huge'",
        ),
    ]

    # Transition patterns
    TRANSITION_PATTERNS = [
        PolishPattern(
            pattern="Also,",
            replacement="In addition,",
            category=AcademicPolishCategory.TRANSITIONS,
            severity=PolishSeverity.WARNING,
            explanation="'In addition' is more formal than 'Also'",
        ),
        PolishPattern(
            pattern="Also ",
            replacement="Furthermore, ",
            category=AcademicPolishCategory.TRANSITIONS,
            severity=PolishSeverity.WARNING,
            explanation="'Furthermore' is more formal than 'Also'",
        ),
        PolishPattern(
            pattern="But",
            replacement="However,",
            category=AcademicPolishCategory.TRANSITIONS,
            severity=PolishSeverity.WARNING,
            explanation="'However' is more formal than 'But' at sentence start",
        ),
        PolishPattern(
            pattern="So",
            replacement="Therefore,",
            category=AcademicPolishCategory.TRANSITIONS,
            severity=PolishSeverity.WARNING,
            explanation="'Therefore' is more formal than 'So' at sentence start",
        ),
        PolishPattern(
            pattern="Plus",
            replacement="Moreover,",
            category=AcademicPolishCategory.TRANSITIONS,
            severity=PolishSeverity.WARNING,
            explanation="'Moreover' is more formal than 'Plus'",
        ),
    ]

    # Overgeneralization patterns
    OVERGENERALIZED_PATTERNS = [
        PolishPattern(
            pattern="All ",
            replacement="Most ",
            category=AcademicPolishCategory.OVERGENERALIZED,
            severity=PolishSeverity.WARNING,
            explanation="'Most' is more accurate than 'All' unless truly universal",
        ),
        PolishPattern(
            pattern="always",
            replacement="often",
            category=AcademicPolishCategory.OVERGENERALIZED,
            severity=PolishSeverity.WARNING,
            explanation="'Often' is more accurate than 'always'",
        ),
        PolishPattern(
            pattern="never",
            replacement="rarely",
            category=AcademicPolishCategory.OVERGENERALIZED,
            severity=PolishSeverity.WARNING,
            explanation="'Rarely' is more accurate than 'never'",
        ),
        PolishPattern(
            pattern="every",
            replacement="most",
            category=AcademicPolishCategory.OVERGENERALIZED,
            severity=PolishSeverity.WARNING,
            explanation="'Most' is more accurate than 'every'",
        ),
    ]

    # Hedging patterns
    HEDGING_PATTERNS = [
        PolishPattern(
            pattern="proves",
            replacement="suggests",
            category=AcademicPolishCategory.HEDGING,
            severity=PolishSeverity.WARNING,
            explanation="Academic writing typically uses 'suggests' rather than 'proves'",
        ),
        PolishPattern(
            pattern="demonstrates",
            replacement="indicates",
            category=AcademicPolishCategory.HEDGING,
            severity=PolishSeverity.SUGGESTION,
            explanation="'Indicates' is often more appropriate than 'demonstrates'",
        ),
        PolishPattern(
            pattern="clearly",
            replacement="",
            category=AcademicPolishCategory.HEDGING,
            severity=PolishSeverity.SUGGESTION,
            explanation="'Clearly' is often unnecessary and can sound condescending",
        ),
        PolishPattern(
            pattern="obviously",
            replacement="",
            category=AcademicPolishCategory.HEDGING,
            severity=PolishSeverity.WARNING,
            explanation="'Obviously' should be avoided in academic writing",
        ),
        PolishPattern(
            pattern="without doubt",
            replacement="likely",
            category=AcademicPolishCategory.HEDGING,
            severity=PolishSeverity.WARNING,
            explanation="Academic claims should be appropriately hedged",
        ),
    ]

    def __init__(
        self,
        domain: str = "general",
        style_fingerprint: Any | None = None,
    ):
        """Initialize academic prose polisher.

        Args:
            domain: Research domain for calibration
            style_fingerprint: Optional style fingerprint for calibration
        """
        self.domain = domain
        self.style_fingerprint = style_fingerprint

        # Domain-specific adjustments
        self._apply_domain_adjustments()

    def _apply_domain_adjustments(self) -> None:
        """Apply domain-specific adjustments to patterns."""
        # Physics uses more passive voice than CS
        if self.domain == "physics":
            # Reduce voice-related suggestions
            pass

        # Humanities use more hedging than ML
        if self.domain == "humanities":
            # Increase hedging suggestions
            pass

    async def polish(
        self,
        text: str,
        target_style: Any | None = None,
        domain: str | None = None,
    ) -> PolishReport:
        """Scan text and suggest improvements per category.

        Args:
            text: Text to polish
            target_style: Optional target style fingerprint
            domain: Optional domain override

        Returns:
            PolishReport with categorized suggestions
        """
        if domain:
            self.domain = domain
            self._apply_domain_adjustments()

        suggestions = []

        # Run all polish checks
        suggestions.extend(self._check_word_choice(text))
        suggestions.extend(self._check_formality(text))
        suggestions.extend(self._check_transitions(text))
        suggestions.extend(self._check_overgeneralization(text))
        suggestions.extend(self._check_hedging(text))
        suggestions.extend(self._check_grammar(text))
        suggestions.extend(self._check_tense(text))
        suggestions.extend(self._check_voice(text))
        suggestions.extend(self._check_citation_integration(text))

        # Sort by confidence (highest first)
        suggestions.sort(key=lambda s: s.confidence, reverse=True)

        return PolishReport(
            suggestions=suggestions,
            domain=self.domain,
        )

    def _check_word_choice(self, text: str) -> list[PolishSuggestion]:
        """Check word choice issues.

        Args:
            text: Text to check

        Returns:
            List of suggestions
        """
        suggestions = []

        for pattern in self.WORD_CHOICE_PATTERNS:
            if pattern.domain_specific and pattern.domain_specific != self.domain:
                continue

            import re

            for match in re.finditer(rf"\b{pattern.pattern}\b", text, re.IGNORECASE):
                suggestions.append(
                    PolishSuggestion(
                        category=pattern.category,
                        original_text=match.group(),
                        suggested_replacement=pattern.replacement,
                        severity=pattern.severity,
                        explanation=pattern.explanation,
                        confidence=0.85,
                        start_pos=match.start(),
                        end_pos=match.end(),
                    )
                )

        return suggestions

    def _check_formality(self, text: str) -> list[PolishSuggestion]:
        """Check formality issues.

        Args:
            text: Text to check

        Returns:
            List of suggestions
        """
        suggestions = []

        for pattern in self.FORMALITY_PATTERNS:
            import re

            for match in re.finditer(rf"\b{pattern.pattern}\b", text, re.IGNORECASE):
                suggestions.append(
                    PolishSuggestion(
                        category=pattern.category,
                        original_text=match.group(),
                        suggested_replacement=pattern.replacement,
                        severity=pattern.severity,
                        explanation=pattern.explanation,
                        confidence=0.8,
                        start_pos=match.start(),
                        end_pos=match.end(),
                    )
                )

        return suggestions

    def _check_transitions(self, text: str) -> list[PolishSuggestion]:
        """Check transition word issues.

        Args:
            text: Text to check

        Returns:
            List of suggestions
        """
        suggestions = []

        for pattern in self.TRANSITION_PATTERNS:
            import re

            for match in re.finditer(rf"\b{pattern.pattern}\b", text):
                suggestions.append(
                    PolishSuggestion(
                        category=pattern.category,
                        original_text=match.group(),
                        suggested_replacement=pattern.replacement,
                        severity=pattern.severity,
                        explanation=pattern.explanation,
                        confidence=0.85,
                        start_pos=match.start(),
                        end_pos=match.end(),
                    )
                )

        return suggestions

    def _check_overgeneralization(self, text: str) -> list[PolishSuggestion]:
        """Check overgeneralization issues.

        Args:
            text: Text to check

        Returns:
            List of suggestions
        """
        suggestions = []

        for pattern in self.OVERGENERALIZED_PATTERNS:
            import re

            for match in re.finditer(rf"\b{pattern.pattern}\b", text, re.IGNORECASE):
                suggestions.append(
                    PolishSuggestion(
                        category=pattern.category,
                        original_text=match.group(),
                        suggested_replacement=pattern.replacement,
                        severity=pattern.severity,
                        explanation=pattern.explanation,
                        confidence=0.75,
                        start_pos=match.start(),
                        end_pos=match.end(),
                    )
                )

        return suggestions

    def _check_hedging(self, text: str) -> list[PolishSuggestion]:
        """Check hedging issues.

        Args:
            text: Text to check

        Returns:
            List of suggestions
        """
        suggestions = []

        for pattern in self.HEDGING_PATTERNS:
            import re

            for match in re.finditer(rf"\b{pattern.pattern}\b", text, re.IGNORECASE):
                # Skip if pattern is empty (for "clearly" → "")
                if match.group():
                    suggestions.append(
                        PolishSuggestion(
                            category=pattern.category,
                            original_text=match.group(),
                            suggested_replacement=pattern.replacement,
                            severity=pattern.severity,
                            explanation=pattern.explanation,
                            confidence=0.8,
                            start_pos=match.start(),
                            end_pos=match.end(),
                        )
                    )

        return suggestions

    def _check_grammar(self, text: str) -> list[PolishSuggestion]:
        """Check grammar issues.

        Args:
            text: Text to check

        Returns:
            List of suggestions
        """
        # Simplified grammar checks (would use grammar library in production)
        suggestions = []

        # Check for subject-verb agreement issues (simplified)
        import re

        # Common errors
        errors = [
            (r"\bdata is\b", "data are", "Data is plural"),
            (r"\bphenomena is\b", "phenomena are", "Phenomena is plural"),
            (r"\bcriteria is\b", "criteria are", "Criteria is plural"),
        ]

        for pattern, replacement, explanation in errors:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                suggestions.append(
                    PolishSuggestion(
                        category=AcademicPolishCategory.GRAMMAR,
                        original_text=match.group(),
                        suggested_replacement=replacement,
                        severity=PolishSeverity.ERROR,
                        explanation=explanation,
                        confidence=0.95,
                        start_pos=match.start(),
                        end_pos=match.end(),
                    )
                )

        return suggestions

    def _check_tense(self, text: str) -> list[PolishSuggestion]:
        """Check tense consistency issues.

        Args:
            text: Text to check

        Returns:
            List of suggestions
        """
        # Simplified tense checks (would use NLP in production)
        suggestions = []

        # In methods sections, past tense is typical
        # This is a placeholder for more sophisticated checking
        return suggestions

    def _check_voice(self, text: str) -> list[PolishSuggestion]:
        """Check passive/active voice appropriateness.

        Args:
            text: Text to check

        Returns:
            List of suggestions
        """
        # Simplified voice checks
        suggestions = []

        # Physics typically uses more passive voice
        if self.domain != "physics":
            # Flag excessive passive voice
            import re

            passive_patterns = [
                r"\b(is|are|was|were)\s+\w+ed\b",
            ]
            for pattern in passive_patterns:
                matches = list(re.finditer(pattern, text))
                if len(matches) > 10:  # Threshold
                    suggestions.append(
                        PolishSuggestion(
                            category=AcademicPolishCategory.PASSIVE_ACTIVE,
                            original_text="multiple passive constructions",
                            suggested_replacement="active voice where appropriate",
                            severity=PolishSeverity.SUGGESTION,
                            explanation=f"Consider using more active voice (found {len(matches)} passive constructions)",
                            confidence=0.6,
                        )
                    )

        return suggestions

    def _check_citation_integration(self, text: str) -> list[PolishSuggestion]:
        """Check citation integration quality.

        Args:
            text: Text to check

        Returns:
            List of suggestions
        """
        suggestions = []

        # Check for weak citation phrasing
        import re

        weak_phrases = [
            (r"\bsays\b", "states", "Use more formal citation verbs"),
            (r"\btalks about\b", "discusses", "Use more formal citation verbs"),
        ]

        for pattern, replacement, explanation in weak_phrases:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Check if near a citation
                context = text[max(0, match.start() - 50) : min(len(text), match.end() + 50)]
                if re.search(r"\[\d+\]|\([A-Z][a-z]+,\s*\d{4}\)", context):
                    suggestions.append(
                        PolishSuggestion(
                            category=AcademicPolishCategory.CITATION_INTEGRATION,
                            original_text=match.group(),
                            suggested_replacement=replacement,
                            severity=PolishSeverity.WARNING,
                            explanation=explanation,
                            confidence=0.8,
                            start_pos=match.start(),
                            end_pos=match.end(),
                        )
                    )

        return suggestions

    async def auto_apply(
        self,
        text: str,
        categories: list[AcademicPolishCategory] | None = None,
        confidence_threshold: float = 0.9,
    ) -> str:
        """Auto-apply suggestions above confidence threshold.

        Only for high-confidence fixes (grammar, obvious word choice).
        Leave hedging/tone changes for human review.

        Args:
            text: Text to polish
            categories: Categories to auto-apply (None = grammar + word choice)
            confidence_threshold: Minimum confidence for auto-apply

        Returns:
            Polished text
        """
        if categories is None:
            categories = [
                AcademicPolishCategory.GRAMMAR,
                AcademicPolishCategory.WORD_CHOICE,
            ]

        report = await self.polish(text)

        # Sort suggestions by position (reverse order for replacement)
        applicable = [
            s
            for s in report.suggestions
            if s.category in categories and s.confidence >= confidence_threshold
        ]
        applicable.sort(key=lambda s: s.start_pos, reverse=True)

        # Apply replacements (reverse order to preserve positions)
        polished = text
        for suggestion in applicable:
            if suggestion.start_pos < len(polished) and suggestion.end_pos <= len(polished):
                polished = (
                    polished[: suggestion.start_pos]
                    + suggestion.suggested_replacement
                    + polished[suggestion.end_pos :]
                )

        return polished


# Convenience functions
async def polish_academic_prose(
    text: str,
    domain: str = "general",
    auto_apply: bool = False,
) -> PolishReport | str:
    """Convenience function for academic polishing.

    Args:
        text: Text to polish
        domain: Research domain
        auto_apply: Whether to auto-apply fixes

    Returns:
        PolishReport or polished text
    """
    polisher = AcademicProsePolisher(domain=domain)

    if auto_apply:
        return await polisher.auto_apply(text)
    else:
        return await polisher.polish(text)
