"""Evidence consensus mapping with Bayesian reasoning.

This module builds structured evidence landscapes for key claims,
showing supporting/contrasting studies and consensus levels.

Uses Bayesian reasoning for evidence aggregation and consensus estimation.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from berb.reasoning.bayesian import BayesianMethod, BayesianResult, Hypothesis, Evidence
from berb.llm.client import LLMProvider

logger = logging.getLogger(__name__)


class ConsensusLevel(str, Enum):
    """Level of scientific consensus.

    Attributes:
        STRONG_SUPPORT: Overwhelming evidence supports claim (>90%)
        MODERATE_SUPPORT: More evidence supports than contradicts (70-90%)
        WEAK_SUPPORT: Slight evidence support (55-70%)
        MIXED: Conflicting evidence (45-55%)
        WEAK_CONTRAST: Slight evidence against (30-45%)
        MODERATE_CONTRAST: More evidence against (10-30%)
        STRONG_CONTRAST: Overwhelming evidence against (<10%)
    """

    STRONG_SUPPORT = "strong_support"
    MODERATE_SUPPORT = "moderate_support"
    WEAK_SUPPORT = "weak_support"
    MIXED = "mixed"
    WEAK_CONTRAST = "weak_contrast"
    MODERATE_CONTRAST = "moderate_contrast"
    STRONG_CONTRAST = "strong_contrast"


class StudyType(str, Enum):
    """Type of study evidence.

    Attributes:
        SUPPORTING: Study supports the claim
        CONTRASTING: Study contradicts the claim
        NEUTRAL: Study mentions claim without taking position
    """

    SUPPORTING = "supporting"
    CONTRASTING = "contrasting"
    NEUTRAL = "neutral"


class StudyProfile(BaseModel):
    """Profile of a study in the evidence map.

    Attributes:
        id: Study identifier (DOI, paper ID, etc.)
        title: Study title
        authors: Author list
        year: Publication year
        journal: Journal/venue name
        study_type: Type of evidence (supporting/contrasting)
        quality_score: Study quality score (0-10)
        sample_size: Sample size (if applicable)
        effect_size: Reported effect size (if applicable)
        methodology: Study methodology
        key_findings: Key findings relevant to claim
    """

    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    journal: str | None = None
    study_type: StudyType
    quality_score: float = Field(default=5.0, ge=0.0, le=10.0)
    sample_size: int | None = None
    effect_size: float | None = None
    methodology: str = ""
    key_findings: list[str] = Field(default_factory=list)

    def weight(self) -> float:
        """Calculate study weight for consensus calculation.

        Returns:
            Study weight (0-1) based on quality and sample size
        """
        quality_weight = self.quality_score / 10.0

        # Sample size weight (logarithmic)
        if self.sample_size:
            size_weight = min(1.0, math.log10(max(self.sample_size, 10)) / 4.0)
        else:
            size_weight = 0.5

        return (quality_weight + size_weight) / 2.0


class ClaimEvidence(BaseModel):
    """Evidence mapping for a single claim.

    Attributes:
        claim: The claim being evaluated
        consensus: Consensus level
        confidence: Confidence in consensus (0-1)
        supporting_count: Number of supporting studies
        contrasting_count: Number of contrasting studies
        key_supporters: Top supporting studies by weight
        key_challengers: Top contrasting studies by weight
        trend: Evidence trend over time
        recommended_hedging: Recommended hedging level for writing
        bayesian_posterior: Posterior probability from Bayesian analysis
    """

    claim: str
    consensus: ConsensusLevel
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_count: int = 0
    contrasting_count: int = 0
    key_supporters: list[StudyProfile] = Field(default_factory=list)
    key_challengers: list[StudyProfile] = Field(default_factory=list)
    trend: Literal["stable", "growing_support", "declining", "emerging_debate"] = "stable"
    recommended_hedging: Literal["assertive", "moderate", "cautious", "highly_hedged"] = "moderate"
    bayesian_posterior: float = Field(default=0.5, ge=0.0, le=1.0)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "claim": self.claim,
            "consensus": self.consensus.value,
            "confidence": self.confidence,
            "supporting_count": self.supporting_count,
            "contrasting_count": self.contrasting_count,
            "key_supporters": [s.model_dump() for s in self.key_supporters],
            "key_challengers": [s.model_dump() for s in self.key_challengers],
            "trend": self.trend,
            "recommended_hedging": self.recommended_hedging,
            "bayesian_posterior": self.bayesian_posterior,
        }


class EvidenceMap(BaseModel):
    """Complete evidence map for multiple claims.

    Attributes:
        claims: Map of claims to their evidence
        generated_at: When the map was generated
        total_studies_analyzed: Total studies analyzed
        domain: Research domain
    """

    claims: dict[str, ClaimEvidence] = Field(default_factory=dict)
    generated_at: str = ""
    total_studies_analyzed: int = 0
    domain: str = ""

    def add_claim(self, claim: str, evidence: ClaimEvidence) -> None:
        """Add claim evidence to map.

        Args:
            claim: Claim text
            evidence: ClaimEvidence object
        """
        self.claims[claim] = evidence
        self.total_studies_analyzed += (
            evidence.supporting_count + evidence.contrasting_count
        )

    def get_consensus_summary(self) -> dict[str, int]:
        """Get summary of consensus levels.

        Returns:
            Dictionary with count per consensus level
        """
        summary = {level.value: 0 for level in ConsensusLevel}
        for evidence in self.claims.values():
            summary[evidence.consensus.value] += 1
        return summary


class EvidenceConsensusConfig(BaseModel):
    """Configuration for evidence consensus mapping.

    Attributes:
        use_bayesian: Whether to use Bayesian reasoning
        min_studies_for_consensus: Minimum studies needed for consensus
        quality_threshold: Minimum quality score for included studies
        recency_weight: Weight for recent studies (0-1)
        llm_provider: LLM provider for Bayesian reasoning
    """

    use_bayesian: bool = True
    min_studies_for_consensus: int = 3
    quality_threshold: float = 5.0
    recency_weight: float = 0.2
    llm_provider: LLMProvider | None = None


class EvidenceConsensusMapper:
    """Build evidence consensus maps using Bayesian reasoning.

    This mapper:
    1. Collects studies for each claim
    2. Weights studies by quality and sample size
    3. Uses Bayesian reasoning to aggregate evidence
    4. Classifies consensus level
    5. Recommends hedging language for writing

    Usage::

        mapper = EvidenceConsensusMapper(
            config=EvidenceConsensusConfig(
                use_bayesian=True,
                llm_provider=llm_provider,
            ),
        )

        evidence_map = await mapper.build_map(
            claims=["Claim 1", "Claim 2"],
            studies=study_list,
        )

    Attributes:
        config: Configuration
        bayesian_method: Bayesian reasoning method
    """

    def __init__(self, config: EvidenceConsensusConfig | None = None):
        """Initialize evidence mapper.

        Args:
            config: Configuration
        """
        self.config = config or EvidenceConsensusConfig()

        # Initialize Bayesian method if LLM provider available
        self.bayesian_method = None
        if self.config.llm_provider and self.config.use_bayesian:
            self.bayesian_method = BayesianMethod(self.config.llm_provider)

        # Study cache
        self._study_cache: dict[str, StudyProfile] = {}

    async def build_map(
        self,
        claims: list[str],
        studies: list[dict[str, Any]],
        domain: str = "",
    ) -> EvidenceMap:
        """Build evidence map for multiple claims.

        Args:
            claims: List of claims to map
            studies: List of study metadata
            domain: Research domain

        Returns:
            EvidenceMap with consensus for each claim
        """
        from datetime import datetime, timezone

        evidence_map = EvidenceMap(
            generated_at=datetime.now(timezone.utc).isoformat(),
            domain=domain,
        )

        # Process each claim
        for claim in claims:
            # Find relevant studies
            relevant_studies = self._find_relevant_studies(claim, studies)

            if not relevant_studies:
                # No studies found
                evidence_map.add_claim(
                    claim,
                    ClaimEvidence(
                        claim=claim,
                        consensus=ConsensusLevel.MIXED,
                        confidence=0.3,
                        bayesian_posterior=0.5,
                    ),
                )
                continue

            # Build consensus
            evidence = await self._build_consensus(claim, relevant_studies)
            evidence_map.add_claim(claim, evidence)

        logger.info(
            f"Built evidence map: {len(claims)} claims, "
            f"{evidence_map.total_studies_analyzed} studies analyzed"
        )

        return evidence_map

    async def build_consensus_for_claim(
        self,
        claim: str,
        supporting_studies: list[StudyProfile],
        contrasting_studies: list[StudyProfile],
    ) -> ClaimEvidence:
        """Build consensus for a single claim.

        Args:
            claim: Claim text
            supporting_studies: Studies supporting the claim
            contrasting_studies: Studies contradicting the claim

        Returns:
            ClaimEvidence with consensus
        """
        # Combine all studies
        all_studies = supporting_studies + contrasting_studies

        if len(all_studies) < self.config.min_studies_for_consensus:
            # Not enough studies for confident consensus
            return ClaimEvidence(
                claim=claim,
                consensus=ConsensusLevel.MIXED,
                confidence=0.4,
                supporting_count=len(supporting_studies),
                contrasting_count=len(contrasting_studies),
                bayesian_posterior=0.5,
            )

        # Calculate weighted evidence
        supporting_weight = sum(s.weight() for s in supporting_studies)
        contrasting_weight = sum(s.weight() for s in contrasting_studies)
        total_weight = supporting_weight + contrasting_weight

        if total_weight == 0:
            return ClaimEvidence(
                claim=claim,
                consensus=ConsensusLevel.MIXED,
                confidence=0.3,
            )

        # Bayesian update
        if self.bayesian_method:
            posterior = await self._bayesian_evidence_update(
                claim=claim,
                supporting=supporting_studies,
                contrasting=contrasting_studies,
            )
        else:
            # Simple weighted calculation
            posterior = supporting_weight / total_weight

        # Classify consensus
        consensus = self._classify_consensus(posterior)

        # Determine trend
        trend = self._determine_trend(supporting_studies, contrasting_studies)

        # Recommend hedging
        hedging = self._recommend_hedging(consensus, posterior)

        # Get top studies
        key_supporters = sorted(
            supporting_studies, key=lambda s: s.weight(), reverse=True
        )[:3]
        key_challengers = sorted(
            contrasting_studies, key=lambda s: s.weight(), reverse=True
        )[:3]

        return ClaimEvidence(
            claim=claim,
            consensus=consensus,
            confidence=min(1.0, len(all_studies) / 10.0),  # More studies = more confidence
            supporting_count=len(supporting_studies),
            contrasting_count=len(contrasting_studies),
            key_supporters=key_supporters,
            key_challengers=key_challengers,
            trend=trend,
            recommended_hedging=hedging,
            bayesian_posterior=posterior,
        )

    def _find_relevant_studies(
        self,
        claim: str,
        studies: list[dict[str, Any]],
    ) -> list[StudyProfile]:
        """Find studies relevant to a claim.

        Args:
            claim: Claim text
            studies: List of study metadata

        Returns:
            List of relevant StudyProfiles
        """
        relevant = []
        claim_lower = claim.lower()

        for study_data in studies:
            # Check if study is relevant (simplified keyword matching)
            # In production, would use semantic similarity
            title = study_data.get("title", "").lower()
            findings = " ".join(study_data.get("key_findings", [])).lower()

            # Extract key terms from claim
            claim_terms = [
                t for t in claim_lower.split()
                if len(t) > 4 and t not in {"that", "this", "which", "there", "their"}
            ]

            # Check for term overlap
            overlap = sum(1 for term in claim_terms if term in title or term in findings)

            if overlap >= 2:  # At least 2 term matches
                # Determine study type (simplified)
                study_type = self._classify_study_type(study_data, claim_lower)

                profile = StudyProfile(
                    id=study_data.get("id", study_data.get("doi", "")),
                    title=study_data.get("title", ""),
                    authors=study_data.get("authors", []),
                    year=study_data.get("year"),
                    journal=study_data.get("journal"),
                    study_type=study_type,
                    quality_score=study_data.get("quality_score", 5.0),
                    sample_size=study_data.get("sample_size"),
                    effect_size=study_data.get("effect_size"),
                    methodology=study_data.get("methodology", ""),
                    key_findings=study_data.get("key_findings", []),
                )

                relevant.append(profile)
                self._study_cache[profile.id] = profile

        return relevant

    def _classify_study_type(
        self,
        study_data: dict[str, Any],
        claim_lower: str,
    ) -> StudyType:
        """Classify study as supporting/contrasting/neutral.

        Args:
            study_data: Study metadata
            claim_lower: Claim text (lowercase)

        Returns:
            StudyType
        """
        findings = " ".join(study_data.get("key_findings", [])).lower()
        conclusion = study_data.get("conclusion", "").lower()

        # Keywords indicating support
        support_keywords = [
            "supports", "confirms", "validates", "demonstrates",
            "consistent with", "in agreement", "corroborates",
        ]

        # Keywords indicating contrast
        contrast_keywords = [
            "contradicts", "challenges", "refutes", "disagrees",
            "inconsistent with", "fails to support", "no evidence",
        ]

        text = findings + " " + conclusion

        support_count = sum(1 for kw in support_keywords if kw in text)
        contrast_count = sum(1 for kw in contrast_keywords if kw in text)

        if support_count > contrast_count:
            return StudyType.SUPPORTING
        elif contrast_count > support_count:
            return StudyType.CONTRASTING
        else:
            return StudyType.NEUTRAL

    async def _bayesian_evidence_update(
        self,
        claim: str,
        supporting: list[StudyProfile],
        contrasting: list[StudyProfile],
    ) -> float:
        """Update belief in claim using Bayesian reasoning.

        Args:
            claim: Claim text
            supporting: Supporting studies
            contrasting: Contrasting studies

        Returns:
            Posterior probability (0-1)
        """
        if not self.bayesian_method:
            # Fallback to simple weighted average
            sup_weight = sum(s.weight() for s in supporting)
            con_weight = sum(s.weight() for s in contrasting)
            total = sup_weight + con_weight
            return sup_weight / total if total > 0 else 0.5

        # Define hypotheses
        hypotheses = [
            Hypothesis(
                name="claim_true",
                prior=0.5,
                description=f"Claim is true: {claim[:100]}",
            ),
            Hypothesis(
                name="claim_false",
                prior=0.5,
                description=f"Claim is false: {claim[:100]}",
            ),
        ]

        # Build evidence items from studies
        evidence_items = []

        for study in supporting[:10]:  # Limit to top 10 per side
            weight = study.weight()
            evidence_items.append(
                Evidence(
                    name=f"support_{study.id}",
                    description=f"Supporting study: {study.title[:50]}",
                    likelihood_given_h={
                        "claim_true": 0.7 + (weight * 0.3),  # High if claim true
                        "claim_false": 0.2,  # Low if claim false
                    },
                    likelihood_given_not_h={
                        "claim_true": 0.2,
                        "claim_false": 0.7 + (weight * 0.3),
                    },
                )
            )

        for study in contrasting[:10]:
            weight = study.weight()
            evidence_items.append(
                Evidence(
                    name=f"contrast_{study.id}",
                    description=f"Contrasting study: {study.title[:50]}",
                    likelihood_given_h={
                        "claim_true": 0.2,  # Low if claim true
                        "claim_false": 0.7 + (weight * 0.3),  # High if claim false
                    },
                    likelihood_given_not_h={
                        "claim_true": 0.7 + (weight * 0.3),
                        "claim_false": 0.2,
                    },
                )
            )

        # Execute Bayesian reasoning
        from berb.reasoning.base import ReasoningContext

        context = ReasoningContext(
            stage_id="EVIDENCE_CONSENSUS",
            stage_name="Evidence Consensus Analysis",
            input_data={
                "hypotheses": hypotheses,
                "evidence": evidence_items,
            },
        )

        try:
            result = await self.bayesian_method.execute(context)

            # Extract posterior for claim_true
            if isinstance(result.output, dict) and "posteriors" in result.output:
                posteriors = result.output["posteriors"]
                for p in posteriors:
                    if p.get("name") == "claim_true":
                        return p.get("posterior", 0.5)

        except Exception as e:
            logger.warning(f"Bayesian evidence update failed: {e}")

        # Fallback to simple weighted average
        sup_weight = sum(s.weight() for s in supporting)
        con_weight = sum(s.weight() for s in contrasting)
        total = sup_weight + con_weight
        return sup_weight / total if total > 0 else 0.5

    def _classify_consensus(self, posterior: float) -> ConsensusLevel:
        """Classify consensus level from posterior probability.

        Args:
            posterior: Posterior probability (0-1)

        Returns:
            ConsensusLevel
        """
        if posterior >= 0.9:
            return ConsensusLevel.STRONG_SUPPORT
        elif posterior >= 0.7:
            return ConsensusLevel.MODERATE_SUPPORT
        elif posterior >= 0.55:
            return ConsensusLevel.WEAK_SUPPORT
        elif posterior >= 0.45:
            return ConsensusLevel.MIXED
        elif posterior >= 0.3:
            return ConsensusLevel.WEAK_CONTRAST
        elif posterior >= 0.1:
            return ConsensusLevel.MODERATE_CONTRAST
        else:
            return ConsensusLevel.STRONG_CONTRAST

    def _determine_trend(
        self,
        supporting: list[StudyProfile],
        contrasting: list[StudyProfile],
    ) -> Literal["stable", "growing_support", "declining", "emerging_debate"]:
        """Determine evidence trend over time.

        Args:
            supporting: Supporting studies
            contrasting: Contrasting studies

        Returns:
            Trend description
        """
        from datetime import datetime

        current_year = datetime.now().year

        # Split by recency (last 5 years vs older)
        recent_cutoff = current_year - 5

        recent_support = sum(
            1 for s in supporting if s.year and s.year >= recent_cutoff
        )
        old_support = len(supporting) - recent_support

        recent_contrast = sum(
            1 for s in contrasting if s.year and s.year >= recent_cutoff
        )
        old_contrast = len(contrasting) - recent_contrast

        # Calculate recent ratio
        recent_total = recent_support + recent_contrast
        if recent_total == 0:
            return "stable"

        recent_support_ratio = recent_support / recent_total

        # Compare recent vs old
        old_total = old_support + old_contrast
        if old_total > 0:
            old_support_ratio = old_support / old_total

            if recent_support_ratio > old_support_ratio + 0.2:
                return "growing_support"
            elif recent_support_ratio < old_support_ratio - 0.2:
                return "declining"

        # Check for emerging debate (both sides have recent studies)
        if recent_support >= 2 and recent_contrast >= 2:
            return "emerging_debate"

        return "stable"

    def _recommend_hedging(
        self,
        consensus: ConsensusLevel,
        posterior: float,
    ) -> Literal["assertive", "moderate", "cautious", "highly_hedged"]:
        """Recommend hedging level for writing.

        Args:
            consensus: Consensus level
            posterior: Posterior probability

        Returns:
            Recommended hedging level
        """
        if consensus in (
            ConsensusLevel.STRONG_SUPPORT,
            ConsensusLevel.STRONG_CONTRAST,
        ):
            return "assertive"
        elif consensus in (
            ConsensusLevel.MODERATE_SUPPORT,
            ConsensusLevel.MODERATE_CONTRAST,
        ):
            return "moderate"
        elif consensus == ConsensusLevel.WEAK_SUPPORT:
            return "cautious"
        else:
            return "highly_hedged"


class EvidenceMapGenerator:
    """High-level interface for evidence map generation.

    Integrates with literature search to automatically
    build evidence maps for claims.

    Usage::

        generator = EvidenceMapGenerator(llm_provider)
        evidence_map = await generator.generate(
            claims=["Claim 1", "Claim 2"],
            domain="machine-learning",
        )
    """

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        search_client: Any | None = None,
    ):
        """Initialize evidence map generator.

        Args:
            llm_provider: LLM provider for Bayesian reasoning
            search_client: Literature search client
        """
        self.mapper = EvidenceConsensusMapper(
            config=EvidenceConsensusConfig(
                use_bayesian=True,
                llm_provider=llm_provider,
            ),
        )
        self.search_client = search_client

    async def generate(
        self,
        claims: list[str],
        domain: str = "",
        max_studies_per_claim: int = 50,
    ) -> EvidenceMap:
        """Generate evidence map for claims.

        Args:
            claims: Claims to map
            domain: Research domain
            max_studies_per_claim: Max studies per claim

        Returns:
            EvidenceMap
        """
        all_studies = []

        # Search for studies for each claim
        if self.search_client:
            for claim in claims:
                studies = await self.search_client.search_papers(
                    query=claim,
                    limit=max_studies_per_claim,
                )
                all_studies.extend(studies)
        else:
            # Would need search client integration
            logger.warning("No search client available - using empty study set")

        return await self.mapper.build_map(claims, all_studies, domain)


# Convenience function
async def build_evidence_map(
    claims: list[str],
    studies: list[dict[str, Any]],
    llm_provider: LLMProvider | None = None,
    domain: str = "",
) -> EvidenceMap:
    """Convenience function to build evidence map.

    Args:
        claims: Claims to map
        studies: Study metadata
        llm_provider: LLM provider for Bayesian reasoning
        domain: Research domain

    Returns:
        EvidenceMap
    """
    mapper = EvidenceConsensusMapper(
        config=EvidenceConsensusConfig(
            use_bayesian=llm_provider is not None,
            llm_provider=llm_provider,
        ),
    )
    return await mapper.build_map(claims, studies, domain)
