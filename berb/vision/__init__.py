"""Vision-based figure generation for Berb.

This module provides design-to-code capabilities for figures,
converting sketches and descriptions into matplotlib/tikz code.
"""

from .figure_generator import (
    FigureCodeGenerator,
    FigureCritic,
    FigureCritique,
    FigureGenerator,
    FigureSpec,
    VisionModelClient,
)

__all__ = [
    "FigureGenerator",
    "FigureSpec",
    "FigureCodeGenerator",
    "VisionModelClient",
    "FigureCritic",
    "FigureCritique",
]
