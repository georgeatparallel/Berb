"""Pipeline preset system — domain-optimised configuration bundles.

Includes auto-detection for intelligent preset selection.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from berb.presets.base import PipelinePreset
from berb.presets.registry import (
    PresetRegistry,
    load_preset,
    list_presets,
    get_preset,
    get_registry,
)
from berb.presets.auto_detect import (
    DomainClassifier,
    DomainDetector,
    DomainSuggestion,
    DomainDetectionResult,
    detect_domain,
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
