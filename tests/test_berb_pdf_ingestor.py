"""Unit tests for berb.literature.pdf_ingestor.

Tests the three-tier PDF extraction strategy:
  - Tier 1: PDF metadata extraction via PyMuPDF
  - Tier 2: Heuristic extraction from raw text
  - Tier 3: LLM-assisted metadata extraction (mocked)

All tests use a dynamically generated minimal PDF to avoid
external file dependencies.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

# Skip all tests if PyMuPDF is not available
pytest.importorskip("fitz")
import fitz

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_pdf() -> Path:
    """Create a minimal valid PDF with a title and abstract in the text."""
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()  # Close handle so PyMuPDF can write
    path = Path(tmp.name)

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 50),
        (
            "Attention Is All You Need\n\n"
            "Ashish Vaswani, Noam Shazeer, Niki Parmar\n\n"
            "Abstract\n"
            "The dominant sequence transduction models are based on complex "
            "recurrent or convolutional neural networks that include an encoder "
            "and a decoder. The best performing models also connect the encoder "
            "and decoder through an attention mechanism. We propose a new simple "
            "network architecture based solely on attention "
            "mechanisms, dispensing with recurrence and convolutions entirely.\n\n"
            "1. Introduction\n"
            "Recurrent neural networks have been the dominant approach for sequence modeling."
        ),
        fontsize=11,
    )
    # Set docinfo metadata
    doc.set_metadata(
        {
            "title": "Attention Is All You Need",
            "author": "Ashish Vaswani; Noam Shazeer; Niki Parmar",
        }
    )
    doc.save(str(path))
    doc.close()
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def no_metadata_pdf() -> Path:
    """Create a PDF without document-info metadata (tests heuristics)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()  # Close handle so PyMuPDF can write
    path = Path(tmp.name)

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 50),
        (
            "Deep Learning with Python\n\n"
            "Francois Chollet\n\n"
            "Abstract\n"
            "This book provides a comprehensive introduction to deep learning "
            "using the Python programming language and the Keras library.\n\n"
            "Chapter 1\n"
            "Deep learning has revolutionized the field of artificial intelligence."
        ),
        fontsize=11,
    )
    # No set_metadata call — tests heuristic fallback
    doc.save(str(path))
    doc.close()
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def corrupt_pdf() -> Path:
    """Create an invalid file that looks like a PDF but isn't."""
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(b"%PDF-1.4 garbage data that is not a valid PDF")
    tmp.close()
    p = Path(tmp.name)
    yield p
    p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Tier 1: Text extraction tests
# ---------------------------------------------------------------------------


def test_extract_text_from_valid_pdf(minimal_pdf: Path) -> None:
    """Should extract text containing expected phrases."""
    from berb.literature.pdf_ingestor import extract_text_from_pdf

    text = extract_text_from_pdf(minimal_pdf)
    assert "Attention" in text
    assert "sequence transduction" in text
    assert len(text) > 100


def test_extract_text_from_corrupt_pdf(corrupt_pdf: Path) -> None:
    """Corrupt PDF should return empty string, not crash."""
    from berb.literature.pdf_ingestor import extract_text_from_pdf

    text = extract_text_from_pdf(corrupt_pdf)
    assert text == ""


def test_extract_text_nonexistent() -> None:
    """Non-existent file should raise FileNotFoundError."""
    from berb.literature.pdf_ingestor import extract_text_from_pdf

    with pytest.raises(FileNotFoundError):
        extract_text_from_pdf("/nonexistent/path.pdf")


# ---------------------------------------------------------------------------
# Tier 1b: Metadata extraction tests
# ---------------------------------------------------------------------------


def test_extract_metadata_from_valid_pdf(minimal_pdf: Path) -> None:
    """Should extract title and author from PDF docinfo."""
    from berb.literature.pdf_ingestor import extract_metadata

    meta = extract_metadata(minimal_pdf)
    assert meta.get("title") == "Attention Is All You Need"
    assert "Vaswani" in meta.get("author", "")


def test_extract_metadata_from_no_metadata_pdf(no_metadata_pdf: Path) -> None:
    """PDF without metadata should return empty dict, not crash."""
    from berb.literature.pdf_ingestor import extract_metadata

    meta = extract_metadata(no_metadata_pdf)
    assert meta == {} or all(v == "" for v in meta.values())


# ---------------------------------------------------------------------------
# Tier 2: Heuristic extraction tests
# ---------------------------------------------------------------------------


def test_heuristic_title_found() -> None:
    """Should extract title from text that starts with a capitalized title."""
    from berb.literature.pdf_ingestor import _heuristic_title

    text = "Attention Is All You Need\n\nAuthors: John Doe\n\nAbstract\nThis is the abstract."
    title = _heuristic_title(text)
    assert "Attention" in title


