"""Open-Ended Discovery Agent for Berb.

Based on AI Scientist V2 (Sakana AI, ICLR 2025 Workshop):
- Template-free discovery
- Progressive agentic tree search (Best-First Tree Search)
- Novelty verification via Semantic Scholar API
- Auto-debugging for failing tree nodes
- Open-ended scientific exploration

Features:
- Best-First Tree Search (BFTS) strategy
- Experiment Manager Agent
- Novelty checking
- Self-healing for failed branches
- Workshop paper generation capability

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.research.open_ended_discovery import OpenEndedDiscoveryAgent
    
    agent = OpenEndedDiscoveryAgent()
    discoveries = await agent.explore(
        direction="efficient neural architectures",
        max_iterations=100
    )
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from collections import deque

logger = logging.getLogger(__name__)


class NodeStatus(str, Enum):
    """Status of a tree node."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PRUNED = "pruned"


@dataclass
class DiscoveryNode:
    """Node in the discovery tree."""
    
    id: str
    parent_id: str | None
    hypothesis: str
    status: NodeStatus = NodeStatus.PENDING
    depth: int = 0
    score: float = 0.0  # Quality score 0-10
    novelty_score: float = 0.0  # Novelty 0-10
    experiments_run: int = 0
    experiments_successful: int = 0
    children: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    error_message: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "hypothesis": self.hypothesis,
            "status": self.status.value,
            "depth": self.depth,
            "score": self.score,
            "novelty_score": self.novelty_score,
            "experiments_run": self.experiments_run,
            "experiments_successful": self.experiments_successful,
            "children": self.children,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "error_message": self.error_message,
        }


@dataclass
class DiscoveryResult:
    """Result from open-ended discovery."""
    
    root_hypothesis: str
    total_nodes: int
    successful_nodes: int
    failed_nodes: int
    best_hypothesis: str
    best_score: float
    tree_depth: int
    total_experiments: int
    novel_ideas_found: int
    paper_draft: str | None
    discoveries: list[dict[str, Any]]


class ExperimentManagerAgent:
    """Agent that manages the tree search process."""
    
    def __init__(self) -> None:
        """Initialize experiment manager."""
        self._iteration = 0
        self._total_budget = 100  # Max iterations
        self._exploration_weight = 0.3  # Weight for exploration vs exploitation
    
    def select_next_node(
        self,
        nodes: dict[str, DiscoveryNode],
        pending_ids: list[str],
    ) -> str | None:
        """Select next node to expand using Best-First strategy.
        
        Args:
            nodes: All nodes in tree
            pending_ids: IDs of pending nodes
            
        Returns:
            ID of selected node or None
        """
        if not pending_ids:
            return None
        
        # Score each pending node
        scored_nodes = []
        
        for node_id in pending_ids:
            node = nodes.get(node_id)
            if not node:
                continue
            
            # Calculate UCB-like score (Upper Confidence Bound)
            exploitation_score = node.score / 10.0
            
            # Exploration bonus for less-visited branches
            if node.parent_id and nodes.get(node.parent_id):
                parent = nodes[node.parent_id]
                if parent.experiments_run > 0:
                    exploration_bonus = self._exploration_weight * (
                        len(parent.children) / max(1, node.experiments_run)
                    )
                else:
                    exploration_bonus = self._exploration_weight
            else:
                exploration_bonus = self._exploration_weight
            
            # Novelty bonus
            novelty_bonus = node.novelty_score / 20.0  # Normalize
            
            total_score = exploitation_score + exploration_bonus + novelty_bonus
            
            scored_nodes.append((node_id, total_score))
        
        if not scored_nodes:
            return None
        
        # Select highest scoring node
        scored_nodes.sort(key=lambda x: x[1], reverse=True)
        return scored_nodes[0][0]
    
    def should_prune(self, node: DiscoveryNode) -> bool:
        """Determine if a node should be pruned."""
        # Prune if score too low
        if node.score < 3.0:
            return True
        
        # Prune if too many failures
        if node.experiments_run > 3 and node.experiments_successful == 0:
            return True
        
        # Prune if depth too large
        if node.depth > 5:
            return True
        
        return False
    
    def generate_child_hypothesis(
        self,
        parent: DiscoveryNode,
        iteration: int,
    ) -> str:
        """Generate child hypothesis from parent.
        
        In production, use LLM to generate variations.
        """
        # Placeholder: generate variation
        variations = [
            f"Variant A: {parent.hypothesis}",
            f"Variant B: {parent.hypothesis}",
            f"Extended: {parent.hypothesis}",
            f"Optimized: {parent.hypothesis}",
        ]
        
        return variations[iteration % len(variations)]


