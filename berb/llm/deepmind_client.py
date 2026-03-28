"""DeepMind AI (xAI) client - separate module.

# Author: Georgios-Chrysovalantis Chatzivantsidis

This is a re-export of the DeepMindAIClient from deep_query_client.py
for backwards compatibility and cleaner imports.
"""

from berb.llm.deep_query_client import (
    DeepMindAIClient,
    DeepMindAIResult,
    create_deepmind_ai_client,
)

__all__ = [
    "DeepMindAIClient",
    "DeepMindAIResult",
    "create_deepmind_ai_client",
]
