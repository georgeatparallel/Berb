"""Stages 3-6: Search strategy, literature collection, screening, and knowledge extraction."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.literature.paper_mill import load_corpus as _load_tortured_phrase_corpus
from berb.literature.paper_mill import screen_text as _screen_tortured_phrases
from berb.literature.retraction import (
    RetractionRecord,
    resolve_retraction,
    screen_bibliography,
)
from berb.llm.client import LLMClient
from berb.pipeline._helpers import (
    StageResult,
    _build_fallback_queries,
    _chat_with_prompt,
    _extract_topic_keywords,
    _extract_yaml_block,
    _get_evolution_overlay,
    _parse_jsonl_rows,
    _read_prior_artifact,
    _safe_filename,
    _safe_json_loads,
    _utcnow_iso,
    _write_jsonl,
)
from berb.pipeline.contracts import StageContract
from berb.pipeline.registry import register_stage
from berb.pipeline.stages import Stage, StageStatus
from berb.prompts import PromptManager
from berb.utils.sanitize import wrap_untrusted

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _expand_search_queries(queries: list[str], topic: str) -> list[str]:
    """Expand search queries for broader literature coverage.

    Generates additional queries by extracting key phrases from the topic
    and creating focused sub-queries. This ensures we find papers even when
    the original queries are too narrow or specific for arXiv.
    """
    expanded = list(queries)  # keep originals
    seen = {q.lower().strip() for q in queries}

    # Extract key phrases from topic by splitting on common delimiters
    # e.g. "Comparing A, B, and C on X with Y" → ["A", "B", "C", "X", "Y"]
    topic_words = topic.split()

    # Generate shorter, broader queries from the topic
    if len(topic_words) > 5:
        # First 5 words as a broader query
        broad = " ".join(topic_words[:5])
        if broad.lower().strip() not in seen:
            expanded.append(broad)
            seen.add(broad.lower().strip())

        # Last 5 words as another perspective
        tail = " ".join(topic_words[-5:])
        if tail.lower().strip() not in seen:
            expanded.append(tail)
            seen.add(tail.lower().strip())

    # Add "survey" and "benchmark" variants of the topic
    for suffix in ("survey", "benchmark", "comparison"):
        # Take first 4 content words + suffix
        short_topic = " ".join(topic_words[:4])
        variant = f"{short_topic} {suffix}"
        if variant.lower().strip() not in seen:
            expanded.append(variant)
            seen.add(variant.lower().strip())

    return expanded


# P2-04: ScholarPeer's literature-expansion agent does k=3 gap-driven
# search rounds; Fig. 5 shows quality declining past k=3 as tangential
# papers dilute the context window. Berb's version seeds each round from
# the previous round's highest-cited new finds (no NLP/gap-analysis
# available — using a real paper's own title as the next query is a
# standard "find related work" technique, not a fabricated heuristic).
_MAX_EXPANSION_ROUNDS = 3
_MIN_NEW_CANDIDATES_TO_CONTINUE = 3


def _seed_expansion_queries(
    round_candidates: list[dict[str, Any]], seen_queries: set[str], *, max_new: int = 3
) -> list[str]:
    """Seed the next search round from titles of this round's highest-cited
    new candidates, skipping titles already used as a query."""
    ranked = sorted(round_candidates, key=lambda c: c.get("citation_count", 0) or 0, reverse=True)
    new_queries: list[str] = []
    for c in ranked:
        title = str(c.get("title", "")).strip()
        if not title or title.lower() in seen_queries:
            continue
        new_queries.append(title)
        seen_queries.add(title.lower())
        if len(new_queries) >= max_new:
            break
    return new_queries


# ---------------------------------------------------------------------------
# Stage executors
# ---------------------------------------------------------------------------


@register_stage(
    stage=Stage.SEARCH_STRATEGY,
    depends_on=frozenset({Stage.PROBLEM_DECOMPOSE}),
    contract=StageContract(
        stage=Stage.SEARCH_STRATEGY,
        input_files=("problem_tree.md",),
        output_files=("search_plan.yaml", "sources.json", "queries.json"),
        dod=">=2 search strategies defined with verified data sources",
        error_code="E03_STRATEGY_BAD",
    ),
)
def _execute_search_strategy(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    problem_tree = _read_prior_artifact(run_dir, "problem_tree.md") or ""
    topic = config.research.topic
    plan: dict[str, Any] | None = None
    sources: list[dict[str, Any]] | None = None
    if llm is not None:
        _pm = prompts or PromptManager()
        _overlay = _get_evolution_overlay(run_dir, "search_strategy")
        sp = _pm.for_stage(
            "search_strategy",
            evolution_overlay=_overlay,
            topic=topic,
            problem_tree=problem_tree,
        )
        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=sp.max_tokens,
        )
        payload = _safe_json_loads(resp.content, {})
        if isinstance(payload, dict):
            yaml_text = str(payload.get("search_plan_yaml", "")).strip()
            if yaml_text:
                try:
                    parsed = yaml.safe_load(_extract_yaml_block(yaml_text))
                except yaml.YAMLError:
                    parsed = None
                if isinstance(parsed, dict):
                    plan = parsed
            src = payload.get("sources", [])
            if isinstance(src, list):
                sources = [item for item in src if isinstance(item, dict)]
    if plan is None:
        # Build smart fallback queries by extracting key terms from topic
        # instead of using the raw (often very long) topic string.
        _fallback_queries = _build_fallback_queries(topic)
        plan = {
            "topic": topic,
            "generated": _utcnow_iso(),
            "search_strategies": [
                {
                    "name": "keyword_core",
                    "queries": _fallback_queries[:5],
                    "sources": ["arxiv", "semantic_scholar", "openreview"],
                    "max_results_per_query": 60,
                },
                {
                    "name": "backward_forward_citation",
                    "queries": _fallback_queries[5:10] or _fallback_queries[:3],
                    "sources": ["semantic_scholar", "google_scholar"],
                    "depth": 1,
                },
            ],
            "filters": {
                "min_year": 2020,
                "language": ["en"],
                "peer_review_preferred": True,
            },
            "deduplication": {"method": "title_doi_hash", "fuzzy_threshold": 0.9},
        }
    if not sources:
        sources = [
            {
                "id": "arxiv",
                "name": "arXiv",
                "type": "api",
                "url": "https://export.arxiv.org/api/query",
                "status": "available",
                "query": topic,
                "verified_at": _utcnow_iso(),
            },
            {
                "id": "semantic_scholar",
                "name": "Semantic Scholar",
                "type": "api",
                "url": "https://api.semanticscholar.org/graph/v1/paper/search",
                "status": "available",
                "query": topic,
                "verified_at": _utcnow_iso(),
            },
        ]
    if config.openclaw_bridge.use_web_fetch:
        for src in sources:
            try:
                response = adapters.web_fetch.fetch(str(src.get("url", "")))
                src["status"] = (
                    "verified" if response.status_code in (200, 301, 302, 405) else "unreachable"
                )
                src["http_status"] = response.status_code
            except Exception:  # noqa: BLE001
                src["status"] = "unknown"
    (stage_dir / "search_plan.yaml").write_text(
        yaml.dump(plan, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    (stage_dir / "sources.json").write_text(
        json.dumps(
            {"sources": sources, "count": len(sources), "generated": _utcnow_iso()},
            indent=2,
        ),
        encoding="utf-8",
    )

    # F1.5: Extract queries from plan for Stage 4 real literature search
    queries_list: list[str] = []
    year_min = 2020
    if isinstance(plan, dict):
        strategies = plan.get("search_strategies", [])
        if isinstance(strategies, list):
            for strat in strategies:
                if isinstance(strat, dict):
                    qs = strat.get("queries", [])
                    if isinstance(qs, list):
                        queries_list.extend(str(q) for q in qs if q)
        filters = plan.get("filters", {})
        if isinstance(filters, dict) and filters.get("min_year"):
            try:
                year_min = int(filters["min_year"])
            except (ValueError, TypeError):
                pass

    # --- Sanitize queries: shorten overly long queries ---
    # LLMs often produce the full topic title as a query, which is too long for
    # arXiv and Semantic Scholar (they work best with 3-8 keyword queries).
    _stop = {
        "a",
        "an",
        "the",
        "of",
        "for",
        "in",
        "on",
        "and",
        "or",
        "with",
        "to",
        "by",
        "from",
        "its",
        "is",
        "are",
        "was",
        "be",
        "as",
        "at",
        "via",
        "using",
        "based",
        "study",
        "analysis",
        "empirical",
        "towards",
        "toward",
        "into",
        "exploring",
        "comparison",
        "tasks",
        "effectiveness",
        "investigation",
        "comprehensive",
        "novel",
    }

    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from text, removing stop words."""
        return [
            w for w in re.split(r"[^a-zA-Z0-9]+", text) if w.lower() not in _stop and len(w) > 1
        ]

    _MAX_QUERY_LEN = 60  # characters — beyond this, shorten to keywords
    _SEARCH_SUFFIXES = ["benchmark", "survey", "seminal", "state of the art"]

    def _shorten_query(q: str, max_kw: int = 6) -> str:
        """Shorten a query to *max_kw* keywords, preserving any trailing suffix."""
        q_stripped = q.strip()
        # Check if query ends with a known search suffix
        suffix = ""
        q_core = q_stripped
        for sfx in _SEARCH_SUFFIXES:
            if q_stripped.lower().endswith(sfx):
                suffix = sfx
                q_core = q_stripped[: -len(sfx)].strip()
                break
        # Extract keywords from the core part
        kws = _extract_keywords(q_core)
        shortened = " ".join(kws[:max_kw])
        if suffix:
            shortened = f"{shortened} {suffix}"
        return shortened

    if queries_list:
        sanitized: list[str] = []
        for q in queries_list:
            if len(q) > _MAX_QUERY_LEN:
                shortened = _shorten_query(q)
                if shortened.strip():
                    sanitized.append(shortened)
            else:
                sanitized.append(q)
        queries_list = sanitized

    if not queries_list:
        # Build diverse keyword queries from the topic
        _words = _extract_keywords(topic)
        kw_primary = " ".join(_words[:6])
        kw_short = " ".join(_words[:4])
        queries_list = [
            kw_primary,
            f"{kw_short} benchmark",
            f"{kw_short} survey",
        ]

    # Ensure minimum query diversity — if dedup leaves too few, add variants
    _all_kw = _extract_keywords(topic)
    _seen_q: set[str] = set()
    unique_queries: list[str] = []
    for q in queries_list:
        q_lower = q.strip().lower()
        if q_lower and q_lower not in _seen_q:
            _seen_q.add(q_lower)
            unique_queries.append(q.strip())
    # If we have fewer than 5 unique queries, generate supplemental keyword variants
    if len(unique_queries) < 5 and len(_all_kw) >= 3:
        supplements = [
            " ".join(_all_kw[:4]) + " survey",
            " ".join(_all_kw[:4]) + " benchmark",
            " ".join(_all_kw[1:5]),  # shifted window for diversity
            " ".join(_all_kw[:3]) + " comparison",
            " ".join(_all_kw[:3]) + " deep learning",
            " ".join(_all_kw[2:6]),  # another shifted window
        ]
        for s in supplements:
            s_lower = s.strip().lower()
            if s_lower not in _seen_q:
                _seen_q.add(s_lower)
                unique_queries.append(s.strip())
            if len(unique_queries) >= 8:
                break
    queries_list = unique_queries
    (stage_dir / "queries.json").write_text(
        json.dumps({"queries": queries_list, "year_min": year_min}, indent=2),
        encoding="utf-8",
    )
    return StageResult(
        stage=Stage.SEARCH_STRATEGY,
        status=StageStatus.DONE,
        artifacts=("search_plan.yaml", "sources.json", "queries.json"),
        evidence_refs=(
            "stage-03/search_plan.yaml",
            "stage-03/sources.json",
            "stage-03/queries.json",
        ),
    )


