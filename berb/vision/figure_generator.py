"""Design-to-Code for Figures using Vision Models.

This module converts figure sketches/designs into matplotlib/tikz code
using vision models like Gemini 2.5 Flash.

Features:
- Sketch/image to figure spec extraction
- Code generation for matplotlib/tikz
- Nano Banana integration for image generation
- Iterative refinement with critic feedback
- VLM-based figure quality critique (AI Scientist P4-OPT-003)

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.vision.figure_generator import FigureGenerator, FigureCritic
    
    gen = FigureGenerator()
    code = await gen.sketch_to_code("my_sketch.png")
    figure = await gen.generate_from_description("bar chart comparing X and Y")
    
    # Critique generated figures
    critic = FigureCritic()
    critique = await critic.analyze_figure("figure.png", paper_context="...")
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FigureSpec:
    """Extracted figure specification from sketch."""
    
    figure_type: str  # bar, line, scatter, heatmap, etc.
    title: str
    xlabel: str
    ylabel: str
    data_description: str
    style: str  # matplotlib, tikz, seaborn
    colors: list[str]
    annotations: list[str]
    dimensions: tuple[int, int]
    metadata: dict[str, Any]


class VisionModelClient:
    """Client for vision model APIs (Gemini 2.5 Flash, GPT-4V)."""
    
    def __init__(self, api_key: str | None = None, provider: str = "gemini") -> None:
        """Initialize vision model client.
        
        Args:
            api_key: API key for the provider
            provider: Vision model provider (gemini, openai)
        """
        self._api_key = api_key
        self._provider = provider
        self._client = None
    
    def _get_client(self):
        """Get or create API client."""
        if self._client is None:
            if self._provider == "gemini":
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=self._api_key)
                    self._client = genai.GenerativeModel('gemini-2.5-flash')
                except ImportError:
                    logger.error("google-generativeai not installed")
                    return None
            elif self._provider == "openai":
                try:
                    from openai import OpenAI
                    self._client = OpenAI(api_key=self._api_key)
                except ImportError:
                    logger.error("openai not installed")
                    return None
        
        return self._client
    
    async def analyze_image(self, image_path: str | Path, prompt: str) -> str:
        """Analyze image with vision model.
        
        Args:
            image_path: Path to image file
            prompt: Analysis prompt
            
        Returns:
            Model response text
        """
        client = self._get_client()
        if not client:
            return ""
        
        image_path = Path(image_path)
        if not image_path.exists():
            logger.error(f"Image not found: {image_path}")
            return ""
        
        try:
            if self._provider == "gemini":
                import google.generativeai as genai
                
                # Upload image
                image = genai.upload_file(str(image_path))
                
                # Generate content
                response = client.generate_content([prompt, image])
                return response.text
            
            elif self._provider == "openai":
                import base64
                
                # Encode image
                with open(image_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode()
                
                # Call API
                response = client.chat.completions.create(
                    model="gpt-4-vision-preview",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image_data}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=2000
                )
                return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"Vision model analysis failed: {e}")
            return ""
    
    async def extract_figure_spec(self, image_path: str | Path) -> FigureSpec | None:
        """Extract figure specification from sketch.
        
        Args:
            image_path: Path to sketch image
            
        Returns:
            Extracted FigureSpec or None
        """
        prompt = """Analyze this figure sketch and extract the following information in JSON format:
{
    "figure_type": "bar|line|scatter|heatmap|box|violin|etc",
    "title": "figure title",
    "xlabel": "x-axis label",
    "ylabel": "y-axis label",
    "data_description": "description of data being shown",
    "style": "matplotlib|tikz|seaborn",
    "colors": ["color1", "color2"],
    "annotations": ["annotation1", "annotation2"],
    "dimensions": [width, height]
}

