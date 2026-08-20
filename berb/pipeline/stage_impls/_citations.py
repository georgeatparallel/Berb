"""Citation loading/resolution helpers and Stage 23: citation verify."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml  # noqa: F401 — available for downstream use

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.llm.client import LLMClient
from berb.pipeline._domain import _detect_domain  # noqa: F401
from berb.pipeline._helpers import (
    StageResult,
    _collect_experiment_results,  # noqa: F401
    _read_prior_artifact,
    _safe_json_loads,
    _topic_constraint_block,  # noqa: F401
    )
from berb.pipeline.contracts import StageContract
from berb.pipeline.registry import register_stage
from berb.pipeline.stages import Stage, StageStatus
from berb.prompts import PromptManager

logger = logging.getLogger(__name__)

# Minimum title-similarity between search result and expected title/query
# for a result to be accepted.  Prevents "Jokowi and the New Developmentalism"
# from replacing "Deep Residual Learning for Image Recognition".
_CITATION_RESOLVE_MIN_SIMILARITY = 0.30


def _load_seminal_papers_by_key() -> dict[str, dict]:
    """Load seminal_papers.yaml and index by cite_key.

    Returns dict like::

        {"he2016deep": {"title": "Deep Residual Learning...", "authors": "He et al.", ...}, ...}

    Returns empty dict on any failure (missing file, bad YAML, etc.).
    """
    try:
        from berb.data import _load_all as _load_seminal_all

        all_papers = _load_seminal_all()
        return {p["cite_key"]: p for p in all_papers if "cite_key" in p}
    except Exception:  # noqa: BLE001
        return {}


def _seminal_to_bibtex(paper: dict, cite_key: str) -> str:
    """Convert a seminal_papers.yaml entry dict to a BibTeX string."""
    title = paper.get("title", "Unknown")
    authors = paper.get("authors", "Unknown")
    year = paper.get("year", "")
    venue = paper.get("venue", "")

    # Decide entry type
    venue_lower = (venue or "").lower()
    is_conf = any(
        kw in venue_lower
        for kw in (
            "neurips",
            "nips",
            "icml",
            "iclr",
            "cvpr",
            "eccv",
            "iccv",
            "aaai",
            "acl",
            "emnlp",
            "naacl",
            "sigir",
            "kdd",
            "www",
            "ijcai",
            "conference",
            "proc",
            "workshop",
        )
    )
    if is_conf:
        return (
            f"@inproceedings{{{cite_key},\n"
            f"  title = {{{title}}},\n"
            f"  author = {{{authors}}},\n"
            f"  year = {{{year}}},\n"
            f"  booktitle = {{{venue}}},\n"
            f"}}"
        )
    return (
        f"@article{{{cite_key},\n"
        f"  title = {{{title}}},\n"
        f"  author = {{{authors}}},\n"
        f"  year = {{{year}}},\n"
        f"  journal = {{{venue}}},\n"
        f"}}"
    )


def _resolve_missing_citations(
    missing_keys: set[str],
    existing_bib: str,
) -> tuple[set[str], list[str]]:
    """Try to find BibTeX entries for citation keys not in references.bib.

    Parses each cite_key (e.g. ``hendrycks2017baseline``) into an author name
    and year, then searches academic APIs.  Returns ``(resolved_keys,
    new_bib_entries)`` where each entry is a complete BibTeX string.

    BUG-194 fix: Three-layer resolution strategy:
      1. **Seminal lookup** — check seminal_papers.yaml (zero API calls, exact match)
      2. **API search with validation** — search Semantic Scholar / arXiv, but ONLY
         accept results whose title has ≥ 30% word overlap with query terms.
         Previously any year-matching result was blindly accepted, causing
         foundational papers to be replaced with garbage.
      3. **Skip** — if no confident match, leave the citation unresolved rather
         than inject a wrong paper.

    Gracefully returns empty results on any network failure.
    """
    import re as _re176
    import time as _time176

    resolved: set[str] = set()
    new_entries: list[str] = []

    def _parse_cite_key(key: str) -> tuple[str, str, str]:
        """Extract (author, year, keyword_hint) from a citation key.

        Common patterns:
          ``he2016deep``       → ("he", "2016", "deep")
          ``vaswani2017attention`` → ("vaswani", "2017", "attention")
          ``goodfellow2014generative`` → ("goodfellow", "2014", "generative")
        """
        m = _re176.match(r"([a-zA-Z]+?)(\d{4})(.*)", key)
        if m:
            return m.group(1), m.group(2), m.group(3)
        return key, "", ""

    def _title_word_overlap(title: str, query_words: list[str]) -> float:
        """Word-overlap score between a paper title and query keywords.

        Returns fraction of query words found in the title (0.0–1.0).
        Used to validate that a search result is actually relevant.
        """
        if not query_words:
            return 0.0
        title_lower = set(_re176.sub(r"[^a-z0-9\s]", "", title.lower()).split()) - {""}
        if not title_lower:
            return 0.0
        matched = sum(1 for w in query_words if w.lower() in title_lower)
        return matched / len(query_words)

    # --- Layer 1: Seminal papers lookup (no API calls) ---
    seminal_by_key = _load_seminal_papers_by_key()

    for key in sorted(missing_keys):
        if key in seminal_by_key and key not in existing_bib:
            sp = seminal_by_key[key]
            bib_entry = _seminal_to_bibtex(sp, key)
            new_entries.append(bib_entry)
            resolved.add(key)
            logger.info(
                "BUG-194: Resolved %r via seminal_papers.yaml → %r (%s)",
                key,
                sp.get("title", "")[:60],
                sp.get("year", ""),
            )

    # Remaining keys that weren't in the seminal database AND aren't already
    # present in the existing bib (no point re-resolving keys we already have).
    remaining = sorted(k for k in (missing_keys - resolved) if k not in existing_bib)
    if not remaining:
        return resolved, new_entries

    # --- Layer 2: API search with title-similarity validation ---
    try:
        from berb.literature.search import search_papers
    except ImportError:
        logger.debug("BUG-176: literature.search not available, skipping resolution")
        return resolved, new_entries

    for key in remaining:
        author, year, hint = _parse_cite_key(key)
        if not author or not year:
            continue

        # BUG-194: Build a better search query.
        # Instead of "he 2016 deep", use "he deep residual learning 2016" or
        # at minimum, split camelCase hints into separate words.
        # Split hint on word boundaries (camelCase or underscore).
        hint_words = _re176.findall(r"[a-zA-Z]+", hint) if hint else []
        # The query words used for validation
        query_words = [author] + hint_words

        # Build search query: author + hint words + year (year helps but isn't
        # the primary discriminator anymore)
        query_parts = [author] + hint_words + [year]
        query = " ".join(query_parts)

        try:
            results = search_papers(query, limit=5, deduplicate=True)
        except Exception as exc:
            logger.debug("BUG-176: Search failed for %r: %s", key, exc)
            continue

        if not results:
            logger.debug(
                "BUG-194: No search results for %r (query=%r), skipping",
                key,
                query,
            )
            continue

        # BUG-194: Find best match by title-word-overlap AND year match.
        # Previously the code just took the first year-matching result.
        best = None
        best_score = -1.0
        for paper in results:
            overlap = _title_word_overlap(paper.title, query_words)
            year_bonus = 0.2 if str(paper.year) == year else 0.0
            # Also give bonus for author name appearing in paper.authors
            author_bonus = 0.0
            if any(author.lower() in a.name.lower() for a in paper.authors):
                author_bonus = 0.2
            score = overlap + year_bonus + author_bonus
            if score > best_score:
                best_score = score
                best = paper

        if best is None:
            continue

        # BUG-194: Validate the result — require minimum similarity.
        # This is the KEY fix: previously ANY result was accepted blindly.
        overlap = _title_word_overlap(best.title, query_words)
        if overlap < _CITATION_RESOLVE_MIN_SIMILARITY:
            logger.info(
                "BUG-194: Rejecting search result for %r — title %r has "
                "too-low overlap (%.2f < %.2f) with query words %r",
                key,
                best.title[:60],
                overlap,
                _CITATION_RESOLVE_MIN_SIMILARITY,
                query_words,
            )
            continue

        # Year must also match (or be within 1 year — sometimes conferences
        # vs arXiv preprint have different years)
        if year and best.year:
            year_diff = abs(int(year) - int(best.year))
            if year_diff > 1:
                logger.info(
                    "BUG-194: Rejecting search result for %r — year mismatch (%s vs %s, diff=%d)",
                    key,
                    year,
                    best.year,
                    year_diff,
                )
                continue

        # Generate BibTeX with the ORIGINAL cite_key (so \cite{key} works)
        bib_entry = best.to_bibtex()
        # Replace the auto-generated cite_key with the one used in the paper
        orig_key_match = _re176.match(r"@(\w+)\{([^,]+),", bib_entry)
        if orig_key_match:
            bib_entry = bib_entry.replace(
                f"@{orig_key_match.group(1)}{{{orig_key_match.group(2)},",
                f"@{orig_key_match.group(1)}{{{key},",
                1,
            )

        # Verify entry doesn't duplicate an existing key
        if key not in existing_bib:
            new_entries.append(bib_entry)
            resolved.add(key)
            logger.info(
                "BUG-194: Resolved %r via API → %r (%s, overlap=%.2f)",
                key,
                best.title[:60],
                best.year,
                overlap,
            )
        else:
            logger.debug(
                "BUG-194: Key %r already in bib, skipping API result",
                key,
            )

        # Rate limit: 0.5s between API calls
        _time176.sleep(0.5)

    return resolved, new_entries


def _check_citation_relevance(
    llm: Any,
    topic: str,
    results: list[Any],
) -> dict[str, float | None]:
    """Use LLM to assess relevance of each citation to the research topic.

    Returns a dict mapping cite_key → relevance score (0.0–1.0).
    Processes citations in batches of 30 to handle large bibliographies.
    """
    citation_lines = []
    for cr in results:
        citation_lines.append(f'- [{cr.cite_key}] "{cr.title}"')
    if not citation_lines:
        return {}

    all_scores: dict[str, float] = {}
    _BATCH_SIZE = 30

    for batch_start in range(0, len(citation_lines), _BATCH_SIZE):
        batch = citation_lines[batch_start : batch_start + _BATCH_SIZE]
        citations_text = "\n".join(batch)

        prompt = (
            f"Research topic: {topic}\n\n"
            f"Rate the relevance of each citation to the research topic "
            f"on a scale of 0.0 to 1.0.\n"
            f"Return ONLY a JSON object mapping cite_key to relevance score.\n"
            f'Example: {{"smith2020": 0.9, "jones2019": 0.2}}\n\n'
            f"Citations:\n{citations_text}"
        )

        try:
            resp = llm.chat(
                [{"role": "user", "content": prompt}],
                system="You assess citation relevance. Return only valid JSON.",
                json_mode=True,
            )
            parsed = _safe_json_loads(resp.content, {})
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if isinstance(v, (int, float)):
                        all_scores[k] = max(0.0, min(1.0, float(v)))
        except Exception:  # noqa: BLE001
            logger.debug(
                "Citation relevance check failed for batch %d–%d, skipping",
                batch_start,
                batch_start + len(batch),
            )

    return all_scores


def _remove_bibtex_entries(bib_text: str, keys_to_remove: set[str]) -> str:
    """Remove BibTeX entries whose keys are in *keys_to_remove*."""
    kept: list[str] = []
    for m in re.finditer(r"@\w+\{([^,]+),", bib_text):
        key = m.group(1).strip()
        if key in keys_to_remove:
            continue
        # Find the full entry (from @ to the next @ or end)
        start = m.start()
        # Find balanced braces
        depth = 0
        end = start
        for i in range(start, len(bib_text)):
            if bib_text[i] == "{":
                depth += 1
            elif bib_text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > start:
            kept.append(bib_text[start:end])
    return "\n\n".join(kept) + "\n" if kept else ""


def _remove_citations_from_text(text: str, keys_to_remove: set[str]) -> str:
    """Remove \\cite{key} and [key] references for specified citation keys."""

    # Handle multi-key LaTeX cites: \cite{a,b,c} → filter keys inside braces
    def _filter_cite(m: re.Match[str]) -> str:
        keys = [k.strip() for k in m.group(1).split(",")]
        kept = [k for k in keys if k not in keys_to_remove]
        if not kept:
            return ""
        return f"\\cite{{{','.join(kept)}}}"

    text = re.sub(r"\\cite\{([^}]+)\}", _filter_cite, text)

    # Markdown: [key]
    for key in keys_to_remove:
        text = re.sub(rf"\[{re.escape(key)}\]", "", text)
    return text


# ---------------------------------------------------------------------------
# Stage 23: Citation Verify
# ---------------------------------------------------------------------------


@register_stage(
    stage=Stage.CITATION_VERIFY,
    depends_on=frozenset({Stage.EXPORT_PUBLISH}),
    contract=StageContract(
        stage=Stage.CITATION_VERIFY,
        input_files=("paper_final.md",),
        output_files=("verification_report.json", "references_verified.bib"),
        dod="All citations verified against real APIs; hallucinated refs flagged",
        error_code="E23_VERIFY_FAIL",
    ),
)
def _execute_citation_verify(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    from berb.literature.verify import (
        VerifyStatus,
        annotate_paper_hallucinations,
        filter_verified_bibtex,
        verify_citations,
    )

    bib_text = _read_prior_artifact(run_dir, "references.bib") or ""
    paper_text = _read_prior_artifact(run_dir, "paper_final.md") or ""

    if not bib_text.strip():
        report_data = {
            "summary": {
                "total": 0,
                "verified": 0,
                "suspicious": 0,
                "hallucinated": 0,
                "skipped": 0,
                "integrity_score": 1.0,
            },
            "results": [],
            "note": "No references.bib found — nothing to verify.",
        }
        (stage_dir / "verification_report.json").write_text(
            json.dumps(report_data, indent=2), encoding="utf-8"
        )
        (stage_dir / "references_verified.bib").write_text(
            "% No references to verify\n", encoding="utf-8"
        )
        return StageResult(
            stage=Stage.CITATION_VERIFY,
            status=StageStatus.DONE,
            artifacts=("verification_report.json", "references_verified.bib"),
            evidence_refs=(
                "stage-23/verification_report.json",
                "stage-23/references_verified.bib",
            ),
        )

    s2_api_key = getattr(config.llm, "s2_api_key", "") or ""

    from berb.literature.verify import parse_bibtex_entries

    _n_entries = len(parse_bibtex_entries(bib_text))
    logger.info(
        "[citation-verify] Verifying %d references (DOI→CrossRef > OpenAlex > arXiv > S2)…",
        _n_entries,
    )
    report = verify_citations(bib_text, s2_api_key=s2_api_key)
    logger.info(
        "[citation-verify] Done: %d verified, %d suspicious, "
        "%d hallucinated, %d skipped (integrity: %.0f%%)",
        report.verified,
        report.suspicious,
        report.hallucinated,
        report.skipped,
        report.integrity_score * 100,
    )

    # --- Relevance check: assess topical relevance of verified citations ---
    if llm is not None and report.results:
        relevance_scores = _check_citation_relevance(
            llm, config.research.topic, report.results
        )
        for cr in report.results:
            score = relevance_scores.get(cr.cite_key)
            if score is not None:
                cr.relevance_score = score

    # FIX-5: Filter low-relevance citations and enforce hard cap
    RELEVANCE_THRESHOLD = 0.5
    MAX_CITATIONS = 60
    low_relevance_keys: set[str] = set()
    for cr in report.results:
        if cr.relevance_score is not None and cr.relevance_score < RELEVANCE_THRESHOLD:
            low_relevance_keys.add(cr.cite_key)

    # Hard cap: if still above MAX_CITATIONS after relevance filter, drop lowest
    # BUG-07 fix: Unscored citations (relevance_score=None) default to 0.7
    # because they passed API verification and are likely relevant.
    # Previously they defaulted to 0.0 which caused mass-deletion.
    _DEFAULT_RELEVANCE = 0.7
    remaining = [
        cr
        for cr in report.results
        if cr.cite_key not in low_relevance_keys
        and cr.status != VerifyStatus.HALLUCINATED
    ]
    if len(remaining) > MAX_CITATIONS:
        remaining.sort(
            key=lambda c: (
                c.relevance_score
                if c.relevance_score is not None
                else _DEFAULT_RELEVANCE
            ),
        )
        overflow = remaining[: len(remaining) - MAX_CITATIONS]
        for cr in overflow:
            low_relevance_keys.add(cr.cite_key)
        logger.info(
            "Stage 23: Hard cap applied, dropping %d additional low-relevance citations",
            len(overflow),
        )

    if low_relevance_keys:
        logger.info(
            "Stage 23: Filtering %d low-relevance citations (threshold=%.1f, cap=%d): %s",
            len(low_relevance_keys),
            RELEVANCE_THRESHOLD,
            MAX_CITATIONS,
            ", ".join(sorted(list(low_relevance_keys)[:20])),
        )

    (stage_dir / "verification_report.json").write_text(
        json.dumps(report.to_dict(), indent=2), encoding="utf-8"
    )

    verified_bib = filter_verified_bibtex(bib_text, report, include_suspicious=True)
    # Remove low-relevance entries from BibTeX
    if low_relevance_keys:
        verified_bib = _remove_bibtex_entries(verified_bib, low_relevance_keys)

    # BUG-26: If verification stripped >50% of entries (e.g. due to rate limiting),
    # fall back to the original bib to avoid breaking the paper's references
    original_count = len(re.findall(r"@\w+\{", bib_text))
    verified_count = len(re.findall(r"@\w+\{", verified_bib))
    if original_count > 0 and verified_count < original_count * 0.5:
        logger.warning(
            "Stage 23: Verification stripped %d→%d entries (>50%% loss). "
            "Keeping original bib to avoid breaking references.",
            original_count,
            verified_count,
        )
        verified_bib = bib_text

    # IMP-1: Also prune uncited entries from verified bib
    # BUG-182: Also scan LaTeX paper.tex (not just Markdown) for \cite{} keys.
    # The Markdown version may use [key] notation while LaTeX uses \cite{key}.
    if paper_text.strip():
        _vbib_keys = set(re.findall(r"@\w+\{([^,]+),", verified_bib))
        _cited_in_paper: set[str] = set()
        _cited_in_paper.update(
            re.findall(r"\[([a-zA-Z]+\d{4}[a-zA-Z0-9_-]*)\]", paper_text)
        )
        for _cm in re.finditer(r"\\cite\{([^}]+)\}", paper_text):
            _cited_in_paper.update(k.strip() for k in _cm.group(1).split(","))
        # BUG-182: Also read stage-22/paper.tex for \cite{} keys
        _latex_paper = stage_dir.parent / "stage-22" / "paper.tex"
        if _latex_paper.exists():
            try:
                _latex_text = _latex_paper.read_text(encoding="utf-8")
                for _cm in re.finditer(r"\\cite[pt]?\{([^}]+)\}", _latex_text):
                    _cited_in_paper.update(k.strip() for k in _cm.group(1).split(","))
            except OSError:
                pass
        _uncited_vbib = _vbib_keys - _cited_in_paper
        if _uncited_vbib:
            verified_bib = _remove_bibtex_entries(verified_bib, _uncited_vbib)
            logger.info(
                "Stage 23: Pruned %d uncited entries from verified bib (kept %d)",
                len(_uncited_vbib),
                len(_vbib_keys) - len(_uncited_vbib),
            )

    # BUG-100: If all entries were filtered out (low-relevance + uncited pruning),
    # write a comment instead of an empty file to avoid "Missing or empty output" error.
    if not verified_bib.strip():
        verified_bib = "% All citations were filtered out during verification\n"
        logger.warning(
            "Stage 23: All BibTeX entries filtered out — writing placeholder"
        )

    (stage_dir / "references_verified.bib").write_text(verified_bib, encoding="utf-8")

    artifacts = ["verification_report.json", "references_verified.bib"]

    if paper_text.strip():
        annotated = annotate_paper_hallucinations(paper_text, report)
        # Remove \cite{} and [cite_key] references for low-relevance entries
        if low_relevance_keys:
            annotated = _remove_citations_from_text(annotated, low_relevance_keys)
        (stage_dir / "paper_final_verified.md").write_text(annotated, encoding="utf-8")
        artifacts.append("paper_final_verified.md")

    logger.info(
        "Stage 23 citation verify: %d total, %d verified, %d suspicious, "
        "%d hallucinated, %d skipped (integrity=%.1f%%)",
        report.total,
        report.verified,
        report.suspicious,
        report.hallucinated,
        report.skipped,
        report.integrity_score * 100,
    )

    return StageResult(
        stage=Stage.CITATION_VERIFY,
        status=StageStatus.DONE,
        artifacts=tuple(artifacts),
        evidence_refs=tuple(f"stage-23/{a}" for a in artifacts),
    )
