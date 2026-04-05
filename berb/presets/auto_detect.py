"""Domain auto-detection for preset selection.

This module automatically classifies research topics into
preset domains using LLM + keyword heuristics.

Features:
- Multi-label classification
- Confidence scoring
- Fallback to manual selection
- Custom domain rules

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from berb.llm.client import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class DomainSuggestion:
    """Domain suggestion with confidence.

    Attributes:
        preset_name: Preset name
        confidence: Confidence score (0-1)
        reasoning: Why this domain was suggested
        keywords_matched: Keywords that matched
    """

    preset_name: str
    confidence: float
    reasoning: str
    keywords_matched: list[str]


class DomainClassifier:
    """Classify research topics into preset domains.

    This classifier uses a combination of:
    1. Keyword matching (fast, deterministic)
    2. LLM-based classification (accurate, handles ambiguity)
    3. Custom rules (domain-specific logic)

    Usage::

        classifier = DomainClassifier(llm_provider)
        suggestions = await classifier.classify(
            topic="quantum error correction with neural networks"
        )
    """

    # Domain keyword mappings
    DOMAIN_KEYWORDS = {
        "ml-conference": [
            "machine learning", "deep learning", "neural network",
            "transformer", "attention", "gradient", "backprop",
            "classification", "regression", "clustering",
            "reinforcement learning", "RL", "policy gradient",
        ],
        "biomedical": [
            "clinical", "patient", "disease", "therapy",
            "drug", "gene", "protein", "cell",
            "trial", "cohort", "biomarker", "diagnosis",
            "treatment", "symptom", "pathology",
        ],
        "nlp": [
            "natural language", "text", "language model",
            "sentiment", "translation", "parsing",
            "named entity", "coreference", "syntax",
            "semantic", "pragmatic", "discourse",
            "LLM", "chatbot", "dialogue",
        ],
        "computer-vision": [
            "image", "video", "visual", "pixel",
            "convolution", "CNN", "detection", "segmentation",
            "object", "face", "scene", "optical",
            "rendering", "3D", "point cloud",
        ],
        "physics": [
            "quantum", "particle", "field", "force",
            "hamiltonian", "lagrangian", "thermodynamic",
            "entropy", "relativity", "spin",
            "chaos", "dynamical", "nonlinear",
        ],
        "social-sciences": [
            "social", "behavior", "psychology", "sociology",
            "survey", "interview", "qualitative",
            "attitude", "perception", "intervention",
            "demographic", "population", "sample",
        ],
        "engineering": [
            "system", "architecture", "distributed",
            "network", "protocol", "scalability",
            "latency", "throughput", "reliability",
            "deployment", "infrastructure", "cloud",
        ],
        "humanities": [
            "philosophy", "history", "literature",
            "cultural", "interpretation", "hermeneutic",
            "discourse", "narrative", "rhetoric",
            "ethical", "aesthetic", "ontological",
        ],
    }

    # Ambiguous topics that need LLM disambiguation
    AMBIGUOUS_TOPICS = {
        "quantum": ["physics", "ml-conference"],  # quantum computing vs quantum physics
        "neural": ["nlp", "ml-conference", "computer-vision"],
        "attention": ["nlp", "ml-conference"],
        "transformer": ["nlp", "computer-vision"],
        "clinical": ["biomedical", "social-sciences"],
        "network": ["engineering", "social-sciences"],
    }

    def __init__(self, llm_provider: LLMProvider | None = None):
        """Initialize domain classifier.

        Args:
            llm_provider: Optional LLM provider for disambiguation
        """
        self.llm_provider = llm_provider

    async def classify(
        self,
        topic: str,
        top_k: int = 2,
    ) -> list[DomainSuggestion]:
        """Classify topic into preset domains.

        Args:
            topic: Research topic string
            top_k: Number of suggestions to return

        Returns:
            List of domain suggestions
        """
        # Step 1: Keyword matching
        keyword_matches = self._keyword_match(topic)

        # Step 2: Check for ambiguity
        ambiguous = self._check_ambiguity(keyword_matches)

        if ambiguous and self.llm_provider:
            # Step 3: LLM disambiguation
            suggestions = await self._llm_disambiguate(topic, keyword_matches)
        else:
            # Convert keyword matches to suggestions
            suggestions = [
                DomainSuggestion(
                    preset_name=domain,
                    confidence=min(1.0, len(matches) / 3.0),  # Normalize
                    reasoning=f"Matched keywords: {', '.join(matches)}",
                    keywords_matched=matches,
                )
                for domain, matches in keyword_matches.items()
                if matches
            ]

        # Sort by confidence
        suggestions.sort(key=lambda s: s.confidence, reverse=True)

        return suggestions[:top_k]

    def _keyword_match(
        self,
        topic: str,
    ) -> dict[str, list[str]]:
        """Match topic keywords to domains.

        Args:
            topic: Research topic

        Returns:
            Dictionary of domain -> matched keywords
        """
        topic_lower = topic.lower()
        matches = {}

        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            domain_matches = []
            for keyword in keywords:
                if keyword in topic_lower:
                    domain_matches.append(keyword)

            if domain_matches:
                matches[domain] = domain_matches

        return matches

    def _check_ambiguity(
        self,
        matches: dict[str, list[str]],
    ) -> bool:
        """Check if topic is ambiguous.

        Args:
            matches: Keyword matches

        Returns:
            True if ambiguous
        """
        # Multiple domains with similar match counts
        if len(matches) > 1:
            match_counts = [len(m) for m in matches.values()]
            if max(match_counts) - min(match_counts) <= 1:
                return True

        # Check for known ambiguous keywords
        for domain, keywords in matches.items():
            for keyword in keywords:
                if keyword in self.AMBIGUOUS_TOPICS:
                    return True

        return False

    async def _llm_disambiguate(
        self,
        topic: str,
        matches: dict[str, list[str]],
    ) -> list[DomainSuggestion]:
        """Use LLM to disambiguate topic.

        Args:
            topic: Research topic
            matches: Keyword matches

        Returns:
            Disambiguated suggestions
        """
        if not self.llm_provider:
            return []

        # Build prompt
        candidate_domains = list(matches.keys())

        prompt = f"""Classify this research topic into the most appropriate domain(s).

