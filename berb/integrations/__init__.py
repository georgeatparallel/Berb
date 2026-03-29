"""Integrations module for Berb.

External service integrations (scite.ai, etc.).

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from berb.integrations.scite_mcp import (
    SciteClient,
    SciteConfig,
    SciteIntegration,
    SciteIntegrationConfig,
    SciteCitationType,
    SmartCitationResult,
    CitationProfile,
    ReferenceCheckReport,
    get_citation_profile,
    check_manuscript_references,
)

__all__ = [
    "SciteClient",
    "SciteConfig",
    "SciteIntegration",
    "SciteIntegrationConfig",
    "SciteCitationType",
    "SmartCitationResult",
    "CitationProfile",
    "ReferenceCheckReport",
    "get_citation_profile",
    "check_manuscript_references",
]
