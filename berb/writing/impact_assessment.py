"""Humanitarian Impact Assessment.

Based on Tao & Klowden philosophical framework:
"AI tools should be viewed through BOTH technical and humanitarian lenses.
Research should advance understanding, not just produce output."

Key Features:
- Contribution type classification
- Broader impact generation
- Understanding advancement check
- Risk assessment

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.writing.impact_assessment import HumanitarianImpactAssessment
    
    assessor = HumanitarianImpactAssessment()
    assessment = await assessor.assess_contribution_type(paper)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ContributionType(str, Enum):
    """Type of research contribution."""
    FUNDAMENTAL_UNDERSTANDING = "fundamental_understanding"
    """Advances fundamental understanding (highest value)"""
    
    USEFUL_TOOLS_METHODS = "useful_tools_methods"
    """Provides useful tools or methods (high value)"""
    
    CONFIRMS_KNOWN = "confirms_known"
    """Confirms known results (moderate value)"""
    
    INCREMENTAL = "incremental"
    """Incremental improvement (lower value)"""
    
    TEXT_WITHOUT_INSIGHT = "text_without_insight"
    """Generates text without insight (low value - flag)"""


@dataclass
class ContributionAssessment:
    """Assessment of research contribution.
    
    Attributes:
        contribution_type: Type of contribution
        confidence: Confidence score (0-1)
        reasoning: Reasoning for classification
        broader_impact: Broader impact statement
        risks: Identified risks
        novelty_score: Novelty score (1-10)
        understanding_advancement: Understanding advancement score (1-10)
    """
    contribution_type: ContributionType
    confidence: float = 0.5
    reasoning: str = ""
    broader_impact: str = ""
    risks: list[str] = field(default_factory=list)
    novelty_score: float = 5.0
    understanding_advancement: float = 5.0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "contribution_type": self.contribution_type.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "broader_impact": self.broader_impact,
            "risks": self.risks,
            "novelty_score": self.novelty_score,
            "understanding_advancement": self.understanding_advancement,
        }


class HumanitarianImpactAssessment:
    """Tao/Klowden humanitarian impact assessment.
    
    Features:
    - Classifies contribution type
    - Generates broader impact statement
    - Assesses understanding advancement
    - Identifies risks
    
    Usage:
        assessor = HumanitarianImpactAssessment()
        assessment = await assessor.assess_contribution_type(paper)
    """
    
    def __init__(self, model: str = "claude-3-opus"):
        """Initialize impact assessor.
        
        Args:
            model: LLM model for assessment
        """
        self.model = model
        logger.info(f"Initialized HumanitarianImpactAssessment with {model}")
    
    async def assess_contribution_type(
        self,
        paper_content: str,
        title: str = "",
        abstract: str = "",
    ) -> ContributionAssessment:
        """Classify research contribution type.
        
        Args:
            paper_content: Full paper content
            title: Paper title
            abstract: Paper abstract
            
        Returns:
            Contribution assessment
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model=self.model)
        
        prompt = f"""
Classify this research paper's contribution type:

Title: {title}
Abstract: {abstract}

Paper Content:
{paper_content[:5000]}...

Contribution Types (choose one):
1. FUNDAMENTAL_UNDERSTANDING - Advances fundamental understanding (highest value)
2. USEFUL_TOOLS_METHODS - Provides useful tools or methods (high value)
3. CONFIRMS_KNOWN - Confirms known results (moderate value)
4. INCREMENTAL - Incremental improvement (lower value)
5. TEXT_WITHOUT_INSIGHT - Generates text without insight (low value - flag)

Provide your classification with:
1. Contribution type
2. Confidence (0-1)
3. Reasoning
4. Novelty score (1-10)
5. Understanding advancement score (1-10)

Format as JSON:
{{
    "contribution_type": "fundamental_understanding",
    "confidence": 0.85,
    "reasoning": "...",
    "novelty_score": 8,
    "understanding_advancement": 9
}}
"""
        
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are a senior researcher assessing research contributions.",
        )
        
        # Parse response
        assessment = self._parse_assessment(response.content)
        
        logger.info(
            f"Contribution assessment: {assessment.contribution_type.value} "
            f"(confidence={assessment.confidence:.2f})"
        )
        
        return assessment
    
    async def generate_broader_impact(
        self,
        paper_content: str,
        title: str = "",
        abstract: str = "",
    ) -> str:
        """Generate broader impact statement.
        
        Args:
            paper_content: Full paper content
            title: Paper title
            abstract: Paper abstract
            
        Returns:
            Broader impact statement
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model=self.model)
        
        prompt = f"""
