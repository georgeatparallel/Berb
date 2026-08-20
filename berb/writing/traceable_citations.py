"""Source-traceable citation links for verification.

This module provides exact page+paragraph citation tracing:
- Every citation links to exact source location
- PDF text extraction with page numbers
- Paragraph-level indexing
- Alignment scoring between claim and source
- HTML verification page generation

Inspired by Writeless AI's traceable citations feature.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TraceableCitation(BaseModel):
    """Citation with full source traceability.

    Attributes:
        paper: Cited paper metadata
        source_paper: Source paper being cited
        page_number: Page number in source
        paragraph_index: Paragraph index on that page
        source_text_snippet: Actual text being referenced (max 200 chars)
        claim_in_paper: What our paper says about this source
        alignment_score: How well claim matches source (0-1)
        citation_location: Where citation appears in our paper
    """

    paper: dict[str, Any] = Field(default_factory=dict)
    source_paper: dict[str, Any] = Field(default_factory=dict)
    page_number: int = 0
    paragraph_index: int = 0
    source_text_snippet: str = ""
    claim_in_paper: str = ""
    alignment_score: float = Field(default=0.5, ge=0.0, le=1.0)
    citation_location: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "paper": self.paper,
            "source_paper": self.source_paper,
            "page": self.page_number,
            "paragraph": self.paragraph_index,
            "snippet": self.source_text_snippet,
            "claim": self.claim_in_paper,
            "alignment": self.alignment_score,
            "location": self.citation_location,
        }


class CitationTraceReport(BaseModel):
    """Complete citation traceability report.

    Attributes:
        total_citations: Total citations traced
        traceable_citations: Citations with page+paragraph
        untraceable_citations: Citations without exact location
        average_alignment: Average alignment score
        low_alignment_citations: Citations with low alignment
        citations: All traceable citations
        verification_html_path: Path to verification HTML
    """

    total_citations: int = 0
    traceable_citations: int = 0
    untraceable_citations: int = 0
    average_alignment: float = 0.0
    low_alignment_citations: list[TraceableCitation] = Field(default_factory=list)
    citations: list[TraceableCitation] = Field(default_factory=list)
    verification_html_path: str = ""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        # Calculate derived fields
        self.total_citations = len(self.citations)
        self.traceable_citations = sum(1 for c in self.citations if c.page_number > 0)
        self.untraceable_citations = self.total_citations - self.traceable_citations

        if self.citations:
            self.average_alignment = sum(
                c.alignment_score for c in self.citations
            ) / len(self.citations)

        self.low_alignment_citations = [
            c for c in self.citations if c.alignment_score < 0.6
        ]


@dataclass
class SourceLocation:
    """Location in source document.

    Attributes:
        page: Page number
        paragraph: Paragraph index
        text: Paragraph text
    """

    page: int
    paragraph: int
    text: str


class PDFTextExtractor:
    """Extract text from PDF with page+paragraph information.

    This extractor:
    1. Reads PDF files
    2. Extracts text per page
    3. Splits into paragraphs
    4. Provides location-based access

    Attributes:
        source_pdfs: Dictionary of DOI to PDF path
    """

    def __init__(self, source_pdfs: dict[str, Path]):
        """Initialize PDF text extractor.

        Args:
            source_pdfs: Dictionary of DOI to PDF path
        """
        self.source_pdfs = source_pdfs
        self._cache: dict[str, list[list[SourceLocation]]] = {}

    async def extract_text_with_locations(
        self,
        doi: str,
    ) -> list[list[SourceLocation]]:
        """Extract text with page+paragraph locations.

        Args:
            doi: Paper DOI

        Returns:
            List of pages, each with list of paragraph locations
        """
        if doi in self._cache:
            return self._cache[doi]

        pdf_path = self.source_pdfs.get(doi)
        if not pdf_path:
            logger.warning(f"No PDF found for DOI: {doi}")
            return []

        try:
            # Try PyMuPDF (fitz) first
            locations = await self._extract_with_pymupdf(pdf_path)
        except ImportError:
            try:
                # Fallback to pdfplumber
                locations = await self._extract_with_pdfplumber(pdf_path)
            except ImportError:
                logger.error("No PDF library available (install PyMuPDF or pdfplumber)")
                return []

        self._cache[doi] = locations
        return locations

    async def _extract_with_pymupdf(
        self,
        pdf_path: Path,
    ) -> list[list[SourceLocation]]:
        """Extract text using PyMuPDF.

        Args:
            pdf_path: Path to PDF

        Returns:
            List of pages with paragraph locations
        """
        import fitz  # PyMuPDF

        doc = fitz.open(pdf_path)
        all_locations = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()

            # Split into paragraphs
            paragraphs = text.split("\n\n")
            page_locations = []

            for para_idx, para_text in enumerate(paragraphs):
                if para_text.strip():
                    page_locations.append(
                        SourceLocation(
                            page=page_num + 1,  # 1-indexed
                            paragraph=para_idx,
                            text=para_text.strip(),
                        )
                    )

            all_locations.append(page_locations)

        doc.close()
        return all_locations

    async def _extract_with_pdfplumber(
        self,
        pdf_path: Path,
    ) -> list[list[SourceLocation]]:
        """Extract text using pdfplumber.

        Args:
            pdf_path: Path to PDF

        Returns:
            List of pages with paragraph locations
        """
        import pdfplumber

        all_locations = []

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text:
                    continue

                # Split into paragraphs
                paragraphs = text.split("\n\n")
                page_locations = []

                for para_idx, para_text in enumerate(paragraphs):
                    if para_text.strip():
                        page_locations.append(
                            SourceLocation(
                                page=page_num + 1,
                                paragraph=para_idx,
                                text=para_text.strip(),
                            )
                        )

                all_locations.append(page_locations)

        return all_locations


class CitationTracer:
    """Trace citations to exact source locations.

    This tracer:
    1. Extracts all citations from paper
    2. Finds corresponding source PDFs
    3. Traces to page+paragraph
    4. Calculates alignment scores
    5. Generates verification HTML

    Usage::

        tracer = CitationTracer(source_pdfs)
        citations = await tracer.trace_all_citations(paper_text, source_pdfs)
        html = await tracer.generate_verification_links(citations)

    Attributes:
        extractor: PDF text extractor
    """

    def __init__(self, source_pdfs: dict[str, Path]):
        """Initialize citation tracer.

        Args:
            source_pdfs: Dictionary of DOI to PDF path
        """
        self.extractor = PDFTextExtractor(source_pdfs)

    async def trace_all_citations(
        self,
        paper_text: str,
        source_pdfs: dict[str, Path] | None = None,
    ) -> list[TraceableCitation]:
        """Trace all citations to exact source locations.

        Args:
            paper_text: Full paper text
            source_pdfs: Optional override for source PDFs

        Returns:
            List of traceable citations
        """
        if source_pdfs:
            self.extractor = PDFTextExtractor(source_pdfs)

        # Extract citations from paper
        citations_in_paper = self._extract_citations_from_paper(paper_text)

        # Trace each citation
        traceable = []
        for citation_info in citations_in_paper:
            doi = citation_info.get("doi")
            if not doi:
                continue

            # Get source text locations
            locations = await self.extractor.extract_text_with_locations(doi)

            # Find best matching location
            if locations:
                best_match = await self._find_best_matching_location(
                    citation_info.get("claim", ""),
                    locations,
                )

                if best_match:
                    traceable.append(
                        TraceableCitation(
                            paper=citation_info.get("paper", {}),
                            source_paper={"doi": doi},
                            page_number=best_match.page,
                            paragraph_index=best_match.paragraph,
                            source_text_snippet=best_match.text[:200],
                            claim_in_paper=citation_info.get("claim", ""),
                            alignment_score=self._calculate_alignment(
                                citation_info.get("claim", ""),
                                best_match.text,
                            ),
                            citation_location=citation_info.get("location", ""),
                        )
                    )

        return traceable

    def _extract_citations_from_paper(
        self,
        paper_text: str,
    ) -> list[dict[str, Any]]:
        """Extract citations from paper text.

        Args:
            paper_text: Full paper text

        Returns:
            List of citation information dictionaries
        """
        import re

        citations = []

        # Find citation patterns with context
        # Pattern: claim text followed by citation
        patterns = [
            r"([^.]+)\.\s*\[([\d,\s]+)\]",  # Claim [1, 2, 3]
            r"([^.]+)\.\s*\(([A-Z][a-z]+),?\s*(\d{4})\)",  # Claim (Smith, 2024)
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, paper_text):
                claim = match.group(1).strip()
                location = match.group(0)

                if "[" in pattern:
                    # Numeric citation
                    ref_nums = [int(x.strip()) for x in match.group(2).split(",")]
                    citations.append(
                        {
                            "type": "numeric",
                            "refs": ref_nums,
                            "claim": claim,
                            "location": location,
                            "paper": {},
                            "doi": "",
                        }
                    )
                else:
                    # Author-year citation
                    author = match.group(3)
                    year = match.group(4)
                    citations.append(
                        {
                            "type": "author_year",
                            "author": author,
                            "year": year,
                            "claim": claim,
                            "location": location,
                            "paper": {},
                            "doi": "",
                        }
                    )

        return citations

    async def _find_best_matching_location(
        self,
        claim: str,
        locations: list[list[SourceLocation]],
    ) -> SourceLocation | None:
        """Find best matching location for a claim.

        Args:
            claim: Claim text from paper
            locations: All source locations

        Returns:
            Best matching location
        """
        if not locations or not claim:
            return None

        best_match = None
        best_score = 0.0

        # Extract keywords from claim
        claim_keywords = self._extract_keywords(claim)

        # Search all locations
        for page_locations in locations:
            for location in page_locations:
                # Calculate keyword overlap
                location_keywords = self._extract_keywords(location.text)
                overlap = len(claim_keywords & location_keywords)
                score = overlap / max(len(claim_keywords), 1)

                if score > best_score:
                    best_score = score
                    best_match = location

        return best_match

    def _extract_keywords(self, text: str) -> set[str]:
        """Extract keywords from text.

        Args:
            text: Text to extract from

        Returns:
            Set of keywords
        """
        import re

        # Remove common words
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "as",
            "is",
            "was",
            "are",
            "were",
            "been",
            "this",
            "that",
            "these",
            "those",
            "it",
            "its",
            "we",
            "our",
            "they",
        }

        # Extract words
        words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
        keywords = {w for w in words if w not in stop_words and len(w) > 3}

        return keywords

    def _calculate_alignment(
        self,
        claim: str,
        source_text: str,
    ) -> float:
        """Calculate alignment score between claim and source.

        Args:
            claim: Claim from paper
            source_text: Source text at location

        Returns:
            Alignment score (0-1)
        """
        if not claim or not source_text:
            return 0.0

        # Keyword overlap
        claim_keywords = self._extract_keywords(claim)
        source_keywords = self._extract_keywords(source_text)

        if not claim_keywords or not source_keywords:
            return 0.5

        overlap = len(claim_keywords & source_keywords)
        keyword_score = overlap / min(len(claim_keywords), len(source_keywords))

        # Check for contradiction indicators
        contradiction_words = {
            "however",
            "but",
            "contrary",
            "opposite",
            "disagree",
            "contradict",
            "challenge",
            "question",
        }

        claim_lower = claim.lower()
        source_lower = source_text.lower()

        has_contradiction = any(
            w in claim_lower or w in source_lower for w in contradiction_words
        )

        # Adjust score
        if has_contradiction:
            return min(0.5, keyword_score)
        else:
            return max(0.5, keyword_score)

    async def generate_verification_links(
        self,
        citations: list[TraceableCitation],
        output_path: Path | str | None = None,
    ) -> str:
        """Generate HTML verification page.

        Args:
            citations: List of traceable citations
            output_path: Output file path (optional)

        Returns:
            HTML content
        """
        html = self._generate_verification_html(citations)

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"Verification page saved to {output_path}")

        return html

    def _generate_verification_html(
        self,
        citations: list[TraceableCitation],
    ) -> str:
        """Generate verification HTML content.

        Args:
            citations: List of traceable citations

        Returns:
            HTML string
        """
        html = (
            """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Citation Verification Links</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
        h1 { color: #333; }
        .citation { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .citation.good { border-left: 4px solid #28a745; }
        .citation.warning { border-left: 4px solid #ffc107; }
        .citation.bad { border-left: 4px solid #dc3545; }
        .claim { background: #f8f9fa; padding: 10px; margin: 10px 0; }
        .source { background: #e9ecef; padding: 10px; margin: 10px 0; }
        .metadata { color: #666; font-size: 0.9em; }
        .score { font-weight: bold; }
        .score.good { color: #28a745; }
        .score.warning { color: #ffc107; }
        .score.bad { color: #dc3545; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background: #f2f2f2; }
    </style>
</head>
<body>
    <h1>Citation Verification Links</h1>
    <p>This page provides clickable links to verify each citation against its source.</p>

    <h2>Summary</h2>
    <table>
        <tr>
            <th>Total Citations</th>
            <td>"""
            + str(len(citations))
            + """</td>
        </tr>
        <tr>
            <th>Traceable</th>
            <td>"""
            + str(sum(1 for c in citations if c.page_number > 0))
            + """</td>
        </tr>
        <tr>
            <th>Average Alignment</th>
            <td>"""
            + f"{sum(c.alignment_score for c in citations) / max(len(citations), 1):.2f}"
            + """</td>
        </tr>
    </table>

    <h2>Citations</h2>
"""
        )

        for i, citation in enumerate(citations, 1):
            # Determine quality class
            if citation.alignment_score >= 0.8:
                quality_class = "good"
            elif citation.alignment_score >= 0.6:
                quality_class = "warning"
            else:
                quality_class = "bad"

            html += f"""
    <div class="citation {quality_class}">
        <h3>Citation {i}</h3>
        <div class="metadata">
            <strong>DOI:</strong> {citation.source_paper.get("doi", "N/A")} |
            <strong>Page:</strong> {citation.page_number} |
            <strong>Paragraph:</strong> {citation.paragraph_index} |
            <strong>Alignment:</strong> <span class="score {quality_class}">{citation.alignment_score:.2f}</span>
        </div>

        <div class="claim">
            <strong>Claim in Paper:</strong><br>
            {citation.claim_in_paper}
        </div>

        <div class="source">
            <strong>Source Text (Page {citation.page_number}, Paragraph {citation.paragraph_index + 1}):</strong><br>
            {citation.source_text_snippet}
        </div>
    </div>
"""

        html += """
</body>
</html>
"""

        return html


async def trace_citations(
    paper_text: str,
    source_pdfs: dict[str, Path],
    output_html: Path | str | None = None,
) -> CitationTraceReport:
    """Convenience function for citation tracing.

    Args:
        paper_text: Paper text
        source_pdfs: Source PDF paths
        output_html: Output HTML path

    Returns:
        CitationTraceReport
    """
    tracer = CitationTracer(source_pdfs)
    citations = await tracer.trace_all_citations(paper_text, source_pdfs)

    if output_html:
        await tracer.generate_verification_links(citations, output_html)

    return CitationTraceReport(
        citations=citations,
        verification_html_path=str(output_html) if output_html else "",
    )
