"""Skill system for Berb autonomous research pipeline.

Provides reusable skills that can be applied across runs:
- Literature Review Skill: Systematic search and synthesis
- Experiment Analysis Skill: Statistical methods and visualization
- Paper Writing Skill: Venue requirements and writing patterns
- Citation Verification Skill: Verification layers and APIs

Each skill includes:
- SKILL.md: Skill definition and usage
- References: Key papers and resources
- Examples: Worked examples

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.skills import SkillRegistry, Skill

    # Load skills
    registry = SkillRegistry()
    lit_review = registry.get("literature-review")
    
    # Apply skill
    result = lit_review.apply(context)
    
    # List all skills
    skills = registry.list_skills()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """A reusable skill definition.

    Attributes:
        id: Unique skill identifier
        name: Human-readable name
        description: Skill description
        category: Skill category (research, writing, analysis, verification)
        triggers: Pipeline stages where skill applies
        instructions: Step-by-step instructions
        references: Key references and resources
        examples: Worked examples
        metadata: Additional metadata
    """

    id: str = ""
    name: str = ""
    description: str = ""
    category: str = ""
    triggers: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "triggers": self.triggers,
            "instructions": self.instructions,
            "references": self.references,
            "examples": self.examples,
            "metadata": self.metadata,
        }

    def apply(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Apply skill to context.

        Args:
            context: Current context

        Returns:
            Enhanced context
        """
        # Default: add skill metadata
        context["applied_skills"] = context.get("applied_skills", [])
        context["applied_skills"].append(self.id)
        return context


class SkillRegistry:
    """Registry for managing and retrieving skills.

    Provides:
    - Skill registration
    - Skill retrieval by ID or category
    - Skill application
    - Cross-run learning integration

    Usage:
        registry = SkillRegistry()
        
        # Get skill by ID
        skill = registry.get("literature-review")
        
        # Get skills by category
        skills = registry.get_by_category("research")
        
        # Get applicable skills for stage
        skills = registry.get_applicable("LITERATURE_SCREEN")
    """

    def __init__(self, skills_dir: Path | None = None):
        """
        Initialize skill registry.

        Args:
            skills_dir: Directory containing skill definitions
        """
        self.skills_dir = skills_dir
        self._skills: dict[str, Skill] = {}
        
        # Load built-in skills
        self._load_builtin_skills()

    def _load_builtin_skills(self) -> None:
        """Load built-in skills."""
        # Skill 1: Literature Review
        self.register(Skill(
            id="literature-review",
            name="Literature Review",
            description="Systematic literature search and synthesis following PRISMA guidelines",
            category="research",
            triggers=["SEARCH_STRATEGY", "LITERATURE_COLLECT", "LITERATURE_SCREEN", "SYNTHESIS"],
            instructions=[
                "1. Define search query based on research question",
                "2. Search multiple databases (arXiv, PubMed, Google Scholar)",
                "3. Apply inclusion/exclusion criteria",
                "4. Extract key information from selected papers",
                "5. Synthesize findings thematically",
                "6. Identify research gaps",
            ],
            references=[
                "PRISMA Statement: www.prisma-statement.org",
                "Systematic Review Methods (Cooper et al.)",
                "Literature Review in 5 Days (Academic Accelerator)",
            ],
            examples=[
                {
                    "topic": "Transformers for NLP",
                    "search_query": "transformer attention neural machine translation",
                    "databases": ["arXiv", "ACL Anthology", "Google Scholar"],
                    "inclusion": ["peer-reviewed", "2017-2024", "NLP focus"],
                    "exclusion": ["non-English", "workshop papers", "short papers"],
                }
            ],
            metadata={
                "version": "1.0",
                "author": "Berb Team",
                "last_updated": "2026-03-28",
            }
        ))

        # Skill 2: Experiment Analysis
        self.register(Skill(
            id="experiment-analysis",
            name="Experiment Analysis",
            description="Statistical analysis and visualization of experiment results",
            category="analysis",
            triggers=["EXPERIMENT_RUN", "RESULT_ANALYSIS", "ITERATIVE_REFINE"],
            instructions=[
                "1. Collect all experimental results",
                "2. Compute descriptive statistics (mean, std, confidence intervals)",
                "3. Perform statistical tests (t-test, ANOVA, etc.)",
                "4. Create visualizations (bar charts, line plots, heatmaps)",
                "5. Identify significant patterns",
                "6. Document ablation study findings",
            ],
            references=[
                "Statistical Methods for ML (Wilkinson)",
                "Visualization Best Practices (Few)",
                "Reproducible Research (Stodden et al.)",
            ],
            examples=[
                {
                    "metrics": ["accuracy", "precision", "recall", "f1"],
                    "statistical_tests": ["paired t-test", "Wilcoxon signed-rank"],
                    "visualizations": ["bar chart with error bars", "learning curve"],
                    "significance_level": 0.05,
                }
            ],
            metadata={
                "version": "1.0",
                "author": "Berb Team",
                "last_updated": "2026-03-28",
            }
        ))

        # Skill 3: Paper Writing
        self.register(Skill(
            id="paper-writing",
            name="Paper Writing",
            description="Academic paper writing following venue-specific requirements",
            category="writing",
            triggers=["PAPER_OUTLINE", "PAPER_DRAFT", "PAPER_REVISION"],
            instructions=[
                "1. Review venue requirements (format, length, style)",
                "2. Create detailed outline with section word counts",
                "3. Write abstract last (summarize key contributions)",
                "4. Introduction: problem, contributions, roadmap",
                "5. Related work: thematic organization, gap identification",
                "6. Method: clear technical description, figures",
                "7. Experiments: setup, results, ablation, analysis",
                "8. Conclusion: summary, limitations, future work",
            ],
            references=[
                "Writing for CS Conferences (Norvig)",
                "Latex Templates (Overleaf)",
                "Venue-specific guidelines (NeurIPS, ICML, ICLR)",
            ],
            examples=[
                {
                    "venue": "NeurIPS",
                    "max_pages": 9,
                    "structure": {
                        "abstract": "150 words",
                        "introduction": "1-1.5 pages",
                        "related_work": "1-2 pages",
                        "method": "2-3 pages",
                        "experiments": "3-4 pages",
                        "conclusion": "0.5 pages",
                    }
                }
            ],
            metadata={
                "version": "1.0",
                "author": "Berb Team",
                "last_updated": "2026-03-28",
            }
        ))

        # Skill 4: Citation Verification
        self.register(Skill(
            id="citation-verification",
            name="Citation Verification",
            description="4-layer citation verification to prevent hallucinations",
            category="verification",
            triggers=["PAPER_DRAFT", "PEER_REVIEW", "CITATION_VERIFY"],
            instructions=[
                "1. Extract all citations from paper",
                "2. Layer 1: Validate DOI/arXiv ID format",
                "3. Layer 2: Verify via CrossRef/DataCite/arXiv API",
                "4. Layer 3: Match title/author/year metadata",
                "5. Layer 4: Check claim-citation alignment",
                "6. Flag or remove hallucinated citations",
                "7. Generate verification report",
            ],
            references=[
                "CrossRef API: api.crossref.org",
                "Semantic Scholar API: semanticscholar.org/api",
                "arXiv API: arxiv.org/help/api",
            ],
            examples=[
                {
                    "citation": {
                        "doi": "10.1038/s41586-021-03819-2",
                        "title": "Attention Is All You Need",
                        "authors": ["Vaswani"],
                        "year": 2017,
                    },
                    "verification": {
                        "layer1_format": "PASS",
                        "layer2_api": "PASS (CrossRef)",
                        "layer3_info": "PASS (title match: 0.95)",
                        "layer4_content": "PASS (alignment: 0.82)",
                        "overall": "VALID",
                    }
                }
            ],
            metadata={
                "version": "1.0",
                "author": "Berb Team",
                "last_updated": "2026-03-28",
            }
        ))

    def register(self, skill: Skill) -> None:
        """
        Register a skill.

        Args:
            skill: Skill to register
        """
        self._skills[skill.id] = skill
        logger.debug(f"Registered skill: {skill.id}")

    def get(self, skill_id: str) -> Skill | None:
        """
        Get skill by ID.

        Args:
            skill_id: Skill identifier

        Returns:
            Skill or None if not found
        """
        return self._skills.get(skill_id)

    def get_by_category(self, category: str) -> list[Skill]:
        """
        Get skills by category.

        Args:
            category: Skill category

        Returns:
            List of matching skills
        """
        return [
            skill for skill in self._skills.values()
            if skill.category == category
        ]

    def get_applicable(self, stage_id: str) -> list[Skill]:
        """
        Get skills applicable to a pipeline stage.

        Args:
            stage_id: Pipeline stage ID

        Returns:
            List of applicable skills
        """
        return [
            skill for skill in self._skills.values()
            if stage_id in skill.triggers
        ]

    def list_skills(self) -> list[str]:
        """
        List all registered skill IDs.

        Returns:
            List of skill IDs
        """
        return list(self._skills.keys())

    def list_categories(self) -> list[str]:
        """
        List all skill categories.

        Returns:
            List of categories
        """
        return list(set(skill.category for skill in self._skills.values()))

    def to_dict(self) -> dict[str, Any]:
        """Convert registry to dictionary."""
        return {
            skill_id: skill.to_dict()
            for skill_id, skill in self._skills.items()
        }


