"""DeepQuery (Perplexity) and DeepMind AI (xAI) client integration.

This module provides clients for DeepQuery (Perplexity Sonar) and DeepMind AI
(xAI Grok) models, enabling enhanced search capabilities and large context
processing for comprehensive literature analysis.

# Author: Georgios-Chrysovalantis Chatzivantsidis

DeepQuery (Perplexity) Models:
- sonar: Quick factual queries
- sonar-pro: Complex queries with follow-ups
- sonar-reasoning-pro: Multi-step reasoning
- sonar-deep-research: Comprehensive literature reviews

DeepMind AI (xAI) Models:
- grok-4.20: 2M context, flagship model
- grok-4: 2M context, reasoning model
- grok-3-mini: 128K context, cost-effective

Usage:
    from berb.llm.deep_query_client import DeepQueryClient
    from berb.llm.deepmind_client import DeepMindAIClient
    
    # DeepQuery for literature search
    dq = DeepQueryClient(api_key="...")
    results = await dq.search("CRISPR gene editing advances")
    
    # DeepMind AI for full paper analysis
    dm = DeepMindAIClient(api_key="...")
    analysis = await dm.analyze_full_paper(paper_text, max_tokens=2_000_000)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DeepQuery (Perplexity) Client
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DeepQueryResult:
    """Single DeepQuery search result."""
    
    title: str
    content: str
    url: str
    source: str
    published_date: str | None = None
    authors: list[str] = field(default_factory=list)
    citations: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class DeepQueryClient:
    """Client for DeepQuery (Perplexity Sonar) API.
    
    Provides search-grounded LLM responses with real-time web access.
    """
    
    BASE_URL = "https://api.perplexity.ai/chat/completions"
    
    # Model mapping
    MODELS = {
        "quick": "sonar",
        "pro": "sonar-pro",
        "reasoning": "sonar-reasoning-pro",
        "deep_research": "sonar-deep-research",
    }
    
    def __init__(
        self,
        api_key: str,
        timeout: int = 60,
        default_model: str = "pro",
    ):
        """Initialize DeepQuery client.
        
        Args:
            api_key: Perplexity API key
            timeout: Request timeout in seconds
            default_model: Default model to use
        """
        self._api_key = api_key
        self._timeout = timeout
        self._default_model = default_model
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
    
    async def search(
        self,
        query: str,
        model: str = "pro",
        max_tokens: int = 4000,
        temperature: float = 0.2,
        return_citations: bool = True,
    ) -> DeepQueryResult:
        """Search using DeepQuery.
        
        Args:
            query: Search query
            model: Model to use (quick, pro, reasoning, deep_research)
            max_tokens: Maximum output tokens
            temperature: Temperature for generation
            return_citations: Include citations in response
            
        Returns:
            Search result with content and citations
        """
        model_name = self.MODELS.get(model, self.MODELS["pro"])
        
        messages = [
            {
                "role": "system",
                "content": "You are a research assistant. Provide accurate, well-cited information."
            },
            {
                "role": "user",
                "content": query,
            },
        ]
        
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "return_citations": return_citations,
        }
        
        try:
            response = await self._client.post(self.BASE_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            citations = data.get("citations", [])
            
            # Extract metadata
            usage = data.get("usage", {})
            
            return DeepQueryResult(
                title=query[:100],  # Use query as title
                content=message.get("content", ""),
                url="",
                source="DeepQuery",
                citations=[{"url": c} for c in citations],
                metadata={
                    "model": model_name,
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
            )
            
        except httpx.HTTPError as e:
            logger.error(f"DeepQuery search failed: {e}")
            raise
        finally:
            await self._client.aclose()
    
    async def literature_review(
        self,
        topic: str,
        focus_areas: list[str] | None = None,
        year_range: tuple[int, int] | None = None,
    ) -> DeepQueryResult:
        """Conduct comprehensive literature review.
        
        Args:
            topic: Research topic
            focus_areas: Specific areas to focus on
            year_range: Year range filter (from, to)
            
        Returns:
            Literature review result
        """
        # Build comprehensive query
        query_parts = [f"Comprehensive literature review on: {topic}"]
        
        if focus_areas:
            query_parts.append(f"Focus areas: {', '.join(focus_areas)}")
        
        if year_range:
            query_parts.append(f"Publications from {year_range[0]} to {year_range[1]}")
        
        query_parts.append("""
Please provide:
1. Key papers with authors, venue, year, DOI
2. Main findings from each paper
3. Research gaps identified
4. Conflicting results or debates
5. Recent developments (last 2 years)
6. Important methodologies used

Format as structured response with clear citations.
""")
        
        query = "\n".join(query_parts)
        
        return await self.search(
            query=query,
            model="deep_research",
            max_tokens=8000,
            temperature=0.3,
        )
    
    async def verify_citation(
        self,
        citation_text: str,
        claimed_finding: str,
    ) -> dict[str, Any]:
        """Verify a citation exists and finding is accurate.
        
        Args:
            citation_text: Citation in any format
            claimed_finding: Finding attributed to the citation
            
        Returns:
            Verification result
        """
        query = f"""Verify this citation and claimed finding:

