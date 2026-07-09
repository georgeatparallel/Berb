"""Parallel Section Writing.

Based on CAID (CMU — arXiv:2603.21489):
"Write paper sections in parallel using git-like isolation and merge with verification."

Key Features:
- Dependency-aware section planning
- Parallel independent section writing
- Coherence verification at merge
- Cross-reference checking

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.writing.parallel_writer import ParallelSectionWriter

    writer = ParallelSectionWriter()
    paper = await writer.write_sections_parallel(outline)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class SectionDependency(StrEnum):
    """Section dependency type."""
    NONE = "none"
    """No dependencies - can write in parallel"""

    SEQUENTIAL = "sequential"
    """Must wait for previous section"""

    PARTIAL = "partial"
    """Can start with partial information"""


@dataclass
class SectionPlan:
    """Plan for writing a section.

    Attributes:
        section_name: Section name
        description: Section description
        dependencies: List of dependent section names
        dependency_type: Type of dependency
        estimated_tokens: Estimated token count
        priority: Writing priority (lower = higher priority)
    """
    section_name: str
    description: str = ""
    dependencies: list[str] = field(default_factory=list)
    dependency_type: SectionDependency = SectionDependency.NONE
    estimated_tokens: int = 1000
    priority: int = 5

    def can_write_parallel(self, completed: set[str]) -> bool:
        """Check if section can be written in parallel.

        Args:
            completed: Set of completed section names

        Returns:
            True if can write
        """
        if self.dependency_type == SectionDependency.NONE:
            return True

        if self.dependency_type == SectionDependency.SEQUENTIAL:
            return all(dep in completed for dep in self.dependencies)

        # Partial: can start if at least one dependency is done
        if self.dependency_type == SectionDependency.PARTIAL:
            return len(set(self.dependencies) & completed) > 0

        return False


@dataclass
class PaperSections:
    """Collection of paper sections.

    Attributes:
        sections: Dictionary of section name to content
        references: List of references
        metadata: Additional metadata
    """
    sections: dict[str, str] = field(default_factory=dict)
    references: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_section(self, name: str, content: str) -> None:
        """Add section content."""
        self.sections[name] = content

    def get_section(self, name: str) -> str | None:
        """Get section content."""
        return self.sections.get(name)

    def to_markdown(self) -> str:
        """Convert to markdown."""
        parts = []
        for name, content in self.sections.items():
            parts.append(f"# {name}\n\n{content}")
        return "\n\n".join(parts)


class ParallelSectionWriter:
    """CAID-inspired parallel section writer.

    Architecture:
    1. Manager creates dependency-aware section plan
    2. Independent sections written in parallel
    3. Dependent sections wait for prerequisites
    4. Integration: merge sections with coherence check
    5. Test: cross-reference verification

    Usage:
        writer = ParallelSectionWriter()
        paper = await writer.write_sections_parallel(outline)
    """

    def __init__(
        self,
        max_parallel: int = 3,
        model: str = "claude-3-sonnet",
    ):
        """Initialize parallel writer.

        Args:
            max_parallel: Maximum parallel writers
            model: LLM model for writing
        """
        self.max_parallel = max_parallel
        self.model = model
        logger.info(f"Initialized ParallelSectionWriter with {model}")

    async def write_sections_parallel(
        self,
        outline: dict[str, Any],
    ) -> PaperSections:
        """Write paper sections in parallel.

        Process:
        1. Create dependency-aware section plan
        2. Write independent sections in parallel
        3. Wait for dependencies, write dependent sections
        4. Merge with coherence check
        5. Verify cross-references

        Args:
            outline: Paper outline

        Returns:
            Completed paper sections
        """
        # Create section plan
        plans = self._create_section_plans(outline)

        # Track completed sections
        completed: set[str] = set()
        paper = PaperSections()

        # Write sections in waves
        while len(completed) < len(plans):
            # Find sections that can be written
            ready = [
                plan for plan in plans
                if plan.section_name not in completed
                and plan.can_write_parallel(completed)
            ]

            if not ready:
                logger.warning("No sections ready - possible deadlock")
                break

            # Write ready sections in parallel
            tasks = [
                self._write_section(plan, outline, paper)
                for plan in ready[:self.max_parallel]
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Add completed sections
            for plan, result in zip(ready, results, strict=False):
                if isinstance(result, Exception):
                    logger.error(f"Failed to write {plan.section_name}: {result}")
                else:
                    paper.add_section(plan.section_name, result)
                    completed.add(plan.section_name)
                    logger.info(f"Completed section: {plan.section_name}")

        # Merge and verify
        await self._verify_coherence(paper)
        await self._verify_cross_references(paper)

        logger.info(f"Completed {len(completed)} sections")
        return paper

    def _create_section_plans(
        self,
        outline: dict[str, Any],
    ) -> list[SectionPlan]:
        """Create section plans from outline.

        Args:
            outline: Paper outline

        Returns:
            List of section plans
        """
        # Standard paper structure with dependencies
        standard_sections = {
            "Abstract": SectionPlan(
                section_name="Abstract",
                description="Paper summary",
                dependency_type=SectionDependency.SEQUENTIAL,
                dependencies=["Introduction", "Results", "Conclusion"],
                priority=10,
            ),
            "Introduction": SectionPlan(
                section_name="Introduction",
                description="Background and motivation",
                dependency_type=SectionDependency.NONE,
                priority=1,
            ),
            "Related Work": SectionPlan(
                section_name="Related Work",
                description="Previous research",
                dependency_type=SectionDependency.PARTIAL,
                dependencies=["Introduction"],
                priority=2,
            ),
            "Methods": SectionPlan(
                section_name="Methods",
                description="Methodology description",
                dependency_type=SectionDependency.NONE,
                priority=2,
            ),
            "Results": SectionPlan(
                section_name="Results",
                description="Experimental results",
                dependency_type=SectionDependency.SEQUENTIAL,
                dependencies=["Methods"],
                priority=3,
            ),
            "Discussion": SectionPlan(
                section_name="Discussion",
                description="Result interpretation",
                dependency_type=SectionDependency.SEQUENTIAL,
                dependencies=["Results"],
                priority=4,
            ),
            "Conclusion": SectionPlan(
                section_name="Conclusion",
                description="Summary and future work",
                dependency_type=SectionDependency.SEQUENTIAL,
                dependencies=["Discussion"],
                priority=5,
            ),
        }

        # Use outline to customize
        if "sections" in outline:
            for section_name in outline["sections"]:
                if section_name in standard_sections:
                    std = standard_sections[section_name]
                    std.description = outline["sections"].get(
                        section_name, {}
                    ).get("description", std.description)

        plans = list(standard_sections.values())
        plans.sort(key=lambda p: p.priority)

        return plans

    async def _write_section(
        self,
        plan: SectionPlan,
        outline: dict[str, Any],
        paper: PaperSections,
    ) -> str:
        """Write single section.

        Args:
            plan: Section plan
            outline: Paper outline
            paper: Current paper state

        Returns:
            Section content
        """
        from berb.llm.client import get_llm_client

        client = get_llm_client(model=self.model)

        # Build context from completed sections
        context = ""
        for dep in plan.dependencies:
            if dep in paper.sections:
                context += f"\n\n== {dep} ==\n{paper.sections[dep][:500]}..."

        prompt = f"""
