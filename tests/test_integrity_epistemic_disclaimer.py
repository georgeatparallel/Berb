"""The epistemic output contract (berb/integrity/findings.py)."""

from __future__ import annotations

from berb.integrity import EPISTEMIC_DISCLAIMER


def test_disclaimer_is_a_nonempty_string() -> None:
    assert isinstance(EPISTEMIC_DISCLAIMER, str)
    assert EPISTEMIC_DISCLAIMER


def test_disclaimer_names_absence_of_findings() -> None:
    assert "absence of findings" in EPISTEMIC_DISCLAIMER.lower()
