"""Pipeline preset system — domain-optimised configuration bundles.

Includes auto-detection for intelligent preset selection.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from berb.presets.auto_detect import (
    DomainClassifier,
    DomainDetectionResult,
    DomainDetector,
    DomainSuggestion,
    detect_domain,
)
from berb.presets.base import PipelinePreset
from berb.presets.registry import (
    PresetRegistry,
    get_preset,
    get_registry,
    list_presets,
    load_preset,
)

__all__ = [
    "PipelinePreset",
    "PresetRegistry",
    "load_preset",
    "list_presets",
    "get_preset",
    "get_registry",
    # Auto-detection
    "DomainClassifier",
    "DomainDetector",
    "DomainSuggestion",
    "DomainDetectionResult",
    "detect_domain",
]
