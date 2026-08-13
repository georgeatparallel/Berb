"""PDF ingestion — user-uploaded PDFs → Paper domain objects.

Three-tier extraction strategy (Strategy pattern):
  1. Metadata extraction from PDF document-info / XMP
  2. Heuristic extraction from raw text (regex patterns for title, authors)
  3. LLM-assisted extraction for difficult cases

Usage::

    papers = ingest_pdfs([Path("paper.pdf")], llm=None)

TODO: Add scanned-PDF OCR support via pytesseract in a future iteration.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC
from pathlib import Path

from berb.utils.sanitize import wrap_untrusted

logger = logging.getLogger(__name__)

# Maximum characters to extract for LLM-based metadata inference
_MAX_TEXT_CHARS = 20_000
# Minimum abstract length for a paper to be considered have decent metadata
_MIN_ABSTRACT_CHARS = 80
# Maximum characters from the beginning used for heuristic title extraction
_MAX_HEADER_CHARS = 2_000

# ---------------------------------------------------------------------------
# Tier 1: PyMuPDF text extraction
# ---------------------------------------------------------------------------


def extract_text_from_pdf(path: Path) -> str:
    """Extract plain text from a PDF using PyMuPDF.

    Args:
        path: Path to the PDF file.

    Returns:
        Extracted text (all pages concatenated with newlines).
        Empty string on failure.

    Raises:
        FileNotFoundError: If the PDF does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    try:
        import fitz  # PyMuPDF
    except ImportError as err:
        logger.warning("PyMuPDF not available — install with: pip install PyMuPDF")
        raise RuntimeError("PyMuPDF is required for PDF ingestion") from err

    try:
        doc = fitz.open(str(path))
        if doc.is_encrypted:
            logger.warning("PDF is password-protected, cannot extract text: %s", path)
            doc.close()
            return ""
        pages: list[str] = []
        for page in doc:
            text = page.get_text()
            if text:
                pages.append(text)
        doc.close()
        text = "\n\n".join(pages)
        logger.debug(
            "Extracted %d characters from %d pages in %s", len(text), len(pages), path.name
        )
        return text
    except Exception:
        logger.warning("Failed to extract text from PDF: %s", path, exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# Tier 2: PDF metadata extraction
# ---------------------------------------------------------------------------


def extract_metadata(path: Path | str) -> dict[str, str]:
    """Extract document-level metadata from a PDF (title, author, subject).

    Reads PDF document-info dictionary and XMP metadata. Returns only
    non-empty string values.

    Args:
        path: Path to the PDF file.

    Returns:
        Dict with keys: ``title``, ``author``, ``subject`` (may be empty).
    """
    try:
        import fitz
    except ImportError as err:
        raise RuntimeError("PyMuPDF is required for PDF metadata extraction") from err

    meta: dict[str, str] = {}
    try:
        doc = fitz.open(str(path))
        md = doc.metadata
        doc.close()

        for key in ("title", "author", "subject"):
            val = str(md.get(key, "") or "").strip()
            if val:
                meta[key] = val

        # Try to extract DOI from XMP or metadata keywords
        doi_val = md.get("doi", "") or ""
        if doi_val and doi_val.strip():
            meta["doi"] = doi_val.strip()
    except Exception:
        logger.warning("Failed to extract PDF metadata: %s", path, exc_info=True)

    return meta


# ---------------------------------------------------------------------------
# Tier 2b: Heuristic extraction from raw text
# ---------------------------------------------------------------------------

# Patterns commonly found at the start of academic papers
_TITLE_HEURISTICS: list[tuple[re.Pattern[str], str]] = [
    # arXiv-style: \\title{...}
    (re.compile(r"\\title\{([^}]+)\}", re.DOTALL), "latex"),
    # First line that looks like a title (all caps, >5 chars)
    (re.compile(r"^([A-Z][A-Za-z0-9\s:,-]{10,})$", re.MULTILINE), "caps"),
    # Title after a blank line at the top
    (re.compile(r"^\n{2,}(.{10,100})\n", re.MULTILINE), "spaced"),
]

# Simple split on common author-separator patterns
_AUTHOR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:^|\n)(?:Authors?|By)[:]\s*(.+?)(?:\n|$)", re.IGNORECASE),
    re.compile(r"\n([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)(?:[,;]\s*(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+))*"),
]


