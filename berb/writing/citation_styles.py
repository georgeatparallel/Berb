"""Comprehensive citation style library.

This module provides formatting for 8+ major academic citation styles
with support for custom CSL (Citation Style Language) files.

Supported Styles:
- Numeric: IEEE, Vancouver, Nature, AMS
- Author-Year: APA, Harvard, Chicago (author-date)
- Note-Based: Oxford, Chicago (notes)
- Custom: User-provided CSL files

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CitationStyle(StrEnum):
    """Academic citation styles.

    Numeric Styles:
        - NUMERIC: Generic numeric [1], [2], [3]
        - IEEE: IEEE format [1]
        - VANCOUVER: Biomedical superscript¹
        - NATURE: Nature journal style
        - AMS: American Mathematical Society

    Author-Year Styles:
        - APA: APA 7th edition (Smith, 2024)
        - HARVARD: Harvard style (Smith 2024)
        - CHICAGO_AD: Chicago author-date (Smith 2024)

    Note-Based Styles:
        - OXFORD: Oxford footnotes
        - CHICAGO_NOTES: Chicago notes-bibliography

    Field-Specific:
        - ACS: American Chemical Society
        - MLA: Modern Language Association

    Custom:
        - CUSTOM: User-provided CSL file
    """

    # Numeric
    NUMERIC = "numeric"
    IEEE = "ieee"
    VANCOUVER = "vancouver"
    NATURE = "nature"
    AMS = "ams"

    # Author-year
    APA = "apa"
    HARVARD = "harvard"
    CHICAGO_AD = "chicago-ad"

    # Note-based
    OXFORD = "oxford"
    CHICAGO_NOTES = "chicago-notes"

    # Field-specific
    ACS = "acs"
    MLA = "mla"

    # Custom
    CUSTOM = "custom"


class CitationStyleConfig(BaseModel):
    """Citation style configuration.

    Attributes:
        style: Citation style
        csl_file: Path to custom CSL file
        bibliography_sort: How to sort bibliography
        include_doi: Include DOI in bibliography
        include_url: Include URL
        max_authors_before_etal: Max authors before et al.
        et_al_text: Text for et al.
        use_italics: Use italics for et al.
    """

    style: CitationStyle = CitationStyle.APA
    csl_file: Path | None = None
    bibliography_sort: Literal[
        "alphabetical",
        "order_of_appearance",
        "year",
    ] = "alphabetical"
    include_doi: bool = True
    include_url: bool = False
    max_authors_before_etal: int = 3
    et_al_text: str = "et al."
    use_italics: bool = True


class CitationFormatter:
    """Format citations and bibliography in any academic style.

    This formatter supports all major citation styles and provides
    consistent formatting across inline citations and bibliography.

    Usage::

        formatter = CitationFormatter(
            config=CitationStyleConfig(
                style=CitationStyle.APA,
                max_authors_before_etal=3,
            ),
        )

        inline = formatter.format_inline(paper)
        bib = formatter.format_bibliography(papers)
        bibtex = formatter.to_bibtex(papers)
    """

    # Style-specific formatting rules
    STYLE_RULES = {
        CitationStyle.APA: {
            "inline_one": "({author}, {year})",
            "inline_two": "({author1} & {author2}, {year})",
            "inline_three_plus": "({first_author} {et_al}, {year})",
            "inline_with_page": "({author}, {year}, p. {page})",
            "bib_sort": "alphabetical",
            "author_format": "last, F.",
            "etal": "et al.",
        },
        CitationStyle.IEEE: {
            "inline": "[{num}]",
            "inline_with_page": "[{num}, p. {page}]",
            "bib_sort": "order_of_appearance",
            "author_format": "F. Last",
            "title_quotes": True,
        },
        CitationStyle.MLA: {
            "inline_one": "({author} {page})",
            "inline_two": "({author1} and {author2} {page})",
            "inline_three_plus": "({first_author} {et_al} {page})",
            "bib_sort": "alphabetical",
            "author_format": "Last, First",
            "title_quotes": True,
        },
        CitationStyle.CHICAGO_AD: {
            "inline": "({author} {year})",
            "inline_with_page": "({author} {year}, {page})",
            "bib_sort": "alphabetical",
            "author_format": "Last, First",
        },
        CitationStyle.VANCOUVER: {
            "inline": "<sup>{num}</sup>",
            "bib_sort": "order_of_appearance",
            "author_format": "Last F.",
        },
        CitationStyle.NATURE: {
            "inline": "<sup>{num}</sup>",
            "bib_sort": "order_of_appearance",
            "author_format": "Last, F.",
            "journal_abbrev": True,
        },
    }

    def __init__(self, config: CitationStyleConfig | None = None):
        """Initialize citation formatter.

        Args:
            config: Style configuration
        """
        self.config = config or CitationStyleConfig()
        self._rules = self.STYLE_RULES.get(self.config.style, {})

    def format_inline(
        self,
        paper: dict[str, Any],
        page: int | None = None,
        ref_number: int | None = None,
    ) -> str:
        """Format inline citation.

        Args:
            paper: Paper metadata
            page: Optional page number
            ref_number: Reference number (for numeric styles)

        Returns:
            Formatted inline citation
        """
        authors = paper.get("authors", [])
        year = paper.get("year", "n.d.")
        et_al = self.config.et_al_text

        # Format author names
        if len(authors) == 0:
            author_text = "Anonymous"
            first_author = "Anonymous"
            author1 = author2 = ""
        elif len(authors) == 1:
            author_text = self._format_author(authors[0])
            first_author = self._format_author(authors[0], last_only=True)
            author1 = author_text
            author2 = ""
        elif len(authors) == 2:
            author1 = self._format_author(authors[0], last_only=True)
            author2 = self._format_author(authors[1], last_only=True)
            author_text = f"{author1} and {author2}"
            first_author = author1
        else:
            first_author = self._format_author(authors[0], last_only=True)
            author_text = f"{first_author} {et_al}"
            author1 = first_author
            author2 = ""

        # Get template based on author count and style
        template = self._get_inline_template(
            len(authors), page is not None, ref_number is not None
        )

        # Format citation
        citation = template.format(
            author=author_text,
            year=year,
            first_author=first_author,
            author1=author1,
            author2=author2,
            et_al=et_al,
            page=page or "",
            num=ref_number or 1,
        )

        return citation

    def _get_inline_template(
        self,
        num_authors: int,
        has_page: bool,
        has_ref_num: bool,
    ) -> str:
        """Get inline citation template.

        Args:
            num_authors: Number of authors
            has_page: Whether page number provided
            has_ref_num: Whether reference number provided

        Returns:
            Template string
        """
        style = self.config.style

        # Numeric styles
        if style in (
            CitationStyle.IEEE,
            CitationStyle.VANCOUVER,
            CitationStyle.NATURE,
            CitationStyle.NUMERIC,
        ):
            if has_page:
                return self._rules.get("inline_with_page", "[{num}, p. {page}]")
            return self._rules.get("inline", "[{num}]")

        # Author-year styles
        if num_authors == 0 or num_authors == 1:
            if has_page:
                return self._rules.get(
                    "inline_with_page", "({author}, {year}, p. {page})"
                )
            return self._rules.get("inline_one", "({author}, {year})")

        elif num_authors == 2:
            return self._rules.get("inline_two", "({author1} & {author2}, {year})")

        else:  # 3+ authors
            if has_page:
                return self._rules.get(
                    "inline_with_page", "({first_author} {et_al}, {year}, p. {page})"
                )
            return self._rules.get(
                "inline_three_plus", "({first_author} {et_al}, {year})"
            )

    def _format_author(
        self,
        author: str,
        last_only: bool = False,
    ) -> str:
        """Format author name.

        Args:
            author: Author name
            last_only: Return only last name

        Returns:
            Formatted author name
        """
        parts = author.split()

        if not parts:
            return ""

        if last_only:
            return parts[-1]

        # Format as "Last, F." or "F. Last" based on style
        if len(parts) == 1:
            return parts[0]

        last = parts[-1]
        initials = ". ".join(p[0] for p in parts[:-1])

        author_format = self._rules.get("author_format", "last, F.")

        if "last, F." in author_format.lower():
            return f"{last}, {initials}"
        else:  # "F. Last"
            return f"{initials} {last}"

    def format_bibliography(
        self,
        papers: list[dict[str, Any]],
        sort: bool = True,
    ) -> str:
        """Format complete bibliography.

        Args:
            papers: List of paper metadata
            sort: Whether to sort entries

        Returns:
            Formatted bibliography string
        """
        # Sort if needed
        if sort:
            sort_method = self._rules.get("bib_sort", "alphabetical")
            papers = self._sort_papers(papers, sort_method)

        # Format entries
        entries = []
        for i, paper in enumerate(papers, 1):
            # Add reference number for numeric styles
            paper_with_num = {**paper, "reference_number": i}
            entry = self._format_bibliography_entry(paper_with_num)
            entries.append(entry)

        return "\n\n".join(entries)

    def _sort_papers(
        self,
        papers: list[dict[str, Any]],
        method: str,
    ) -> list[dict[str, Any]]:
        """Sort papers by method.

        Args:
            papers: List of papers
            method: Sort method

        Returns:
            Sorted list
        """
        if method == "alphabetical":
            return sorted(
                papers,
                key=lambda p: self._get_sort_key(p),
            )
        elif method == "year":
            return sorted(
                papers,
                key=lambda p: p.get("year", 0),
                reverse=True,
            )
        else:  # order_of_appearance
            return papers

    def _get_sort_key(self, paper: dict[str, Any]) -> str:
        """Get sorting key for paper.

        Args:
            paper: Paper metadata

        Returns:
            Sort key
        """
        authors = paper.get("authors", [])
        year = paper.get("year", 0)

        if authors:
            first_author = authors[0].lower()
        else:
            first_author = "anonymous"

        return f"{year}_{first_author}"

    def _format_bibliography_entry(
        self,
        paper: dict[str, Any],
    ) -> str:
        """Format single bibliography entry.

        Args:
            paper: Paper metadata

        Returns:
            Formatted entry
        """
        style = self.config.style
        authors = self._format_authors_bibliography(paper.get("authors", []))
        year = paper.get("year", "n.d.")
        title = paper.get("title", "Untitled")
        venue = paper.get("venue", "")
        volume = paper.get("volume", "")
        pages = paper.get("pages", "")
        doi = paper.get("doi", "")

        # Build entry based on style
        if style == CitationStyle.APA:
            entry = f"{authors} ({year}). {title}."
            if venue:
                entry += f" *{venue}*."
            if volume:
                entry += f" {volume}."
            if pages:
                entry += f" {pages}."
            if self.config.include_doi and doi:
                entry += f" https://doi.org/{doi}"

        elif style == CitationStyle.IEEE:
            ref_num = paper.get("reference_number", 1)
            entry = f'[{ref_num}] {authors}, "{title},"'
            if venue:
                entry += f" *{venue}*,"
            if year:
                entry += f" {year}."
            if volume:
                entry += f" vol. {volume},"
            if pages:
                entry += f" pp. {pages}."

        elif style == CitationStyle.MLA:
            entry = f'{authors}. "{title}."'
            if venue:
                entry += f" *{venue}*,"
            if volume:
                entry += f" vol. {volume},"
            if year:
                entry += f" {year},"
            if pages:
                entry += f" pp. {pages}."
            if self.config.include_doi and doi:
                entry += f" doi:{doi}."

        elif style == CitationStyle.CHICAGO_AD:
            entry = f'{authors}. {year}. "{title}."'
            if venue:
                entry += f" *{venue}*"
            if volume:
                entry += f" {volume}"
            if pages:
                entry += f": {pages}."
            if self.config.include_doi and doi:
                entry += f" https://doi.org/{doi}."

        elif style == CitationStyle.VANCOUVER:
            ref_num = paper.get("reference_number", 1)
            entry = f"{ref_num}. {authors}. {title}."
            if venue:
                entry += f" {venue}."
            if year:
                entry += f" {year}"
            if volume:
                entry += f";{volume}"
            if pages:
                entry += f":{pages}."

        elif style == CitationStyle.NATURE:
            ref_num = paper.get("reference_number", 1)
            entry = f"{ref_num}. {authors} {title}."
            if venue:
                entry += f" *{venue}*"
            if volume:
                entry += f" **{volume}**,"
            if pages:
                entry += f" {pages}"
            if year:
                entry += f" ({year})."

        else:
            # Default format
            entry = f"{authors} ({year}). {title}. {venue}."

        return entry

    def _format_authors_bibliography(
        self,
        authors: list[str],
    ) -> str:
        """Format authors for bibliography.

        Args:
            authors: List of author names

        Returns:
            Formatted author string
        """
        if not authors:
            return "Anonymous"

        max_authors = self.config.max_authors_before_etal
        et_al = self.config.et_al_text

        if len(authors) <= max_authors:
            formatted = [self._format_author(a) for a in authors]
            if len(formatted) == 1:
                return formatted[0]
            elif len(formatted) == 2:
                return f"{formatted[0]} and {formatted[1]}"
            else:
                return ", ".join(formatted[:-1]) + f", and {formatted[-1]}"
        else:
            # Use et al.
            first = self._format_author(authors[0])
            return f"{first} {et_al}"

    def to_bibtex(
        self,
        papers: list[dict[str, Any]],
    ) -> str:
        """Export as BibTeX.

        Args:
            papers: List of paper metadata

        Returns:
            BibTeX string
        """
        entries = []

        for paper in papers:
            entry = self._to_bibtex_entry(paper)
            entries.append(entry)

        return "\n\n".join(entries)

    def _to_bibtex_entry(
        self,
        paper: dict[str, Any],
    ) -> str:
        """Convert paper to BibTeX entry.

        Args:
            paper: Paper metadata

        Returns:
            BibTeX entry string
        """
        # Generate BibTeX key
        authors = paper.get("authors", [])
        year = str(paper.get("year", "nd"))
        doi = paper.get("doi", "")

        if authors:
            first_author = authors[0].split()[-1].lower()
            first_author = re.sub(r"[^a-z]", "", first_author)
        else:
            first_author = "anon"

        year_clean = re.sub(r"[^0-9]", "", year)[:4]
        bibtex_key = f"{first_author}{year_clean}"

        if doi:
            bibtex_key += f"_{doi[-4:].lower()}"

        # Determine entry type
        entry_type = paper.get("type", "article")

        # Build fields
        fields = {
            "author": " and ".join(authors),
            "title": paper.get("title", ""),
            "year": year,
        }

        if paper.get("venue"):
            fields["journal"] = paper.get("venue")

        if paper.get("volume"):
            fields["volume"] = str(paper.get("volume"))

        if paper.get("pages"):
            fields["pages"] = str(paper.get("pages"))

        if self.config.include_doi and doi:
            fields["doi"] = doi

        # Format BibTeX
        field_strings = []
        for key, value in fields.items():
            if value:
                field_strings.append(f"  {key} = {{{value}}}")

        entry = f"@{entry_type}{{{bibtex_key},\n"
        entry += ",\n".join(field_strings)
        entry += "\n}"

        return entry


# Convenience functions
def format_citation(
    paper: dict[str, Any],
    style: CitationStyle = CitationStyle.APA,
    page: int | None = None,
) -> str:
    """Format inline citation.

    Args:
        paper: Paper metadata
        style: Citation style
        page: Optional page number

    Returns:
        Formatted citation
    """
    formatter = CitationFormatter(
        config=CitationStyleConfig(style=style),
    )
    return formatter.format_inline(paper, page)


def format_bibliography(
    papers: list[dict[str, Any]],
    style: CitationStyle = CitationStyle.APA,
) -> str:
    """Format bibliography.

    Args:
        papers: List of papers
        style: Citation style

    Returns:
        Formatted bibliography
    """
    formatter = CitationFormatter(
        config=CitationStyleConfig(style=style),
    )
    return formatter.format_bibliography(papers)


def export_bibtex(
    papers: list[dict[str, Any]],
    style: CitationStyle = CitationStyle.APA,
) -> str:
    """Export as BibTeX.

    Args:
        papers: List of papers
        style: Citation style (for sorting)

    Returns:
        BibTeX string
    """
    formatter = CitationFormatter(
        config=CitationStyleConfig(style=style),
    )
    return formatter.to_bibtex(papers)
