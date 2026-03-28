"""HyperAgent - Self-Referential Self-Improving Agents for Berb.

Based on Facebook AI Research paper (arXiv:2603.19461v1):
"Hyperagents: Self-Referential Self-Improving Agents for Any Computable Task"

Key Innovation:
- Task Agent + Meta Agent integrated into single editable program
- Meta-level modification procedure is ITSELF editable (metacognitive)
- Improvements accumulate across runs and transfer across domains

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.hyperagent import Hyperagent
    
    agent = Hyperagent(config)
    
    # Run task
    result = await agent.run_task("Your research task")
    
    # Self-improve
    improvement = await agent.self_improve()
"""

from berb.hyperagent.base import (
    Hyperagent,
    HyperagentState,
    ImprovementResult,
)
from berb.hyperagent.task_agent import TaskAgent
from berb.hyperagent.meta_agent import MetaAgent
from berb.hyperagent.memory import PersistentMemory
from berb.hyperagent.improvement_loop import ImprovementLoop

__all__ = [
    "Hyperagent",
    "HyperagentState",
    "ImprovementResult",
    "TaskAgent",
    "MetaAgent",
    "PersistentMemory",
    "ImprovementLoop",
]