Be specific about the data structure and visualization requirements."""
        
        response = await self.analyze_image(image_path, prompt)
        
        if not response:
            return None
        
        # Parse JSON response
        import json
        try:
            # Extract JSON from response
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                
                return FigureSpec(
                    figure_type=data.get('figure_type', 'bar'),
                    title=data.get('title', ''),
                    xlabel=data.get('xlabel', ''),
                    ylabel=data.get('ylabel', ''),
                    data_description=data.get('data_description', ''),
                    style=data.get('style', 'matplotlib'),
                    colors=data.get('colors', []),
                    annotations=data.get('annotations', []),
                    dimensions=tuple(data.get('dimensions', [8, 6])),
                    metadata=data,
                )
        except Exception as e:
            logger.error(f"Failed to parse figure spec: {e}")
        
        return None


class FigureCodeGenerator:
    """Generate matplotlib/tikz code from figure specifications."""
    
    def __init__(self) -> None:
        """Initialize code generator."""
        self._templates = self._load_templates()
    
    def _load_templates(self) -> dict[str, str]:
        """Load code templates for different figure types."""
        return {
            'bar': '''
import matplotlib.pyplot as plt
import numpy as np

# Data
categories = {categories}
values = {values}

# Create figure
fig, ax = plt.subplots(figsize={dimensions})

# Plot
bars = ax.bar(categories, values, color={colors})

# Labels and title
ax.set_xlabel('{xlabel}')
ax.set_ylabel('{ylabel}')
ax.set_title('{title}')

# Annotations
{annotations}

# Style
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig('figure.png', dpi=300, bbox_inches='tight')
plt.show()
''',
            'line': '''
import matplotlib.pyplot as plt
import numpy as np

# Data
x = {x_values}
y = {y_values}

# Create figure
fig, ax = plt.subplots(figsize={dimensions})

# Plot
ax.plot(x, y, marker='o', linewidth=2, markersize=6, color={color})

# Labels and title
ax.set_xlabel('{xlabel}')
ax.set_ylabel('{ylabel}')
ax.set_title('{title}')

# Grid
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('figure.png', dpi=300, bbox_inches='tight')
plt.show()
''',
            'scatter': '''
import matplotlib.pyplot as plt
import numpy as np

# Data
x = {x_values}
y = {y_values}

# Create figure
fig, ax = plt.subplots(figsize={dimensions})

# Plot
ax.scatter(x, y, s=100, alpha=0.6, c={color}, edgecolors='black')

# Labels and title
ax.set_xlabel('{xlabel}')
ax.set_ylabel('{ylabel}')
ax.set_title('{title}')

# Grid
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('figure.png', dpi=300, bbox_inches='tight')
plt.show()
''',
        }
    
    def generate_code(self, spec: FigureSpec, data: dict[str, Any] | None = None) -> str:
        """Generate code from figure specification.
        
        Args:
            spec: Figure specification
            data: Optional data dictionary
            
        Returns:
            Generated Python code
        """
        template = self._templates.get(spec.figure_type, self._templates['bar'])
        
        # Fill template
        code = template.format(
            categories=data.get('categories', ['A', 'B', 'C']) if data else ['Category 1', 'Category 2', 'Category 3'],
            values=data.get('values', [10, 20, 30]) if data else [10, 20, 30],
            x_values=data.get('x', [1, 2, 3, 4, 5]) if data else [1, 2, 3, 4, 5],
            y_values=data.get('y', [2, 4, 6, 8, 10]) if data else [2, 4, 6, 8, 10],
            dimensions=spec.dimensions,
            colors=spec.colors if spec.colors else ['#1f77b4', '#ff7f0e', '#2ca02c'],
            color=spec.colors[0] if spec.colors else '#1f77b4',
            xlabel=spec.xlabel,
            ylabel=spec.ylabel,
            title=spec.title,
            annotations=self._generate_annotations(spec.annotations),
        )
        
        return code
    
    def _generate_annotations(self, annotations: list[str]) -> str:
        """Generate annotation code."""
        if not annotations:
            return "pass"
        
        lines = []
        for i, ann in enumerate(annotations):
            lines.append(f"ax.text({i}, {i*10}, '{ann}', ha='center', va='bottom')")
        
        return '\n'.join(lines)


class FigureGenerator:
    """Main figure generator combining vision and code generation."""
    
    def __init__(
        self,
        vision_api_key: str | None = None,
        vision_provider: str = "gemini",
    ) -> None:
        """Initialize figure generator.
        
        Args:
            vision_api_key: API key for vision model
            vision_provider: Vision model provider
        """
        self._vision = VisionModelClient(vision_api_key, vision_provider)
        self._code_gen = FigureCodeGenerator()
    
    async def sketch_to_code(
        self,
        image_path: str | Path,
        style: str = "matplotlib",
    ) -> str | None:
        """Convert sketch to matplotlib/tikz code.
        
        Args:
            image_path: Path to sketch image
            style: Output style (matplotlib/tikz)
            
        Returns:
            Generated code or None
        """
        # Extract figure spec from sketch
        spec = await self._vision.extract_figure_spec(image_path)
        
        if not spec:
            logger.error("Failed to extract figure spec from sketch")
            return None
        
        # Override style if specified
        spec.style = style
        
        # Generate code
        code = self._code_gen.generate_code(spec)
        
        logger.info(f"Generated {style} code from sketch")
        return code
    
    async def generate_from_description(
        self,
        description: str,
        style: str = "matplotlib",
    ) -> str:
        """Generate figure code from text description.
        
        Args:
            description: Text description of desired figure
            style: Output style
            
        Returns:
            Generated code
        """
        # Use LLM to parse description into spec
        # For now, use simple heuristics
        spec = self._parse_description(description, style)
        
        # Generate code
        code = self._code_gen.generate_code(spec)
        
        logger.info(f"Generated {style} code from description")
        return code
    
    def _parse_description(self, description: str, style: str) -> FigureSpec:
        """Parse text description into figure spec."""
        # Simple keyword-based parsing
        description_lower = description.lower()
        
        # Determine figure type
        if 'bar' in description_lower:
            figure_type = 'bar'
        elif 'line' in description_lower or 'trend' in description_lower:
            figure_type = 'line'
        elif 'scatter' in description_lower or 'correlation' in description_lower:
            figure_type = 'scatter'
        elif 'heatmap' in description_lower:
            figure_type = 'heatmap'
        else:
            figure_type = 'bar'
        
        return FigureSpec(
            figure_type=figure_type,
            title="Generated Figure",
            xlabel="X Axis",
            ylabel="Y Axis",
            data_description=description,
            style=style,
            colors=[],
            annotations=[],
            dimensions=(8, 6),
            metadata={'description': description},
        )
    
    async def refine_code(
        self,
        code: str,
        feedback: str,
    ) -> str:
        """Refine generated code based on feedback.
        
        Args:
            code: Current code
            feedback: Refinement feedback
            
        Returns:
            Refined code
        """
        # Use LLM to refine code based on feedback
        # For now, return original code
        logger.info(f"Refining code with feedback: {feedback}")
        return code


class FigureCritic:
    """Vision-based figure critique using VLM (AI Scientist P4-OPT-003).
    
    Analyzes rendered figures for:
    - Clarity and readability
    - Label accuracy
    - Color scheme effectiveness
    - Data-ink ratio
    - Consistency with paper claims
    
    Based on AI Scientist (Nature 2026) - Section 3.4: Visualization & VLM Feedback
    """
    
    def __init__(
        self,
        vision_api_key: str | None = None,
        vision_provider: str = "gemini",
    ) -> None:
        """Initialize figure critic.
        
        Args:
            vision_api_key: API key for vision model
            vision_provider: Vision model provider (gemini, openai)
        """
        self._vision = VisionModelClient(vision_api_key, vision_provider)
        self._critique_history: list[dict] = []
    
    async def analyze_figure(
        self,
        figure_path: str | Path,
        paper_context: str | None = None,
        figure_caption: str | None = None,
    ) -> FigureCritique:
        """Analyze a rendered figure using VLM.
        
        Args:
            figure_path: Path to rendered figure image
            paper_context: Optional paper text for consistency check
            figure_caption: Optional figure caption
            
        Returns:
            FigureCritique with scores and feedback
        """
        figure_path = Path(figure_path)
        if not figure_path.exists():
            logger.error(f"Figure not found: {figure_path}")
            return FigureCritique(overall_score=0.0, error="Figure not found")
        
        # Build critique prompt
        prompt = self._build_critique_prompt(
            paper_context=paper_context,
            figure_caption=figure_caption,
        )
        
        # Analyze with VLM
        response = await self._vision.analyze_image(figure_path, prompt)
        
        # Parse critique from response
        critique = self._parse_critique_response(response)
        critique.figure_path = str(figure_path)
        
        # Store in history
        self._critique_history.append(critique.to_dict())
        
        logger.info(
            f"Figure critique complete: {critique.overall_score:.1f}/10 "
            f"({len(critique.issues)} issues found)"
        )
        
        return critique
    
    def _build_critique_prompt(
        self,
        paper_context: str | None,
        figure_caption: str | None,
    ) -> str:
        """Build VLM prompt for figure critique."""
        base_prompt = """You are an expert scientific reviewer evaluating figures for a top-tier conference (Nature/Science/NeurIPS/ICML).

