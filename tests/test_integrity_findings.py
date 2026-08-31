"""Tests for berb.integrity.findings — the severity/gate vocabulary shared
by the W1-W6 screening checks (tasks/ars_integration_plan.md W0.2)."""

from __future__ import annotations

import itertools

import pytest

from berb.integrity.findings import (
    MAX_EVIDENCE_SPAN_CHARS,
    CheckId,
    Finding,
    Severity,
    gates,
)


def _finding(severity: Severity) -> Finding:
    return Finding(
        check=CheckId.RETRACTION,
        severity=severity,
        message="test finding",
    )


# Exhaustive severity x mode truth table (4 severities x 3 modes = 12 cases).
_TRUTH_TABLE = {
    ("draft", Severity.INFO): False,
    ("draft", Severity.ADVISORY): False,
    ("draft", Severity.WARN): False,
    ("draft", Severity.BLOCK): False,
    ("submission", Severity.INFO): False,
    ("submission", Severity.ADVISORY): False,
    ("submission", Severity.WARN): True,
    ("submission", Severity.BLOCK): True,
    ("strict", Severity.INFO): False,
    ("strict", Severity.ADVISORY): True,
    ("strict", Severity.WARN): True,
    ("strict", Severity.BLOCK): True,
}


@pytest.mark.parametrize(("mode", "severity"), list(_TRUTH_TABLE))
def test_gates_truth_table(mode: str, severity: Severity) -> None:
    finding = _finding(severity)
    result = gates((finding,), mode)
    expected_gated = _TRUTH_TABLE[(mode, severity)]
    assert (finding in result) is expected_gated


def test_truth_table_is_exhaustive() -> None:
    modes = {"draft", "submission", "strict"}
    severities = set(Severity)
    assert set(_TRUTH_TABLE) == set(itertools.product(modes, severities))


def test_info_never_gates_in_any_mode() -> None:
    finding = _finding(Severity.INFO)
    for mode in ("draft", "submission", "strict", "unknown-mode"):
        assert gates((finding,), mode) == ()


def test_unknown_mode_gates_nothing() -> None:
    finding = _finding(Severity.BLOCK)
    assert gates((finding,), "not-a-real-mode") == ()


def test_gates_preserves_order_and_is_pure() -> None:
    findings = (
        _finding(Severity.INFO),
        _finding(Severity.WARN),
        _finding(Severity.ADVISORY),
        _finding(Severity.BLOCK),
    )
    result = gates(findings, "strict")
    assert result == (findings[1], findings[2], findings[3])
    # Purity: calling again with the same args returns an equal result and
    # the input tuple is untouched.
    assert gates(findings, "strict") == result
    assert findings == (
        _finding(Severity.INFO),
        _finding(Severity.WARN),
        _finding(Severity.ADVISORY),
        _finding(Severity.BLOCK),
    )


def test_finding_evidence_is_length_capped() -> None:
    long_span = "x" * (MAX_EVIDENCE_SPAN_CHARS + 500)
    finding = Finding(
        check=CheckId.UNCITED_ASSERTION,
        severity=Severity.WARN,
        message="m",
        evidence=(long_span,),
    )
    assert len(finding.evidence[0]) == MAX_EVIDENCE_SPAN_CHARS


def test_finding_is_frozen() -> None:
    finding = _finding(Severity.WARN)
    with pytest.raises(AttributeError):
        finding.message = "mutated"  # type: ignore[misc]


def test_finding_to_dict_round_trips_fields() -> None:
    finding = Finding(
        check=CheckId.ANCHOR_QUOTE_MISMATCH,
        severity=Severity.BLOCK,
        message="quote does not match source",
        locator="paper.md:412",
        evidence=("the quoted span",),
        remediation="fix the quote or drop the anchor",
    )
    d = finding.to_dict()
    assert d == {
        "check": "anchor_quote_mismatch",
        "severity": "block",
        "message": "quote does not match source",
        "locator": "paper.md:412",
        "evidence": ["the quoted span"],
        "remediation": "fix the quote or drop the anchor",
    }