def _heuristic_title(text: str) -> str:
    """Attempt to extract a title from raw PDF text using heuristics."""
    first_block = text[:_MAX_HEADER_CHARS]
    for pattern, kind in _TITLE_HEURISTICS:
        match = pattern.search(first_block)
        if match:
            title = match.group(1).strip()
            # Clean up whitespace
            title = re.sub(r"\s+", " ", title)
            if 5 < len(title) < 500:
                logger.debug("Heuristic title extraction (%s): %r", kind, title[:60])
                return title
    return ""


def _heuristic_author(text: str) -> str:
    """Attempt to extract author names from raw PDF text."""
    first_block = text[:_MAX_HEADER_CHARS]
    for pattern in _AUTHOR_PATTERNS:
        match = pattern.search(first_block)
        if match:
            raw = match.group(1 if pattern.groups >= 1 else 0).strip()
            # Limit length — authors line shouldn't be huge
            if 3 < len(raw) < 300:
                return raw.strip()
    return ""


def _heuristic_abstract(text: str) -> str:
    """Extract the abstract section from PDF text."""
    # Look for "Abstract" followed by text until next section heading
    match = re.search(
        r"(?:^|\n)\s*(?:Abstract)[:\s]*\n*(.*?)(?:\n\s*(?:Introduction|1\.\s|Keywords|CCS))",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        abstract = match.group(1).strip()
        # Strip trailing garbage
        abstract = re.sub(r"\s+", " ", abstract)
        if len(abstract) > _MIN_ABSTRACT_CHARS:
            return abstract
    return ""


# ---------------------------------------------------------------------------
# Tier 3: LLM-assisted metadata extraction
# ---------------------------------------------------------------------------


def _llm_extract_metadata(
    text: str,
    llm: object,
) -> dict[str, object]:
    """Use LLM to extract structured metadata from PDF text.

    Args:
        text: Extracted PDF plain text.
        llm: LLM client with a ``chat_completion(messages, json_mode=True)``
             interface (e.g. ``LLMClient`` from ``berb.llm``).

    Returns:
        Dict with keys: ``title``, ``authors`` (list of str), ``abstract``,
        ``doi``, ``year``.
    """
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "Extract the following metadata from this academic paper PDF text. "
                    "Respond in JSON with keys: title, authors (list), abstract, "
                    "doi (or empty string), year (4-digit number or 0). "
                    "Use null for any field you cannot determine."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Extract metadata from this paper text:\n\n"
                    + wrap_untrusted(text[:_MAX_TEXT_CHARS], "PDF-extracted paper text")
                ),
            },
        ]
        # Duck-type the LLM interface
        if hasattr(llm, "chat"):
            response = llm.chat(messages, json_mode=True)
        elif hasattr(llm, "chat_completion"):
            response = llm.chat_completion(messages, json_mode=True)
        else:
            # Fallback for simpler interfaces (callable)
            response = llm(messages, json_mode=True)

        content = response.content if hasattr(response, "content") else str(response)
        import json

        payload = json.loads(content)
        if not isinstance(payload, dict):
            return {}
        return {
            "title": str(payload.get("title", "") or ""),
            "authors": list(payload.get("authors", [])),
            "abstract": str(payload.get("abstract", "") or ""),
            "doi": str(payload.get("doi", "") or ""),
            "year": int(payload.get("year", 0) or 0),
        }
    except Exception:
        logger.warning("LLM metadata extraction failed", exc_info=True)
        return {}


# ---------------------------------------------------------------------------
# Paper construction
# ---------------------------------------------------------------------------


def _compute_paper_id(path: Path) -> str:
    """Compute a stable content-hash-based paper ID."""
    path = Path(path)
    try:
        raw = path.read_bytes()
        return "upload-" + hashlib.sha256(raw).hexdigest()[:16]
    except Exception:
        return f"upload-{path.stem}"


