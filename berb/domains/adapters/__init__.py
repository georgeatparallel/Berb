"""Domain-specific prompt adapters.

Each adapter customizes prompt blocks for a specific research domain
while the ML adapter preserves existing behavior unchanged.
"""

from berb.domains.adapters.biology import BiologyPromptAdapter
from berb.domains.adapters.chemistry import ChemistryPromptAdapter
from berb.domains.adapters.economics import EconomicsPromptAdapter
from berb.domains.adapters.generic import GenericPromptAdapter
from berb.domains.adapters.ml import MLPromptAdapter
from berb.domains.adapters.neuroscience import NeurosciencePromptAdapter
from berb.domains.adapters.physics import PhysicsPromptAdapter
from berb.domains.adapters.robotics import RoboticsPromptAdapter

__all__ = [
    "MLPromptAdapter",
    "GenericPromptAdapter",
    "PhysicsPromptAdapter",
    "EconomicsPromptAdapter",
    "BiologyPromptAdapter",
    "ChemistryPromptAdapter",
    "NeurosciencePromptAdapter",
    "RoboticsPromptAdapter",
]
