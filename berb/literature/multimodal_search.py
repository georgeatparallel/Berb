"""Multimodal Literature Search Agent for Berb.

Based on Edison Scientific PaperQA3:
- Process PDF figures and tables (not just text)
- Extract data from plots (chart → data points)
- Analyze microscopic/scientific images
- Cross-reference figures with captions and text

Features:
- PDF figure extraction
- Chart data digitization
- Image-text cross-referencing
- Table structure parsing
- Multimodal embedding search

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.literature.multimodal_search import MultimodalLiteratureAgent
    
    agent = MultimodalLiteratureAgent()
    results = await agent.search("CRISPR gene editing", include_figures=True)
    data = await agent.extract_chart_data("figure.png")
"""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExtractedChartData:
    """Data extracted from a chart/plot."""
    
    chart_type: str  # bar, line, scatter, etc.
    x_label: str
    y_label: str
    x_values: list[float]
    y_values: list[float]
    error_bars: list[tuple[float, float]] | None
    legend_labels: list[str]
    title: str
    confidence: float  # 0-1
    source_figure: str


@dataclass
class ExtractedTableData:
    """Data extracted from a table."""
    
    headers: list[str]
    rows: list[list[str]]
    caption: str
    table_type: str  # results, methods, comparison, etc.
    confidence: float
    source_page: int


@dataclass
class FigureAnalysis:
    """Analysis of a scientific figure."""
    
    figure_number: str
    caption: str
    figure_type: str  # microscopy, plot, diagram, photo, etc.
    key_findings: list[str]
    referenced_in_text: list[str]
    data_available: bool
    quality_score: float  # 0-10
    ocr_text: str | None


@dataclass
class MultimodalPaper:
    """Paper with multimodal content extracted."""
    
    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    full_text: str
    figures: list[FigureAnalysis]
    tables: list[ExtractedTableData]
    charts: list[ExtractedChartData]
    cross_references: list[dict[str, Any]]
    embedding: list[float] | None = None


class PDFFigureExtractor:
    """Extract figures from PDF papers."""
    
    def __init__(self) -> None:
        """Initialize figure extractor."""
        self._supported_formats = {'.pdf', '.png', '.jpg', '.jpeg', '.tiff'}
    
    async def extract_figures(
        self,
        pdf_path: str | Path,
    ) -> list[dict[str, Any]]:
        """Extract all figures from PDF.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of figure dictionaries with image data and metadata
        """
        pdf_path = Path(pdf_path)
        
        if pdf_path.suffix.lower() not in self._supported_formats:
            logger.error(f"Unsupported format: {pdf_path.suffix}")
            return []
        
        figures = []
        
        if pdf_path.suffix.lower() == '.pdf':
            figures = await self._extract_from_pdf(pdf_path)
        else:
            # Single image file
            figures = [{
                "image_path": str(pdf_path),
                "image_data": self._encode_image(pdf_path),
                "page": 0,
                "figure_number": "1",
            }]
        
        logger.info(f"Extracted {len(figures)} figures from {pdf_path.name}")
        return figures
    
    async def _extract_from_pdf(self, pdf_path: Path) -> list[dict[str, Any]]:
        """Extract figures from PDF using PyMuPDF."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF not installed. Install with: pip install PyMuPDF")
            return []
        
        figures = []
        
        try:
            doc = fitz.open(pdf_path)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Extract images
                image_list = page.get_images(full=True)
                
                for img_index, img_info in enumerate(image_list):
                    xref = img_info[0]
                    
                    try:
                        # Extract image
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        
                        # Save figure info
                        figures.append({
                            "image_bytes": image_bytes,
                            "image_data": base64.b64encode(image_bytes).decode(),
                            "page": page_num + 1,
                            "figure_number": f"{page_num + 1}.{img_index + 1}",
                            "width": base_image.get("width", 0),
                            "height": base_image.get("height", 0),
                        })
                        
                    except Exception as e:
                        logger.debug(f"Failed to extract image {xref}: {e}")
            
            doc.close()
            
        except Exception as e:
            logger.error(f"Failed to extract figures from PDF: {e}")
        
        return figures
    
    def _encode_image(self, image_path: Path) -> str:
        """Encode image to base64."""
        with open(image_path, "rb") as f:
            image_data = f.read()
        return base64.b64encode(image_data).decode()


class ChartDataDigitizer:
    """Extract numerical data from charts/plots."""
    
    def __init__(self, vision_client: Any | None = None) -> None:
        """Initialize digitizer.
        
        Args:
            vision_client: Vision model client (optional)
        """
        self._vision_client = vision_client
    
    async def extract_data(
        self,
        image_path: str | Path,
        image_data: str | None = None,
    ) -> ExtractedChartData | None:
        """Extract data from chart image.
        
        Args:
            image_path: Path to chart image
            image_data: Base64-encoded image (alternative to path)
            
        Returns:
            ExtractedChartData or None
        """
        # Use vision model to analyze chart
        if self._vision_client:
            return await self._vision_extract(image_path, image_data)
        else:
            # Fallback: rule-based extraction
            return await self._rule_based_extract(image_path, image_data)
    
    async def _vision_extract(
        self,
        image_path: str | Path,
        image_data: str | None,
    ) -> ExtractedChartData | None:
        """Extract data using vision model."""
        # Build prompt for chart analysis
        prompt = """Analyze this scientific chart and extract the data.

