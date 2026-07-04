"""Agent collaboration and knowledge sharing system.

Enables multiple Berb instances to share research artifacts
(literature summaries, experiment results, code templates, review feedback)
through a file-system-based shared repository.
"""

from berb.collaboration.dedup import deduplicate_artifacts
from berb.collaboration.publisher import ArtifactPublisher
from berb.collaboration.repository import ResearchRepository
from berb.collaboration.subscriber import ArtifactSubscriber

__all__ = [
    "ResearchRepository",
    "ArtifactPublisher",
    "ArtifactSubscriber",
    "deduplicate_artifacts",
]
