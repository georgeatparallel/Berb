"""Perplexity Sonar as a literature search top-up source.

Unlike OpenAlex/Semantic Scholar/arXiv, Perplexity doesn't expose a
structured papers-metadata endpoint — it returns a natural-language answer
grounded by live web search. To get ``Paper``-shaped results we ask it to
answer in a constrained JSON shape and only trust papers it actually cites.

This is deliberately NOT part of the default per-query cascade in
``search.py`` — it's a paid top-up called only when the free academic APIs
(OpenAlex, Semantic Scholar, arXiv) under-deliver or fail outright.

Public API
----------
- ``search_perplexity(query, limit, year_min, domain_filter, recency_filter)``
  → ``list[Paper]``
"""

from __future__ import annotations

import json
import logging
import os

from berb.literature.models import Author, Paper

logger = logging.getLogger(__name__)

# Scholarly domains — keeps top-up results academic rather than general web.
DEFAULT_DOMAIN_FILTER = [
    "arxiv.org",
    "openreview.net",
    "aclanthology.org",
    "openalex.org",
    "semanticscholar.org",
    "nature.com",
    "science.org",
    "*.edu",
]

_SEARCH_PROMPT_TEMPLATE = """Search for real, existing academic papers on: {query}

Return ONLY a JSON object in this exact shape, nothing else:
{{"papers": [{{"title": "...", "authors": ["Last, First", ...], "year": 2024, \
"venue": "...", "url": "...", "abstract": "one or two sentence summary"}}]}}

Rules:
- Include up to {limit} papers.
- Only include papers you found through search and can cite — never invent one.
- If you found fewer than {limit} real papers, return fewer entries.
- "year" must be an integer publication year.
- Do not include any text outside the JSON object."""


def _extract_json(text: str) -> dict | None:
    """Parse a JSON object out of LLM output, tolerating markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        result = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None
    return result if isinstance(result, dict) else None


def _parse_year(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def search_perplexity(
    query: str,
    *,
    limit: int = 20,
    year_min: int = 0,
    domain_filter: list[str] | None = None,
    recency_filter: str | None = None,
    api_key: str = "",
) -> list[Paper]:
    """Search for papers via Perplexity Sonar, grounded by live web search.

    Parameters
    ----------
    query:
        Free-text search query.
    limit:
        Maximum number of papers requested.
    year_min:
        If >0, mentioned in the search context (Perplexity has no hard
        year filter param for chat completions; recency_filter is the
        closest lever).
    domain_filter:
        Domains to restrict search to. Defaults to ``DEFAULT_DOMAIN_FILTER``.
    recency_filter:
        One of ``"day"``, ``"week"``, ``"month"``, ``"year"``.
    api_key:
        Perplexity API key. Falls back to ``PERPLEXITY_API_KEY`` env var.

    Returns
    -------
    list[Paper]
        Parsed papers, empty list if the API key is missing, the request
        fails, or the response isn't parseable JSON.
    """
    key = api_key or os.environ.get("PERPLEXITY_API_KEY", "")
    if not key:
        logger.debug("Perplexity search skipped — no PERPLEXITY_API_KEY set")
        return []

    from berb.llm.deep_query_client import DeepQueryClient

    client = DeepQueryClient(api_key=key)

    prompt_query = query
    if year_min > 0:
        prompt_query = f"{query} (published {year_min} or later)"

    prompt = _SEARCH_PROMPT_TEMPLATE.format(query=prompt_query, limit=limit)

    try:
        result = client.search(
            prompt,
            model="pro",
            max_tokens=4000,
            temperature=0.1,
            domain_filter=domain_filter or DEFAULT_DOMAIN_FILTER,
            recency_filter=recency_filter,
        )
    except RuntimeError as exc:
        logger.warning("Perplexity search failed for %r: %s", query, exc)
        return []

    payload = _extract_json(result.content)
    if not payload or not isinstance(payload.get("papers"), list):
        logger.warning("Perplexity search returned unparseable content for %r", query)
        return []

    papers: list[Paper] = []
    for item in payload["papers"]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        authors = tuple(
            Author(name=str(a).strip())
            for a in item.get("authors", [])
            if str(a).strip()
        )
        papers.append(
            Paper(
                paper_id=f"perplexity-{abs(hash((title, item.get('url', '')))):x}",
                title=title,
                authors=authors,
                year=_parse_year(item.get("year", 0)),
                abstract=str(item.get("abstract", "")).strip(),
                venue=str(item.get("venue", "")).strip(),
                url=str(item.get("url", "")).strip(),
                source="perplexity",
            )
        )

    logger.info("Perplexity top-up returned %d papers for %r", len(papers), query)
    return papers