@register_stage(
    stage=Stage.LITERATURE_COLLECT,
    depends_on=frozenset({Stage.SEARCH_STRATEGY}),
    contract=StageContract(
        stage=Stage.LITERATURE_COLLECT,
        input_files=("search_plan.yaml",),
        output_files=("candidates.jsonl",),
        dod=">=N candidate papers collected from specified sources",
        error_code="E04_COLLECT_EMPTY",
        max_retries=2,
    ),
)
def _execute_literature_collect(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    """Stage 4: Collect literature — prefer real APIs, fallback to LLM."""
    topic = config.research.topic

    # Read queries.json from Stage 3 (F1.5 output)
    queries_text = _read_prior_artifact(run_dir, "queries.json")
    queries_data = _safe_json_loads(queries_text or "{}", {})
    queries: list[str] = queries_data.get("queries", [topic])
    year_min: int = queries_data.get("year_min", 2020)
    # P2-04: only an upper bound existed before (year_min) — this keeps the
    # pipeline from citing work published after its own experiments ran.
    year_max: int = queries_data.get("year_max", 0)

    # --- Try real API search first, k=3 gap-driven expansion rounds ---
    candidates: list[dict[str, Any]] = []
    bibtex_entries: list[str] = []
    real_search_succeeded = False
    _seen_titles: set[str] = set()
    _seen_queries: set[str] = {q.lower().strip() for q in queries}

    try:
        from berb.literature.search import (
            search_papers_multi_query,
        )

        _pplx = config.perplexity
        _round_queries = _expand_search_queries(queries, config.research.topic)
        for _round in range(_MAX_EXPANSION_ROUNDS):
            logger.info(
                "[literature] Round %d/%d: searching %d queries across OpenAlex → S2 → arXiv…",
                _round + 1,
                _MAX_EXPANSION_ROUNDS,
                len(_round_queries),
            )
            papers = search_papers_multi_query(
                _round_queries,
                limit_per_query=40,
                year_min=year_min,
                year_max=year_max,
                s2_api_key=config.llm.s2_api_key,
                perplexity_top_up=_pplx.enabled and _round == 0,
                perplexity_min_candidates=_pplx.literature_min_candidates,
                perplexity_min_failed_sources=_pplx.literature_min_failed_sources,
                perplexity_domain_filter=list(_pplx.domain_filter) or None,
                perplexity_recency_filter=_pplx.recency_filter or None,
                perplexity_api_key=os.environ.get(_pplx.api_key_env, ""),
            )
            _round_new: list[dict[str, Any]] = []
            if papers:
                real_search_succeeded = True
                src_counts: dict[str, int] = {}
                for p in papers:
                    title_key = p.title.strip().lower()
                    if title_key in _seen_titles:
                        continue
                    _seen_titles.add(title_key)
                    src_counts[p.source] = src_counts.get(p.source, 0) + 1
                    d = p.to_dict()
                    d["collected_at"] = _utcnow_iso()
                    candidates.append(d)
                    bibtex_entries.append(p.to_bibtex())
                    _round_new.append(d)
                src_str = ", ".join(f"{s}: {n}" for s, n in src_counts.items())
                logger.info(
                    "[literature] Round %d: %d new papers (%s)",
                    _round + 1,
                    len(_round_new),
                    src_str or "none",
                )
            if _round == _MAX_EXPANSION_ROUNDS - 1:
                break
            if len(_round_new) < _MIN_NEW_CANDIDATES_TO_CONTINUE:
                logger.info(
                    "[literature] Only %d new paper(s) this round — stopping "
                    "expansion early (diminishing returns).",
                    len(_round_new),
                )
                break
            _round_queries = _seed_expansion_queries(_round_new, _seen_queries)
            if not _round_queries:
                break
    except Exception:  # noqa: BLE001
        logger.warning(
            "[rate-limit] Literature search failed — falling back to LLM",
            exc_info=True,
        )

    # --- Ingest uploaded PDFs (tier 0 — always included) ---
    uploaded_paths: tuple[str, ...] = config.research.uploaded_file_paths
    if uploaded_paths:
        from berb.literature.pdf_ingestor import ingest_pdfs as _ingest_pdfs

        uploaded_path_objs = [Path(p) for p in uploaded_paths]
        logger.info(
            "Stage 4: Ingesting %d uploaded PDF(s)…",
            len(uploaded_path_objs),
        )
        uploaded_papers = _ingest_pdfs(uploaded_path_objs, llm=adapters.llm)
        if uploaded_papers:
            _existing_titles = {c.get("title", "").lower() for c in candidates}
            _added = 0
            for up in uploaded_papers:
                if up.get("title", "").lower() not in _existing_titles:
                    up["collected_at"] = _utcnow_iso()
                    candidates.append(up)
                    _existing_titles.add(up.get("title", "").lower())
                    _added += 1
            logger.info(
                "Stage 4: Added %d papers from %d uploaded PDF(s) (skipped %d duplicates)",
                _added,
                len(uploaded_path_objs),
                len(uploaded_papers) - _added,
            )

    # --- Inject foundational/seminal papers ---
    try:
        from berb.data import load_seminal_papers

        seminal = load_seminal_papers(topic)
        if seminal:
            _existing_titles = {c.get("title", "").lower() for c in candidates}
            _injected = 0
            for sp in seminal:
                if sp.get("title", "").lower() not in _existing_titles:
                    candidates.append(
                        {
                            "id": f"seminal-{sp.get('cite_key', '')}",
                            "title": sp.get("title", ""),
                            "source": "seminal_library",
                            "url": "",
                            "year": sp.get("year", 2020),
                            "abstract": f"Foundational paper on {', '.join(sp.get('keywords', [])[:3])}.",
                            "authors": [{"name": sp.get("authors", "")}],
                            "cite_key": sp.get("cite_key", ""),
                            "venue": sp.get("venue", ""),
                            "collected_at": _utcnow_iso(),
                        }
                    )
                    _injected += 1
            if _injected:
                logger.info("Stage 4: Injected %d seminal papers from seed library", _injected)
    except Exception:  # noqa: BLE001
        logger.debug("Seminal paper injection skipped", exc_info=True)

    # --- Fallback: LLM-generated candidates ---
    if not candidates and llm is not None:
        plan_text = _read_prior_artifact(run_dir, "search_plan.yaml") or ""
        _pm = prompts or PromptManager()
        _overlay = _get_evolution_overlay(run_dir, "literature_collect")
        sp = _pm.for_stage(
            "literature_collect",
            evolution_overlay=_overlay,
            topic=topic,
            plan_text=plan_text,
        )
        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=sp.max_tokens,
        )
        payload = _safe_json_loads(resp.content, {})
        if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
            candidates = [row for row in payload["candidates"] if isinstance(row, dict)]

    # --- Web search augmentation (Tavily/DDG + Google Scholar + Crawl4AI) ---
    web_context_parts: list[str] = []
    if config.web_search.enabled:
        try:
            from berb.web.agent import WebSearchAgent

            tavily_key = config.web_search.tavily_api_key or os.environ.get(
                config.web_search.tavily_api_key_env, ""
            )
            web_agent = WebSearchAgent(
                tavily_api_key=tavily_key,
                enable_scholar=config.web_search.enable_scholar,
                enable_crawling=config.web_search.enable_crawling,
                enable_pdf=config.web_search.enable_pdf_extraction,
                max_web_results=config.web_search.max_web_results,
                max_scholar_results=config.web_search.max_scholar_results,
                max_crawl_urls=config.web_search.max_crawl_urls,
            )
            web_result = web_agent.search_and_extract(
                topic,
                search_queries=queries,
            )

            # Convert Google Scholar papers into candidates
            for sp in web_result.scholar_papers:
                _existing_titles = {str(c.get("title", "")).lower().strip() for c in candidates}
                if sp.title.lower().strip() not in _existing_titles:
                    lit_paper = sp.to_literature_paper()
                    d = lit_paper.to_dict()
                    d["collected_at"] = _utcnow_iso()
                    candidates.append(d)
                    bibtex_entries.append(lit_paper.to_bibtex())

            # Save web search context for downstream stages
            web_context = web_result.to_context_string(max_length=20_000)
            if web_context.strip():
                (stage_dir / "web_context.md").write_text(web_context, encoding="utf-8")
                web_context_parts.append(web_context)

            # Save full web search metadata
            (stage_dir / "web_search_result.json").write_text(
                json.dumps(web_result.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )

            logger.info(
                "[web-search] Added %d scholar papers, %d web results, %d crawled pages",
                len(web_result.scholar_papers),
                len(web_result.web_results),
                len(web_result.crawled_pages),
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "[web-search] Web search augmentation failed — continuing with academic APIs only",
                exc_info=True,
            )

    # --- Ultimate fallback: placeholder data ---
    # BUG-L2: Do NOT overwrite real_search_succeeded here — it was already
    # set correctly in the search block above. Overwriting would mislabel
    # LLM-hallucinated or seminal papers as "real search" results.
    if not candidates:
        logger.warning("Stage 4: All literature searches failed — using placeholder papers")
        candidates = [
            {
                "id": f"candidate-{idx + 1}",
                "title": f"[Placeholder] Study {idx + 1} on {topic}",
                "source": "arxiv" if idx % 2 == 0 else "semantic_scholar",
                "url": f"https://example.org/{_safe_filename(topic.lower())}/{idx + 1}",
                "year": 2024,
                "abstract": f"This candidate investigates {topic} and reports preliminary findings.",
                "collected_at": _utcnow_iso(),
                "is_placeholder": True,
            }
            for idx in range(max(20, config.research.daily_paper_count or 20))
        ]

    # Write candidates
    out = stage_dir / "candidates.jsonl"
    _write_jsonl(out, candidates)

    # BUG-50 fix: Generate BibTeX from candidates when real search failed
    # (LLM/placeholder fallback paths don't populate bibtex_entries)
    if not bibtex_entries and candidates:
        for c in candidates:
            if c.get("is_placeholder"):
                continue
            _ck = c.get("cite_key", "")
            if not _ck:
                # Derive cite_key from first author surname + year
                _authors = c.get("authors", [])
                _surname = "unknown"
                if isinstance(_authors, list) and _authors:
                    _a0 = (
                        _authors[0]
                        if isinstance(_authors[0], str)
                        else (_authors[0].get("name", "") if isinstance(_authors[0], dict) else "")
                    )
                    _surname = _a0.split()[-1].lower() if _a0.strip() else "unknown"
                _yr = c.get("year", 2024)
                _title_word = "".join(
                    w[0] for w in str(c.get("title", "study")).split()[:3]
                ).lower()
                _ck = f"{_surname}{_yr}{_title_word}"
            _title = c.get("title", "Untitled")
            _year = c.get("year", 2024)
            _author_str = ""
            _raw_authors = c.get("authors", [])
            if isinstance(_raw_authors, list):
                _names = []
                for _a in _raw_authors:
                    if isinstance(_a, str):
                        _names.append(_a)
                    elif isinstance(_a, dict):
                        _names.append(_a.get("name", ""))
                _author_str = " and ".join(n for n in _names if n)
            bibtex_entries.append(
                f"@article{{{_ck},\n"
                f"  title={{{_title}}},\n"
                f"  author={{{_author_str or 'Unknown'}}},\n"
                f"  year={{{_year}}},\n"
                f"  url={{{c.get('url', '')}}},\n"
                f"}}"
            )
        logger.info(
            "Stage 4: Generated %d BibTeX entries from candidates (fallback)",
            len(bibtex_entries),
        )

    # Write references.bib (F2.4)
    artifacts = ["candidates.jsonl"]
    if web_context_parts:
        artifacts.append("web_context.md")
    if (stage_dir / "web_search_result.json").exists():
        artifacts.append("web_search_result.json")
    if bibtex_entries:
        bib_content = "\n\n".join(bibtex_entries) + "\n"
        (stage_dir / "references.bib").write_text(bib_content, encoding="utf-8")
        artifacts.append("references.bib")
        logger.info("Stage 4: Wrote %d BibTeX entries to references.bib", len(bibtex_entries))

    # Write search metadata
    (stage_dir / "search_meta.json").write_text(
        json.dumps(
            {
                "real_search": real_search_succeeded,
                "queries_used": queries,
                "year_min": year_min,
                "total_candidates": len(candidates),
                "bibtex_entries": len(bibtex_entries),
                "ts": _utcnow_iso(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    artifacts.append("search_meta.json")

    return StageResult(
        stage=Stage.LITERATURE_COLLECT,
        status=StageStatus.DONE,
        artifacts=tuple(artifacts),
        evidence_refs=tuple(f"stage-04/{a}" for a in artifacts),
    )


@register_stage(
    stage=Stage.LITERATURE_SCREEN,
    depends_on=frozenset({Stage.LITERATURE_COLLECT}),
    contract=StageContract(
        stage=Stage.LITERATURE_SCREEN,
        input_files=("candidates.jsonl",),
        output_files=("shortlist.jsonl",),
        dod="Relevance + quality dual screening completed and approved",
        error_code="E05_GATE_REJECT",
        max_retries=0,
    ),
)
def _execute_literature_screen(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    candidates_text = _read_prior_artifact(run_dir, "candidates.jsonl") or ""

    # P0-04: stage 4 falls back to letting the LLM invent the entire
    # candidate corpus from parametric memory when every search source
    # fails, and records that in search_meta.json — but nothing downstream
    # checked the flag, so a fabricated literature corpus proceeded to
    # publication indistinguishably from a real one. Screening the corpus
    # is meaningless if the corpus itself doesn't exist; fail here rather
    # than silently accept it, and roll back to LITERATURE_COLLECT
    # (stages.py GATE_ROLLBACK) so a retry can hit real search sources.
    _search_meta = _safe_json_loads(_read_prior_artifact(run_dir, "search_meta.json") or "", {})
    if isinstance(_search_meta, dict) and _search_meta.get("real_search") is False:
        return StageResult(
            stage=Stage.LITERATURE_SCREEN,
            status=StageStatus.FAILED,
            artifacts=(),
            evidence_refs=(),
            error=(
                "E05_GATE_REJECT: literature search failed for all sources at "
                "stage 4 — the candidate corpus was LLM-generated from "
                "parametric memory, not retrieved. Refusing to screen a "
                "fabricated corpus."
            ),
        )

    # --- P1-1: keyword relevance pre-filter ---
    # Before LLM screening, drop papers whose title+abstract share no keywords
    # with the research topic.  This catches cross-domain noise cheaply.
    topic_keywords = _extract_topic_keywords(config.research.topic, config.research.domains)
    filtered_rows: list[dict[str, Any]] = []
    dropped_count = 0
    for raw_line in candidates_text.strip().splitlines():
        row = _safe_json_loads(raw_line, {})
        if not isinstance(row, dict):
            continue
        title = str(row.get("title", "")).lower()
        abstract = str(row.get("abstract", "")).lower()
        text_blob = f"{title} {abstract}"
        overlap = sum(1 for kw in topic_keywords if kw in text_blob)
        # T2.2: Relaxed from ≥2 to ≥1 keyword hit — previous threshold was
        # too aggressive (94% rejection rate).  Single-keyword matches are
        # still screened by the LLM in the next step.
        if overlap >= 1:
            row["keyword_overlap"] = overlap
            filtered_rows.append(row)
        else:
            dropped_count += 1
    # If pre-filter dropped everything, fall back to original (safety valve)
    if not filtered_rows:
        filtered_rows = _parse_jsonl_rows(candidates_text)
    # Rebuild candidates_text from filtered rows
    candidates_text = "\n".join(json.dumps(r, ensure_ascii=False) for r in filtered_rows)
    logger.info(
        "Domain pre-filter: kept %d, dropped %d (keywords: %s)",
        len(filtered_rows),
        dropped_count,
        topic_keywords[:8],
    )

    shortlist: list[dict[str, Any]] = []
    if llm is not None:
        _pm = prompts or PromptManager()
        _overlay = _get_evolution_overlay(run_dir, "literature_screen")
        sp = _pm.for_stage(
            "literature_screen",
            evolution_overlay=_overlay,
            topic=config.research.topic,
            domains=(", ".join(config.research.domains) if config.research.domains else "general"),
            quality_threshold=config.research.quality_threshold,
            candidates_text=wrap_untrusted(candidates_text, "candidate paper metadata"),
        )
        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=sp.max_tokens,
        )
        payload = _safe_json_loads(resp.content, {})
        if isinstance(payload, dict) and isinstance(payload.get("shortlist"), list):
            shortlist = [row for row in payload["shortlist"] if isinstance(row, dict)]
    # T2.2: Ensure minimum shortlist size of 15 for adequate related work
    _MIN_SHORTLIST = 15
    if not shortlist:
        rows = (
            filtered_rows[:_MIN_SHORTLIST]
            if filtered_rows
            else _parse_jsonl_rows(candidates_text)[:_MIN_SHORTLIST]
        )
        for idx, item in enumerate(rows):
            item["relevance_score"] = round(0.75 - idx * 0.02, 3)
            item["quality_score"] = round(0.72 - idx * 0.015, 3)
            item["keep_reason"] = "Template screened entry"
            shortlist.append(item)
    elif len(shortlist) < _MIN_SHORTLIST:
        # T2.2: LLM returned too few — supplement from filtered candidates
        existing_titles = {str(s.get("title", "")).lower().strip() for s in shortlist}
        for row in filtered_rows:
            if len(shortlist) >= _MIN_SHORTLIST:
                break
            title_lower = str(row.get("title", "")).lower().strip()
            if title_lower and title_lower not in existing_titles:
                row.setdefault("relevance_score", 0.5)
                row.setdefault("quality_score", 0.5)
                row.setdefault("keep_reason", "Supplemented to meet minimum shortlist")
                shortlist.append(row)
                existing_titles.add(title_lower)
        logger.info(
            "Stage 5: Supplemented shortlist to %d papers (minimum: %d)",
            len(shortlist),
            _MIN_SHORTLIST,
        )
    out = stage_dir / "shortlist.jsonl"
    _write_jsonl(out, shortlist)

    # tasks/ars_integration_plan.md W2: advisory retraction / expression-of-
    # concern screening. Only rows carrying a DOI trigger a lookup — most
    # arXiv-only candidates have none, and resolve_retraction short-circuits
    # to UNKNOWN with zero network calls when the DOI is empty. Advisory
    # only: never fails the stage, matching plan §5's stage-5 wiring.
    artifacts = ["shortlist.jsonl"]
    evidence_refs = ["stage-05/shortlist.jsonl"]
    retraction_records: dict[str, RetractionRecord] = {}
    for idx, row in enumerate(shortlist):
        doi = str(row.get("doi", "")).strip()
        if not doi:
            continue
        locator = str(row.get("cite_key") or row.get("paper_id") or f"shortlist:{idx}")
        try:
            retraction_records[locator] = resolve_retraction(locator, doi)
        except Exception:  # noqa: BLE001 - advisory check must never fail the stage
            logger.debug("Retraction lookup failed for %s", locator, exc_info=True)
    if retraction_records:
        retraction_findings = screen_bibliography(retraction_records)
        if retraction_findings:
            (stage_dir / "retraction_findings.json").write_text(
                json.dumps([f.to_dict() for f in retraction_findings], indent=2),
                encoding="utf-8",
            )
            artifacts.append("retraction_findings.json")
            evidence_refs.append("stage-05/retraction_findings.json")
            for finding in retraction_findings:
                logger.warning("[retraction] %s: %s", finding.locator, finding.message)

    # tasks/ars_integration_plan.md W4: advisory tortured-phrase risk
    # screening on each shortlisted candidate's title+abstract. A hit is a
    # risk MARKER, never an authorship judgment — Severity.ADVISORY means
    # this never gates below strict mode. Corpus loaded once per stage
    # call, not per-row.
    try:
        _phrase_corpus = _load_tortured_phrase_corpus()
    except Exception:  # noqa: BLE001 - advisory check must never fail the stage
        logger.debug("Could not load tortured-phrase corpus", exc_info=True)
        _phrase_corpus = None

    if _phrase_corpus is not None and _phrase_corpus.size:
        paper_mill_findings: list[Any] = []
        for idx, row in enumerate(shortlist):
            locator = str(row.get("cite_key") or row.get("paper_id") or f"shortlist:{idx}")
            text_blob = f"{row.get('title', '')} {row.get('abstract', '')}"
            try:
                paper_mill_findings.extend(
                    _screen_tortured_phrases(text_blob, _phrase_corpus, locator=locator)
                )
            except Exception:  # noqa: BLE001 - advisory check must never fail the stage
                logger.debug("Paper-mill screening failed for %s", locator, exc_info=True)
        if paper_mill_findings:
            (stage_dir / "paper_mill_findings.json").write_text(
                json.dumps([f.to_dict() for f in paper_mill_findings], indent=2),
                encoding="utf-8",
            )
            artifacts.append("paper_mill_findings.json")
            evidence_refs.append("stage-05/paper_mill_findings.json")
            for finding in paper_mill_findings:
                logger.warning("[paper-mill] %s: %s", finding.locator, finding.message)

    return StageResult(
        stage=Stage.LITERATURE_SCREEN,
        status=StageStatus.DONE,
        artifacts=tuple(artifacts),
        evidence_refs=tuple(evidence_refs),
    )


@register_stage(
    stage=Stage.KNOWLEDGE_EXTRACT,
    depends_on=frozenset({Stage.LITERATURE_SCREEN}),
    contract=StageContract(
        stage=Stage.KNOWLEDGE_EXTRACT,
        input_files=("shortlist.jsonl",),
        output_files=("cards/",),
        dod="Structured knowledge card per shortlisted paper",
        error_code="E06_EXTRACT_FAIL",
    ),
)
def _execute_knowledge_extract(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    """Extract knowledge cards with batching for efficiency.

    P0 2026-04-06: Added batching (5 papers/batch) and fast model fallback
    to prevent timeouts on large shortlists.
    """
    import json

    shortlist_text = _read_prior_artifact(run_dir, "shortlist.jsonl") or ""

    # Parse papers into individual rows
    rows = _parse_jsonl_rows(shortlist_text)
    if not rows:
        logger.warning("Stage 6: No papers in shortlist, using template cards")
        rows = []

    # Get web context
    web_context = _read_prior_artifact(run_dir, "web_context.md") or ""

    cards_dir = stage_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    all_cards: list[dict[str, Any]] = []

    # P0 2026-04-06: Process in batches of 5 with fast model
    BATCH_SIZE = 5
    FAST_MODEL = "qwen/qwen3.5-flash"  # 5x faster than DeepSeek V3.2

    if llm is not None:
        _pm = prompts or PromptManager()
        _overlay = _get_evolution_overlay(run_dir, "knowledge_extract")

        # Try to use fast model by creating a temporary config.
        # FAST_MODEL is an OpenRouter-catalog model ID ("qwen/..."); it only
        # resolves against OpenRouter's own routing. Sending it to a direct
        # OpenAI/DeepSeek/etc. endpoint 404s, so only switch when the
        # configured endpoint actually is OpenRouter — otherwise keep using
        # the original llm client/model unchanged.
        fast_llm = llm
        if "openrouter.ai" in (llm.config.base_url or ""):
            try:
                from berb.llm.client import LLMClient, LLMConfig

                fast_config = LLMConfig(
                    provider_name="openrouter",
                    base_url=llm.config.base_url,
                    api_key=llm.config.api_key,
                    primary_model=FAST_MODEL,
                    fallback_providers=llm.config.fallback_providers or [],
                )
                fast_llm = LLMClient(fast_config)
                logger.info("Stage 6: Using fast model %s for batch processing", FAST_MODEL)
            except Exception as e:
                logger.warning("Stage 6: Could not switch to fast model, using default: %s", e)
                fast_llm = llm
        else:
            logger.debug(
                "Stage 6: Non-OpenRouter endpoint (%s), skipping fast-model switch",
                llm.config.base_url,
            )

        # Process papers in batches
        for batch_idx in range(0, len(rows), BATCH_SIZE):
            batch_rows = rows[batch_idx : batch_idx + BATCH_SIZE]
            batch_num = batch_idx // BATCH_SIZE + 1
            total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE

            logger.info(
                "Stage 6: Processing batch %d/%d (%d papers)",
                batch_num,
                total_batches,
                len(batch_rows),
            )

            # Format batch as JSONL
            batch_jsonl = "\n".join(json.dumps(row, ensure_ascii=False) for row in batch_rows)

            # Add web context only to first batch
            batch_shortlist = batch_jsonl
            if batch_idx == 0 and web_context:
                batch_shortlist = (
                    batch_shortlist + "\n\n--- Web Search Context ---\n" + web_context[:2_000]
                )

            try:
                sp = _pm.for_stage(
                    "knowledge_extract",
                    evolution_overlay=_overlay,
                    shortlist=batch_shortlist,
                )
                resp = _chat_with_prompt(
                    fast_llm,
                    sp.system,
                    sp.user,
                    json_mode=sp.json_mode,
                    max_tokens=sp.max_tokens,
                    call_timeout_sec=120,  # Shorter timeout per batch
                )
                payload = _safe_json_loads(resp.content, {})
                if isinstance(payload, dict) and isinstance(payload.get("cards"), list):
                    batch_cards = [item for item in payload["cards"] if isinstance(item, dict)]
                    all_cards.extend(batch_cards)
                    logger.info(
                        "Stage 6: Batch %d extracted %d cards",
                        batch_num,
                        len(batch_cards),
                    )
                else:
                    logger.warning("Stage 6: Batch %d returned no cards", batch_num)
            except Exception as e:
                logger.error("Stage 6: Batch %d failed: %s", batch_num, e)
                # Continue with next batch instead of failing entirely
                continue

    # Deduplicate cards by title
    seen_titles = set()
    cards = []
    for card in all_cards:
        title = str(card.get("title", "")).lower().strip()
        if title and title not in seen_titles:
            cards.append(card)
            seen_titles.add(title)

    logger.info("Stage 6: Total unique cards extracted: %d", len(cards))

    # If no cards extracted, use template fallback
    if not cards:
        # Fallback: generate template cards for all papers in shortlist
        for idx, paper in enumerate(rows):
            title = str(paper.get("title", f"Paper {idx + 1}"))
            cards.append(
                {
                    "card_id": f"card-{idx + 1}",
                    "title": title,
                    "problem": f"How to improve {config.research.topic}",
                    "method": "Template method summary",
                    "data": "Template dataset",
                    "metrics": "Template metric",
                    "findings": "Template key finding",
                    "limitations": "Template limitation",
                    "citation": str(paper.get("url", "")),
                    "cite_key": str(paper.get("cite_key", "")),
                }
            )
    for idx, card in enumerate(cards):
        card_id = _safe_filename(str(card.get("card_id", f"card-{idx + 1}")))
        parts = [f"# {card.get('title', card_id)}", ""]
        for key in (
            "cite_key",
            "problem",
            "method",
            "data",
            "metrics",
            "findings",
            "limitations",
            "citation",
        ):
            parts.append(f"## {key.title()}")
            parts.append(str(card.get(key, "")))
            parts.append("")
        (cards_dir / f"{card_id}.md").write_text("\n".join(parts), encoding="utf-8")
    return StageResult(
        stage=Stage.KNOWLEDGE_EXTRACT,
        status=StageStatus.DONE,
        artifacts=("cards/",),
        evidence_refs=("stage-06/cards/",),
    )
