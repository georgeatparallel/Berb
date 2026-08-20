"""Rebuttal/response generation for peer review.

This module generates evidence-based responses to reviewer comments:
- Classify review comments by type (major/minor/typo/misunderstanding)
- Select response strategy (accept/defend/clarify/experiment)
- Generate evidence-based responses
- Assemble complete rebuttal letter

Inspired by Claude Scholar's review-response skill.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ReviewCommentType(StrEnum):
    """Review comment type.

    Attributes:
        MAJOR: Requires new experiments or analysis
        MINOR: Clarification or small change
        TYPO: Surface-level fix
        MISUNDERSTANDING: Reviewer didn't understand
    """

    MAJOR = "major"
    MINOR = "minor"
    TYPO = "typo"
    MISUNDERSTANDING = "misunderstanding"


class ResponseStrategy(StrEnum):
    """Response strategy for review comment.

    Attributes:
        ACCEPT: Agree and implement change
        DEFEND: Provide evidence for current approach
        CLARIFY: Explain more clearly
        EXPERIMENT: Run additional experiment
    """

    ACCEPT = "accept"
    DEFEND = "defend"
    CLARIFY = "clarify"
    EXPERIMENT = "experiment"


class ClassifiedComment(BaseModel):
    """Classified review comment.

    Attributes:
        comment_text: Original comment text
        comment_type: Classified type
        severity: Severity level (1-5)
        section: Paper section referenced
        actionable: Whether comment is actionable
        confidence: Classification confidence (0-1)
    """

    comment_text: str
    comment_type: ReviewCommentType
    severity: int = Field(default=3, ge=1, le=5)
    section: str = ""
    actionable: bool = True
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "comment_text": self.comment_text,
            "comment_type": self.comment_type.value,
            "severity": self.severity,
            "section": self.section,
            "actionable": self.actionable,
            "confidence": self.confidence,
        }


class RebuttalResponse(BaseModel):
    """Response to a review comment.

    Attributes:
        comment: Original comment
        strategy: Response strategy
        response_text: Generated response
        changes_made: Changes made to paper
        evidence_cited: Evidence cited in response
        additional_experiments: Additional experiments run (if any)
    """

    comment: ClassifiedComment
    strategy: ResponseStrategy
    response_text: str = ""
    changes_made: list[str] = Field(default_factory=list)
    evidence_cited: list[str] = Field(default_factory=list)
    additional_experiments: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "comment": self.comment.to_dict(),
            "strategy": self.strategy.value,
            "response_text": self.response_text,
            "changes_made": self.changes_made,
            "evidence_cited": self.evidence_cited,
            "additional_experiments": self.additional_experiments,
        }


class RebuttalLetter(BaseModel):
    """Complete rebuttal letter.

    Attributes:
        manuscript_id: Manuscript identifier
        authors: Author list
        date: Response date
        editor_response: Response to editor
        reviewer_responses: Responses per reviewer
        summary_of_changes: Summary of changes made
        word_count: Total word count
    """

    manuscript_id: str
    authors: list[str] = Field(default_factory=list)
    date: str = Field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%d"))
    editor_response: str = ""
    reviewer_responses: dict[str, list[RebuttalResponse]] = Field(default_factory=dict)
    summary_of_changes: list[str] = Field(default_factory=list)
    word_count: int = 0

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        # Calculate word count
        self.word_count = self._calculate_word_count()

    def _calculate_word_count(self) -> int:
        """Calculate total word count.

        Returns:
            Word count
        """
        text = self.editor_response
        for responses in self.reviewer_responses.values():
            for response in responses:
                text += " " + response.response_text
        return len(text.split())

    def to_text(self) -> str:
        """Convert to text format.

        Returns:
            Formatted rebuttal letter text
        """
        lines = [
            f"Date: {self.date}",
            f"Manuscript ID: {self.manuscript_id}",
            f"Authors: {', '.join(self.authors)}",
            "",
            "=" * 60,
            "RESPONSE TO EDITOR",
            "=" * 60,
            "",
            "Dear Editor,",
            "",
            self.editor_response,
            "",
        ]

        for reviewer, responses in self.reviewer_responses.items():
            lines.extend(
                [
                    "=" * 60,
                    f"RESPONSE TO {reviewer.upper()}",
                    "=" * 60,
                    "",
                ]
            )

            for i, response in enumerate(responses, 1):
                lines.extend(
                    [
                        f"**Comment {i}:** {response.comment.comment_text}",
                        "",
                        f"**Response:** {response.response_text}",
                        "",
                    ]
                )

                if response.changes_made:
                    lines.append(
                        f"**Changes made:** {', '.join(response.changes_made)}"
                    )
                    lines.append("")

        lines.extend(
            [
                "=" * 60,
                "SUMMARY OF CHANGES",
                "=" * 60,
                "",
            ]
        )
        lines.extend(f"- {change}" for change in self.summary_of_changes)

        return "\n".join(lines)


class RebuttalGenerator:
    """Generate evidence-based responses to reviewer comments.

    This generator:
    1. Classifies review comments by type
    2. Selects appropriate response strategy
    3. Generates evidence-based responses
    4. Assembles complete rebuttal letter

    Usage::

        generator = RebuttalGenerator(llm_provider)
        responses = await generator.generate_responses(reviews, paper, evidence_map)
        letter = await generator.generate_rebuttal_letter(responses)

    Attributes:
        llm_provider: LLM provider for generation
    """

    # Classification keywords
    MAJOR_KEYWORDS = [
        "new experiment",
        "additional analysis",
        "major concern",
        "fundamental",
        "significant",
        "substantial",
        "must",
        "required",
        "essential",
    ]

    MINOR_KEYWORDS = [
        "clarify",
        "explain",
        "minor",
        "suggest",
        "could",
        "might",
        "consider",
    ]

    TYPO_KEYWORDS = [
        "typo",
        "grammar",
        "spelling",
        "formatting",
        "reference",
        "citation",
        "figure",
    ]

    MISUNDERSTANDING_KEYWORDS = [
        "unclear",
        "confusing",
        "not clear",
        "don't understand",
        "missing",
        "where",
        "how",
    ]

    def __init__(self, llm_provider: Any | None = None):
        """Initialize rebuttal generator.

        Args:
            llm_provider: LLM provider for generation
        """
        self.llm_provider = llm_provider

    async def classify_reviews(
        self,
        reviews: list[str],
    ) -> list[list[ClassifiedComment]]:
        """Classify each review comment by type.

        Args:
            reviews: List of review texts

        Returns:
            List of classified comments per review
        """
        all_classified = []

        for review_text in reviews:
            # Split into individual comments
            comments = self._split_into_comments(review_text)
            classified = []

            for comment in comments:
                classification = await self._classify_comment(comment)
                classified.append(classification)

            all_classified.append(classified)

        return all_classified

    def _split_into_comments(
        self,
        review_text: str,
    ) -> list[str]:
        """Split review into individual comments.

        Args:
            review_text: Full review text

        Returns:
            List of individual comments
        """
        # Split by numbered comments or line breaks
        import re

        # Try numbered pattern first
        numbered = re.split(r"\d+[\.\)]\s*", review_text)
        comments = [c.strip() for c in numbered if c.strip() and len(c) > 20]

        if len(comments) < 2:
            # Fall back to line breaks
            comments = [
                c.strip() for c in review_text.split("\n") if c.strip() and len(c) > 20
            ]

        return comments[:20]  # Limit to 20 comments per review

    async def _classify_comment(
        self,
        comment: str,
    ) -> ClassifiedComment:
        """Classify single comment.

        Args:
            comment: Comment text

        Returns:
            ClassifiedComment
        """
        comment_lower = comment.lower()

        # Count keyword matches
        major_count = sum(1 for kw in self.MAJOR_KEYWORDS if kw in comment_lower)
        minor_count = sum(1 for kw in self.MINOR_KEYWORDS if kw in comment_lower)
        typo_count = sum(1 for kw in self.TYPO_KEYWORDS if kw in comment_lower)
        misunderstanding_count = sum(
            1 for kw in self.MISUNDERSTANDING_KEYWORDS if kw in comment_lower
        )

        # Determine type
        counts = {
            ReviewCommentType.MAJOR: major_count,
            ReviewCommentType.MINOR: minor_count,
            ReviewCommentType.TYPO: typo_count,
            ReviewCommentType.MISUNDERSTANDING: misunderstanding_count,
        }

        comment_type = max(counts, key=counts.get)
        confidence = min(1.0, counts[comment_type] * 0.3)

        # Determine severity
        if comment_type == ReviewCommentType.MAJOR:
            severity = 5
        elif comment_type == ReviewCommentType.MINOR:
            severity = 3
        elif comment_type == ReviewCommentType.TYPO:
            severity = 1
        else:  # MISUNDERSTANDING
            severity = 3

        # Detect section
        section = self._detect_section(comment)

        return ClassifiedComment(
            comment_text=comment,
            comment_type=comment_type,
            severity=severity,
            section=section,
            actionable=comment_type != ReviewCommentType.TYPO,
            confidence=confidence,
        )

    def _detect_section(
        self,
        comment: str,
    ) -> str:
        """Detect paper section referenced.

        Args:
            comment: Comment text

        Returns:
            Section name
        """
        comment_lower = comment.lower()

        sections = {
            "abstract": ["abstract", "summary"],
            "introduction": ["introduction", "intro", "background"],
            "methods": ["method", "methodology", "approach", "experimental"],
            "results": ["result", "experiment", "figure", "table"],
            "discussion": ["discussion", "conclusion", "implication"],
        }

        for section, keywords in sections.items():
            if any(kw in comment_lower for kw in keywords):
                return section

        return "general"

    async def generate_response(
        self,
        comment: ClassifiedComment,
        paper_text: str,
        evidence_map: list[dict[str, Any]] | None = None,
    ) -> RebuttalResponse:
        """Generate evidence-based response.

        Args:
            comment: Classified comment
            paper_text: Paper text
            evidence_map: Evidence map from claim analysis

        Returns:
            RebuttalResponse
        """
        # Select strategy based on comment type
        strategy = self._select_strategy(comment)

        # Generate response
        if self.llm_provider:
            response_text = await self._generate_llm_response(
                comment, paper_text, strategy
            )
        else:
            response_text = self._generate_template_response(comment, strategy)

        # Determine changes
        changes = self._determine_changes(comment, strategy)

        return RebuttalResponse(
            comment=comment,
            strategy=strategy,
            response_text=response_text,
            changes_made=changes,
        )

    def _select_strategy(
        self,
        comment: ClassifiedComment,
    ) -> ResponseStrategy:
        """Select response strategy.

        Args:
            comment: Classified comment

        Returns:
            ResponseStrategy
        """
        if comment.comment_type == ReviewCommentType.TYPO:
            return ResponseStrategy.ACCEPT

        elif comment.comment_type == ReviewCommentType.MINOR:
            return ResponseStrategy.CLARIFY

        elif comment.comment_type == ReviewCommentType.MISUNDERSTANDING:
            return ResponseStrategy.CLARIFY

        else:  # MAJOR
            # Check if experiment is feasible
            if "experiment" in comment.comment_text.lower():
                return ResponseStrategy.EXPERIMENT
            else:
                return ResponseStrategy.DEFEND

    async def _generate_llm_response(
        self,
        comment: ClassifiedComment,
        paper_text: str,
        strategy: ResponseStrategy,
    ) -> str:
        """Generate response using LLM.

        Args:
            comment: Classified comment
            paper_text: Paper text
            strategy: Response strategy

        Returns:
            Response text
        """
        prompt = f"""You are responding to a peer review comment.

