"""World model for the cyclic discovery loop (E2).

A typed, pure-domain state machine that tracks what the research system
knows, what it has ruled out, and what remains to explore.  No LLM calls,
no I/O — fully unit-testable.

The world model prevents re-exploration of dead ends and surfaces
contradictions that steer the next cycle's hypothesis generation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Supporting types
# ─────────────────────────────────────────────────────────────────────────────


class FindingVerdict(str, Enum):
    """Whether a finding was empirically supported or refuted."""
    SUPPORTED = "supported"
    REFUTED = "refuted"


@dataclass(frozen=True)
class Finding:
    """A single empirical or literature finding."""
    id: str
    statement: str
    verdict: FindingVerdict
    metric_key: str = ""
    effect_size: float = 0.0
    source_cycle: int = 1


@dataclass(frozen=True)
class Question:
    """An open research question."""
    id: str
    text: str
    priority: float = 0.5
    source_cycle: int = 1


@dataclass(frozen=True)
class Contradiction:
    """Two findings that cannot both be true."""
    finding_a_id: str
    finding_b_id: str
    description: str


@dataclass(frozen=True)
class DeadEnd:
    """A path that was explored and found unproductive."""
    description: str
    reason: str
    source_cycle: int = 1


@dataclass
class Guidance:
    """Strategic guidance produced by the REFLECT step."""
    gaps: list[str] = field(default_factory=list)
    confounds: list[str] = field(default_factory=list)
    compound_hypotheses: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# The world model
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class WorldModel:
    """Structured state of the research system's current knowledge.

    This replaces a flat KV store with typed epistemic slots:
    - ``established`` — findings that passed the F2/F3 predicate
    - ``refuted`` — findings that were rejected; kept to guide REFLECT
    - ``open_questions`` — questions still to be answered
    - ``contradictions`` — pairs of findings that conflict
    - ``dead_ends`` — paths already explored and found unproductive
    - ``current_best_explanation`` — the leading explanation so far
    - ``guidance`` — optional directional signal from REFLECT

    The model is per-run and bounded: ``established``/``refuted`` lists
    are capped with summarisation beyond a configured size.
    """

    objective: str
    """The research objective this world model tracks."""

    established: list[Finding] = field(default_factory=list)
    """Findings that passed the F2/F3 admissibility predicate."""

    refuted: list[Finding] = field(default_factory=list)
    """Findings that were rejected.  Kept to steer REFLECT away from
    repeating the same mistakes."""

    open_questions: list[Question] = field(default_factory=list)
    """Questions the system has identified but not yet answered."""

    contradictions: list[Contradiction] = field(default_factory=list)
    """Explicit contradictions between established findings.
    Surfacing these is a key mechanism from OriGene."""

    dead_ends: list[DeadEnd] = field(default_factory=list)
    """Paths explored and found unproductive.  The anti-re-exploration
    mechanism — cycle N+1 must not re-propose cycle N's failures."""

    current_best_explanation: str = ""
    """The best explanation so far, synthesised from established findings."""

    guidance: Guidance | None = None
    """Optional directional signal produced by the REFLECT step."""

    max_list_size: int = 50
    """Maximum size of any list before summarisation kicks in."""

    current_cycle: int = 0
    """The current discovery cycle number (0 = initial state)."""

    def update(
        self,
        new_findings: list[Finding],
        rejected: list[Finding],
        new_questions: list[Question] | None = None,
        new_dead_ends: list[DeadEnd] | None = None,
        new_contradictions: list[Contradiction] | None = None,
    ) -> None:
        """Update the world model with outputs from a discovery cycle.

        Args:
            new_findings: Findings that passed the F2/F3 predicate.
            rejected: Findings that were rejected.
            new_questions: New open questions identified.
            new_dead_ends: New dead ends to record.
            new_contradictions: New contradictions found.
        """
        self.established.extend(new_findings)
        self.refuted.extend(rejected)
        if new_questions:
            self.open_questions.extend(new_questions)
        if new_dead_ends:
            self.dead_ends.extend(new_dead_ends)
        if new_contradictions:
            self.contradictions.extend(new_contradictions)

        # Cap lists to prevent unbounded growth
        self._cap_list(self.established)
        self._cap_list(self.refuted)
        self._cap_list(self.open_questions)
        self._cap_list(self.dead_ends)
        self._cap_list(self.contradictions)

        self.current_cycle += 1

    def _cap_list(self, lst: list) -> None:
        """Trim a list to ``max_list_size``, keeping the most recent entries."""
        while len(lst) > self.max_list_size:
            lst.pop(0)

    def propose_tasks(self, k: int = 3) -> list[str]:
        """Propose exploration tasks for the next cycle.

        Uses the current state to suggest directions.  Avoids dead ends
        and favours open questions and contradictions.

        Args:
            k: Number of tasks to propose.

        Returns:
            A list of task descriptions.
        """
        tasks: list[str] = []

        # 1. Follow up on contradictions
        for c in self.contradictions[:k]:
            tasks.append(
                f"Resolve contradiction: {c.description}"
            )

        # 2. Pursue high-priority open questions
        sorted_qs = sorted(self.open_questions, key=lambda q: q.priority, reverse=True)
        for q in sorted_qs[:k]:
            tasks.append(
                f"Investigate: {q.text}"
            )

        # 3. Follow guidance if available
        if self.guidance:
            for g in self.guidance.gaps[:k]:
                tasks.append(f"Address gap: {g}")

        # 4. Fallback: propose from best explanation
        if not tasks and self.current_best_explanation:
            tasks.append(
                f"Strengthen or challenge: {self.current_best_explanation[:200]}"
            )

        # 5. Last resort: generic exploration
        if not tasks:
            tasks.append(
                f"Explore new directions for: {self.objective[:200]}"
            )

        return tasks[:k]

    def is_dead_end(self, description: str) -> bool:
        """Check if a description matches a known dead end.

        Args:
            description: The proposed exploration direction.

        Returns:
            True if this direction has been tried and ruled out.
        """
        desc_lower = description.lower()
        for de in self.dead_ends:
            if de.description.lower() in desc_lower or desc_lower in de.description.lower():
                return True
        return False

    def converged(self, min_established: int = 3) -> bool:
        """Check whether the world model has converged.

        Convergence means: enough established findings to draw a conclusion,
        no unresolved contradictions, and no high-priority open questions.

        Args:
            min_established: Minimum number of established findings needed.

        Returns:
            True if converged.
        """
        if len(self.established) < min_established:
            return False
        if self.contradictions:
            return False
        high_priority = [q for q in self.open_questions if q.priority > 0.7]
        if high_priority:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-compatible dict for ``world_model.json``."""
        return {
            "objective": self.objective,
            "current_cycle": self.current_cycle,
            "converged": self.converged(),
            "established": [vars(f) for f in self.established],
            "refuted": [vars(f) for f in self.refuted],
            "open_questions": [vars(q) for q in self.open_questions],
            "contradictions": [vars(c) for c in self.contradictions],
            "dead_ends": [vars(d) for d in self.dead_ends],
            "current_best_explanation": self.current_best_explanation,
            "guidance": vars(self.guidance) if self.guidance else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorldModel:
        """Restore from a dict produced by ``to_dict``."""
        wm = cls(
            objective=data.get("objective", ""),
            current_cycle=data.get("current_cycle", 0),
            current_best_explanation=data.get("current_best_explanation", ""),
        )
        for f_data in data.get("established", []):
            wm.established.append(Finding(**f_data))
        for f_data in data.get("refuted", []):
            wm.refuted.append(Finding(**f_data))
        for q_data in data.get("open_questions", []):
            wm.open_questions.append(Question(**q_data))
        for c_data in data.get("contradictions", []):
            wm.contradictions.append(Contradiction(**c_data))
        for d_data in data.get("dead_ends", []):
            wm.dead_ends.append(DeadEnd(**d_data))
        g_data = data.get("guidance")
        if g_data:
            wm.guidance = Guidance(**g_data)
        return wm