Research Topic: "{topic}"

Candidate Domains: {', '.join(candidate_domains)}

For each domain, consider:
1. How well does the topic fit the domain's typical research?
2. What methodology would be used?
3. What venue would publish this?

Respond with JSON:
{{
    "primary_domain": "domain name",
    "confidence": 0.0-1.0,
    "reasoning": "explanation",
    "secondary_domain": "optional second domain",
    "secondary_confidence": 0.0-1.0
}}
"""

        try:
            response = await self.llm_provider.complete(
                messages=[{"role": "user", "content": prompt}],
                model="gpt-4o-mini",  # Budget model for classification
                temperature=0.3,
            )

            # Parse response
            import json
            import re

            json_match = re.search(r"\{.*\}", response.content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())

                suggestions = []

                # Primary suggestion
                if "primary_domain" in data:
                    suggestions.append(
                        DomainSuggestion(
                            preset_name=data["primary_domain"],
                            confidence=data.get("confidence", 0.5),
                            reasoning=data.get("reasoning", ""),
                            keywords_matched=matches.get(data["primary_domain"], []),
                        )
                    )

                # Secondary suggestion
                if "secondary_domain" in data:
                    suggestions.append(
                        DomainSuggestion(
                            preset_name=data["secondary_domain"],
                            confidence=data.get("secondary_confidence", 0.3),
                            reasoning=data.get("reasoning", ""),
                            keywords_matched=matches.get(data["secondary_domain"], []),
                        )
                    )

                return suggestions

        except Exception as e:
            logger.warning(f"LLM disambiguation failed: {e}")

        # Fallback to keyword-based suggestions
        return [
            DomainSuggestion(
                preset_name=domain,
                confidence=min(1.0, len(kw) / 3.0),
                reasoning=f"Keyword match: {', '.join(kw)}",
                keywords_matched=kw,
            )
            for domain, kw in matches.items()
        ]


class DomainDetector:
    """High-level domain detection interface.

    Provides simple interface for detecting domains
    and suggesting presets.

    Usage::

        detector = DomainDetector(llm_provider)
        result = await detector.detect_domain(
            topic="quantum error correction"
        )
        print(f"Suggested preset: {result.best_preset}")
    """

    def __init__(self, llm_provider: LLMProvider | None = None):
        """Initialize domain detector.

        Args:
            llm_provider: LLM provider
        """
        self.classifier = DomainClassifier(llm_provider)

    async def detect_domain(
        self,
        topic: str,
    ) -> DomainDetectionResult:
        """Detect domain for a topic.

        Args:
            topic: Research topic

        Returns:
            DomainDetectionResult
        """
        suggestions = await self.classifier.classify(topic, top_k=3)

        return DomainDetectionResult(
            topic=topic,
            suggestions=suggestions,
            best_preset=suggestions[0].preset_name if suggestions else "ml-conference",
        )


class DomainDetectionResult(BaseModel):
    """Result of domain detection.

    Attributes:
        topic: Original topic
        suggestions: All suggestions
        best_preset: Best preset name
    """

    topic: str
    suggestions: list[DomainSuggestion] = Field(default_factory=list)
    best_preset: str = "ml-conference"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "topic": self.topic,
            "best_preset": self.best_preset,
            "suggestions": [
                {
                    "preset": s.preset_name,
                    "confidence": s.confidence,
                    "reasoning": s.reasoning,
                }
                for s in self.suggestions
            ],
        }


# Convenience function
async def detect_domain(
    topic: str,
    llm_provider: LLMProvider | None = None,
) -> DomainDetectionResult:
    """Convenience function for domain detection.

    Args:
        topic: Research topic
        llm_provider: LLM provider

    Returns:
        DomainDetectionResult
    """
    detector = DomainDetector(llm_provider)
    return await detector.detect_domain(topic)
