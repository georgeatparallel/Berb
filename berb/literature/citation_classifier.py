"""Smart citation classification engine.

This module classifies citations by intent (supporting/contrasting/mentioning)
using LLM-based analysis, enabling evidence-grounded research and intelligent
citation placement.

Features:
- Citation intent classification (supporting/contrasting/mentioning)
- Batch classification for efficiency
- Paper citation profile aggregation
- Berb confidence score computation
- Integration with literature search pipeline

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from berb.llm.client import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class CitationIntent(str, Enum):
    """Citation intent classification.

    Attributes:
        SUPPORTING: Citation provides evidence FOR the cited claim
        CONTRASTING: Citation provides evidence AGAINST the cited claim
        MENTIONING: Citation references without evaluative stance
    """

    SUPPORTING = "supporting"
    CONTRASTING = "contrasting"
    MENTIONING = "mentioning"


class CitationClassification(BaseModel):
    """Classification result for a single citation.

    Attributes:
        citing_paper_id: ID of the paper doing the citing
        cited_paper_id: ID of the paper being cited
        intent: Classification intent
        confidence: Confidence score (0.0-1.0)
        context_snippet: The sentence(s) surrounding the citation
        section: Section where citation appears (intro/methods/results/discussion)
        reasoning: Brief reasoning for the classification
    """

    citing_paper_id: str
    cited_paper_id: str
    intent: CitationIntent
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for classification",
    )
    context_snippet: str = Field(
        description="Sentence(s) surrounding the citation",
    )
    section: str = Field(
        default="unknown",
        description="Section where citation appears",
    )
    reasoning: str = Field(
        default="",
        description="Brief reasoning for the classification",
    )


class PaperCitationProfile(BaseModel):
    """Aggregate citation profile for a paper.

    Attributes:
        paper_id: Paper identifier
        total_citations: Total number of citations
        supporting_count: Number of supporting citations
        contrasting_count: Number of contrasting citations
        mentioning_count: Number of mentioning citations
        classifications: Individual citation classifications
        berb_confidence_score: Overall confidence score
    """

    paper_id: str
    total_citations: int = 0
    supporting_count: int = 0
    contrasting_count: int = 0
    mentioning_count: int = 0
    classifications: list[CitationClassification] = Field(default_factory=list)
    berb_confidence_score: float = Field(
        default=0.0,
        description="(supporting - contrasting) / total, weighted by recency",
    )


class CitationClassifier:
    """LLM-based citation intent classifier.

    This classifier analyzes citation context to determine whether a citation
    supports, contrasts, or merely mentions the cited work.

    Usage::

        classifier = CitationClassifier(llm_provider)
        result = await classifier.classify(
            context="Smith (2024) demonstrated that X improves Y by 15%.",
            claim="X improves Y",
            citing_paper_id="paper-123",
            cited_paper_id="smith-2024",
        )

    Attributes:
        llm_provider: LLM provider for classification
        model: Model to use for classification
        min_confidence: Minimum confidence threshold
    """

    # Classification prompt template
    CLASSIFICATION_PROMPT = """You are an expert research analyst assistant. Your task is to classify the intent of citations in academic papers.

Given a citation context from a research paper and the cited paper's main finding, classify whether the citation:
- SUPPORTS the cited finding (provides evidence for it)
- CONTRASTS the cited finding (provides evidence against it or challenges it)
- MERELY MENTIONS the cited finding (references it without evaluative stance)

## Citation Context
{context}

## Cited Paper's Main Finding
{claim}

## Instructions
1. Analyze the relationship between the context and the claim
2. Look for keywords indicating support (e.g., "consistent with", "confirms", "demonstrates")
3. Look for keywords indicating contrast (e.g., "however", "in contrast", "challenges", "contradicts")
4. Consider the overall tone and framing

Respond with JSON in this exact format:
{{
    "intent": "supporting|contrasting|mentioning",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of your classification"
}}

