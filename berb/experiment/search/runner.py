"""SearchRunner — orchestrates parallel tree-diverse experiment search.

Evaluates candidates in isolated sandboxes, applies budget governance,
selects the best result, and records everything in the ExperimentJournal.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from berb.experiment.journal import ExperimentJournal, JournalNode
from berb.experiment.search.policy import SearchConfig, SearchPolicy
from berb.experiment.search.scoring import ScoreBreakdown, score_node
from berb.llm.cost_tracker import CostTracker, get_cost_tracker

logger = logging.getLogger(__name__)

# Type alias for a sandbox factory callable
SandboxFactory = Callable[[], Any]


@dataclass
class SearchResult:
    """Result from a search run.

    Attributes:
        best_node: The highest-scoring node found.
        journal: The populated experiment journal.
        termination_reason: Why search stopped.
        nodes_explored: Total nodes evaluated.
        total_cost_usd: Total cost incurred.
        total_wallclock_sec: Total wall-clock time.
    """

    best_node: JournalNode | None
    journal: ExperimentJournal
    termination_reason: str
    nodes_explored: int
    total_cost_usd: float
    total_wallclock_sec: float


class BudgetGovernor:
    """Tracks accumulated cost and wall-clock time, stopping search when
    limits are breached.

    Before each batch, the runner checks the governor. On breach,
    it stops expansion, evaluates outstanding nodes, and returns
    the best found so far. Search NEVER terminates without a result.
    """

    def __init__(
        self,
        config: SearchConfig,
        cost_tracker: CostTracker,
    ) -> None:
        self._config = config
        self._cost_tracker = cost_tracker
        self._start_time = time.monotonic()

    def check(self, nodes_completed: int) -> str | None:
        """Check budget limits.

        Returns:
            None if within budget, or a termination reason string if breached.
        """
        elapsed = time.monotonic() - self._start_time
        if elapsed > self._config.budget_wallclock_sec:
            return (
                f"wallclock budget exceeded ({elapsed:.0f}s > {self._config.budget_wallclock_sec}s)"
            )

        total_cost = self._cost_tracker.total_usd()
        if total_cost > self._config.budget_usd:
            return f"cost budget exceeded (${total_cost:.2f} > ${self._config.budget_usd:.2f})"

        if nodes_completed >= self._config.max_nodes:
            return f"max_nodes reached ({nodes_completed} >= {self._config.max_nodes})"

        return None

    def elapsed_sec(self) -> float:
        """Seconds since start."""
        return time.monotonic() - self._start_time


class SearchRunner:
    """Orchestrates parallel tree-diverse search over experiment candidates.

    Architecture:
        SearchRunner loops over batches of candidate evaluations.
        Each batch:
        1. Asks the SearchPolicy which nodes to expand next.
        2. Generates candidate code via a Generator callable.
        3. Dispatches evaluations to a sandbox factory.
        4. Scores results and appends to the journal.
        5. Checks the BudgetGovernor.

    The runner is agnostic to HOW candidates are generated —
    that is injected via the generator callable, which returns
    a list of (files, plan, node_origin) tuples.
    """

    def __init__(
        self,
        config: SearchConfig,
        policy: SearchPolicy,
        sandbox_factory: SandboxFactory,
        generator: Callable[..., list[dict[str, Any]]],
        *,
        cost_tracker: CostTracker | None = None,
        metric_key: str = "",
        metric_maximize: bool = True,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        """Initialize SearchRunner.

        Args:
            config: Search configuration.
            policy: Node selection policy.
            sandbox_factory: Factory creating isolated sandbox environments.
            generator: Callable that returns a list of candidate dicts,
                each with keys "files" (dict[str,str]), "plan" (str), and
                "origin" (str).
            cost_tracker: Optional cost tracker. Uses global singleton if None.
            metric_key: Primary metric key for scoring.
            metric_maximize: True if higher metric is better.
            semaphore: Optional concurrency limiter. Uses
                asyncio.Semaphore(config.num_workers) if None.
        """
        self._config = config
        self._policy = policy
        self._sandbox_factory = sandbox_factory
        self._generator = generator
        self._cost_tracker = cost_tracker or get_cost_tracker()
        self._metric_key = metric_key
        self._metric_maximize = metric_maximize
        self._semaphore = semaphore or asyncio.Semaphore(config.num_workers)

        self._journal = ExperimentJournal()
        self._governor = BudgetGovernor(config, self._cost_tracker)
        self._node_counter = 0

    async def run(
        self,
        topic: str = "",
        exp_plan: str = "",
        context: dict[str, Any] | None = None,
    ) -> SearchResult:
        """Run the search until a termination condition is met.

        Args:
            topic: Research topic.
            exp_plan: Experiment plan text.
            context: Additional context for the generator.

        Returns:
            SearchResult with the best node and journal.
        """
        t0 = time.monotonic()
        context = context or {}
        termination_reason = "exhausted"

        while True:
            # 1. Check budget
            reason = self._governor.check(self._node_counter)
            if reason is not None:
                termination_reason = reason
                logger.info("Search stopping: %s", reason)
                break

            # 2. Ask policy which nodes to expand
            selections = self._policy.select(
                self._journal,
                n=self._config.num_workers,
                config=self._config,
            )

            # 3. Expand each selection
            tasks = []
            for sel in selections:
                tasks.append(self._expand_one(sel, topic, exp_plan, context))

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # 4. Process results
            has_new = False
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error("Batch evaluation failed: %s", result)
                    continue
                if result is not None:
                    has_new = True

            # 5. If nothing new was added and no roots to grow, stop
            if not has_new:
                if self._journal.roots():
                    termination_reason = "no_new_candidates"
                    break

        # Determine best node
        best = self._journal.best_node(
            self._metric_key,
            maximize=self._metric_maximize,
        )

        elapsed = time.monotonic() - t0
        logger.info(
            "Search complete: %d nodes explored, best=%s, reason=%s, cost=$%.4f, wall=%.1fs",
            self._node_counter,
            best.node_id[:8] if best else "none",
            termination_reason,
            self._cost_tracker.total_usd(),
            elapsed,
        )

        return SearchResult(
            best_node=best,
            journal=self._journal,
            termination_reason=termination_reason,
            nodes_explored=self._node_counter,
            total_cost_usd=self._cost_tracker.total_usd(),
            total_wallclock_sec=elapsed,
        )

    async def _expand_one(
        self,
        selection: JournalNode | None,
        topic: str,
        exp_plan: str,
        context: dict[str, Any],
    ) -> JournalNode | None:
        """Expand one policy selection: generate code and evaluate it.

        Args:
            selection: The node to expand, or None for a new root.
            topic: Research topic.
            exp_plan: Experiment plan.
            context: Additional context.

        Returns:
            The resulting JournalNode, or None if generation failed.
        """
        # Generate candidate code
        if selection is None:
            # New root — full generation
            candidates = self._generator(
                topic=topic,
                exp_plan=exp_plan,
                context=context,
                origin="draft",
            )
        else:
            # Improve existing node
            candidates = self._generator(
                topic=topic,
                exp_plan=exp_plan,
                context=context,
                origin="improve",
                parent_files=selection.files,
                parent_stdout=selection.stdout,
                parent_stderr=selection.stderr,
                parent_analysis=selection.analysis,
            )

        if not candidates:
            logger.debug("Generator returned no candidates for selection")
            return None

        candidate = candidates[0]
        node_id = str(uuid.uuid4())
        phase = selection.phase if selection else context.get("phase", "baseline")
        depth = (selection.depth + 1) if selection else 0

        node = JournalNode(
            node_id=node_id,
            parent_id=selection.node_id if selection else None,
            depth=depth,
            phase=phase,
            origin=candidate.get("origin", "draft"),
            plan=candidate.get("plan", ""),
            files=candidate.get("files", {}),
        )
        self._journal.append(node)

        # Evaluate in sandbox
        async with self._semaphore:
            node = await self._evaluate_node(node)

        self._node_counter += 1
        return node

    async def _evaluate_node(self, node: JournalNode) -> JournalNode:
        """Evaluate a single node's code in a sandbox.

        Args:
            node: The node to evaluate.

        Returns:
            The updated node with execution results and score.
        """
        if not node.files:
            node.is_buggy = True
            node.score = ScoreBreakdown(
                total=0.0,
                runs_ok=False,
                reason="No files to evaluate",
            )
            return node

        try:
            sandbox = self._sandbox_factory()
            # Execute the code — exact sandbox interface depends on the
            # concrete factory, but standard attributes:
            result = await asyncio.wait_for(
                self._run_in_sandbox(sandbox, node.files),
                timeout=self._config.eval_timeout_sec,
            )

            # Populate execution results
            node.returncode = getattr(result, "returncode", 0)
            node.stdout = getattr(result, "stdout", "")
            node.stderr = getattr(result, "stderr", "")
            node.elapsed_sec = getattr(result, "elapsed_sec", None)
            node.timed_out = False
            node.is_buggy = node.returncode != 0

            # Parse metrics (from stdout or structured result)
            node.metrics = {}
            result_metrics = getattr(result, "metrics", None) or {}
            if result_metrics:
                # Coerce values to float
                for k, v in result_metrics.items():
                    try:
                        node.metrics[k] = float(v)
                    except (TypeError, ValueError):
                        pass

            if not node.metrics:
                # Try parsing from stdout
                parsed = self._parse_metrics_from_stdout(node.stdout)
                if parsed:
                    node.metrics.update(parsed)
                    node.result_source = "stdout_fallback"

        except TimeoutError:
            node.returncode = -1
            node.stderr = "Timed out"
            node.timed_out = True
            node.is_buggy = True
            logger.warning(
                "Node %s timed out after %ds", node.node_id[:8], self._config.eval_timeout_sec
            )

        except Exception as e:
            node.returncode = -1
            node.stderr = str(e)
            node.is_buggy = True
            logger.error("Node %s evaluation failed: %s", node.node_id[:8], e)

        # Score the node
        all_nodes = self._journal.good_nodes() + [node]
        node.score = score_node(
            node,
            self._metric_key,
            maximize=self._metric_maximize,
            cohort=all_nodes if len(all_nodes) > 1 else None,
        )

        # Update cost from tracker
        node.cost_usd = self._cost_tracker.total_usd()

        # Update the journal with evaluation results
        self._journal.record_evaluation(
            node.node_id,
            is_buggy=node.is_buggy,
            score=node.score,
        )

        return node

    async def _run_in_sandbox(self, sandbox: Any, files: dict[str, str]) -> Any:
        """Run candidate code in a sandbox.

        Concrete sandbox implementations should return an object with:
        - returncode: int
        - stdout: str
        - stderr: str
        - elapsed_sec: float
        - metrics: dict[str, float]

        Args:
            sandbox: Sandbox instance from factory.
            files: Dict of filename -> code content.

        Returns:
            Result object.
        """
        # Default implementation: write files to sandbox and run
        if hasattr(sandbox, "write_files"):
            sandbox.write_files(files)

        if hasattr(sandbox, "run"):
            return await sandbox.run()

        raise NotImplementedError(f"Sandbox {type(sandbox).__name__} does not support run()")

    def _parse_metrics_from_stdout(self, stdout: str) -> dict[str, float]:
        """Parse metrics from stdout fallback.

        Looks for lines containing "metric:" or "result:" patterns.

        Args:
            stdout: Process stdout.

        Returns:
            Dict of metric name -> value.
        """
        import re

        metrics: dict[str, float] = {}

        # Pattern: "metric_name: value" or "metric_name = value"
        patterns = [
            r"(?:metric|result|score)\s*[:=]\s*([0-9.]+)",
            r"(\w+)\s*[:=]\s*([0-9.]+)\s*(?:$|,|\s)",
        ]

        for line in stdout.split("\n"):
            line = line.strip().lower()
            for pat in patterns:
                m = re.search(pat, line)
                if m:
                    try:
                        val = float(m.group(1))
                        metrics["parsed_metric"] = val
                        break
                    except ValueError:
                        pass

        return metrics

    @property
    def journal(self) -> ExperimentJournal:
        """The populated experiment journal."""
        return self._journal
