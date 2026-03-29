"""Claim integrity tracker for scientific integrity.

This module tracks every empirical claim through the pipeline:
- Register claims when made
- Track challenges from reviewers
- Verify claims with evidence (enhanced with Bayesian reasoning)
- Kill claims that don't hold up

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ClaimVerdict(str, Enum):
    """Verdict for claim verification.

    Attributes:
        SUPPORTED: Claim is supported by evidence
        WEAKENED: Claim has some support but weakened
        REFUTED: Claim is refuted by evidence
        INCONCLUSIVE: Cannot determine support
    """

    SUPPORTED = "supported"
    WEAKENED = "weakened"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class ChallengeEvent(BaseModel):
    """Challenge event for a claim.

    Attributes:
        round: Improvement round number
        reason: Reason for challenge
        challenger: Who challenged (reviewer, self-check, etc.)
        timestamp: When challenged
    """

    round: int
    reason: str
    challenger: str = "reviewer"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ClaimRecord(BaseModel):
    """Track lifecycle of an empirical claim.

    Attributes:
        id: Unique claim identifier
        text: Claim text
        source_stage: Pipeline stage where claim originated
        registered_round: Round when claim was registered
        evidence: Supporting evidence
        status: Current claim status
        challenge_history: History of challenges
        kill_reason: Reason if claim was killed
        verification_round: Round when verified
        last_updated: Last update timestamp
    """

    id: str
    text: str
    source_stage: int
    registered_round: int = 0
    evidence: list[str] = Field(default_factory=list)
    status: Literal["active", "challenged", "verified", "killed", "weakened"] = "active"
    challenge_history: list[ChallengeEvent] = Field(default_factory=list)
    kill_reason: str | None = None
    verification_round: int | None = None
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump(mode="json")


class ClaimIntegrityReport(BaseModel):
    """Summary report of claim integrity.

    Attributes:
        total_claims: Total claims registered
        verified: Number of verified claims
        killed: Number of killed claims
        weakened: Number of weakened claims
        active: Number of active claims
        challenged: Number of challenged claims
        verification_rate: Percentage of verified claims
        claims: Detailed claim information
        generated_at: When report was generated
    """

    total_claims: int = 0
    verified: int = 0
    killed: int = 0
    weakened: int = 0
    active: int = 0
    challenged: int = 0
    verification_rate: float = 0.0
    claims: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        # Calculate derived fields
        self.total_claims = len(self.claims)
        self.verified = sum(1 for c in self.claims if c["status"] == "verified")
        self.killed = sum(1 for c in self.claims if c["status"] == "killed")
        self.weakened = sum(1 for c in self.claims if c["status"] == "weakened")
        self.active = sum(1 for c in self.claims if c["status"] == "active")
        self.challenged = sum(1 for c in self.claims if c["status"] == "challenged")

        if self.total_claims > 0:
            self.verification_rate = self.verified / self.total_claims


class ClaimTracker:
    """Track lifecycle of every empirical claim in the paper.

    This tracker ensures scientific integrity by:
    1. Registering all claims when made
    2. Tracking challenges from reviewers
    3. Verifying claims with evidence
    4. Killing claims that don't hold up

    Usage::

        tracker = ClaimTracker()
        claim_id = await tracker.register_claim(
            claim="Method X improves accuracy by 15%",
            source_stage=17,
            evidence=["experiment_1_results"],
        )

        await tracker.challenge_claim(claim_id, round=2, reason="Unsupported")
        await tracker.verify_claim(claim_id, experiment_results)

    Attributes:
        claims: Dictionary of claim records
        round: Current improvement round
    """

    def __init__(self):
        """Initialize claim tracker."""
        self.claims: dict[str, ClaimRecord] = {}
        self._counter = 0
        self.round = 0

    async def register_claim(
        self,
        claim: str,
        source_stage: int,
        evidence: list[str] | None = None,
        round_num: int | None = None,
    ) -> str:
        """Register a new empirical claim.

        Args:
            claim: Claim text
            source_stage: Pipeline stage where claim originated
            evidence: Supporting evidence
            round_num: Current improvement round

        Returns:
            Claim ID
        """
        self._counter += 1
        claim_id = f"claim_{self._counter}"

        self.claims[claim_id] = ClaimRecord(
            id=claim_id,
            text=claim,
            source_stage=source_stage,
            registered_round=round_num or self.round,
            evidence=evidence or [],
            status="active",
        )

        logger.info(f"Registered claim {claim_id}: {claim[:50]}...")
        return claim_id

    async def challenge_claim(
        self,
        claim_id: str,
        round_num: int | None = None,
        reason: str = "",
        challenger: str = "reviewer",
    ) -> bool:
        """Mark claim as challenged by reviewer.

        Args:
            claim_id: Claim ID
            round_num: Current round
            reason: Challenge reason
            challenger: Who challenged

        Returns:
            True if claim was challenged
        """
        if claim_id not in self.claims:
            logger.warning(f"Claim {claim_id} not found for challenge")
            return False

        claim = self.claims[claim_id]
        claim.status = "challenged"
        claim.challenge_history.append(
            ChallengeEvent(
                round=round_num or self.round,
                reason=reason,
                challenger=challenger,
            )
        )
        claim.last_updated = datetime.now(timezone.utc).isoformat()

        logger.info(f"Challenged claim {claim_id}: {reason}")
        return True

    async def verify_claim(
        self,
        claim_id: str,
        experiment_results: dict[str, Any],
        round_num: int | None = None,
        use_bayesian: bool = True,
        prior_belief: float = 0.5,
    ) -> ClaimVerdict:
        """Verify claim with new evidence.

        Args:
            claim_id: Claim ID
            experiment_results: Results from verification experiment
            round_num: Current round
            use_bayesian: Whether to use Bayesian belief updates
            prior_belief: Prior belief in claim (0-1)

        Returns:
            ClaimVerdict
        """
        if claim_id not in self.claims:
            logger.warning(f"Claim {claim_id} not found for verification")
            return ClaimVerdict.INCONCLUSIVE

        claim = self.claims[claim_id]

        # Use Bayesian verification if enabled
        if use_bayesian:
            verdict = await self._bayesian_verify_claim(
                claim, experiment_results, prior_belief
            )
        else:
            # Fallback to rule-based verification
            verdict = self._rule_based_verify_claim(claim, experiment_results)

        # Update claim status based on verdict
        if verdict == ClaimVerdict.SUPPORTED:
            claim.status = "verified"
            claim.verification_round = round_num or self.round
        elif verdict in [ClaimVerdict.WEAKENED, ClaimVerdict.REFUTED]:
            claim.status = "weakened"
        else:
            claim.status = "weakened"

        claim.last_updated = datetime.now(timezone.utc).isoformat()

        logger.info(f"Verified claim {claim_id}: {verdict.value}")
        return verdict

    async def _bayesian_verify_claim(
        self,
        claim: ClaimRecord,
        experiment_results: dict[str, Any],
        prior_belief: float = 0.5,
    ) -> ClaimVerdict:
        """Verify claim using Bayesian belief updates.

        Uses Bayesian reasoning to update belief in claim based on evidence:
        1. Define hypotheses (claim_true, claim_false)
        2. Assess likelihood of evidence given each hypothesis
        3. Update posterior beliefs using Bayes' rule
        4. Determine verdict based on posterior probability

        Args:
            claim: Claim record
            experiment_results: Results from verification experiment
            prior_belief: Prior belief in claim (0-1)

        Returns:
            ClaimVerdict based on posterior belief
        """
        # Extract evidence from experiment results
        success = experiment_results.get("success", False)
        effect_size = experiment_results.get("effect_size", 0.0)
        p_value = experiment_results.get("p_value", 1.0)
        sample_size = experiment_results.get("sample_size", 0)

        # Define likelihoods
        # P(evidence | claim_true) - How likely is this evidence if claim is true?
        if success and abs(effect_size) > 0.3 and p_value < 0.05:
            likelihood_given_true = 0.9  # Strong evidence
        elif success and p_value < 0.1:
            likelihood_given_true = 0.7  # Moderate evidence
        else:
            likelihood_given_true = 0.3  # Weak evidence

        # P(evidence | claim_false) - How likely is this evidence if claim is false?
        if success and abs(effect_size) > 0.3 and p_value < 0.05:
            likelihood_given_false = 0.1  # Unlikely if false
        elif success and p_value < 0.1:
            likelihood_given_false = 0.3  # Somewhat unlikely
        else:
            likelihood_given_false = 0.5  # Could happen either way

        # Apply Bayes' rule
        # P(claim_true | evidence) = P(evidence | claim_true) × P(claim_true) / P(evidence)
        prior_true = prior_belief
        prior_false = 1 - prior_belief

        # P(evidence) = P(evidence | true) × P(true) + P(evidence | false) × P(false)
        evidence_prob = (
            likelihood_given_true * prior_true +
            likelihood_given_false * prior_false
        )

        # Posterior belief
        if evidence_prob > 0:
            posterior_true = (likelihood_given_true * prior_true) / evidence_prob
        else:
            posterior_true = prior_true  # No update if no evidence

        # Adjust for sample size (larger samples = more confidence)
        if sample_size > 100:
            posterior_true = min(1.0, posterior_true + 0.1)
        elif sample_size < 10:
            posterior_true = max(0.0, posterior_true - 0.1)

        # Determine verdict based on posterior belief
        if posterior_true >= 0.8:
            return ClaimVerdict.SUPPORTED
        elif posterior_true >= 0.6:
            return ClaimVerdict.WEAKENED  # Leaning toward supported
        elif posterior_true >= 0.4:
            return ClaimVerdict.INCONCLUSIVE
        elif posterior_true >= 0.2:
            return ClaimVerdict.WEAKENED  # Leaning toward refuted
        else:
            return ClaimVerdict.REFUTED

    def _rule_based_verify_claim(
        self,
        claim: ClaimRecord,
        experiment_results: dict[str, Any],
    ) -> ClaimVerdict:
        """Verify claim using rule-based approach (fallback).

        Args:
            claim: Claim record
            experiment_results: Results from verification experiment

        Returns:
            ClaimVerdict
        """
        success = experiment_results.get("success", False)
        effect_size = experiment_results.get("effect_size", 0.0)
        p_value = experiment_results.get("p_value", 1.0)

        # Determine verdict using rules
        if success and p_value < 0.05 and abs(effect_size) > 0.3:
            return ClaimVerdict.SUPPORTED
        elif success and p_value < 0.1:
            return ClaimVerdict.WEAKENED
        elif not success and p_value < 0.05:
            return ClaimVerdict.REFUTED
        else:
            return ClaimVerdict.INCONCLUSIVE

    async def kill_claim(
        self,
        claim_id: str,
        reason: str,
        round_num: int | None = None,
    ) -> bool:
        """Remove claim from paper.

        Args:
            claim_id: Claim ID
            reason: Reason for killing
            round_num: Current round

        Returns:
            True if claim was killed
        """
        if claim_id not in self.claims:
            logger.warning(f"Claim {claim_id} not found for killing")
            return False

        claim = self.claims[claim_id]
        claim.status = "killed"
        claim.kill_reason = reason
        claim.last_updated = datetime.now(timezone.utc).isoformat()

        logger.info(f"Killed claim {claim_id}: {reason}")
        return True

    async def update_claim_evidence(
        self,
        claim_id: str,
        evidence: list[str],
    ) -> bool:
        """Update claim evidence.

        Args:
            claim_id: Claim ID
            evidence: New evidence

        Returns:
            True if evidence was updated
        """
        if claim_id not in self.claims:
            return False

        claim = self.claims[claim_id]
        claim.evidence.extend(evidence)
        claim.last_updated = datetime.now(timezone.utc).isoformat()
        return True

    def get_claim(self, claim_id: str) -> ClaimRecord | None:
        """Get claim by ID.

        Args:
            claim_id: Claim ID

        Returns:
            ClaimRecord or None
        """
        return self.claims.get(claim_id)

    def get_claims_by_status(
        self,
        status: str,
    ) -> list[ClaimRecord]:
        """Get claims by status.

        Args:
            status: Claim status

        Returns:
            List of ClaimRecords
        """
        return [c for c in self.claims.values() if c.status == status]

    def get_challenged_claims(self) -> list[ClaimRecord]:
        """Get all challenged claims.

        Returns:
            List of challenged ClaimRecords
        """
        return self.get_claims_by_status("challenged")

    def get_killed_claims(self) -> list[ClaimRecord]:
        """Get all killed claims.

        Returns:
            List of killed ClaimRecords
        """
        return self.get_claims_by_status("killed")

    def generate_claim_report(self) -> ClaimIntegrityReport:
        """Generate claim integrity report.

        Returns:
            ClaimIntegrityReport
        """
        return ClaimIntegrityReport(
            claims=[c.to_dict() for c in self.claims.values()],
        )

    def get_claim_statistics(self) -> dict[str, Any]:
        """Get claim statistics.

        Returns:
            Statistics dictionary
        """
        report = self.generate_claim_report()

        return {
            "total_claims": report.total_claims,
            "verified": report.verified,
            "killed": report.killed,
            "weakened": report.weakened,
            "active": report.active,
            "challenged": report.challenged,
            "verification_rate": report.verification_rate,
            "claims_per_round": self._claims_per_round(),
        }

    def _claims_per_round(self) -> dict[int, int]:
        """Count claims per round.

        Returns:
            Dictionary of round -> count
        """
        counts: dict[int, int] = {}
        for claim in self.claims.values():
            round_num = claim.registered_round
            counts[round_num] = counts.get(round_num, 0) + 1
        return counts


class ClaimIntegrityChecker:
    """Check claim integrity across the pipeline.

    This checker validates claims at different pipeline stages.

    Usage::

        checker = ClaimIntegrityChecker(tracker)
        report = await checker.check_paper_integrity(paper_text)
    """

    def __init__(self, tracker: ClaimTracker):
        """Initialize integrity checker.

        Args:
            tracker: Claim tracker
        """
        self.tracker = tracker

    async def check_paper_integrity(
        self,
        paper_text: str,
    ) -> ClaimIntegrityReport:
        """Check integrity of all claims in paper.

        Args:
            paper_text: Full paper text

        Returns:
            ClaimIntegrityReport
        """
        # Extract claims from paper (simplified)
        claims = self._extract_claims(paper_text)

        # Check each claim
        for claim_text in claims:
            # Find matching claim in tracker
            matching = self._find_matching_claim(claim_text)
            if matching:
                if matching.status == "killed":
                    logger.warning(f"Paper contains killed claim: {claim_text[:50]}")

        return self.tracker.generate_claim_report()

    def _extract_claims(
        self,
        text: str,
    ) -> list[str]:
        """Extract empirical claims from text.

        Args:
            text: Paper text

        Returns:
            List of claim strings
        """
        # Simplified claim extraction
        # In production, would use NLP
        claims = []

        # Look for claim indicators
        indicators = [
            "we found", "we show", "we demonstrate", "our results",
            "this paper", "our approach", "experiments show",
            "significantly", "substantially", "improves by",
        ]

        sentences = text.split(".")
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20 or len(sentence) > 500:
                continue

            for indicator in indicators:
                if indicator in sentence.lower():
                    claims.append(sentence)
                    break

        return claims

    def _find_matching_claim(
        self,
        claim_text: str,
    ) -> ClaimRecord | None:
        """Find matching claim in tracker.

        Args:
            claim_text: Claim text

        Returns:
            Matching ClaimRecord or None
        """
        for claim in self.tracker.claims.values():
            # Simple text matching
            if claim.text.lower() in claim_text.lower() or claim_text.lower() in claim.text.lower():
                return claim
        return None


@dataclass
class ClaimExtractionConfig:
    """Configuration for claim extraction.

    Attributes:
        min_sentence_length: Minimum sentence length
        max_sentence_length: Maximum sentence length
        confidence_threshold: Minimum confidence for extraction
        extract_stage: Pipeline stage for extraction
    """

    min_sentence_length: int = 20
    max_sentence_length: int = 500
    confidence_threshold: float = 0.5
    extract_stage: int = 17  # PAPER_DRAFT


# Convenience functions
async def track_paper_claims(
    paper_text: str,
    source_stage: int = 17,
    round_num: int = 0,
) -> ClaimTracker:
    """Extract and track claims from paper.

    Args:
        paper_text: Paper text
        source_stage: Pipeline stage
        round_num: Current round

    Returns:
        ClaimTracker with extracted claims
    """
    tracker = ClaimTracker()
    tracker.round = round_num

    # Simple claim extraction
    sentences = paper_text.split(".")
    for sentence in sentences:
        sentence = sentence.strip()
        if 50 < len(sentence) < 500:
            # Check for claim indicators
            indicators = ["we found", "we show", "improves", "achieves"]
            if any(ind in sentence.lower() for ind in indicators):
                await tracker.register_claim(
                    claim=sentence,
                    source_stage=source_stage,
                    round_num=round_num,
                )

    return tracker