**Comment:** {comment.comment_text}
**Comment Type:** {comment.comment_type.value}
**Strategy:** {strategy.value}

Generate a professional, evidence-based response that:
1. Acknowledges the reviewer's point
2. Provides evidence or clarification
3. Describes changes made (if any)
4. Is respectful and constructive

Response:"""

        try:
            response = await self.llm_provider.complete(
                messages=[{"role": "user", "content": prompt}],
                model="gpt-4o-mini",
                temperature=0.3,
            )
            return response.content.strip()
        except Exception as e:
            logger.error(f"LLM response generation failed: {e}")
            return self._generate_template_response(comment, strategy)

    def _generate_template_response(
        self,
        comment: ClassifiedComment,
        strategy: ResponseStrategy,
    ) -> str:
        """Generate response from template.

        Args:
            comment: Classified comment
            strategy: Response strategy

        Returns:
            Response text
        """
        templates = {
            ResponseStrategy.ACCEPT: (
                "We thank the reviewer for this valuable suggestion. "
                "We have implemented the suggested change in the revised manuscript. "
                "Specifically, we have [describe change]. This strengthens our paper by [benefit]."
            ),
            ResponseStrategy.DEFEND: (
                "We appreciate the reviewer's concern. However, we believe our approach is justified because "
                "[provide evidence/reasoning]. Our choice is consistent with prior work [cite if possible]. "
                "We have added clarification to the manuscript to make this clearer."
            ),
            ResponseStrategy.CLARIFY: (
                "We thank the reviewer for pointing out this lack of clarity. "
                "We have revised the text to better explain [topic]. "
                "Specifically, we now state: [quote new text]. We hope this addresses the concern."
            ),
            ResponseStrategy.EXPERIMENT: (
                "We appreciate this suggestion for additional experimentation. "
                "We have conducted the suggested experiment and the results [describe findings]. "
                "These results [support/qualify] our original claims. We have added these findings to [section]."
            ),
        }

        return templates.get(strategy, "We thank the reviewer for this comment.")

    def _determine_changes(
        self,
        comment: ClassifiedComment,
        strategy: ResponseStrategy,
    ) -> list[str]:
        """Determine changes made based on strategy.

        Args:
            comment: Classified comment
            strategy: Response strategy

        Returns:
            List of changes
        """
        changes = []

        if strategy == ResponseStrategy.ACCEPT:
            changes.append(f"Implemented suggested change in {comment.section}")

        elif strategy == ResponseStrategy.CLARIFY:
            changes.append(f"Clarified explanation in {comment.section}")

        elif strategy == ResponseStrategy.EXPERIMENT:
            changes.append("Added new experiment results")

        elif strategy == ResponseStrategy.DEFEND:
            changes.append(f"Added justification in {comment.section}")

        return changes

    async def generate_rebuttal_letter(
        self,
        responses: list[list[RebuttalResponse]],
        manuscript_id: str,
        authors: list[str],
        editor_name: str = "",
    ) -> RebuttalLetter:
        """Assemble complete rebuttal letter.

        Args:
            responses: Responses per reviewer
            manuscript_id: Manuscript ID
            authors: Author list
            editor_name: Editor name

        Returns:
            RebuttalLetter
        """
        # Generate editor response
        editor_response = self._generate_editor_response(responses)

        # Organize by reviewer
        reviewer_responses = {}
        for i, reviewer_responses_list in enumerate(responses, 1):
            reviewer_responses[f"Reviewer {i}"] = reviewer_responses_list

        # Generate summary of changes
        all_changes = []
        for reviewer_responses_list in responses:
            for response in reviewer_responses_list:
                all_changes.extend(response.changes_made)

        return RebuttalLetter(
            manuscript_id=manuscript_id,
            authors=authors,
            editor_response=editor_response,
            reviewer_responses=reviewer_responses,
            summary_of_changes=list(set(all_changes)),
        )

    def _generate_editor_response(
        self,
        responses: list[list[RebuttalResponse]],
    ) -> str:
        """Generate response to editor.

        Args:
            responses: All reviewer responses

        Returns:
            Editor response text
        """
        total_comments = sum(len(r) for r in responses)
        total_changes = sum(
            len(response.changes_made)
            for reviewer_responses in responses
            for response in reviewer_responses
        )

        return f"""We are grateful for the opportunity to revise our manuscript.
