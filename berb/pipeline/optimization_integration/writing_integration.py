"""Writing Integration (Upgrade 9).

Integrates Parallel Section Writing with pipeline stage:
- Stage 17: PAPER_DRAFT

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from typing import Any

from berb.writing.parallel_writer import (
    ParallelSectionWriter,
    PaperSections,
    SectionPlan,
)

logger = logging.getLogger(__name__)


class WritingIntegration:
    """Integrates parallel section writing with pipeline.
    
    Usage in pipeline:
        integration = WritingIntegration()
        paper = await integration.write_paper_parallel(outline)
    """
    
    def __init__(
        self,
        max_parallel: int = 3,
        model: str = "claude-3-sonnet",
    ):
        """Initialize writing integration.
        
        Args:
            max_parallel: Maximum parallel writers
            model: LLM model for writing
        """
        self.max_parallel = max_parallel
        self.model = model
        self.writer = ParallelSectionWriter(
            max_parallel=max_parallel,
            model=model,
        )
        
        logger.info(
            f"Initialized WritingIntegration: "
            f"parallel={max_parallel}, model={model}"
        )
    
    async def write_paper_parallel(
        self,
        outline: dict[str, Any],
        results: dict[str, Any],
        literature_context: dict[str, Any],
    ) -> PaperSections:
        """Stage 17: Write paper sections in parallel.
        
        Args:
            outline: Paper outline
            results: Experimental results
            literature_context: Literature context
            
        Returns:
            Paper sections
        """
        # Enrich outline with results and literature
        enriched_outline = {
            **outline,
            "results": results,
            "literature": literature_context,
        }
        
        logger.info(f"Writing paper with {self.max_parallel} parallel writers")
        
        paper = await self.writer.write_sections_parallel(enriched_outline)
        
        logger.info(
            f"Paper writing complete: {len(paper.sections)} sections"
        )
        
        return paper
    
    async def write_specific_section(
        self,
        section_name: str,
        outline: dict[str, Any],
        completed_sections: dict[str, str],
    ) -> str:
        """Write specific section with dependencies.
        
        Args:
            section_name: Section to write
            outline: Paper outline
            completed_sections: Already completed sections
            
        Returns:
            Section content
        """
        plan = SectionPlan(
            section_name=section_name,
            dependencies=list(completed_sections.keys()),
        )
        
        logger.info(f"Writing section: {section_name}")
        
        content = await self.writer._write_section(
            plan=plan,
            outline=outline,
            paper=PaperSections(sections=completed_sections),
        )
        
        return content


async def write_paper_parallel(
    outline: dict[str, Any],
    results: dict[str, Any],
    literature_context: dict[str, Any],
    max_parallel: int = 3,
    model: str = "claude-3-sonnet",
) -> PaperSections:
    """Stage 17 integration: Write paper in parallel.
    
    Args:
        outline: Paper outline
        results: Experimental results
        literature_context: Literature context
        max_parallel: Maximum parallel writers
        model: LLM model
        
    Returns:
        Paper sections
    """
    integration = WritingIntegration(
        max_parallel=max_parallel,
        model=model,
    )
    
    return await integration.write_paper_parallel(
        outline, results, literature_context
    )