Analyze this figure comprehensively across these dimensions:

1. CLARITY & READABILITY (1-10)
   - Is the figure easy to understand at a glance?
   - Are text elements legible (font size, contrast)?
   - Is the layout logical and well-organized?

2. LABEL ACCURACY (1-10)
   - Are axes labeled correctly with units?
   - Do legend entries match the data shown?
   - Are all symbols/shapes explained?

3. COLOR SCHEME EFFECTIVENESS (1-10)
   - Is the color palette appropriate for the data type?
   - Is it colorblind-friendly?
   - Does it use color purposefully (not decoratively)?

4. DATA-INK RATIO (1-10)
   - Is there any unnecessary chartjunk?
   - Are gridlines, borders minimal?
   - Does every element serve a purpose?

5. CONSISTENCY WITH CLAIMS (1-10)
   - Does the figure support the stated claims?
   - Are error bars shown where appropriate?
   - Is the visual encoding accurate (no misleading scales)?

OUTPUT FORMAT (JSON):
{
    "scores": {
        "clarity": <1-10>,
        "label_accuracy": <1-10>,
        "color_scheme": <1-10>,
        "data_ink_ratio": <1-10>,
        "claim_consistency": <1-10>
    },
    "overall_score": <float 1-10>,
    "strengths": ["strength 1", "strength 2", ...],
    "issues": [
        {
            "type": "clarity|labels|color|data_ink|consistency",
            "severity": "critical|major|minor",
            "description": "Issue description",
            "suggestion": "How to fix"
        }
    ],
    "recommendations": ["recommendation 1", ...],
    "accessibility_concerns": ["concern 1", ...],
    "detailed_feedback": "<2-3 paragraphs>"
}
"""
        
        if figure_caption:
            base_prompt += f"\nFIGURE CAPTION:\n{figure_caption}\n"
        
        if paper_context:
            # Truncate context if too long
            if len(paper_context) > 2000:
                paper_context = paper_context[:2000] + "..."
            base_prompt += f"\nPAPER CONTEXT:\n{paper_context}\n"
        
        return base_prompt
    
    def _parse_critique_response(self, response: str) -> FigureCritique:
        """Parse VLM response into FigureCritique."""
        import json
        import re
        
        # Try to extract JSON from response
        try:
            # Find JSON block
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
            else:
                # Fallback: create structured critique from text
                data = self._create_fallback_critique(response)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to parse critique JSON: {e}")
            data = self._create_fallback_critique(response)
        
        # Calculate overall score
        scores = data.get("scores", {})
        if scores:
            overall = sum(scores.values()) / len(scores)
        else:
            overall = 5.0
        
        return FigureCritique(
            overall_score=round(overall, 2),
            clarity_score=scores.get("clarity", 5),
            label_accuracy_score=scores.get("label_accuracy", 5),
            color_scheme_score=scores.get("color_scheme", 5),
            data_ink_ratio_score=scores.get("data_ink_ratio", 5),
            claim_consistency_score=scores.get("claim_consistency", 5),
            strengths=data.get("strengths", []),
            issues=data.get("issues", []),
            recommendations=data.get("recommendations", []),
            accessibility_concerns=data.get("accessibility_concerns", []),
            detailed_feedback=data.get("detailed_feedback", ""),
        )
    
    def _create_fallback_critique(self, response: str) -> dict:
        """Create fallback critique when JSON parsing fails."""
        return {
            "scores": {
                "clarity": 6,
                "label_accuracy": 6,
                "color_scheme": 6,
                "data_ink_ratio": 6,
                "claim_consistency": 6,
            },
            "overall_score": 6.0,
            "strengths": ["Figure appears to show relevant data"],
            "issues": [{"type": "general", "severity": "minor", "description": "Could not parse detailed critique", "suggestion": "Review figure manually"}],
            "recommendations": ["Manual review recommended"],
            "detailed_feedback": response[:500],
        }
    
    async def suggest_improvements(
        self,
        critique: FigureCritique,
        current_code: str,
    ) -> str:
        """Generate code improvements based on critique.
        
        Args:
            critique: Figure critique results
            current_code: Current matplotlib/tikz code
            
        Returns:
            Suggested code modifications
        """
        # Build improvement prompt
        prompt = f"""Based on this figure critique, suggest specific code improvements:

CRITIQUE SUMMARY:
- Overall Score: {critique.overall_score:.1f}/10
- Issues: {len(critique.issues)}

ISSUES:
"""
        for issue in critique.issues:
            prompt += f"- [{issue.get('severity', 'minor').upper()}] {issue.get('description', '')}\n"
            prompt += f"  Suggestion: {issue.get('suggestion', '')}\n"
        
        prompt += f"""
CURRENT CODE:
```python
{current_code[:2000]}  # Truncate if too long
```

Provide specific code changes to address the issues. Focus on:
1. Critical and major issues first
2. Accessibility improvements
3. Clarity enhancements

Output format:
```python
# IMPROVEMENT 1: [Description]
# Before: [original code line]
# After: [improved code line]

# IMPROVEMENT 2: ...
```
"""
        
        # Call LLM for suggestions
        # In production:
        # response = await self._llm_client.chat(
        #     messages=[{"role": "user", "content": prompt}]
        # )
        # return response.content
        
        # Placeholder
        return f"# Improvements based on critique (placeholder)\n# {len(critique.issues)} issues to address\n"
    
    def get_critique_statistics(self) -> dict:
        """Get statistics from critique history."""
        if not self._critique_history:
            return {"error": "No critiques performed"}
        
        scores = []
        issue_types = {}
        
        for critique in self._critique_history:
            if "overall_score" in critique:
                scores.append(critique["overall_score"])
            
            for issue in critique.get("issues", []):
                issue_type = issue.get("type", "unknown")
                issue_types[issue_type] = issue_types.get(issue_type, 0) + 1
        
        return {
            "total_critiques": len(self._critique_history),
            "avg_overall_score": sum(scores) / len(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "issue_distribution": issue_types,
        }


@dataclass
class FigureCritique:
    """Results of VLM-based figure critique."""
    
    overall_score: float
    figure_path: str = ""
    clarity_score: float = 5.0
    label_accuracy_score: float = 5.0
    color_scheme_score: float = 5.0
    data_ink_ratio_score: float = 5.0
    claim_consistency_score: float = 5.0
    strengths: list[str] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    accessibility_concerns: list[str] = field(default_factory=list)
    detailed_feedback: str = ""
    error: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "overall_score": self.overall_score,
            "figure_path": self.figure_path,
            "clarity_score": self.clarity_score,
            "label_accuracy_score": self.label_accuracy_score,
            "color_scheme_score": self.color_scheme_score,
            "data_ink_ratio_score": self.data_ink_ratio_score,
            "claim_consistency_score": self.claim_consistency_score,
            "strengths": self.strengths,
            "issues": self.issues,
            "recommendations": self.recommendations,
            "accessibility_concerns": self.accessibility_concerns,
            "detailed_feedback": self.detailed_feedback,
        }
    
    @property
    def is_acceptable(self) -> bool:
        """Check if figure meets minimum quality threshold."""
        return self.overall_score >= 7.0 and not any(
            i.get("severity") == "critical" for i in self.issues
        )