def pdf_to_paper(path: Path | str, llm: object | None = None) -> dict[str, object]:
    """Convert a single PDF into a Paper-like dict for ``candidates.jsonl``.

    Three-tier strategy:
      1. Read PDF metadata (title, author from document-info).
      2. Extract raw text; use heuristics for title/abstract if metadata
         is insufficient.
      3. If LLM is available and heuristics failed, use LLM to extract.

    Args:
        path: Path to a PDF file.
        llm: Optional LLM client for AI-assisted metadata extraction.

    Returns:
        A dict matching the ``candidates.jsonl`` row format:
        ``id``, ``title``, ``authors``, ``abstract``, ``source``,
        ``year``, ``doi``, ``collected_at``.
    """
    from datetime import datetime

    path = Path(path)
    paper_id = _compute_paper_id(path)

    # Tier 1: PDF metadata
    meta = extract_metadata(path)
    title = meta.get("title", "")
    author_str = meta.get("author", "")
    doi = meta.get("doi", "")

    # Tier 2: Raw text + heuristics
    text = extract_text_from_pdf(path)

    if not title:
        title = _heuristic_title(text)

    if not author_str:
        author_str = _heuristic_author(text)

    abstract = _heuristic_abstract(text)

    # Tier 3: LLM-assisted (only if heuristics failed on critical fields)
    if llm is not None and (not title or not abstract):
        llm_meta = _llm_extract_metadata(text, llm)
        if not title:
            title = llm_meta.get("title", "") or ""
        if not abstract:
            abstract = llm_meta.get("abstract", "") or ""
        if not doi:
            doi = llm_meta.get("doi", "") or ""
        if not author_str and llm_meta.get("authors"):
            author_str = ", ".join(str(a) for a in llm_meta["authors"])

    # Fallback: use filename as title
    if not title:
        _stem = path.stem.replace("_", " ").replace("-", " ").strip()
        title = _stem or "Untitled Upload"

    # Build authors list
    authors_list: list[dict[str, str]] = []
    if author_str:
        for name_part in re.split(r"[;,]\s*", author_str):
            name_part = name_part.strip()
            if name_part and len(name_part) > 2:
                authors_list.append({"name": name_part})

    # Compute a simple citation key from first author + first title word
    _surname = authors_list[0]["name"].split()[-1].lower() if authors_list else "upload"
    _title_word = re.sub(r"[^a-zA-Z]", "", title.split()[0]).lower() if title else "paper"
    cite_key = f"{_surname}{datetime.now(UTC).year}{_title_word}"

    return {
        "id": paper_id,
        "paper_id": paper_id,
        "title": title,
        "authors": authors_list,
        "abstract": abstract[:5_000] if abstract else "",
        "source": "upload",
        "year": 0,
        "doi": doi,
        "arxiv_id": "",
        "url": str(path),
        "venue": "Uploaded PDF",
        "citation_count": 0,
        "cite_key": cite_key,
        "collected_at": datetime.now(UTC).isoformat(),
        "is_uploaded": True,
    }


# ---------------------------------------------------------------------------
# Batch ingestion
# ---------------------------------------------------------------------------


def ingest_pdfs(
    paths: list[Path] | list[str],
    llm: object | None = None,
) -> list[dict[str, object]]:
    """Ingest multiple PDFs into Paper-like dicts for the pipeline.

    Each PDF is processed independently. Malformed or unreadable PDFs
    are skipped with a warning.

    Args:
        paths: List of paths to PDF files.
        llm: Optional LLM client for AI-assisted metadata extraction.

    Returns:
        List of dicts ready for inclusion in ``candidates.jsonl``.
    """
    papers: list[dict[str, object]] = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            logger.warning("Uploaded PDF not found, skipping: %s", path)
            continue
        if path.suffix.lower() != ".pdf":
            logger.warning("Skipping non-PDF file: %s (extension: %s)", path, path.suffix)
            continue

        try:
            paper = pdf_to_paper(path, llm=llm)
            papers.append(paper)
            logger.info(
                "Ingested PDF: %s → title=%r authors=%d abstract=%d chars",
                path.name,
                paper.get("title", "")[:60],
                len(paper.get("authors", [])),
                len(paper.get("abstract", "")),
            )
        except Exception:
            logger.error("Failed to ingest PDF: %s", path, exc_info=True)

    if not papers:
        logger.warning("No papers could be ingested from %d uploaded PDF(s)", len(paths))

    return papers
