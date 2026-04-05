"""Reference integrity checker for validating citations.

This module validates all references before paper output, checking for:
- Retraction status
- Editorial notices (corrections, expressions of concern)
- Journal quality (predatory journals, impact metrics)
- Staleness (outdated references)
- Self-citation ratio

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RetractionStatus(str, Enum):
    """Paper retraction status.

    Attributes:
        ACTIVE: Paper is active (not retracted)
        RETRACTED: Paper has been retracted
        EXPRESSION_OF_CONCERN: Paper has expression of concern
        CORRECTED: Paper has been corrected
        UNKNOWN: Status unknown
    """

    ACTIVE = "active"
    RETRACTED = "retracted"
    EXPRESSION_OF_CONCERN = "expression_of_concern"
    CORRECTED = "corrected"
    UNKNOWN = "unknown"


class JournalQuality(BaseModel):
    """Journal quality assessment.

    Attributes:
        journal_name: Journal name
        impact_factor: Journal impact factor (if available)
        h_index: Journal h-index (if available)
        is_predatory: Whether journal is on predatory lists
        retraction_count: Number of retractions from this journal
        quality_score: Overall quality score (0-10)
    """

    journal_name: str
    impact_factor: float | None = None
    h_index: int | None = None
    is_predatory: bool = False
    retraction_count: int = 0
    quality_score: float = Field(default=5.0, ge=0.0, le=10.0)


class StalenessReport(BaseModel):
    """Report on reference staleness.

    Attributes:
        paper_id: Paper identifier
        publication_year: Year of publication
        age_years: Age in years
        is_stale: Whether reference is considered stale (>10 years)
        has_recent_citations: Whether paper has recent supporting citations
        staleness_score: Score indicating staleness (0=fresh, 1=stale)
    """

    paper_id: str
    publication_year: int | None = None
    age_years: int = 0
    is_stale: bool = False
    has_recent_citations: bool = True
    staleness_score: float = Field(default=0.0, ge=0.0, le=1.0)


class ReferenceIntegrityIssue(BaseModel):
    """Single reference integrity issue.

    Attributes:
        paper_id: Paper identifier
        issue_type: Type of issue
        severity: Issue severity (critical/major/minor/cosmetic)
        description: Issue description
        recommendation: Recommended action
    """

    paper_id: str
    issue_type: str
    severity: str  # critical, major, minor, cosmetic
    description: str
    recommendation: str


class IntegrityReport(BaseModel):
    """Complete reference integrity report.

    Attributes:
        total_references: Total number of references checked
        issues_found: Number of issues found
        issues: List of specific issues
        overall_score: Overall integrity score (0-10)
        passed: Whether references pass integrity check
        retracted_count: Number of retracted references
        predatory_count: Number of predatory journal references
        stale_count: Number of stale references
    """

    total_references: int = 0
    issues_found: int = 0
    issues: list[ReferenceIntegrityIssue] = Field(default_factory=list)
    overall_score: float = Field(default=10.0, ge=0.0, le=10.0)
    passed: bool = True
    retracted_count: int = 0
    predatory_count: int = 0
    stale_count: int = 0


@dataclass
class EditorialNotice:
    """Editorial notice for a paper.

    Attributes:
        notice_type: Type of notice (correction/erratum/expression_of_concern)
        date: Notice date
        reason: Reason for notice
        url: URL to notice
    """

    notice_type: str
    date: datetime | None = None
    reason: str = ""
    url: str | None = None


class ReferenceIntegrityChecker:
    """Validates all references before paper output.

    This checker performs comprehensive validation:
    - Retraction status via Retraction Watch and CrossRef
    - Editorial notices
    - Journal quality assessment
    - Staleness detection
    - Self-citation analysis

    Usage::

        checker = ReferenceIntegrityChecker()
        report = await checker.full_check(references)
        if not report.passed:
            # Handle issues

    Attributes:
        http_client: HTTP client for API calls
        check_retractions: Whether to check retraction status
        check_journal_quality: Whether to check journal quality
        staleness_threshold_years: Years after which reference is stale
    """

    # Retraction Watch API base (when available)
    RETRACTION_WATCH_API = "https://api.retractionwatch.com/v1"

    # CrossRef API base
    CROSSREF_API = "https://api.crossref.org"

    # Predatory journal lists (simplified - would need actual data)
    PREDATORY_JOURNAL_DOMAINS = {
        "predatory-journal.com",
        "fake-science.org",
    }

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        check_retractions: bool = True,
        check_journal_quality: bool = True,
        staleness_threshold_years: int = 10,
    ):
        """Initialize reference integrity checker.

        Args:
            http_client: HTTP client for API calls
            check_retractions: Whether to check retraction status
            check_journal_quality: Whether to check journal quality
            staleness_threshold_years: Years after which reference is stale
        """
        self.http_client = http_client or httpx.AsyncClient()
        self.check_retractions = check_retractions
        self.check_journal_quality = check_journal_quality
        self.staleness_threshold_years = staleness_threshold_years

        # Cache for journal quality
        self._journal_cache: dict[str, JournalQuality] = {}

    async def check_retraction_status(self, doi: str) -> RetractionStatus:
        """Check Retraction Watch database for retraction notices.

        Args:
            doi: Paper DOI

        Returns:
            RetractionStatus
        """
        if not self.check_retractions:
            return RetractionStatus.UNKNOWN

        try:
            # Try Retraction Watch API
            async with self.http_client as client:
                response = await client.get(
                    f"{self.RETRACTION_WATCH_API}/retractions",
                    params={"doi": doi},
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("retractions"):
                        return RetractionStatus.RETRACTED
        except Exception as e:
            logger.debug(f"Retraction Watch check failed for {doi}: {e}")

        # Fallback: Check CrossRef
        try:
            async with self.http_client as client:
                response = await client.get(
                    f"{self.CROSSREF_API}/works/{doi}",
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    work = data.get("message", {})
                    # Check for retraction in type or update info
                    type_info = work.get("type", "").lower()
                    if "retraction" in type_info:
                        return RetractionStatus.RETRACTED
        except Exception as e:
            logger.debug(f"CrossRef check failed for {doi}: {e}")

        return RetractionStatus.ACTIVE

    async def check_editorial_notices(self, doi: str) -> list[EditorialNotice]:
        """Check for corrections, expressions of concern, errata.

        Args:
            doi: Paper DOI

        Returns:
            List of editorial notices
        """
        notices = []

        try:
            async with self.http_client as client:
                response = await client.get(
                    f"{self.CROSSREF_API}/works/{doi}",
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    work = data.get("message", {})

                    # Check for updates/corrections
                    updates = work.get("update", [])
                    for update in updates:
                        notice_type = update.get("type", "unknown")
                        if "correction" in notice_type.lower() or "erratum" in notice_type.lower():
                            notices.append(
                                EditorialNotice(
                                    notice_type=notice_type,
                                    date=datetime.fromisoformat(update.get("timestamp", "")) if update.get("timestamp") else None,
                                    reason=update.get("label", ""),
                                )
                            )

                    # Check for expression of concern
                    if work.get("is-retraction") or work.get("is-correction"):
                        notices.append(
                            EditorialNotice(
                                notice_type="expression_of_concern",
                                reason="CrossRef indicates concern/correction",
                            )
                        )
        except Exception as e:
            logger.debug(f"Editorial notice check failed for {doi}: {e}")

        return notices

    async def check_journal_quality(self, journal_name: str) -> JournalQuality:
        """Check journal quality metrics.

        Args:
            journal_name: Journal name

        Returns:
            JournalQuality assessment
        """
        # Check cache
        if journal_name in self._journal_cache:
            return self._journal_cache[journal_name]

        quality = JournalQuality(journal_name=journal_name)

        # Check for predatory indicators
        journal_lower = journal_name.lower()
        for domain in self.PREDATORY_JOURNAL_DOMAINS:
            if domain in journal_lower:
                quality.is_predatory = True
                quality.quality_score = 1.0
                break

        # Try to get impact factor from CrossRef
        if not quality.is_predatory:
            try:
                async with self.http_client as client:
                    response = await client.get(
                        f"{self.CROSSREF_API}/journals",
                        params={"query": journal_name},
                        timeout=10,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        items = data.get("message", {}).get("items", [])
                        if items:
                            journal_data = items[0]
                            # Extract available metrics
                            if "impact-factor" in journal_data:
                                quality.impact_factor = journal_data["impact-factor"]
                            # Estimate quality score from impact factor
                            if quality.impact_factor:
                                quality.quality_score = min(
                                    10.0, 3.0 + (quality.impact_factor * 0.5)
                                )
            except Exception as e:
                logger.debug(f"Journal quality check failed: {e}")

        # Penalize predatory journals
        if quality.is_predatory:
            quality.quality_score = 0.0

        # Cache result
        self._journal_cache[journal_name] = quality
        return quality

    async def check_staleness(
        self,
        paper_id: str,
        publication_year: int | None = None,
        current_year: int | None = None,
    ) -> StalenessReport:
        """Check if reference is stale (outdated).

        Args:
            paper_id: Paper identifier
            publication_year: Year of publication
            current_year: Current year (default: now)

        Returns:
            StalenessReport
        """
        if current_year is None:
            current_year = datetime.now(timezone.utc).year

        if publication_year is None:
            return StalenessReport(
                paper_id=paper_id,
                age_years=0,
                is_stale=False,
                staleness_score=0.0,
            )

        age = current_year - publication_year
        is_stale = age > self.staleness_threshold_years

        # Calculate staleness score (0=fresh, 1=very stale)
        if age <= 5:
            staleness_score = 0.0
        elif age <= self.staleness_threshold_years:
            staleness_score = (age - 5) / (self.staleness_threshold_years - 5) * 0.5
        else:
            staleness_score = min(1.0, 0.5 + (age - self.staleness_threshold_years) * 0.05)

        return StalenessReport(
            paper_id=paper_id,
            publication_year=publication_year,
            age_years=age,
            is_stale=is_stale,
            has_recent_citations=True,  # Would need citation analysis
            staleness_score=staleness_score,
        )

    async def check_self_citation_ratio(
        self,
        paper: dict[str, Any],
        references: list[dict[str, Any]],
    ) -> float:
        """Detect papers with abnormally high self-citation.

        Args:
            paper: Paper metadata
            references: List of reference metadata

        Returns:
            Self-citation ratio (0-1)
        """
        if not references:
            return 0.0

        # Get author names from paper
        authors = paper.get("authors", [])
        author_names = {a.get("name", "").lower() for a in authors}

        # Count self-citations
        self_citations = 0
        for ref in references:
            ref_authors = ref.get("authors", [])
            for ref_author in ref_authors:
                ref_name = ref_author.get("name", "").lower()
                if ref_name in author_names and ref_name:
                    self_citations += 1
                    break

        ratio = self_citations / len(references) if references else 0.0

        # Flag if >50% self-citations
        if ratio > 0.5:
            logger.warning(
                f"High self-citation ratio ({ratio:.1%}) for paper {paper.get('id', 'unknown')}"
            )

        return ratio

    async def full_check(
        self,
        references: list[dict[str, Any]],
    ) -> IntegrityReport:
        """Run all integrity checks on references.

        Args:
            references: List of reference metadata dictionaries

        Returns:
            IntegrityReport with all findings
        """
        issues = []
        retracted_count = 0
        predatory_count = 0
        stale_count = 0

        for ref in references:
            doi = ref.get("doi", "")
            journal = ref.get("journal", ref.get("container-title", ""))
            pub_year = ref.get("year") or ref.get("published-print", {}).get("year")

            # Check retraction status
            if doi and self.check_retractions:
                status = await self.check_retraction_status(doi)
                if status == RetractionStatus.RETRACTED:
                    retracted_count += 1
                    issues.append(
                        ReferenceIntegrityIssue(
                            paper_id=ref.get("id", doi),
                            issue_type="retracted",
                            severity="critical",
                            description=f"Reference {doi} has been retracted",
                            recommendation="Remove or replace with non-retracted reference",
                        )
                    )
                elif status == RetractionStatus.EXPRESSION_OF_CONCERN:
                    issues.append(
                        ReferenceIntegrityIssue(
                            paper_id=ref.get("id", doi),
                            issue_type="expression_of_concern",
                            severity="major",
                            description=f"Reference {doi} has expression of concern",
                            recommendation="Verify claims and consider alternative sources",
                        )
                    )

            # Check journal quality
            if journal and self.check_journal_quality:
                journal_quality = await self.check_journal_quality(journal)
                if journal_quality.is_predatory:
                    predatory_count += 1
                    issues.append(
                        ReferenceIntegrityIssue(
                            paper_id=ref.get("id", doi),
                            issue_type="predatory_journal",
                            severity="critical",
                            description=f"Reference published in potentially predatory journal: {journal}",
                            recommendation="Replace with reference from reputable journal",
                        )
                    )
                elif journal_quality.quality_score < 3.0:
                    issues.append(
                        ReferenceIntegrityIssue(
                            paper_id=ref.get("id", doi),
                            issue_type="low_quality_journal",
                            severity="minor",
                            description=f"Reference from low-quality journal: {journal}",
                            recommendation="Consider higher quality alternative",
                        )
                    )

            # Check staleness
            if pub_year:
                staleness = await self.check_staleness(
                    ref.get("id", doi), pub_year
                )
                if staleness.is_stale:
                    stale_count += 1
                    issues.append(
                        ReferenceIntegrityIssue(
                            paper_id=ref.get("id", doi),
                            issue_type="stale_reference",
                            severity="cosmetic",
                            description=f"Reference is {staleness.age_years} years old",
                            recommendation="Consider updating with more recent work if available",
                        )
                    )

        # Calculate overall score
        total = len(references)
        critical_issues = sum(1 for i in issues if i.severity == "critical")
        major_issues = sum(1 for i in issues if i.severity == "major")
        minor_issues = sum(1 for i in issues if i.severity == "minor")

        # Start with 10, deduct for issues
        overall_score = 10.0
        overall_score -= critical_issues * 3.0
        overall_score -= major_issues * 1.5
        overall_score -= minor_issues * 0.5
        overall_score = max(0.0, overall_score)

        # Auto-fail if any retracted references
        passed = retracted_count == 0 and overall_score >= 5.0

        return IntegrityReport(
            total_references=total,
            issues_found=len(issues),
            issues=issues,
            overall_score=overall_score,
            passed=passed,
            retracted_count=retracted_count,
            predatory_count=predatory_count,
            stale_count=stale_count,
        )
