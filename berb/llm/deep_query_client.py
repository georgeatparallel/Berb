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
- grok-4.5: 2M context, flagship/reasoning model
- grok-3-mini: 128K context, cost-effective

Usage:
    from berb.llm.deep_query_client import DeepQueryClient
    from berb.llm.deepmind_client import DeepMindAIClient

    # DeepQuery for literature search
    dq = DeepQueryClient(api_key="...")
    result = dq.search("CRISPR gene editing advances")

    # DeepMind AI for full paper analysis
    dm = DeepMindAIClient(api_key="...")
    analysis = await dm.analyze_full_paper(paper_text, max_tokens=2_000_000)
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import httpx

from berb.literature._rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DeepQuery (Perplexity) Client — sync, stdlib urllib (matches LLMClient and
# the rest of berb/literature/'s clients; no async lifecycle to manage).
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


_RATE_LIMIT_SEC = 1.0  # conservative spacing between requests
_MAX_RETRIES = 3
_MAX_WAIT_SEC = 60
_TIMEOUT_SEC = 60

_rate_limiter = RateLimiter(min_interval_sec=_RATE_LIMIT_SEC)

# ---------------------------------------------------------------------------
# Three-state circuit breaker (same shape as berb/literature/semantic_scholar.py)
# ---------------------------------------------------------------------------

_CB_THRESHOLD = 3  # consecutive 429s to trip
_CB_INITIAL_COOLDOWN = 120  # seconds before first HALF_OPEN probe
_CB_MAX_COOLDOWN = 600  # cap cooldown at 10 minutes

_CB_CLOSED = "closed"
_CB_OPEN = "open"
_CB_HALF_OPEN = "half_open"

_cb_state: str = _CB_CLOSED
_cb_consecutive_429s: int = 0
_cb_cooldown_sec: float = _CB_INITIAL_COOLDOWN
_cb_open_since: float = 0.0
_cb_trip_count: int = 0
_cb_lock = threading.Lock()


def _reset_circuit_breaker() -> None:
    """Reset circuit breaker state (for tests)."""
    global _cb_state, _cb_consecutive_429s, _cb_cooldown_sec  # noqa: PLW0603
    global _cb_open_since, _cb_trip_count  # noqa: PLW0603
    with _cb_lock:
        _cb_state = _CB_CLOSED
        _cb_consecutive_429s = 0
        _cb_cooldown_sec = _CB_INITIAL_COOLDOWN
        _cb_open_since = 0.0
        _cb_trip_count = 0


def _cb_should_allow() -> bool:
    """Check if circuit breaker allows a request."""
    global _cb_state  # noqa: PLW0603
    with _cb_lock:
        if _cb_state == _CB_CLOSED:
            return True
        if _cb_state == _CB_OPEN:
            elapsed = time.monotonic() - _cb_open_since
            if elapsed >= _cb_cooldown_sec:
                _cb_state = _CB_HALF_OPEN
                logger.info(
                    "Perplexity circuit breaker → HALF_OPEN after %.0fs cooldown. "
                    "Trying one probe request...",
                    elapsed,
                )
                return True
            return False
        return True  # HALF_OPEN: allow the probe


def _cb_on_success() -> None:
    """Record a successful request."""
    global _cb_state, _cb_consecutive_429s, _cb_cooldown_sec  # noqa: PLW0603
    with _cb_lock:
        _cb_consecutive_429s = 0
        if _cb_state != _CB_CLOSED:
            logger.info("Perplexity circuit breaker → CLOSED (request succeeded)")
            _cb_state = _CB_CLOSED
            _cb_cooldown_sec = _CB_INITIAL_COOLDOWN


def _cb_on_429() -> bool:
    """Record a 429 response. Returns True if breaker is now OPEN."""
    global _cb_state, _cb_consecutive_429s, _cb_cooldown_sec  # noqa: PLW0603
    global _cb_open_since, _cb_trip_count  # noqa: PLW0603
    with _cb_lock:
        _cb_consecutive_429s += 1

        if _cb_state == _CB_HALF_OPEN:
            _cb_cooldown_sec = min(_cb_cooldown_sec * 2, _CB_MAX_COOLDOWN)
            _cb_state = _CB_OPEN
            _cb_open_since = time.monotonic()
            _cb_trip_count += 1
            logger.warning(
                "Perplexity circuit breaker → OPEN (probe failed). Next cooldown: %.0fs (trip #%d)",
                _cb_cooldown_sec,
                _cb_trip_count,
            )
            return True

        if _cb_consecutive_429s >= _CB_THRESHOLD:
            _cb_state = _CB_OPEN
            _cb_open_since = time.monotonic()
            _cb_trip_count += 1
            logger.warning(
                "Perplexity circuit breaker TRIPPED after %d consecutive 429s. "
                "Cooldown: %.0fs (trip #%d).",
                _cb_consecutive_429s,
                _cb_cooldown_sec,
                _cb_trip_count,
            )
            return True
        return False


class DeepQueryClient:
    """Sync client for DeepQuery (Perplexity Sonar) API.

    Provides search-grounded LLM responses with real-time web access.
    Pure stdlib urllib — matches ``LLMClient`` and the rest of
    ``berb/literature/``'s clients. No connection lifecycle to manage,
    so unlike the old async/httpx version, the same instance can be
    reused for any number of sequential calls.
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
        timeout: int = _TIMEOUT_SEC,
        default_model: str = "pro",
        run_id: str | None = None,
    ):
        """Initialize DeepQuery client.

        Args:
            api_key: Perplexity API key
            timeout: Request timeout in seconds
            default_model: Default model to use
            run_id: Optional pipeline run ID, attached to cost-tracking
                records via ``ExtendedReasoningCostTracker`` (best-effort —
                tracking failures never break a search call).
        """
        self._api_key = api_key
        self._timeout = timeout
        self._default_model = default_model
        self._run_id = run_id

    def search(
        self,
        query: str,
        model: str = "pro",
        max_tokens: int = 4000,
        temperature: float = 0.2,
        return_citations: bool = True,
        domain_filter: list[str] | None = None,
        recency_filter: str | None = None,
    ) -> DeepQueryResult:
        """Search using DeepQuery.

        Args:
            query: Search query
            model: Model to use (quick, pro, reasoning, deep_research)
            max_tokens: Maximum output tokens
            temperature: Temperature for generation
            return_citations: Include citations in response
            domain_filter: Optional list of domains to restrict search to
                (Perplexity ``search_domain_filter``), e.g.
                ``["arxiv.org", "openreview.net"]``.
            recency_filter: Optional recency window — one of
                ``"day"``, ``"week"``, ``"month"``, ``"year"``
                (Perplexity ``search_recency_filter``).

        Returns:
            Search result with content and citations

        Raises:
            RuntimeError: If the circuit breaker is open or all retries
                are exhausted.
        """
        model_name = self.MODELS.get(model, self.MODELS["pro"])

        messages = [
            {
                "role": "system",
                "content": "You are a research assistant. Provide accurate, well-cited information.",
            },
            {
                "role": "user",
                "content": query,
            },
        ]

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "return_citations": return_citations,
        }
        if domain_filter:
            payload["search_domain_filter"] = domain_filter
        if recency_filter:
            payload["search_recency_filter"] = recency_filter

        start = time.monotonic()
        data = self._post_with_retry(payload)
        duration_ms = int((time.monotonic() - start) * 1000)
        if data is None:
            raise RuntimeError(f"Perplexity search failed for query: {query!r}")

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})

        citations = _parse_citations(data)

        self._track_cost(model_name, usage, duration_ms)

        return DeepQueryResult(
            title=query[:100],
            content=message.get("content", ""),
            url="",
            source="DeepQuery",
            citations=citations,
            metadata={
                "model": model_name,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "num_search_queries": usage.get("num_search_queries", 1),
            },
        )

    def literature_review(
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

        return self.search(
            query=query,
            model="deep_research",
            max_tokens=8000,
            temperature=0.3,
        )

    def verify_citation(
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

        result = self.search(query, model="pro")

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
        """Get information about available models."""
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _track_cost(self, model_name: str, usage: dict[str, Any], duration_ms: int) -> None:
        """Record cost via ExtendedReasoningCostTracker (best-effort).

        ``_calculate_cost`` keys Perplexity's per-search cost add-on off
        ``"perplexity" in model.lower()`` — model IDs like ``"sonar-pro"``
        don't match that, so record under the ``perplexity/<model>`` form.
        """
        try:
            from berb.metrics.reasoning_cost_tracker import get_cost_tracker

            tracker = get_cost_tracker()
            tracker.track(
                method="perplexity_search",
                phase=model_name,
                model=f"perplexity/{model_name}",
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                duration_ms=duration_ms,
                run_id=self._run_id,
                search_count=usage.get("num_search_queries", 1),
            )
        except Exception:  # noqa: BLE001
            logger.debug("Perplexity cost tracking failed (non-fatal)", exc_info=True)

    def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST to the chat completions endpoint with retry + circuit breaker."""
        if not _cb_should_allow():
            logger.warning("Perplexity circuit breaker open — skipping request")
            return None

        _rate_limiter.wait_sync()

        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(_MAX_RETRIES):
            try:
                req = urllib.request.Request(
                    self.BASE_URL, data=body, headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    _cb_on_success()
                    return data
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    if _cb_on_429():
                        return None  # breaker tripped
                    delay = min(2 ** (attempt + 1), _MAX_WAIT_SEC)
                    jitter = random.uniform(0, delay * 0.3)
                    wait = delay + jitter
                    logger.warning(
                        "Perplexity rate-limited (429). Waiting %.1fs (attempt %d/%d)...",
                        wait,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                logger.warning("Perplexity HTTP %d", exc.code)
                return None
            except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
                wait = min(2**attempt, _MAX_WAIT_SEC)
                jitter = random.uniform(0, wait * 0.2)
                logger.warning(
                    "Perplexity request failed (%s). Retry %d/%d in %.1fs...",
                    exc,
                    attempt + 1,
                    _MAX_RETRIES,
                    wait + jitter,
                )
                time.sleep(wait + jitter)

        logger.error("Perplexity request exhausted retries")
        return None


def _parse_citations(data: dict[str, Any]) -> list[dict[str, str]]:
    """Parse citations from a Perplexity response.

    Handles both the legacy top-level ``citations: [url, ...]`` shape and
    the newer ``search_results: [{title, url, date}, ...]`` shape.
    """
    search_results = data.get("search_results")
    if isinstance(search_results, list) and search_results:
        return [
            {
                "title": str(r.get("title", "")),
                "url": str(r.get("url", "")),
                "date": str(r.get("date", "")),
            }
            for r in search_results
            if isinstance(r, dict)
        ]

    citations = data.get("citations")
    if isinstance(citations, list):
        return [{"url": str(c)} for c in citations]

    return []


def create_deepquery_client(
    api_key: str | None = None,
    default_model: str = "pro",
) -> DeepQueryClient:
    """Create DeepQuery client from config or environment.

    Args:
        api_key: API key (or from PERPLEXITY_API_KEY env)
        default_model: Default model

    Returns:
        Configured DeepQueryClient
    """
    import os

    key = api_key or os.environ.get("PERPLEXITY_API_KEY", "")
    if not key:
        raise ValueError(
            "Perplexity API key required. Set PERPLEXITY_API_KEY env var or pass api_key."
        )

    return DeepQueryClient(api_key=key, default_model=default_model)


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
        "flagship": "grok-4.5",
        "reasoning": "grok-4.5",
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

        prompt = prompts.get(analysis_type, prompts["comprehensive"]).format(paper=paper_text)

        messages = [
            {
                "role": "system",
                "content": "You are an expert research analyst. Analyze papers thoroughly and objectively.",
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
                "content": "You are an expert research synthesizer. Identify patterns and generate insights across multiple papers.",
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
                "grok-4.5": {
                    "description": "Flagship/reasoning model with 2M context",
                    "context_window": "2M tokens",
                    "best_for": "Full paper analysis, cross-paper synthesis, complex reasoning, experiment design",
                    "speed": "Fastest",
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
