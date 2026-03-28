"""Parallelized Agentic Tree Search for Berb.

Based on AI Scientist (Nature 2026) - Section 3.2

This module implements tree search for exploring multiple research directions
in parallel, scoring branches, and merging best findings.

Key Features:
- Branch at key decision points (hypothesis, experiment design, analysis)
- Explore 3-5 parallel branches per decision
- Score and prune low-performing branches
- Merge best findings into final paper

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.research import ParallelizedTreeSearch
    
    search = ParallelizedTreeSearch(max_branches=4, max_depth=3)
    best_path = await search.explore(topic="Your research topic")
    merged_results = search.merge_branches(best_path)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

logger = logging.getLogger(__name__)


class BranchStatus(str, Enum):
    """Status of a search branch."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PRUNED = "pruned"
    FAILED = "failed"


class DecisionPoint(str, Enum):
    """Key decision points where branching occurs."""
    HYPOTHESIS_GENERATION = "hypothesis_generation"
    EXPERIMENT_DESIGN = "experiment_design"
    METHOD_SELECTION = "method_selection"
    ANALYSIS_APPROACH = "analysis_approach"
    INTERPRETATION = "interpretation"


@dataclass
class BranchNode:
    """Single node in the search tree."""
    
    id: str
    parent_id: str | None
    decision_point: DecisionPoint
    description: str  # What this branch explores
    status: BranchStatus = BranchStatus.PENDING
    score: float = 0.0  # 0-10 quality score
    confidence: float = 0.0  # 0-1 confidence in score
    cost: float = 0.0  # USD spent on this branch
    duration_sec: float = 0.0
    results: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Path] = field(default_factory=list)
    error_message: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "decision_point": self.decision_point.value,
            "description": self.description,
            "status": self.status.value,
            "score": self.score,
            "confidence": self.confidence,
            "cost": self.cost,
            "duration_sec": self.duration_sec,
            "results": self.results,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class SearchPath:
    """Complete path from root to leaf in search tree."""
    
    nodes: list[BranchNode]
    total_score: float
    total_cost: float
    total_duration_sec: float
    success_rate: float  # 0-1


@dataclass
class SearchConfig:
    """Configuration for tree search."""
    
    max_branches: int = 4  # Max parallel branches per decision
    max_depth: int = 3  # Max tree depth
    pruning_threshold: float = 4.0  # Prune branches scoring below this
    timeout_per_branch_sec: int = 1800  # 30 min per branch
    max_total_cost_usd: float = 5.0  # Budget cap
    scoring_weights: dict[str, float] = field(default_factory=lambda: {
        "novelty": 0.25,
        "feasibility": 0.20,
        "impact": 0.25,
        "clarity": 0.15,
        "cost_efficiency": 0.15,
    })