Generate an honest broader impact statement for this research:

Title: {title}
Abstract: {abstract}

Paper Content:
{paper_content[:5000]}...

Address:
1. Who benefits from this research?
2. What are the potential risks?
3. How does this change what we UNDERSTAND (not just what we can do)?
4. Is this genuinely novel or incremental?
5. What are the societal implications?

Provide a thoughtful, honest assessment (200-300 words).
"""
        
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are assessing the broader impact of research.",
        )
        
        logger.info("Generated broader impact statement")
        return response.content
    
    async def identify_risks(
        self,
        paper_content: str,
        title: str = "",
    ) -> list[str]:
        """Identify potential risks.
        
        Args:
            paper_content: Full paper content
            title: Paper title
            
        Returns:
            List of identified risks
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model=self.model)
        
        prompt = f"""
Identify potential risks and negative implications of this research:

Title: {title}

Paper Content:
{paper_content[:5000]}...

Consider:
1. Misuse potential
2. Unintended consequences
3. Ethical concerns
4. Environmental impact
5. Social implications

List risks as bullet points.
"""
        
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are identifying research risks.",
        )
        
        # Parse as list
        lines = response.content.strip().split("\n")
        risks = [
            line.strip().lstrip("-*•").strip()
            for line in lines
            if line.strip() and not line.strip().startswith("Consider")
        ]
        
        logger.info(f"Identified {len(risks)} risks")
        return risks
    
    def _parse_assessment(self, response: str) -> ContributionAssessment:
        """Parse assessment from LLM response.
        
        Args:
            response: LLM response
            
        Returns:
            Contribution assessment
        """
        import json
        
        try:
            # Extract JSON
            start = response.find("{")
            end = response.rfind("}") + 1
            
            if start >= 0 and end > start:
                json_str = response[start:end]
                data = json.loads(json_str)
                
                contribution_type = ContributionType(
                    data.get("contribution_type", "incremental")
                )
                
                return ContributionAssessment(
                    contribution_type=contribution_type,
                    confidence=float(data.get("confidence", 0.5)),
                    reasoning=data.get("reasoning", ""),
                    novelty_score=float(data.get("novelty_score", 5.0)),
                    understanding_advancement=float(
                        data.get("understanding_advancement", 5.0)
                    ),
                )
        except Exception as e:
            logger.warning(f"Failed to parse assessment: {e}")
        
        # Default
        return ContributionAssessment(
            contribution_type=ContributionType.INCREMENTAL,
            confidence=0.5,
            reasoning="Parse failed",
        )


async def assess_contribution_type(
    paper_content: str,
    title: str = "",
    abstract: str = "",
    model: str = "claude-3-opus",
) -> ContributionAssessment:
    """Convenience function to assess contribution type.
    
    Args:
        paper_content: Paper content
        title: Paper title
        abstract: Paper abstract
        model: LLM model
        
    Returns:
        Contribution assessment
    """
    assessor = HumanitarianImpactAssessment(model=model)
    return await assessor.assess_contribution_type(paper_content, title, abstract)


__all__ = [
    "HumanitarianImpactAssessment",
    "ContributionType",
    "ContributionAssessment",
    "assess_contribution_type",
]
