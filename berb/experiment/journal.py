"""ExperimentJournal — unified attempt tree for Berb.

Provides a single, persisted, replayable structure recording every experiment
attempt with its full provenance: code, execution evidence, evaluation, figures,
scoring, and topology (parent-child relationships).

This is the substrate on which E2 (search), E3 (VLM figure verdicts),
E4 (staged escalation), E5 (multi-seed), and E7 (writeup reflection)
all depend.

Design decisions:
- Parent by ID, not by object reference (survives serialization across
  process boundaries without custom pickle support).
- Good_nodes requires BOTH clean execution AND valid figures (E3 gate).
- is_buggy_plots is Three-valued logic: None = not yet evaluated,
  must not exclude nodes before E3 is enabled.
- JSON, not pickle: human-inspectable, diffable, versionable.
- Append-only: no mutation of appended nodes; evaluation results arrive
  via record_evaluation which appends a revision.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from berb.experiment.search.scoring import ScoreBreakdown

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"


@dataclass
class JournalNode:
    """A single node in the experiment journal.

    Attributes:
        node_id: Unique identifier for this node.
        parent_id: ID of the parent node (None for root nodes).
        depth: Tree depth (0 for roots).
        phase: Research phase ("baseline", "tuning", "creative", "ablation").
        origin: How this node was created.
        plan: The experiment plan/code that was executed.
        files: Files produced as a dict of path -> content.
        plot_code: Code used to generate plots (if any).

        returncode: Process exit code.
        stdout: Standard output from execution.
        stderr: Standard error from execution.
        elapsed_sec: Wall-clock execution time in seconds.
        timed_out: Whether execution was terminated by timeout.
        metrics: Dict of metric_name -> value.

        analysis: LLM reading of stdout + traceback.
        is_buggy: Whether the run produced errors (True/False/None).
        is_buggy_plots: VLM verdict on figure quality (True/False/None).
        plot_paths: Paths to generated plot files.
        plot_analyses: VLM analysis per plot.
        vlm_feedback_summary: Overall VLM feedback text.
        score: Scored breakdown from the scoring module.

        ablation_name: Name of the ablation (if this is an ablation node).
        hyperparam_name: Name of the hyperparameter search (if applicable).
        seed: Random seed used (if applicable).
        cost_usd: Total LLM + compute cost for this node in USD.
        created_at: When this node was created.
    """

    # Identity & topology
    node_id: str
    parent_id: str | None = None
    depth: int = 0
    phase: str = "baseline"
    origin: str = "draft"  # draft, debug, improve, ablation, hyperparam, seed

    # Content
    plan: str = ""
    files: dict[str, str] = field(default_factory=dict)
    plot_code: str | None = None

    # Execution evidence
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    elapsed_sec: float | None = None
    timed_out: bool = False
    metrics: dict[str, float] = field(default_factory=dict)

    # Evaluation
    analysis: str | None = None
    is_buggy: bool | None = None
    is_buggy_plots: bool | None = None
    plot_paths: tuple[Path, ...] = field(default_factory=tuple)
    plot_analyses: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    vlm_feedback_summary: str | None = None
    score: ScoreBreakdown | None = None

    # Bookkeeping
    ablation_name: str | None = None
    hyperparam_name: str | None = None
    seed: int | None = None
    cost_usd: float = 0.0
    result_source: str = "structured"  # structured, stdout_fallback, synthesized
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        d: dict[str, Any] = {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "phase": self.phase,
            "origin": self.origin,
            "plan": self.plan,
            "files": self.files,
            "plot_code": self.plot_code,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "elapsed_sec": self.elapsed_sec,
            "timed_out": self.timed_out,
            "metrics": self.metrics,
            "analysis": self.analysis,
            "is_buggy": self.is_buggy,
            "is_buggy_plots": self.is_buggy_plots,
            "plot_paths": [str(p) for p in self.plot_paths],
            "plot_analyses": list(self.plot_analyses),
            "vlm_feedback_summary": self.vlm_feedback_summary,
            "ablation_name": self.ablation_name,
            "hyperparam_name": self.hyperparam_name,
            "seed": self.seed,
            "cost_usd": round(self.cost_usd, 6),
            "result_source": self.result_source,
            "created_at": self.created_at.isoformat(),
        }
        if self.score is not None:
            d["score"] = {
                "total": round(self.score.total, 6),
                "runs_ok": self.score.runs_ok,
                "metric_value": (
                    round(self.score.metric_value, 6)
                    if self.score.metric_value is not None
                    else None
                ),  # noqa: E501
                "metric_normalized": (
                    round(self.score.metric_normalized, 6)
                    if self.score.metric_normalized is not None
                    else None
                ),  # noqa: E501
                "buggy_plots": self.score.buggy_plots,
                "penalties": list(self.score.penalties),
                "reason": self.score.reason,
            }
        else:
            d["score"] = None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> JournalNode:
        """Deserialize from a dictionary."""
        plot_paths = tuple(Path(p) for p in d.get("plot_paths", []))
        plot_analyses = tuple(d.get("plot_analyses", []))
        created_at_raw = d.get("created_at")
        if isinstance(created_at_raw, str):
            created_at = datetime.fromisoformat(created_at_raw)
        else:
            created_at = datetime.now()

        score_raw = d.get("score")
        score: ScoreBreakdown | None = None
        if score_raw is not None and isinstance(score_raw, dict):
            from berb.experiment.search.scoring import ScoreBreakdown

            score = ScoreBreakdown(
                total=score_raw.get("total", 0.0),
                runs_ok=score_raw.get("runs_ok", False),
                metric_value=score_raw.get("metric_value"),
                metric_normalized=score_raw.get("metric_normalized"),
                buggy_plots=score_raw.get("buggy_plots"),
                penalties=tuple(score_raw.get("penalties", [])),
                reason=score_raw.get("reason", ""),
            )

        return cls(
            node_id=d["node_id"],
            parent_id=d.get("parent_id"),
            depth=d.get("depth", 0),
            phase=d.get("phase", "baseline"),
            origin=d.get("origin", "draft"),
            plan=d.get("plan", ""),
            files=d.get("files", {}),
            plot_code=d.get("plot_code"),
            returncode=d.get("returncode"),
            stdout=d.get("stdout", ""),
            stderr=d.get("stderr", ""),
            elapsed_sec=d.get("elapsed_sec"),
            timed_out=d.get("timed_out", False),
            metrics=d.get("metrics", {}),
            analysis=d.get("analysis"),
            is_buggy=d.get("is_buggy"),
            is_buggy_plots=d.get("is_buggy_plots"),
            plot_paths=plot_paths,
            plot_analyses=plot_analyses,
            vlm_feedback_summary=d.get("vlm_feedback_summary"),
            score=score,
            ablation_name=d.get("ablation_name"),
            hyperparam_name=d.get("hyperparam_name"),
            seed=d.get("seed"),
            cost_usd=d.get("cost_usd", 0.0),
            result_source=d.get("result_source", "structured"),
            created_at=created_at,
        )

    @property
    def runs_ok(self) -> bool:
        """Check if this run completed successfully (exit code 0)."""
        return self.returncode == 0


class ExperimentJournal:
    """Append-only, serializable journal of experiment attempts.

    Provides tree topology queries (roots, leaves, children_of, good_nodes)
    and best-candidate selection (best_node).

    The journal is the single source of truth for all experimentation:
    - E2 (search) selects nodes from it
    - E3 (VLM verdicts) writes to it
    - E5 (seed eval) appends to it
    - E7 (writeup reflection) reads from it
    """

    def __init__(self) -> None:
        self._nodes: list[JournalNode] = []
        self._node_map: dict[str, JournalNode] = {}
        self._schema_version: str = SCHEMA_VERSION

    # ─────────────────────────────────────────────────────────────────────────
    # Append / Mutate
    # ─────────────────────────────────────────────────────────────────────────

    def append(self, node: JournalNode) -> None:
        """Append a node to the journal.

        Nodes are append-only. Use record_evaluation to add evaluation
        results to an existing node without reassigning it.

        Args:
            node: The node to append.
        """
        self._nodes.append(node)
        self._node_map[node.node_id] = node

    def record_evaluation(
        self,
        node_id: str,
        *,
        analysis: str | None = None,
        is_buggy: bool | None = None,
        is_buggy_plots: bool | None = None,
        plot_paths: tuple[Path, ...] | None = None,
        plot_analyses: tuple[dict[str, Any], ...] | None = None,
        vlm_feedback_summary: str | None = None,
        score: ScoreBreakdown | None = None,
    ) -> None:
        """Record evaluation results for an existing node.

        This does NOT reassign the node; it updates in place. The journal
        is append-only for new nodes, but evaluation arrives asynchronously
        (VLM takes time) and must update the existing node.

        Args:
            node_id: ID of the node to update.
            analysis: LLM analysis of the run.
            is_buggy: Whether the run produced errors.
            is_buggy_plots: VLM figure quality verdict.
            plot_paths: Paths to generated plot files.
            plot_analyses: VLM analyses per plot.
            vlm_feedback_summary: VLM feedback text.
            score: Scored breakdown.
        """
        node = self._node_map.get(node_id)
        if node is None:
            logger.warning("record_evaluation: node %s not found", node_id)
            return

        if analysis is not None:
            node.analysis = analysis
        if is_buggy is not None:
            node.is_buggy = is_buggy
        if is_buggy_plots is not None:
            node.is_buggy_plots = is_buggy_plots
        if plot_paths is not None:
            node.plot_paths = plot_paths
        if plot_analyses is not None:
            node.plot_analyses = plot_analyses
        if vlm_feedback_summary is not None:
            node.vlm_feedback_summary = vlm_feedback_summary
        if score is not None:
            node.score = score

    def update_cost(self, node_id: str, cost_usd: float) -> None:
        """Update the cost for a node (called by CostTracker).

        Args:
            node_id: ID of the node to update.
            cost_usd: Total cost in USD.
        """
        node = self._node_map.get(node_id)
        if node is not None:
            node.cost_usd = cost_usd

    # ─────────────────────────────────────────────────────────────────────────
    # Queries
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def nodes(self) -> list[JournalNode]:
        """All nodes in the journal."""
        return list(self._nodes)

    def get_node(self, node_id: str) -> JournalNode | None:
        """Get a node by ID."""
        return self._node_map.get(node_id)

    def roots(self) -> list[JournalNode]:
        """All root nodes (nodes with no parent)."""
        return [n for n in self._nodes if n.parent_id is None]

    def leaves(self) -> list[JournalNode]:
        """All leaf nodes (nodes with no children)."""
        child_ids = {n.parent_id for n in self._nodes if n.parent_id is not None}
        return [n for n in self._nodes if n.node_id not in child_ids]

    def children_of(self, node_id: str) -> list[JournalNode]:
        """Direct children of a node."""
        return [n for n in self._nodes if n.parent_id == node_id]

    def siblings_of(self, node_id: str) -> list[JournalNode]:
        """Nodes sharing the same parent as the given node."""
        node = self._node_map.get(node_id)
        if node is None or node.parent_id is None:
            return []
        return [n for n in self._nodes if n.parent_id == node.parent_id and n.node_id != node_id]

    def ancestors_of(self, node_id: str) -> list[JournalNode]:
        """All ancestors of a node, root-first."""
        result: list[JournalNode] = []
        node = self._node_map.get(node_id)
        while node is not None and node.parent_id is not None:
            parent = self._node_map.get(node.parent_id)
            if parent is not None:
                result.insert(0, parent)
                node = parent
            else:
                break
        return result

    def path_from_root(self, node_id: str) -> list[JournalNode]:
        """Full path from the root to this node, inclusive."""
        ancestors = self.ancestors_of(node_id)
        node = self._node_map.get(node_id)
        if node is not None:
            ancestors.append(node)
        return ancestors

    def by_phase(self, phase: str) -> list[JournalNode]:
        """All nodes in a given phase."""
        return [n for n in self._nodes if n.phase == phase]

    def by_origin(self, origin: str) -> list[JournalNode]:
        """All nodes with a given origin."""
        return [n for n in self._nodes if n.origin == origin]

    def good_nodes(self) -> list[JournalNode]:
        """Nodes that both ran cleanly AND produced valid figures.

        Three-valued logic for is_buggy_plots:
        - True → NOT good (VLM deemed figures invalid)
        - False → good (VLM deemed figures valid)
        - None → not yet evaluated BY VLM, but acceptable if the run
                 itself was clean (VLM decision pending)

        Returns:
            List of nodes that are acceptable for selection.
        """
        return [
            n
            for n in self._nodes
            if n.is_buggy is not True  # clean run (True=buggy, False/None=ok)
            and n.is_buggy_plots is not True  # valid plots (True=invalid, False/None=ok)
        ]

    def best_node(
        self,
        metric_key: str,
        *,
        maximize: bool = True,
    ) -> JournalNode | None:
        """Find the best node by primary metric among good nodes.

        Args:
            metric_key: Primary metric name.
            maximize: True if higher is better, False if lower is better.

        Returns:
            The best node, or None if no good nodes exist.
        """
        candidates = self.good_nodes()
        if not candidates:
            return None

        scored: list[tuple[float, JournalNode]] = []
        for node in candidates:
            if metric_key in node.metrics:
                val = node.metrics[metric_key]
                if val is not None:
                    try:
                        scored.append((float(val), node))
                    except (TypeError, ValueError):
                        pass

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=maximize)
        return scored[0][1]

    def node_count(self) -> int:
        """Total number of nodes in the journal."""
        return len(self._nodes)

    # ─────────────────────────────────────────────────────────────────────────
    # Serialization
    # ─────────────────────────────────────────────────────────────────────────

    def to_json(self) -> str:
        """Serialize the journal to a JSON string."""
        data = {
            "schema_version": self._schema_version,
            "nodes": [n.to_dict() for n in self._nodes],
        }
        return json.dumps(data, indent=2, default=str)

    @classmethod
    def from_json(cls, text: str) -> ExperimentJournal:
        """Deserialize a journal from a JSON string.

        Args:
            text: JSON string.

        Returns:
            Deserialized ExperimentJournal.
        """
        data = json.loads(text)
        journal = cls()
        journal._schema_version = data.get("schema_version", SCHEMA_VERSION)

        # First pass: create all nodes
        for nd in data.get("nodes", []):
            node = JournalNode.from_dict(nd)
            journal._nodes.append(node)
            journal._node_map[node.node_id] = node

        return journal

    @classmethod
    def from_legacy_run_dir(cls, run_dir: Path | str) -> ExperimentJournal:
        """Synthesize a journal from legacy run-*.json + refinement_log.json.

        Args:
            run_dir: Path to a legacy run directory containing runs/
                and refinement_log.json.

        Returns:
            An ExperimentJournal with the available data.
        """
        import uuid as uuid_mod

        run_dir = Path(run_dir)
        journal = cls()

        # Find run files
        run_files = sorted(run_dir.glob("**/run-*.json"))
        if not run_files:
            run_files = sorted(run_dir.glob("**/runs/run-*.json"))

        for rf in run_files:
            try:
                data = json.loads(rf.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to read %s, skipping", rf)
                continue

            node = JournalNode(
                node_id=data.get("id", str(uuid_mod.uuid4())),
                parent_id=data.get("parent_id"),
                depth=data.get("depth", 0),
                phase=data.get("phase", "baseline"),
                origin=data.get("origin", "draft"),
                plan=data.get("plan", ""),
                files=data.get("files", {}),
                returncode=data.get("returncode"),
                stdout=data.get("stdout", ""),
                stderr=data.get("stderr", ""),
                elapsed_sec=data.get("elapsed_sec"),
                timed_out=data.get("timed_out", False),
                metrics=data.get("metrics", {}),
                is_buggy=data.get("is_buggy"),
                seed=data.get("seed"),
                result_source="structured",
            )
            journal.append(node)

        # Try refinement_log.json
        ref_log = run_dir / "refinement_log.json"
        if ref_log.exists():
            try:
                ref_data = json.loads(ref_log.read_text(encoding="utf-8"))
                for entry in ref_data if isinstance(ref_data, list) else [ref_data]:
                    node = JournalNode(
                        node_id=entry.get("id", str(uuid_mod.uuid4())),
                        parent_id=entry.get("parent_id"),
                        depth=entry.get("depth", 1),
                        phase=entry.get("phase", "tuning"),
                        origin="improve",
                        plan=entry.get("plan", ""),
                        files=entry.get("files", {}),
                        returncode=entry.get("returncode"),
                        stdout=entry.get("stdout", ""),
                        stderr=entry.get("stderr", ""),
                        elapsed_sec=entry.get("elapsed_sec"),
                        metrics=entry.get("metrics", {}),
                        result_source="stdout_fallback",
                    )
                    journal.append(node)
            except (json.JSONDecodeError, OSError):
                pass

        logger.info(
            "Synthesized journal from legacy run dir %s: %d nodes",
            run_dir,
            journal.node_count(),
        )
        return journal

    def write(self, path: Path | str) -> None:
        """Write the journal to a JSON file.

        Args:
            path: File path to write to.
        """
        path = Path(path)
        path.write_text(self.to_json(), encoding="utf-8")
        logger.info("Journal written to %s (%d nodes)", path, self.node_count())

    @classmethod
    def read(cls, path: Path | str) -> ExperimentJournal:
        """Read a journal from a JSON file.

        Args:
            path: File path to read from.

        Returns:
            Deserialized ExperimentJournal.
        """
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        return cls.from_json(text)

    def to_summary(self) -> dict[str, Any]:
        """Produce a human-readable summary of the journal.

        Returns:
            Dict with summary statistics.
        """
        return {
            "schema_version": self._schema_version,
            "node_count": self.node_count(),
            "root_count": len(self.roots()),
            "leaf_count": len(self.leaves()),
            "good_nodes": len(self.good_nodes()),
            "phases": {
                p: len(nodes)
                for p, nodes in {
                    phase: self.by_phase(phase) for phase in {n.phase for n in self._nodes}
                }.items()
            },
            "origins": {
                o: len(nodes)
                for o, nodes in {
                    origin: self.by_origin(origin) for origin in {n.origin for n in self._nodes}
                }.items()
            },
            "total_cost_usd": round(sum(n.cost_usd for n in self._nodes), 6),
        }