class ParallelizedTreeSearch:
    """Parallelized agentic tree search for research exploration."""
    
    def __init__(
        self,
        config: SearchConfig | None = None,
        llm_client: Any | None = None,
    ) -> None:
        """Initialize tree search.
        
        Args:
            config: Search configuration
            llm_client: LLM client for scoring and generation
        """
        self._config = config or SearchConfig()
        self._llm_client = llm_client
        self._root: BranchNode | None = None
        self._nodes: dict[str, BranchNode] = {}
        self._completed_paths: list[SearchPath] = []
        self._total_cost: float = 0.0
        self._start_time: datetime | None = None
    
    async def explore(
        self,
        topic: str,
        domain: str = "machine_learning",
    ) -> list[BranchNode]:
        """Explore research space via tree search.
        
        Args:
            topic: Research topic to explore
            domain: Research domain
            
        Returns:
            List of best leaf nodes (top-k paths)
        """
        self._start_time = datetime.now()
        logger.info(f"Starting tree search for topic: {topic}")
        
        # Create root node
        self._root = BranchNode(
            id=str(uuid4()),
            parent_id=None,
            decision_point=DecisionPoint.HYPOTHESIS_GENERATION,
            description=f"Research topic: {topic}",
        )
        self._nodes[self._root.id] = self._root
        
        # Generate initial hypotheses (first branching)
        hypotheses = await self._generate_branches(
            node=self._root,
            topic=topic,
            domain=domain,
        )
        
        logger.info(f"Generated {len(hypotheses)} initial hypotheses")
        
        # Explore each hypothesis in parallel
        await self._explore_subtree_parallel(hypotheses)
        
        # Collect and rank paths
        paths = self._collect_all_paths()
        self._completed_paths = sorted(
            paths,
            key=lambda p: p.total_score,
            reverse=True,
        )
        
        # Return best leaf nodes
        if self._completed_paths:
            best_path = self._completed_paths[0]
            logger.info(
                f"Tree search complete. Best path score: {best_path.total_score:.2f}, "
                f"cost: ${best_path.total_cost:.2f}"
            )
            return [best_path.nodes[-1]]
        
        return []
    
    async def _explore_subtree_parallel(self, nodes: list[BranchNode]) -> None:
        """Explore subtree in parallel with pruning."""
        while nodes:
            # Check budget and timeout
            if self._total_cost >= self._config.max_total_cost_usd:
                logger.warning("Budget exceeded, pruning remaining branches")
                for node in nodes:
                    node.status = BranchStatus.PRUNED
                break
            
            # Score and prune low-performing branches
            scored_nodes = await self._score_branches(nodes)
            pruned_nodes = self._prune_branches(scored_nodes)
            
            if not pruned_nodes:
                logger.info("All branches pruned")
                break
            
            # Expand next level in parallel
            next_level_tasks = [
                self._expand_node(node)
                for node in pruned_nodes
            ]
            
            next_level_results = await asyncio.gather(*next_level_tasks, return_exceptions=True)
            
            # Collect child nodes for next iteration
            nodes = []
            for result in next_level_results:
                if isinstance(result, Exception):
                    logger.error(f"Branch expansion failed: {result}")
                    continue
                if result:
                    nodes.extend(result)
    
    async def _generate_branches(
        self,
        node: BranchNode,
        topic: str,
        domain: str,
    ) -> list[BranchNode]:
        """Generate child branches for a node.
        
        Uses LLM to generate diverse options.
        """
        node.started_at = datetime.now()
        node.status = BranchStatus.RUNNING
        
        # Build prompt for branch generation
        prompt = self._build_branch_generation_prompt(
            node=node,
            topic=topic,
            domain=domain,
        )
        
        # Call LLM (placeholder - integrate with actual client)
        # In production:
        # response = await self._llm_client.chat(
        #     messages=[{"role": "user", "content": prompt}],
        #     json_mode=True
        # )
        # branches_data = json.loads(response.content)
        
        # Placeholder: generate synthetic branches
        branches_data = self._generate_placeholder_branches(
            node.decision_point,
            self._config.max_branches,
        )
        
        # Create child nodes
        children = []
        for i, branch_data in enumerate(branches_data):
            child = BranchNode(
                id=str(uuid4()),
                parent_id=node.id,
                decision_point=self._get_next_decision_point(node.decision_point),
                description=branch_data["description"],
                results=branch_data.get("details", {}),
            )
            self._nodes[child.id] = child
            children.append(child)
        
        node.completed_at = datetime.now()
        node.duration_sec = (node.completed_at - node.started_at).total_seconds()
        node.status = BranchStatus.COMPLETED
        
        return children
    
    def _build_branch_generation_prompt(
        self,
        node: BranchNode,
        topic: str,
        domain: str,
    ) -> str:
        """Build LLM prompt for generating branches."""
        decision_prompts = {
            DecisionPoint.HYPOTHESIS_GENERATION: f"""Generate {self._config.max_branches} distinct research hypotheses for:

Topic: {topic}
Domain: {domain}

Each hypothesis should:
1. Be novel and testable
2. Have clear success criteria
3. Be computationally feasible

Output format (JSON):
[
    {{
        "description": "Hypothesis description",
        "details": {{
            "novelty_score": 1-10,
            "feasibility_score": 1-10,
            "expected_impact": "high/medium/low"
        }}
    }}
]
""",
            DecisionPoint.EXPERIMENT_DESIGN: f"""Generate {self._config.max_branches} distinct experimental approaches:

Parent hypothesis: {node.description}

Each approach should:
1. Test the hypothesis rigorously
2. Include appropriate baselines
3. Have clear evaluation metrics

Output format (JSON): [...]
""",
            DecisionPoint.METHOD_SELECTION: f"""Generate {self._config.max_branches} method variants:

Context: {node.description}

Each method should:
1. Be technically sound
2. Have clear advantages
3. Be implementable

Output format (JSON): [...]
""",
        }
        
        return decision_prompts.get(node.decision_point, "")
    
    def _generate_placeholder_branches(
        self,
        decision_point: DecisionPoint,
        count: int,
    ) -> list[dict[str, Any]]:
        """Generate placeholder branches (replace with LLM call)."""
        import random
        
        branch_templates = {
            DecisionPoint.HYPOTHESIS_GENERATION: [
                "Novel approach using {method} for {task}",
                "Improving {baseline} via {technique}",
                "Cross-domain application of {method} to {domain}",
                "Theoretical analysis of {phenomenon}",
            ],
            DecisionPoint.EXPERIMENT_DESIGN: [
                "Comprehensive ablation study",
                "Comparison with SOTA methods",
                "Scaling analysis across {dimension}",
                "Robustness testing under {condition}",
            ],
            DecisionPoint.METHOD_SELECTION: [
                "Method A: Conservative baseline",
                "Method B: Moderate innovation",
                "Method C: High-risk high-reward",
                "Method D: Hybrid approach",
            ],
        }
        
        templates = branch_templates.get(decision_point, ["Branch {i}"])
        
        branches = []
        for i in range(count):
            template = templates[i % len(templates)]
            branches.append({
                "description": template.format(
                    i=i+1,
                    method=f"method_{i}",
                    task=f"task_{i}",
                    baseline=f"baseline_{i}",
                    technique=f"technique_{i}",
                    domain=f"domain_{i}",
                    phenomenon=f"phenomenon_{i}",
                    dimension=f"dimension_{i}",
                    condition=f"condition_{i}",
                ),
                "details": {
                    "novelty_score": random.uniform(5, 9),
                    "feasibility_score": random.uniform(6, 10),
                },
            })
        
        return branches
    
    def _get_next_decision_point(self, current: DecisionPoint) -> DecisionPoint:
        """Get next decision point in sequence."""
        sequence = list(DecisionPoint)
        try:
            idx = sequence.index(current)
            return sequence[min(idx + 1, len(sequence) - 1)]
        except ValueError:
            return DecisionPoint.HYPOTHESIS_GENERATION
    
    async def _score_branches(self, nodes: list[BranchNode]) -> list[tuple[BranchNode, float]]:
        """Score branches based on multiple criteria."""
        scored = []
        
        for node in nodes:
            if node.status == BranchStatus.PRUNED:
                continue
            
            # Calculate score based on config weights
            weights = self._config.scoring_weights
            results = node.results
            
            score = 0.0
            if "novelty_score" in results:
                score += weights.get("novelty", 0) * results["novelty_score"]
            if "feasibility_score" in results:
                score += weights.get("feasibility", 0) * results["feasibility_score"]
            if "expected_impact" in results:
                impact_map = {"high": 10, "medium": 6, "low": 3}
                impact = results["expected_impact"]
                score += weights.get("impact", 0) * impact_map.get(impact, 5)
            
            # Normalize to 0-10
            total_weight = sum(weights.values())
            if total_weight > 0:
                score = (score / total_weight) * 10
            
            node.score = min(10.0, max(0.0, score))
            node.confidence = 0.7  # Placeholder - would come from LLM
            
            scored.append((node, score))
        
        return scored
    
    def _prune_branches(
        self,
        scored_nodes: list[tuple[BranchNode, float]],
    ) -> list[BranchNode]:
        """Prune low-scoring branches."""
        threshold = self._config.pruning_threshold
        
        # Sort by score descending
        scored_nodes.sort(key=lambda x: x[1], reverse=True)
        
        # Keep top-k and those above threshold
        kept = []
        for node, score in scored_nodes:
            if len(kept) >= self._config.max_branches:
                break
            if score >= threshold:
                kept.append(node)
            else:
                node.status = BranchStatus.PRUNED
                logger.debug(f"Pruned branch {node.id[:8]} (score {score:.2f} < {threshold})")
        
        return kept
    
    async def _expand_node(self, node: BranchNode) -> list[BranchNode]:
        """Expand a single node (generate children)."""
        # Placeholder - in production, call appropriate generation method
        # based on decision point
        return await self._generate_branches(
            node=node,
            topic="research topic",  # Would come from root
            domain="ml",
        )
    
    def _collect_all_paths(self) -> list[SearchPath]:
        """Collect all complete paths from root to leaf."""
        if not self._root:
            return []
        
        paths = []
        
        def dfs(node: BranchNode, current_path: list[BranchNode]) -> None:
            if node.status in (BranchStatus.COMPLETED, BranchStatus.PRUNED):
                current_path = current_path + [node]
                
                # Check if leaf node
                children = [n for n in self._nodes.values() if n.parent_id == node.id]
                
                if not children or node.status == BranchStatus.PRUNED:
                    # Calculate path metrics
                    total_score = sum(n.score for n in current_path) / len(current_path)
                    total_cost = sum(n.cost for n in current_path)
                    total_duration = sum(n.duration_sec for n in current_path)
                    completed = sum(1 for n in current_path if n.status == BranchStatus.COMPLETED)
                    success_rate = completed / len(current_path)
                    
                    paths.append(SearchPath(
                        nodes=current_path,
                        total_score=total_score,
                        total_cost=total_cost,
                        total_duration_sec=total_duration,
                        success_rate=success_rate,
                    ))
                else:
                    for child in children:
                        dfs(child, current_path)
        
        dfs(self._root, [])
        return paths
    
    def merge_branches(self, best_path: SearchPath) -> dict[str, Any]:
        """Merge findings from best path into coherent results.
        
        Args:
            best_path: Best path from tree search
            
        Returns:
            Merged results dictionary
        """
        merged = {
            "path_id": str(uuid4()),
            "total_score": best_path.total_score,
            "total_cost": best_path.total_cost,
            "branches_explored": len(best_path.nodes),
            "findings": [],
            "hypothesis": None,
            "experiment_design": None,
            "method": None,
            "results": {},
        }
        
        for node in best_path.nodes:
            if node.decision_point == DecisionPoint.HYPOTHESIS_GENERATION:
                merged["hypothesis"] = node.description
            elif node.decision_point == DecisionPoint.EXPERIMENT_DESIGN:
                merged["experiment_design"] = node.description
            elif node.decision_point == DecisionPoint.METHOD_SELECTION:
                merged["method"] = node.description
            
            # Merge results
            merged["results"].update(node.results)
            merged["findings"].append({
                "decision_point": node.decision_point.value,
                "description": node.description,
                "score": node.score,
            })
        
        return merged
    
    def get_search_statistics(self) -> dict[str, Any]:
        """Get statistics about the search process."""
        if not self._nodes:
            return {"error": "No search performed"}
        
        nodes_by_status = {}
        for node in self._nodes.values():
            status = node.status.value
            nodes_by_status[status] = nodes_by_status.get(status, 0) + 1
        
        scores = [n.score for n in self._nodes.values() if n.score > 0]
        
        return {
            "total_nodes": len(self._nodes),
            "nodes_by_status": nodes_by_status,
            "avg_score": sum(scores) / len(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "total_cost": self._total_cost,
            "total_duration_sec": sum(n.duration_sec for n in self._nodes.values()),
            "completed_paths": len(self._completed_paths),
            "best_path_score": self._completed_paths[0].total_score if self._completed_paths else 0,
        }


# Convenience function
async def explore_research_space(
    topic: str,
    domain: str = "machine_learning",
    max_branches: int = 4,
) -> dict[str, Any]:
    """Quick function to explore research space.
    
    Args:
        topic: Research topic
        domain: Research domain
        max_branches: Max parallel branches
        
    Returns:
        Merged results from best path
    """
    config = SearchConfig(max_branches=max_branches)
    search = ParallelizedTreeSearch(config)
    
    best_leaves = await search.explore(topic, domain)
    
    if search._completed_paths:
        best_path = search._completed_paths[0]
        return search.merge_branches(best_path)
    
    return {"error": "No results found"}