Be conservative with confidence scores. Only assign high confidence (>0.8) when the intent is unambiguous."""

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        model: str = "gemini-2.5-flash",  # Budget model for throughput
        min_confidence: float = 0.7,
    ):
        """Initialize citation classifier.

        Args:
            llm_provider: LLM provider instance
            model: Model to use for classification
            min_confidence: Minimum confidence threshold for valid classifications
        """
        self.llm_provider = llm_provider
        self.model = model
        self.min_confidence = min_confidence

        # Classification cache
        self._cache: dict[str, CitationClassification] = {}

    async def classify(
        self,
        context: str,
        claim: str,
        citing_paper_id: str,
        cited_paper_id: str,
        section: str = "unknown",
    ) -> CitationClassification:
        """Classify a single citation.

        Args:
            context: Citation context (sentence containing citation)
            claim: The cited paper's main finding/claim
            citing_paper_id: ID of paper doing the citing
            cited_paper_id: ID of paper being cited
            section: Section where citation appears

        Returns:
            CitationClassification result
        """
        # Check cache
        cache_key = f"{citing_paper_id}:{cited_paper_id}:{hash(context)}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not self.llm_provider:
            # Return default mentioning classification
            return CitationClassification(
                citing_paper_id=citing_paper_id,
                cited_paper_id=cited_paper_id,
                intent=CitationIntent.MENTIONING,
                confidence=0.5,
                context_snippet=context,
                section=section,
                reasoning="No LLM provider available",
            )

        # Build prompt
        prompt = self.CLASSIFICATION_PROMPT.format(
            context=context,
            claim=claim,
        )

        try:
            # Call LLM
            response = await self.llm_provider.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.3,  # Low temperature for consistency
            )

            # Parse response
            result = self._parse_response(response, context)
            result.citing_paper_id = citing_paper_id
            result.cited_paper_id = cited_paper_id
            result.section = section

            # Cache result
            self._cache[cache_key] = result

            logger.debug(
                f"Classified citation {cited_paper_id} in {citing_paper_id}: "
                f"{result.intent.value} (confidence: {result.confidence:.2f})"
            )

            return result

        except Exception as e:
            logger.warning(f"Citation classification failed: {e}")
            # Return low-confidence mentioning classification
            return CitationClassification(
                citing_paper_id=citing_paper_id,
                cited_paper_id=cited_paper_id,
                intent=CitationIntent.MENTIONING,
                confidence=0.3,
                context_snippet=context,
                section=section,
                reasoning=f"Classification failed: {e}",
            )

    def _parse_response(
        self, response: LLMResponse, context: str
    ) -> CitationClassification:
        """Parse LLM response into CitationClassification.

        Args:
            response: LLM response
            context: Original context snippet

        Returns:
            Parsed CitationClassification
        """
        import json
        import re

        text = response.content.strip()

        # Try to extract JSON from response
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return CitationClassification(
                    citing_paper_id="",  # Will be set by caller
                    cited_paper_id="",
                    intent=CitationIntent(data.get("intent", "mentioning")),
                    confidence=float(data.get("confidence", 0.5)),
                    context_snippet=context,
                    reasoning=data.get("reasoning", ""),
                )
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse JSON response: {e}")

        # Fallback: keyword-based classification
        return self._keyword_classify(context)

    def _keyword_classify(self, context: str) -> CitationClassification:
        """Fallback keyword-based classification.

        Args:
            context: Citation context

        Returns:
            Keyword-based Classification
        """
        context_lower = context.lower()

        # Supporting keywords
        supporting_keywords = [
            "consistent with", "confirms", "demonstrates", "supports",
            "validates", "corroborates", "in agreement with", "replicates",
        ]

        # Contrasting keywords
        contrasting_keywords = [
            "however", "in contrast", "contradicts", "challenges",
            "disagrees with", "unlike", "differs from", "questions",
            "casts doubt on", "refutes",
        ]

        support_count = sum(1 for kw in supporting_keywords if kw in context_lower)
        contrast_count = sum(1 for kw in contrasting_keywords if kw in context_lower)

        if support_count > contrast_count:
            intent = CitationIntent.SUPPORTING
            confidence = min(0.5 + (support_count * 0.15), 0.85)
        elif contrast_count > support_count:
            intent = CitationIntent.CONTRASTING
            confidence = min(0.5 + (contrast_count * 0.15), 0.85)
        else:
            intent = CitationIntent.MENTIONING
            confidence = 0.5

        return CitationClassification(
            citing_paper_id="",
            cited_paper_id="",
            intent=intent,
            confidence=confidence,
            context_snippet=context,
            reasoning="Keyword-based classification (fallback)",
        )

    async def classify_batch(
        self,
        citations: list[tuple[str, str, str, str]],  # (context, claim, citing_id, cited_id)
        model: str | None = None,
    ) -> list[CitationClassification]:
        """Classify multiple citations in batch.

        Args:
            citations: List of (context, claim, citing_paper_id, cited_paper_id) tuples
            model: Optional model override

        Returns:
            List of CitationClassification results
        """
        model = model or self.model
        results = []

        # Process in parallel if possible
        tasks = [
            self.classify(
                context=context,
                claim=claim,
                citing_paper_id=citing_id,
                cited_paper_id=cited_id,
            )
            for context, claim, citing_id, cited_id in citations
        ]

        import asyncio
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Batch classification failed for item {i}: {result}")
                final_results.append(
                    CitationClassification(
                        citing_paper_id=citations[i][2],
                        cited_paper_id=citations[i][3],
                        intent=CitationIntent.MENTIONING,
                        confidence=0.3,
                        context_snippet=citations[i][0],
                        reasoning=f"Batch classification failed: {result}",
                    )
                )
            else:
                final_results.append(result)

        return final_results

    async def build_paper_citation_profile(
        self,
        paper_id: str,
        citations: list[tuple[str, str, str]],  # (context, claim, cited_paper_id)
    ) -> PaperCitationProfile:
        """Build aggregate citation profile for a paper.

        Args:
            paper_id: Paper identifier
            citations: List of (context, claim, cited_paper_id) tuples

        Returns:
            PaperCitationProfile with aggregate statistics
        """
        classifications = await self.classify_batch([
            (context, claim, paper_id, cited_id)
            for context, claim, cited_id in citations
        ])

        # Count by intent
        supporting = sum(1 for c in classifications if c.intent == CitationIntent.SUPPORTING)
        contrasting = sum(1 for c in classifications if c.intent == CitationIntent.CONTRASTING)
        mentioning = sum(1 for c in classifications if c.intent == CitationIntent.MENTIONING)

        # Compute Berb confidence score
        total = len(classifications)
        if total > 0:
            # (supporting - contrasting) / total, normalized to 0-1
            raw_score = (supporting - contrasting) / total
            berb_confidence = (raw_score + 1) / 2  # Normalize to 0-1
        else:
            berb_confidence = 0.5

        return PaperCitationProfile(
            paper_id=paper_id,
            total_citations=total,
            supporting_count=supporting,
            contrasting_count=contrasting,
            mentioning_count=mentioning,
            classifications=classifications,
            berb_confidence_score=berb_confidence,
        )

    def compute_berb_confidence_score(
        self, profile: PaperCitationProfile
    ) -> float:
        """Compute Berb confidence score from citation profile.

        The Berb confidence score represents the net support for a paper's
        claims, normalized to 0-1.

        Formula: (supporting - contrasting) / total, normalized to 0-1

        Args:
            profile: Paper citation profile

        Returns:
            Berb confidence score (0-1)
        """
        total = profile.total_citations
        if total == 0:
            return 0.5

        raw_score = (profile.supporting_count - profile.contrasting_count) / total
        # Normalize from [-1, 1] to [0, 1]
        return (raw_score + 1) / 2


class CitationClassifierConfig(BaseModel):
    """Configuration for citation classifier.

    Attributes:
        enabled: Whether citation classification is enabled
        classifier_model: Model for classification
        min_confidence: Minimum confidence threshold
        classify_top_n_papers: Only classify top N most relevant papers
        inject_into_writing: Whether to inject classification into writing prompts
    """

    enabled: bool = True
    classifier_model: str = "gemini-2.5-flash"
    min_confidence: float = 0.7
    classify_top_n_papers: int = 50
    inject_into_writing: bool = True


async def classify_citations(
    citations: list[tuple[str, str, str, str]],
    llm_provider: LLMProvider | None = None,
    model: str = "gemini-2.5-flash",
) -> list[CitationClassification]:
    """Convenience function to classify citations.

    Args:
        citations: List of (context, claim, citing_paper_id, cited_paper_id) tuples
        llm_provider: LLM provider instance
        model: Model for classification

    Returns:
        List of CitationClassification results
    """
    classifier = CitationClassifier(llm_provider=llm_provider, model=model)
    return await classifier.classify_batch(citations)
