"""Reporting-guideline checklist screening (tasks/ars_integration_plan.md W8.1).

Checklist-as-data plus one generic evaluator. PRISMA/CONSORT/STROBE differ
in *items*, not in *evaluation logic*, so one evaluator walks whichever
checklist is loaded rather than one class per guideline — adding a new
guideline is a YAML file, not code.

Checklist item wording is paraphrased in plain language describing
well-known, public reporting-guideline concepts — NOT verbatim text from
any EQUATOR Network guideline document, whose exact checklist wording
carries its own terms. See each YAML file's header for the primary
academic source to consult for authoritative wording.

Advisory only (``Severity.ADVISORY``): a missing detection cue means a
substring search didn't find the concept in the draft text, not that the
paper is non-compliant with the guideline — always a human judgment call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from berb.integrity.findings import CheckId, Finding, Severity

logger = logging.getLogger(__name__)

_DEFAULT_DIR: Final = Path(__file__).resolve().parent.parent / "data" / "reporting_guidelines"

# Defensive caps on checklist load — same discipline as
# berb.literature.paper_mill's corpus loader.
_MAX_FILE_BYTES: Final = 200_000
_MAX_ITEMS: Final = 100


@dataclass(frozen=True)
class ChecklistItem:
    item_id: str
    section: str
    requirement: str
    detect: tuple[str, ...]
    """Case-insensitive substring cues; any one matching counts as present."""


@dataclass(frozen=True)
class Checklist:
    name: str
    items: tuple[ChecklistItem, ...] = ()


def load_checklist(name: str, *, path: Path | None = None) -> Checklist:
    """Load a named checklist (e.g. ``"prisma"``) from
    ``berb/data/reporting_guidelines/{name}.yaml``, or *path* if given.

    Never raises — a missing, oversized, or malformed checklist degrades
    to an empty ``Checklist`` (``evaluate_checklist`` is then a guaranteed
    no-op), matching ``berb.literature.paper_mill.load_corpus``'s
    fail-safe-to-no-op discipline.
    """
    checklist_path = path or (_DEFAULT_DIR / f"{name}.yaml")
    try:
        if not checklist_path.is_file():
            logger.warning("Reporting-guideline checklist not found: %s", checklist_path)
            return Checklist(name=name)
        if checklist_path.stat().st_size > _MAX_FILE_BYTES:
            logger.warning(
                "Reporting-guideline checklist exceeds size cap, skipping: %s",
                checklist_path,
            )
            return Checklist(name=name)
        raw: Any = yaml.safe_load(checklist_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        logger.warning("Failed to load checklist %s: %s", checklist_path, exc)
        return Checklist(name=name)

    entries = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        return Checklist(name=name)

    items: list[ChecklistItem] = []
    for entry in entries[:_MAX_ITEMS]:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("id", "")).strip()
        requirement = str(entry.get("requirement", "")).strip()
        raw_detect = entry.get("detect", [])
        if not item_id or not requirement or not isinstance(raw_detect, list):
            continue
        cues = tuple(str(cue).strip().lower() for cue in raw_detect if str(cue).strip())
        if not cues:
            continue
        items.append(
            ChecklistItem(
                item_id=item_id,
                section=str(entry.get("section", "")).strip(),
                requirement=requirement,
                detect=cues,
            )
        )
    return Checklist(name=name, items=tuple(items))


def evaluate_checklist(checklist: Checklist, draft_text: str) -> tuple[Finding, ...]:
    """For each checklist item, pass if any of its ``detect`` cues appears
    (case-insensitively, as a plain substring — never a regex) in
    *draft_text*; otherwise emit an advisory finding naming the missing
    item. Pure, total, never raises."""
    if not checklist.items or not draft_text:
        return ()

    lowered = draft_text.lower()
    findings: list[Finding] = []
    for item in checklist.items:
        if any(cue in lowered for cue in item.detect):
            continue
        remediation = f"Add or clarify: {item.requirement}"
        if item.section:
            remediation += f" (typically in: {item.section})"
        findings.append(
            Finding(
                check=CheckId.REPORTING_GUIDELINE,
                severity=Severity.ADVISORY,
                message=(
                    f"{checklist.name.upper()} item {item.item_id!r} not detected: "
                    f"{item.requirement}"
                ),
                locator=f"{checklist.name}:{item.item_id}",
                remediation=remediation,
            )
        )
    return tuple(findings)