We have carefully addressed all {total_comments} comments from the reviewers
and have made {total_changes} changes to the manuscript.

The reviewers' comments have been invaluable in improving our paper.
We have clarified our methodology, strengthened our analysis, and
better positioned our contributions in light of the feedback received.

All changes are highlighted in the revised manuscript for your convenience.
We believe the paper is now significantly improved and hope it meets
the standards of your journal."""


# Convenience functions
async def generate_review_responses(
    reviews: list[str],
    paper_text: str,
    llm_provider: Any | None = None,
) -> list[list[RebuttalResponse]]:
    """Generate responses to all reviews.

    Args:
        reviews: List of review texts
        paper_text: Paper text
        llm_provider: LLM provider

    Returns:
        Responses per reviewer
    """
    generator = RebuttalGenerator(llm_provider)

    # Classify reviews
    classified = await generator.classify_reviews(reviews)

    # Generate responses
    all_responses = []
    for reviewer_comments in classified:
        reviewer_responses = []
        for comment in reviewer_comments:
            response = await generator.generate_response(comment, paper_text)
            reviewer_responses.append(response)
        all_responses.append(reviewer_responses)

    return all_responses


async def create_rebuttal_letter(
    reviews: list[str],
    paper_text: str,
    manuscript_id: str,
    authors: list[str],
    llm_provider: Any | None = None,
) -> RebuttalLetter:
    """Create complete rebuttal letter.

    Args:
        reviews: List of review texts
        paper_text: Paper text
        manuscript_id: Manuscript ID
        authors: Author list
        llm_provider: LLM provider

    Returns:
        RebuttalLetter
    """
    responses = await generate_review_responses(reviews, paper_text, llm_provider)

    generator = RebuttalGenerator(llm_provider)
    return await generator.generate_rebuttal_letter(responses, manuscript_id, authors)
