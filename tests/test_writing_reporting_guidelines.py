"""Tests for berb.writing.reporting_guidelines (tasks/ars_integration_plan.md W8.1)."""

from __future__ import annotations

from berb.integrity.findings import CheckId, Severity, gates
from berb.writing.reporting_guidelines import (
    Checklist,
    ChecklistItem,
    evaluate_checklist,
    load_checklist,
)


def _checklist(*items: ChecklistItem) -> Checklist:
    return Checklist(name="test", items=items)


def _item(item_id: str, *cues: str, section: str = "Methods") -> ChecklistItem:
    return ChecklistItem(
        item_id=item_id, section=section, requirement=f"requirement for {item_id}", detect=cues
    )


# ---------------------------------------------------------------------------
# evaluate_checklist
# ---------------------------------------------------------------------------


def test_present_cue_produces_no_finding() -> None:
    checklist = _checklist(_item("randomization", "randomi"))
    findings = evaluate_checklist(checklist, "Participants were randomized into two arms.")
    assert findings == ()


def test_missing_cue_produces_advisory_finding() -> None:
    checklist = _checklist(_item("randomization", "randomi"))
    findings = evaluate_checklist(checklist, "Participants were assigned to two arms.")
    assert len(findings) == 1
    assert findings[0].check is CheckId.REPORTING_GUIDELINE
    assert findings[0].severity is Severity.ADVISORY
    assert findings[0].locator == "test:randomization"


def test_case_insensitive_match() -> None:
    checklist = _checklist(_item("blinding", "blind"))
    findings = evaluate_checklist(checklist, "The study was DOUBLE-BLIND.")
    assert findings == ()


def test_any_of_multiple_cues_satisfies_item() -> None:
    checklist = _checklist(_item("bias", "risk of bias", "selection bias"))
    findings = evaluate_checklist(checklist, "We discuss selection bias at length.")
    assert findings == ()


def test_multiple_missing_items_each_produce_a_finding() -> None:
    checklist = _checklist(_item("a", "alpha cue"), _item("b", "beta cue"))
    findings = evaluate_checklist(checklist, "Neither cue appears here.")
    assert len(findings) == 2
    assert {f.locator for f in findings} == {"test:a", "test:b"}


def test_empty_checklist_is_a_no_op() -> None:
    assert evaluate_checklist(Checklist(name="empty"), "Some paper text.") == ()


def test_empty_text_is_a_no_op() -> None:
    checklist = _checklist(_item("a", "cue"))
    assert evaluate_checklist(checklist, "") == ()


def test_advisory_never_gates_below_strict() -> None:
    checklist = _checklist(_item("a", "cue"))
    findings = evaluate_checklist(checklist, "No match.")
    assert gates(findings, "draft") == ()
    assert gates(findings, "submission") == ()
    assert gates(findings, "strict") == findings


def test_remediation_names_the_requirement_and_section() -> None:
    checklist = _checklist(_item("a", "cue", section="Results"))
    findings = evaluate_checklist(checklist, "No match.")
    assert "requirement for a" in findings[0].remediation
    assert "Results" in findings[0].remediation


# ---------------------------------------------------------------------------
# load_checklist
# ---------------------------------------------------------------------------


def test_load_checklist_missing_file_is_empty(tmp_path) -> None:
    checklist = load_checklist("nonexistent", path=tmp_path / "does-not-exist.yaml")
    assert checklist.items == ()


def test_load_checklist_malformed_yaml_is_empty(tmp_path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("{not: valid: yaml: [", encoding="utf-8")
    assert load_checklist("bad", path=p).items == ()


def test_load_checklist_not_a_dict_is_empty(tmp_path) -> None:
    p = tmp_path / "list.yaml"
    p.write_text("- a\n- b\n", encoding="utf-8")
    assert load_checklist("list", path=p).items == ()


def test_load_checklist_skips_entries_missing_required_fields(tmp_path) -> None:
    p = tmp_path / "partial.yaml"
    p.write_text(
        "items:\n"
        '  - id: ok\n    requirement: "r"\n    detect: ["cue"]\n'
        '  - id: no_requirement\n    detect: ["cue"]\n'
        '  - requirement: "no id"\n    detect: ["cue"]\n'
        '  - id: no_detect\n    requirement: "r"\n'
        '  - id: empty_detect\n    requirement: "r"\n    detect: []\n',
        encoding="utf-8",
    )
    checklist = load_checklist("partial", path=p)
    assert [i.item_id for i in checklist.items] == ["ok"]


def test_load_checklist_oversized_file_is_rejected(tmp_path) -> None:
    p = tmp_path / "huge.yaml"
    p.write_text(
        "items:\n" + ('  - id: x\n    requirement: "r"\n    detect: ["c"]\n' * 20000),
        encoding="utf-8",
    )
    assert load_checklist("huge", path=p).items == ()


def test_load_checklist_entry_count_capped(tmp_path) -> None:
    import berb.writing.reporting_guidelines as rg_mod

    entries = "\n".join(
        f'  - id: item{i}\n    requirement: "r{i}"\n    detect: ["cue{i}"]'
        for i in range(rg_mod._MAX_ITEMS + 10)
    )
    p = tmp_path / "many.yaml"
    p.write_text(f"items:\n{entries}\n", encoding="utf-8")
    checklist = load_checklist("many", path=p)
    assert len(checklist.items) <= rg_mod._MAX_ITEMS


def test_default_prisma_checklist_loads() -> None:
    checklist = load_checklist("prisma")
    assert len(checklist.items) > 0


def test_default_consort_checklist_loads() -> None:
    checklist = load_checklist("consort")
    assert len(checklist.items) > 0


def test_default_strobe_checklist_loads() -> None:
    checklist = load_checklist("strobe")
    assert len(checklist.items) > 0


def test_prisma_checklist_flags_missing_items_on_thin_paper() -> None:
    checklist = load_checklist("prisma")
    findings = evaluate_checklist(checklist, "# Paper\n\nA short paper with no methodology detail.")
    assert len(findings) > 0
    assert all(f.check is CheckId.REPORTING_GUIDELINE for f in findings)