Citation: {citation_text}
Claimed Finding: {claimed_finding}

Search for:
1. Does this paper exist?
2. Are the authors, title, venue correct?
3. Does the paper actually support the claimed finding?
4. Any retractions or corrections?
5. Citation count and impact

Output: VERIFIED, UNVERIFIED, or INACCURATE with evidence."""
        
        result = await self.search(query, model="pro")
        
        # Parse verification status
        content = result.content.upper()
        if "VERIFIED" in content and "INACCURATE" not in content:
            status = "verified"
        elif "INACCURATE" in content:
            status = "inaccurate"
        else:
            status = "unverified"
        
        return {
            "status": status,
            "evidence": result.content,
            "citations": result.citations,
        }
    
    def get_model_info(self) -> dict[str, Any]:
        """Get information about available models.
        
        Returns:
            Dictionary with model information
        """
        return {
            "provider": "DeepQuery (Perplexity)",
            "models": {
                "sonar": {
                    "description": "Quick factual queries",
                    "context_window": "128K",
                    "best_for": "Fact-checking, quick lookups",
                },
                "sonar-pro": {
                    "description": "Advanced search with follow-ups",
                    "context_window": "128K",
                    "best_for": "Complex queries, multi-part questions",
                },
                "sonar-reasoning-pro": {
                    "description": "Chain of thought reasoning",
                    "context_window": "128K",
                    "best_for": "Multi-step reasoning, logical tasks",
                },
                "sonar-deep-research": {
                    "description": "Exhaustive web research",
                    "context_window": "256K",
                    "best_for": "Literature reviews, comprehensive reports",
                },
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# DeepMind AI (xAI) Client
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DeepMindAIResult:
    """Single DeepMind AI response."""
    
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class DeepMindAIClient:
    """Client for DeepMind AI (xAI Grok) API.
    
    Provides access to models with 2M token context window for
    full-paper analysis and cross-paper synthesis.
    """
    
    BASE_URL = "https://api.x.ai/v1/chat/completions"
    
    # Model mapping
    MODELS = {
        "flagship": "grok-4.20",
        "reasoning": "grok-4",
        "mini": "grok-3-mini",
    }
    
    def __init__(
        self,
        api_key: str,
        timeout: int = 120,
        default_model: str = "flagship",
    ):
        """Initialize DeepMind AI client.
        
        Args:
            api_key: xAI API key
            timeout: Request timeout in seconds
            default_model: Default model to use
        """
        self._api_key = api_key
        self._timeout = timeout
        self._default_model = default_model
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
    
    async def chat(
        self,
        messages: list[dict],
        model: str = "flagship",
        max_tokens: int = 32000,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> DeepMindAIResult:
        """Send chat completion request.
        
        Args:
            messages: List of message dicts
            model: Model to use
            max_tokens: Maximum output tokens
            temperature: Temperature for generation
            stream: Enable streaming
            
        Returns:
            Model response
        """
        model_name = self.MODELS.get(model, self.MODELS["flagship"])
        
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        
        try:
            response = await self._client.post(self.BASE_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            usage = data.get("usage", {})
            
            return DeepMindAIResult(
                content=message.get("content", ""),
                model=model_name,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                finish_reason=choice.get("finish_reason", ""),
                metadata={
                    "id": data.get("id"),
                    "created": data.get("created"),
                },
            )
            
        except httpx.HTTPError as e:
            logger.error(f"DeepMind AI chat failed: {e}")
            raise
        finally:
            await self._client.aclose()
    
    async def analyze_full_paper(
        self,
        paper_text: str,
        analysis_type: str = "comprehensive",
    ) -> dict[str, Any]:
        """Analyze a complete research paper (up to 2M tokens).
        
        Args:
            paper_text: Full paper text
            analysis_type: Type of analysis (comprehensive, methodology, results)
            
        Returns:
            Analysis results
        """
        # Truncate to model limit if needed
        max_context = 1_800_000  # Leave room for prompt/response
        if len(paper_text) > max_context:
            paper_text = paper_text[:max_context]
            logger.warning(f"Paper truncated to {max_context} characters")
        
        prompts = {
            "comprehensive": """Analyze this complete research paper:

{paper}

Extract:
1. Research question and hypothesis
2. Methodology (detailed)
3. Key findings with statistics
4. Limitations acknowledged by authors
5. Future work suggested
6. Code/data availability
7. Reproducibility score (1-10)
8. Novelty score (1-10)
9. Impact potential (1-10)

Output as structured JSON.""",
            
            "methodology": """Analyze the methodology of this paper:

{paper}

Evaluate:
1. Study design appropriateness
2. Sample size and power
3. Controls and baselines
4. Statistical methods
5. Potential confounds
6. Reproducibility details
7. Ethical considerations

Output as structured JSON.""",
            
            "results": """Analyze the results of this paper:

{paper}

Extract:
1. Main results with effect sizes
2. Statistical significance
3. Confidence intervals
4. Comparison to baselines
5. Ablation studies
6. Qualitative results
7. Failure cases