# =============================================================================
# Skill Application Helper
# =============================================================================

def apply_skills(
    context: dict[str, Any],
    stage_id: str,
    registry: SkillRegistry | None = None,
) -> dict[str, Any]:
    """
    Apply all applicable skills to context.

    Args:
        context: Current context
        stage_id: Pipeline stage ID
        registry: Skill registry (creates default if None)

    Returns:
        Enhanced context with applied skills
    """
    if registry is None:
        registry = SkillRegistry()

    applicable_skills = registry.get_applicable(stage_id)

    for skill in applicable_skills:
        context = skill.apply(context)

    logger.debug(
        f"Applied {len(applicable_skills)} skills for stage {stage_id}"
    )

    return context


# =============================================================================
# Skill Export for MetaClaw
# =============================================================================

def export_skills_for_metaclaw(output_dir: Path) -> None:
    """
    Export skills in MetaClaw-compatible format.

    Args:
        output_dir: Output directory for skill files
    """
    registry = SkillRegistry()

    for skill_id, skill in registry._skills.items():
        skill_dir = output_dir / skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write SKILL.md
        skill_md = f"""# Skill: {skill.name}

**ID:** {skill_id}  
**Category:** {skill.category}  
**Description:** {skill.description}

## Triggers

This skill applies at stages: {', '.join(skill.triggers)}

## Instructions

"""
        for instruction in skill.instructions:
            skill_md += f"{instruction}\n"

        skill_md += "\n## References\n\n"
        for ref in skill.references:
            skill_md += f"- {ref}\n"

        skill_md += "\n## Examples\n\n"
        for i, example in enumerate(skill.examples, 1):
            skill_md += f"### Example {i}\n\n"
            for key, value in example.items():
                skill_md += f"**{key}:** {value}\n"
            skill_md += "\n"

        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

        logger.info(f"Exported skill: {skill_id}")

    logger.info(f"Exported {len(registry._skills)} skills to {output_dir}")