class NoveltyVerifier:
    """Verify novelty of ideas using Semantic Scholar API."""
    
    def __init__(self, api_key: str | None = None) -> None:
        """Initialize novelty verifier.
        
        Args:
            api_key: Semantic Scholar API key (optional)
        """
        self._api_key = api_key
        self._known_papers: dict[str, Any] = {}
    
    async def check_novelty(
        self,
        hypothesis: str,
        domain: str = "computer_science",
    ) -> float:
        """Check novelty of a hypothesis.
        
        Args:
            hypothesis: Research hypothesis
            domain: Research domain
            
        Returns:
            Novelty score 0-10 (10 = completely novel)
        """
        # In production, call Semantic Scholar API
        # For now, return placeholder
        
        # Check if similar ideas exist in known papers
        similar_count = self._find_similar_work(hypothesis, domain)
        
        # Calculate novelty score
        if similar_count == 0:
            return 9.0  # Very novel
        elif similar_count < 3:
            return 7.0  # Moderately novel
        elif similar_count < 10:
            return 5.0  # Somewhat novel
        else:
            return 3.0  # Not very novel
    
    def _find_similar_work(
        self,
        hypothesis: str,
        domain: str,
    ) -> int:
        """Find similar work in literature."""
        # Placeholder - would call Semantic Scholar API
        # https://api.semanticscholar.org/api-docs/
        return 0
    
    async def get_related_work(
        self,
        hypothesis: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get related work for a hypothesis."""
        # In production, call Semantic Scholar API
        return []


class AutoDebugger:
    """Auto-debugging for failed tree nodes."""
    
    def __init__(self) -> None:
        """Initialize auto-debugger."""
        self._fix_history: list[dict] = []
    
    async def debug_failed_node(
        self,
        node: DiscoveryNode,
        error_message: str,
    ) -> bool:
        """Attempt to debug a failed node.
        
        Args:
            node: Failed node
            error_message: Error message
            
        Returns:
            True if debug succeeded
        """
        logger.info(f"Debugging failed node {node.id}: {error_message[:100]}...")
        
        # Check if we've seen this error before
        for fix_entry in self._fix_history:
            if error_message in fix_entry.get("error", ""):
                # Apply cached fix
                logger.info("Using cached fix")
                return True
        
        # In production, use LLM to diagnose and fix
        # For now, random success for demonstration
        import random
        success = random.random() > 0.5
        
        if success:
            self._fix_history.append({
                "error": error_message,
                "fix": "Auto-applied fix",
                "timestamp": datetime.now().isoformat(),
            })
        
        return success


class OpenEndedDiscoveryAgent:
    """Main agent for open-ended scientific discovery."""
    
    def __init__(
        self,
        max_iterations: int = 100,
        max_budget_usd: float = 20.0,
        novelty_threshold: float = 5.0,
    ) -> None:
        """Initialize discovery agent.
        
        Args:
            max_iterations: Maximum tree search iterations
            max_budget_usd: Maximum budget in USD
            novelty_threshold: Minimum novelty score to pursue
        """
        self._max_iterations = max_iterations
        self._max_budget = max_budget_usd
        self._novelty_threshold = novelty_threshold
        
        # Initialize components
        self._experiment_manager = ExperimentManagerAgent()
        self._novelty_verifier = NoveltyVerifier()
        self._auto_debugger = AutoDebugger()
        
        # Tree state
        self._nodes: dict[str, DiscoveryNode] = {}
        self._pending_queue: deque = deque()
        self._root_id: str | None = None
        
        # Statistics
        self._total_cost = 0.0
        self._iteration = 0
    
    async def explore(
        self,
        direction: str,
        domain: str = "machine_learning",
    ) -> DiscoveryResult:
        """Explore research space via open-ended discovery.
        
        Args:
            direction: Research direction (e.g., "efficient neural architectures")
            domain: Research domain
            
        Returns:
            DiscoveryResult
        """
        logger.info(f"Starting open-ended discovery: {direction}")
        
        # Create root node
        root = DiscoveryNode(
            id="root",
            parent_id=None,
            hypothesis=direction,
            depth=0,
        )
        
        # Check novelty of root hypothesis
        root.novelty_score = await self._novelty_verifier.check_novelty(
            direction, domain
        )
        
        self._nodes[root.id] = root
        self._root_id = root.id
        self._pending_queue.append(root.id)
        
        # Best-First Tree Search loop
        while (
            self._iteration < self._max_iterations and
            self._pending_queue and
            self._total_cost < self._max_budget
        ):
            self._iteration += 1
            
            # Select next node to expand
            pending_ids = list(self._pending_queue)
            selected_id = self._experiment_manager.select_next_node(
                self._nodes, pending_ids
            )
            
            if not selected_id:
                break
            
            # Expand node
            await self._expand_node(selected_id, domain)
            
            # Check for pruning
            self._prune_low_performing_nodes()
        
        # Generate result
        return self._generate_result()
    
    async def _expand_node(
        self,
        node_id: str,
        domain: str,
    ) -> None:
        """Expand a tree node."""
        node = self._nodes.get(node_id)
        if not node:
            return
        
        logger.info(f"Expanding node {node_id}: {node.hypothesis[:50]}...")
        
        node.status = NodeStatus.IN_PROGRESS
        
        # Run experiment for this hypothesis
        experiment_success = await self._run_experiment(node, domain)
        
        if experiment_success:
            node.status = NodeStatus.COMPLETED
            node.experiments_successful += 1
            
            # Generate child hypotheses
            for i in range(2):  # Generate 2 children per node
                child_hypothesis = self._experiment_manager.generate_child_hypothesis(
                    node, i
                )
                
                # Check novelty
                novelty = await self._novelty_verifier.check_novelty(
                    child_hypothesis, domain
                )
                
                if novelty >= self._novelty_threshold:
                    child = DiscoveryNode(
                        id=f"{node_id}_child_{i}",
                        parent_id=node_id,
                        hypothesis=child_hypothesis,
                        depth=node.depth + 1,
                        novelty_score=novelty,
                    )
                    
                    self._nodes[child.id] = child
                    node.children.append(child.id)
                    self._pending_queue.append(child.id)
        else:
            node.status = NodeStatus.FAILED
            
            # Try auto-debugging
            if node.error_message:
                debug_success = await self._auto_debugger.debug_failed_node(
                    node, node.error_message
                )
                
                if debug_success:
                    # Re-queue for retry
                    node.status = NodeStatus.PENDING
                    self._pending_queue.append(node_id)
    
    async def _run_experiment(
        self,
        node: DiscoveryNode,
        domain: str,
    ) -> bool:
        """Run experiment for a hypothesis.
        
        In production, this would:
        1. Generate experiment code
        2. Execute experiment
        3. Analyze results
        4. Score hypothesis
        """
        # Placeholder: simulate experiment
        import random
        
        # Simulate success/failure
        success = random.random() > 0.3  # 70% success rate
        
        if success:
            node.score = random.uniform(5.0, 9.5)
            node.experiments_successful += 1
        else:
            node.error_message = "Experiment failed (placeholder)"
        
        node.experiments_run += 1
        
        # Update cost
        self._total_cost += 0.20  # $0.20 per experiment
        
        return success
    
    def _prune_low_performing_nodes(self) -> None:
        """Prune nodes that are performing poorly."""
        nodes_to_prune = []
        
        for node_id, node in self._nodes.items():
            if node.status == NodeStatus.PENDING:
                if self._experiment_manager.should_prune(node):
                    nodes_to_prune.append(node_id)
        
        for node_id in nodes_to_prune:
            node = self._nodes[node_id]
            node.status = NodeStatus.PRUNED
            
            # Remove from pending queue
            if node_id in self._pending_queue:
                self._pending_queue.remove(node_id)
            
            logger.debug(f"Pruned node {node_id}")
    
    def _generate_result(self) -> DiscoveryResult:
        """Generate discovery result."""
        successful_nodes = [
            n for n in self._nodes.values()
            if n.status == NodeStatus.COMPLETED
        ]
        failed_nodes = [
            n for n in self._nodes.values()
            if n.status == NodeStatus.FAILED
        ]
        
        # Find best hypothesis
        best_node = max(successful_nodes, key=lambda n: n.score) if successful_nodes else None
        
        # Count novel ideas
        novel_ideas = sum(
            1 for n in self._nodes.values()
            if n.novelty_score >= 7.0
        )
        
        # Calculate max depth
        max_depth = max((n.depth for n in self._nodes.values()), default=0)
        
        return DiscoveryResult(
            root_hypothesis=self._nodes[self._root_id].hypothesis if self._root_id else "",
            total_nodes=len(self._nodes),
            successful_nodes=len(successful_nodes),
            failed_nodes=len(failed_nodes),
            best_hypothesis=best_node.hypothesis if best_node else "",
            best_score=best_node.score if best_node else 0.0,
            tree_depth=max_depth,
            total_experiments=sum(n.experiments_run for n in self._nodes.values()),
            novel_ideas_found=novel_ideas,
            paper_draft=self._generate_paper_draft(best_node) if best_node else None,
            discoveries=[n.to_dict() for n in successful_nodes],
        )
    
    def _generate_paper_draft(
        self,
        best_node: DiscoveryNode,
    ) -> str:
        """Generate draft paper from best discovery."""
        return f"""# Research Paper Draft

## Title
{best_node.hypothesis}

## Abstract
This paper presents novel findings from automated scientific discovery.
Our best hypothesis achieved a score of {best_node.score:.1f}/10 with novelty score {best_node.novelty_score:.1f}/10.

## Introduction
Starting from the research direction, we explored the hypothesis space using best-first tree search.

## Method
- Total nodes explored: {best_node.experiments_run}
- Successful experiments: {best_node.experiments_successful}
- Tree depth: {best_node.depth}

## Results
Best hypothesis: {best_node.hypothesis}
Score: {best_node.score:.1f}/10
Novelty: {best_node.novelty_score:.1f}/10

## Conclusion
This automated discovery demonstrates the potential of AI-driven scientific exploration.

---
*Generated by Berb Open-Ended Discovery Agent*
"""
    
    def get_statistics(self) -> dict[str, Any]:
        """Get discovery statistics."""
        return {
            "iterations": self._iteration,
            "total_nodes": len(self._nodes),
            "pending_nodes": len(self._pending_queue),
            "total_cost_usd": self._total_cost,
            "budget_remaining_usd": self._max_budget - self._total_cost,
            "max_iterations": self._max_iterations,
        }


# Convenience function
async def run_open_ended_discovery(
    direction: str,
    domain: str = "machine_learning",
    max_iterations: int = 100,
) -> DiscoveryResult:
    """Quick function to run open-ended discovery.
    
    Args:
        direction: Research direction
        domain: Research domain
        max_iterations: Maximum iterations
        
    Returns:
        DiscoveryResult
    """
    agent = OpenEndedDiscoveryAgent(max_iterations=max_iterations)
    return await agent.explore(direction, domain)