Write the {plan.section_name} section of this paper.

Paper Outline:
{outline}

Section Description: {plan.description}

Completed sections for context:
{context}

Write a complete, well-structured section ({plan.estimated_tokens // 4} words).
Include appropriate citations and cross-references.
"""

        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system=f"You are writing the {plan.section_name} section of an academic paper.",
        )

        return response.content

    async def _verify_coherence(self, paper: PaperSections) -> None:
        """Verify paper coherence after merge.

        Args:
            paper: Completed paper
        """
        from berb.llm.client import get_llm_client

        client = get_llm_client(model=self.model)

        content = paper.to_markdown()

        prompt = f"""
Verify coherence of this paper:

{content[:5000]}...

Check:
1. Logical flow between sections
2. Consistent terminology
3. Consistent notation
4. No contradictions between sections

List any coherence issues found.
"""

        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are verifying paper coherence.",
        )

        if "no issues" not in response.content.lower():
            logger.warning(f"Coherence issues: {response.content[:500]}")
        else:
            logger.info("Paper coherence verified")

    async def _verify_cross_references(self, paper: PaperSections) -> None:
        """Verify cross-references between sections.

        Args:
            paper: Completed paper
        """
        # Check that referenced sections exist
        import re

        for section_name, content in paper.sections.items():
            # Look for section references
            refs = re.findall(r"Section~?(\w+)", content, re.IGNORECASE)
            refs += re.findall(r"see\s+(\w+)\s+section", content, re.IGNORECASE)

            for ref in refs:
                if ref not in paper.sections:
                    logger.warning(
                        f"Section {section_name} references "
                        f"non-existent section: {ref}"
                    )

        logger.info("Cross-reference verification complete")


async def write_paper_parallel(
    outline: dict[str, Any],
    max_parallel: int = 3,
    model: str = "claude-3-sonnet",
) -> PaperSections:
    """Convenience function to write paper in parallel.

    Args:
        outline: Paper outline
        max_parallel: Maximum parallel writers
        model: LLM model

    Returns:
        Paper sections
    """
    writer = ParallelSectionWriter(max_parallel=max_parallel, model=model)
    return await writer.write_sections_parallel(outline)


__all__ = [
    "ParallelSectionWriter",
    "SectionPlan",
    "SectionDependency",
    "PaperSections",
    "write_paper_parallel",
]
