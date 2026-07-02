"""Persistent evolutionary memory system for Berb.

Provides three categories of memory:
- **Ideation**: Research topics, hypotheses, and their outcomes.
- **Experiment**: Hyperparameters, architectures, and training tricks.
- **Writing**: Review feedback, paper structure patterns.

Each category supports semantic retrieval via embeddings, time-decay
weighting, and confidence scoring.
"""

from berb.memory.decay import confidence_update, time_decay_weight
from berb.memory.retriever import MemoryRetriever
from berb.memory.store import MemoryEntry, MemoryStore

__all__ = [
    "MemoryEntry",
    "MemoryStore",
    "MemoryRetriever",
    "time_decay_weight",
    "confidence_update",
]