Output as structured JSON.""",
        }
        
        prompt = prompts.get(analysis_type, prompts["comprehensive"]).format(
            paper=paper_text
        )
        
        messages = [
            {
                "role": "system",
                "content": "You are an expert research analyst. Analyze papers thoroughly and objectively."
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]
        
        result = await self.chat(
            messages=messages,
            model="flagship",
            max_tokens=8000,
            temperature=0.2,
        )
        
        return {
            "analysis": result.content,
            "model": result.model,
            "tokens_used": result.total_tokens,
            "analysis_type": analysis_type,
        }
    
    async def synthesize_papers(
        self,
        papers: list[dict[str, str]],
        synthesis_goal: str = "hypothesis_generation",
    ) -> dict[str, Any]:
        """Synthesize findings across multiple papers (up to 2M context).
        
        Args:
            papers: List of paper dicts with title, text
            synthesis_goal: Goal of synthesis
            
        Returns:
            Synthesis results
        """
        # Combine papers within context limit
        max_context = 1_600_000
        combined = []
        current_length = 0
        
        for paper in papers:
            paper_text = f"=== {paper.get('title', 'Untitled')} ===\n\n{paper.get('text', '')}"
            if current_length + len(paper_text) > max_context:
                logger.warning(f"Skipping paper '{paper.get('title')}' - context limit")
                break
            combined.append(paper_text)
            current_length += len(paper_text)
        
        full_context = "\n\n".join(combined)
        
        goals = {
            "hypothesis_generation": """Based on these research papers, generate novel hypotheses:

{papers}

Identify:
1. Patterns across papers
2. Contradictions to resolve
3. Unexplored combinations
4. Methodology gaps
5. Promising directions

Generate 5-10 testable hypotheses with rationale.""",
            
            "survey": """Create a comprehensive survey from these papers:

{papers}

Organize by:
1. Research themes
2. Methodological approaches
3. Key findings per theme
4. Open questions
5. Future directions

Include citation counts and impact assessment.""",
            
            "meta_analysis": """Perform meta-analysis synthesis:

{papers}

For each finding:
1. Effect sizes across papers
2. Consistency of results
3. Moderator variables
4. Publication bias assessment
5. Overall conclusion strength

Output structured findings.""",
        }
        
        prompt = goals.get(synthesis_goal, goals["hypothesis_generation"]).format(
            papers=full_context
        )
        
        messages = [
            {
                "role": "system",
                "content": "You are an expert research synthesizer. Identify patterns and generate insights across multiple papers."
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]
        
        result = await self.chat(
            messages=messages,
            model="flagship",
            max_tokens=12000,
            temperature=0.4,
        )
        
        return {
            "synthesis": result.content,
            "papers_analyzed": len(combined),
            "model": result.model,
            "tokens_used": result.total_tokens,
            "synthesis_goal": synthesis_goal,
        }
    
    def get_model_info(self) -> dict[str, Any]:
        """Get information about available models.
        
        Returns:
            Dictionary with model information
        """
        return {
            "provider": "DeepMind AI (xAI)",
            "models": {
                "grok-4.20": {
                    "description": "Flagship model with 2M context",
                    "context_window": "2M tokens",
                    "best_for": "Full paper analysis, cross-paper synthesis",
                    "speed": "Fastest",
                },
                "grok-4": {
                    "description": "Reasoning model with 2M context",
                    "context_window": "2M tokens",
                    "best_for": "Complex reasoning, experiment design",
                },
                "grok-3-mini": {
                    "description": "Cost-effective model",
                    "context_window": "128K tokens",
                    "best_for": "Simple tasks, classification, summarization",
                },
            },
            "features": [
                "2M token context window (industry leading)",
                "Batch API with 50% discount",
                "Function calling support",
                "Structured outputs",
                "Low hallucination rate",
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Factory Functions
# ─────────────────────────────────────────────────────────────────────────────


def create_deepquery_client(
    api_key: str | None = None,
    default_model: str = "pro",
) -> DeepQueryClient:
    """Create DeepQuery client from config or environment.
    
    Args:
        api_key: API key (or from DEEPQUERY_API_KEY env)
        default_model: Default model
        
    Returns:
        Configured DeepQueryClient
    """
    import os
    
    key = api_key or os.environ.get("DEEPQUERY_API_KEY", "")
    if not key:
        raise ValueError(
            "DeepQuery API key required. Set DEEPQUERY_API_KEY env var or pass api_key."
        )
    
    return DeepQueryClient(api_key=key, default_model=default_model)


def create_deepmind_ai_client(
    api_key: str | None = None,
    default_model: str = "flagship",
) -> DeepMindAIClient:
    """Create DeepMind AI client from config or environment.
    
    Args:
        api_key: API key (or from DEEPMIND_AI_API_KEY env)
        default_model: Default model
        
    Returns:
        Configured DeepMindAIClient
    """
    import os
    
    key = api_key or os.environ.get("DEEPMIND_AI_API_KEY", "")
    if not key:
        raise ValueError(
            "DeepMind AI API key required. Set DEEPMIND_AI_API_KEY env var or pass api_key."
        )
    
    return DeepMindAIClient(api_key=key, default_model=default_model)