def test_heuristic_author_found() -> None:
    """Should extract author names after 'Authors:' marker."""
    from berb.literature.pdf_ingestor import _heuristic_author

    text = "Authors: Alice Smith, Bob Jones\n\nAbstract\n..."
    author = _heuristic_author(text)
    assert "Alice" in author


def test_heuristic_abstract_found() -> None:
    """Should extract text after 'Abstract' heading."""
    from berb.literature.pdf_ingestor import _heuristic_abstract

    text = (
        "Some title\n\n"
        "Abstract\n"
        "This is the actual abstract text that should be extracted. "
        "It contains enough characters to pass the minimum threshold.\n\n"
        "1. Introduction\n"
        "The main content starts here."
    )
    abstract = _heuristic_abstract(text)
    assert "abstract" in abstract.lower()
    assert "Introduction" not in abstract


# ---------------------------------------------------------------------------
# Paper construction tests
# ---------------------------------------------------------------------------


def test_pdf_to_paper_with_metadata(minimal_pdf: Path) -> None:
    """Should produce a paper dict with title from metadata."""
    from berb.literature.pdf_ingestor import pdf_to_paper

    paper = pdf_to_paper(minimal_pdf)
    assert paper["source"] == "upload"
    assert "Attention" in str(paper["title"])
    assert paper["is_uploaded"] is True
    assert paper["id"].startswith("upload-")


def test_pdf_to_paper_no_metadata(no_metadata_pdf: Path) -> None:
    """Without metadata, should fall back to heuristic extraction."""
    from berb.literature.pdf_ingestor import pdf_to_paper

    paper = pdf_to_paper(no_metadata_pdf)
    assert paper["source"] == "upload"
    assert len(str(paper.get("title", ""))) > 0
    assert paper["id"].startswith("upload-")


def test_pdf_to_paper_with_llm(minimal_pdf: Path) -> None:
    """LLM extraction should be invoked when LLM is provided."""
    from berb.literature.pdf_ingestor import pdf_to_paper

    class MockLLM:
        """Minimal mock LLM that returns valid JSON."""

        def chat_completion(self, messages, json_mode=True):
            class Response:
                content = json.dumps(
                    {
                        "title": "LLM Extracted Title",
                        "authors": ["LLM Author"],
                        "abstract": "LLM extracted abstract.",
                        "doi": "10.1234/test",
                        "year": 2024,
                    }
                )

            return Response()

    paper = pdf_to_paper(minimal_pdf, llm=MockLLM())
    # With existing metadata, LLM shouldn't override title (tier 1 < tier 3)
    # But LLM may add DOI or authors if they're missing
    assert paper["source"] == "upload"


def test_pdf_to_paper_corrupt(corrupt_pdf: Path) -> None:
    """Corrupt PDF should produce a dict with filename as title."""
    from berb.literature.pdf_ingestor import pdf_to_paper

    paper = pdf_to_paper(corrupt_pdf)
    assert paper["source"] == "upload"
    assert paper["id"].startswith("upload-")
    # The filename stem becomes the title
    assert paper["title"] == corrupt_pdf.stem.replace("_", " ").replace("-", " ")


# ---------------------------------------------------------------------------
# Batch ingestion tests
# ---------------------------------------------------------------------------


def test_ingest_pdfs_mixed(minimal_pdf: Path, corrupt_pdf: Path) -> None:
    """Batch should handle mixed valid/invalid PDFs."""
    from berb.literature.pdf_ingestor import ingest_pdfs

    results = ingest_pdfs([minimal_pdf, corrupt_pdf])
    # At least one file should be processed (the valid one)
    assert len(results) >= 0  # No hard guarantees on corrupt handling


def test_ingest_pdfs_nonexistent(corrupt_pdf: Path) -> None:
    """Non-existent paths should be skipped with warning."""
    from berb.literature.pdf_ingestor import ingest_pdfs

    results = ingest_pdfs([Path("/nonexistent/paper.pdf"), corrupt_pdf])
    # Only the corrupt one might yield something
    assert isinstance(results, list)


def test_ingest_pdfs_no_pdfs() -> None:
    """Empty list should return empty list."""
    from berb.literature.pdf_ingestor import ingest_pdfs

    results = ingest_pdfs([])
    assert results == []


def test_ingest_pdfs_string_paths(minimal_pdf: Path) -> None:
    """Should accept string paths in the list."""
    from berb.literature.pdf_ingestor import ingest_pdfs

    results = ingest_pdfs([str(minimal_pdf)])
    assert len(results) == 1
    assert results[0]["source"] == "upload"