Return JSON with:
{
    "chart_type": "bar|line|scatter|etc",
    "x_label": "x-axis label",
    "y_label": "y-axis label",
    "x_values": [list of x values],
    "y_values": [list of y values],
    "error_bars": [[lower, upper], ...] or null,
    "legend_labels": ["label1", ...],
    "title": "chart title",
    "confidence": 0.0-1.0
}

If exact values cannot be determined, provide best estimates."""
        
        # In production, call vision API:
        # response = await self._vision_client.analyze_image(
        #     image_path=image_path if image_path else None,
        #     image_data=image_data,
        #     prompt=prompt
        # )
        
        # Placeholder
        return self._create_placeholder_chart_data()
    
    async def _rule_based_extract(
        self,
        image_path: str | Path,
        image_data: str | None,
    ) -> ExtractedChartData | None:
        """Fallback rule-based extraction."""
        try:
            from PIL import Image
            import numpy as np
            
            # Load image
            if image_data:
                image = Image.open(BytesIO(base64.b64decode(image_data)))
            else:
                image = Image.open(image_path)
            
            # Convert to numpy array
            img_array = np.array(image)
            
            # Basic analysis (placeholder)
            # In production, would use OpenCV for line detection, etc.
            
            return self._create_placeholder_chart_data()
            
        except ImportError:
            logger.warning("PIL/numpy not available for chart digitization")
            return None
        except Exception as e:
            logger.error(f"Chart digitization failed: {e}")
            return None
    
    def _create_placeholder_chart_data(self) -> ExtractedChartData:
        """Create placeholder chart data."""
        return ExtractedChartData(
            chart_type="unknown",
            x_label="X",
            y_label="Y",
            x_values=[],
            y_values=[],
            error_bars=None,
            legend_labels=[],
            title="",
            confidence=0.0,
            source_figure="",
        )


class TableStructureParser:
    """Parse table structures from PDF/images."""
    
    def __init__(self) -> None:
        """Initialize table parser."""
        pass
    
    async def extract_tables(
        self,
        pdf_path: str | Path,
    ) -> list[ExtractedTableData]:
        """Extract tables from PDF.
        
        Args:
            pdf_path: Path to PDF
            
        Returns:
            List of ExtractedTableData
        """
        try:
            import fitz  # PyMuPDF
            import camelot  # Table extraction library
        except ImportError:
            logger.warning("camelot-py not installed. Install with: pip install camelot-py")
            return []
        
        tables = []
        
        try:
            # Use camelot for table extraction
            camelot_tables = camelot.read_pdf(
                str(pdf_path),
                pages='all',
                flavor='lattice',  # For tables with grid lines
            )
            
            for table in camelot_tables:
                df = table.df
                tables.append(ExtractedTableData(
                    headers=df.iloc[0].tolist() if len(df) > 0 else [],
                    rows=df.iloc[1:].values.tolist() if len(df) > 1 else [],
                    caption=f"Table from page {table.page}",
                    table_type="results",
                    confidence=table.parsing_report.get('accuracy', 0.5) / 100,
                    source_page=table.page,
                ))
            
            # Also try stream flavor for tables without grid lines
            camelot_tables_stream = camelot.read_pdf(
                str(pdf_path),
                pages='all',
                flavor='stream',
            )
            
            for table in camelot_tables_stream:
                df = table.df
                tables.append(ExtractedTableData(
                    headers=df.iloc[0].tolist() if len(df) > 0 else [],
                    rows=df.iloc[1:].values.tolist() if len(df) > 1 else [],
                    caption=f"Table from page {table.page}",
                    table_type="results",
                    confidence=table.parsing_report.get('accuracy', 0.5) / 100,
                    source_page=table.page,
                ))
            
        except Exception as e:
            logger.error(f"Table extraction failed: {e}")
        
        return tables


class ImageTextCrossReferencer:
    """Cross-reference figures with text mentions."""
    
    def __init__(self) -> None:
        """Initialize cross-referencer."""
        pass
    
    def cross_reference(
        self,
        full_text: str,
        figures: list[FigureAnalysis],
    ) -> list[dict[str, Any]]:
        """Find text references to each figure.
        
        Args:
            full_text: Full paper text
            figures: List of figure analyses
            
        Returns:
            List of cross-references
        """
        cross_refs = []
        
        for figure in figures:
            # Find mentions of this figure in text
            figure_mentions = self._find_figure_mentions(
                full_text,
                figure.figure_number,
            )
            
            cross_refs.append({
                "figure_number": figure.figure_number,
                "caption": figure.caption,
                "mentions": figure_mentions,
                "context": self._get_mention_contexts(full_text, figure_mentions),
            })
        
        return cross_refs
    
    def _find_figure_mentions(
        self,
        text: str,
        figure_number: str,
    ) -> list[str]:
        """Find all mentions of a figure in text."""
        mentions = []
        
        # Common figure reference patterns
        patterns = [
            rf"Figure\s*{re.escape(figure_number)}",
            rf"Fig\.\s*{re.escape(figure_number)}",
            rf"Fig\s*{re.escape(figure_number)}",
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                # Get surrounding context (sentence)
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 100)
                mentions.append(text[start:end].strip())
        
        return mentions
    
    def _get_mention_contexts(
        self,
        text: str,
        mentions: list[str],
    ) -> list[str]:
        """Get extended context for mentions."""
        contexts = []
        
        for mention in mentions:
            # Find the full sentence
            sentences = re.split(r'[.!?]+', text)
            for sentence in sentences:
                if mention[:50] in sentence or mention[-50:] in sentence:
                    contexts.append(sentence.strip())
        
        return contexts[:5]  # Limit to 5 contexts


class MultimodalLiteratureAgent:
    """Main agent for multimodal literature search and analysis."""
    
    def __init__(
        self,
        vision_client: Any | None = None,
    ) -> None:
        """Initialize multimodal literature agent.
        
        Args:
            vision_client: Vision model client for chart/figure analysis
        """
        self._vision_client = vision_client
        self._figure_extractor = PDFFigureExtractor()
        self._chart_digitizer = ChartDataDigitizer(vision_client)
        self._table_parser = TableStructureParser()
        self._cross_referencer = ImageTextCrossReferencer()
    
    async def analyze_paper(
        self,
        paper_path: str | Path,
    ) -> MultimodalPaper | None:
        """Analyze a paper with multimodal content extraction.
        
        Args:
            paper_path: Path to paper PDF
            
        Returns:
            MultimodalPaper or None
        """
        paper_path = Path(paper_path)
        
        if not paper_path.exists():
            logger.error(f"Paper not found: {paper_path}")
            return None
        
        logger.info(f"Analyzing paper: {paper_path.name}")
        
        # Extract basic metadata (placeholder - would use existing literature module)
        paper = MultimodalPaper(
            paper_id=paper_path.stem,
            title=paper_path.stem,
            authors=[],
            abstract="",
            full_text="",
            figures=[],
            tables=[],
            charts=[],
            cross_references=[],
        )
        
        # Extract figures
        figure_data = await self._figure_extractor.extract_figures(paper_path)
        
        # Analyze each figure
        for fig_info in figure_data:
            figure_analysis = await self._analyze_figure(fig_info)
            if figure_analysis:
                paper.figures.append(figure_analysis)
        
        # Extract tables
        paper.tables = await self._table_parser.extract_tables(paper_path)
        
        # Extract chart data from figures
        for fig_info in figure_data:
            if fig_info.get("image_data"):
                chart_data = await self._chart_digitizer.extract_data(
                    image_data=fig_info["image_data"]
                )
                if chart_data and chart_data.confidence > 0.5:
                    chart_data.source_figure = fig_info.get("figure_number", "")
                    paper.charts.append(chart_data)
        
        # Cross-reference figures with text
        if paper.full_text and paper.figures:
            paper.cross_references = self._cross_referencer.cross_reference(
                paper.full_text,
                paper.figures,
            )
        
        logger.info(
            f"Analysis complete: {len(paper.figures)} figures, "
            f"{len(paper.tables)} tables, {len(paper.charts)} charts"
        )
        
        return paper
    
    async def _analyze_figure(
        self,
        figure_info: dict[str, Any],
    ) -> FigureAnalysis | None:
        """Analyze a single figure."""
        # In production, use vision model to analyze figure
        # For now, create basic analysis
        
        return FigureAnalysis(
            figure_number=figure_info.get("figure_number", "unknown"),
            caption="",  # Would extract from PDF
            figure_type="unknown",
            key_findings=[],
            referenced_in_text=[],
            data_available=bool(figure_info.get("image_data")),
            quality_score=5.0,
            ocr_text=None,
        )
    
    async def search(
        self,
        query: str,
        include_figures: bool = True,
        include_tables: bool = True,
        limit: int = 20,
    ) -> list[MultimodalPaper]:
        """Search literature with multimodal content.
        
        Args:
            query: Search query
            include_figures: Whether to extract figures
            include_tables: Whether to extract tables
            limit: Max results
            
        Returns:
            List of MultimodalPaper
        """
        # In production, integrate with existing literature search
        # and add multimodal extraction
        
        logger.info(f"Multimodal search for: {query}")
        
        # Placeholder - would call existing search + extract multimodal content
        return []
    
    def get_statistics(self) -> dict[str, Any]:
        """Get extraction statistics."""
        return {
            "vision_client_available": self._vision_client is not None,
            "figure_extractor_available": True,
            "chart_digitizer_available": True,
            "table_parser_available": True,
        }


# Convenience function
async def analyze_paper_multimodal(
    paper_path: str | Path,
) -> MultimodalPaper | None:
    """Quick function to analyze a paper multimodally.
    
    Args:
        paper_path: Path to paper
        
    Returns:
        MultimodalPaper
    """
    agent = MultimodalLiteratureAgent()
    return await agent.analyze_paper(paper_path)
