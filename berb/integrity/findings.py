"""Shared finding/severity vocabulary for the Berb integrity screening layer.

Every screening check (retraction status, uncited-assertion detection,
citation anchors, paper-mill risk, revision guards, cross-model verification)
returns ``Finding`` objects through this module rather than raising or
deciding gate behaviour itself.  ``gates()`` is the single place severity is
turned into a pass/fail decision, driven by ``IntegrityConfig.mode`` — see
``tasks/ars_integration_plan.md`` sections 3 and 12 for the design rationale.

A check that raises kills a 23-stage pipeline run over what may be an
advisory-only observation.  Checks must be total: given any input they
return a (possibly empty) tuple of findings, never an exception for a
detection outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from berb.config import IntegrityConfig

# Evidence spans quoted into a Finding (e.g. the offending sentence, the
# mismatched quote) are attacker-influenceable paper/PDF text.  Capping their
# length bounds both the size of persisted findings and how much untrusted
# text a downstream consumer could re-inject into a prompt.
MAX_EVIDENCE_SPAN_CHARS = 300


class Severity(StrEnum):
    """How strongly a finding should be treated once surfaced.

    Gate behaviour is a function of (severity, ``IntegrityConfig.mode``) —
    see ``gates()``. A severity level does not gate anything by itself.
    """

    INFO = "info"
    """Observation only. Never gates a stage, in any mode."""

    ADVISORY = "advisory"
    """Judgment-based or heuristic signal. Gates only in ``strict`` mode."""

    WARN = "warn"
    """High-precision but not certain. Gates in ``submission`` and ``strict``."""

    BLOCK = "block"
    """The check's own domain considers this a hard failure (e.g. a quote
    that does not appear in its cited source). Gates in ``submission`` and
    ``strict`` — mode ``draft`` is warn-only for every severity, matching
    ``IntegrityConfig.mode``'s documented "draft (warn only)" contract."""


class CheckId(StrEnum):
    """Stable identifiers for each screening check.

    Persisted in finding records and run artifacts — treat as append-only.
    """

    RETRACTION = "retraction"
    UNCITED_ASSERTION = "uncited_assertion"
    PAPER_MILL_RISK = "paper_mill_risk"
    ANCHOR_UNRESOLVED = "anchor_unresolved"
    ANCHOR_QUOTE_MISMATCH = "anchor_quote_mismatch"
    ANCHOR_UNVERIFIABLE = "anchor_unverifiable"
    TOKEN_CONSERVATION = "token_conservation"
    CLAIM_STRENGTH_DRIFT = "claim_strength_drift"
    CROSS_MODEL_UNVERIFIED = "cross_model_unverified"


def _capped(spans: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(s[:MAX_EVIDENCE_SPAN_CHARS] for s in spans)


@dataclass(frozen=True)
class Finding:
    """A single screening result. Immutable value object — see
    ``berb/pipeline/contracts.py`` for the same frozen-dataclass convention
    used for other pure pipeline signals."""

    check: CheckId
    severity: Severity
    message: str
    locator: str = ""
    """Where the finding applies — e.g. ``"paper.md:412"`` or a cite_key.
    Never a raw filesystem path outside the run directory."""

    evidence: tuple[str, ...] = field(default_factory=tuple)
    """Short quoted spans supporting the finding. Length-capped per entry
    (see ``MAX_EVIDENCE_SPAN_CHARS``) — this is untrusted paper-derived
    text and must stay bounded wherever it is persisted or re-displayed."""

    remediation: str = ""

    def __post_init__(self) -> None:
        # Enforce the cap even if a caller builds a Finding directly.
        object.__setattr__(self, "evidence", _capped(tuple(self.evidence)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check.value,
            "severity": self.severity.value,
            "message": self.message,
            "locator": self.locator,
            "evidence": list(self.evidence),
            "remediation": self.remediation,
        }


# Severity x mode gate truth table. `draft` gates nothing — IntegrityConfig
# documents mode="draft" as warn-only for every check. `submission` and
# `strict` differ only in whether ADVISORY findings gate.
_GATING_SEVERITIES_BY_MODE: dict[str, frozenset[Severity]] = {
    "draft": frozenset(),
    "submission": frozenset({Severity.WARN, Severity.BLOCK}),
    "strict": frozenset({Severity.ADVISORY, Severity.WARN, Severity.BLOCK}),
}


def gates(
    findings: tuple[Finding, ...],
    mode: str,
    cfg: IntegrityConfig | None = None,
) -> tuple[Finding, ...]:
    """Return the subset of ``findings`` that must fail the current stage.

    ``cfg`` is accepted for forward compatibility with per-check
    ``fail_on_*`` overrides in ``IntegrityConfig`` (e.g. a future
    ``fail_on_retraction=False`` escape hatch) but is not yet consulted —
    today gating is mode-only, exactly as specified in
    ``tasks/ars_integration_plan.md`` W0.2.  Unknown modes gate nothing
    rather than fail closed on a typo'd config value; callers that want
    fail-closed-on-unknown behaviour should validate ``mode`` up front
    (``berb.config`` already restricts it to the three known values).
    """
    del cfg  # reserved, see docstring
    gating = _GATING_SEVERITIES_BY_MODE.get(mode, frozenset())
    return tuple(f for f in findings if f.severity in gating)
