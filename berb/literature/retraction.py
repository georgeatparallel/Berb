"""Per-work retraction / expression-of-concern status (tasks/ars_integration_plan.md W2).

Berb verifies that a cited work *exists* (``berb/literature/verify.py``,
``berb/pipeline/citation_verification.py``) but never whether it was
subsequently retracted or flagged.  This module closes that gap by parsing
the retraction-relevant fields OpenAlex and Crossref already put in their
work records — no new endpoint, no new network dependency.

Design (functional core, imperative shell — see plan §5):

- ``parse_retraction`` is a pure, total function: raw API dicts in, a
  ``RetractionRecord`` out, never raises.
- ``screen_bibliography`` is a pure function over already-resolved records.
- ``cached_lookup`` / ``store_lookup`` are the only impure parts, and they
  reuse ``berb.literature.cache`` rather than inventing a second cache.

Index coverage of retractions is incomplete, so "no usable metadata" must
never render as "clean" — that is why ``RetractionState.UNKNOWN`` exists and
never gates. See ``berb/integrity/findings.py`` for the severity model.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from berb.integrity.findings import CheckId, Finding, Severity
from berb.literature import cache as _cache

logger = logging.getLogger(__name__)

# Retraction status is far less volatile than search results, and a false
# "clean" reading is the failure mode we most want to avoid — so this gets
# its own, longer TTL rather than the default per-source ones in cache.py.
RETRACTION_TTL_SEC = 86400 * 30  # 30 days
_CACHE_SOURCE = "retraction_status"

# Fixed https:// API bases — same hosts berb/literature/verify.py and
# berb/literature/openalex_client.py already call. DOI is percent-encoded
# via urllib.parse.quote before insertion, so an attacker-influenceable DOI
# string (from LLM-extracted BibTeX) cannot redirect the request or inject
# path segments. This matches the B310 bandit-skip rationale in
# pyproject.toml: fixed API base, no caller-supplied host.
_CROSSREF_WORKS_URL = "https://api.crossref.org/works"
_OPENALEX_WORKS_URL = "https://api.openalex.org/works"
_FETCH_TIMEOUT_SEC = 20
_POLITE_EMAIL = "berb@users.noreply.github.com"

# Defensive caps on external-API list fields (R6: untrusted input) — a
# malformed or hostile payload should not let this module iterate or
# allocate without bound.
_MAX_EVENTS = 20
_MAX_FIELD_CHARS = 200


class RetractionState(StrEnum):
    """Tri-state plus UNKNOWN. UNKNOWN is load-bearing: it is what a caller
    sees when there was no usable metadata, and it must never be treated as
    equivalent to NONE."""

    NONE = "none"
    """Metadata present; no retraction or concern event found."""

    CONCERN = "expression_of_concern"
    RETRACTED = "retracted"

    UNKNOWN = "unknown"
    """No usable metadata (missing payload, malformed fields, or the work
    predates/escapes both indexes' retraction coverage)."""


_STATE_SEVERITY: dict[RetractionState, Severity] = {
    RetractionState.NONE: Severity.INFO,
    RetractionState.UNKNOWN: Severity.INFO,
    RetractionState.CONCERN: Severity.WARN,
    RetractionState.RETRACTED: Severity.BLOCK,
}

# Crossref `update-to[].type` values (and OpenAlex's boolean, handled
# separately) that count as adverse events, ranked by severity so a work
# with multiple events reports its worst one.
_ADVERSE_TYPES: dict[str, RetractionState] = {
    "retraction": RetractionState.RETRACTED,
    "expression of concern": RetractionState.CONCERN,
    "expression_of_concern": RetractionState.CONCERN,
}
_STATE_RANK: dict[RetractionState, int] = {
    RetractionState.UNKNOWN: 0,
    RetractionState.NONE: 1,
    RetractionState.CONCERN: 2,
    RetractionState.RETRACTED: 3,
}


@dataclass(frozen=True)
class RetractionRecord:
    """Resolved retraction status for one cite_key / DOI."""

    cite_key: str
    state: RetractionState
    detail: str = ""
    """Human-readable summary, e.g. the Crossref update type and date."""

    def to_dict(self) -> dict[str, Any]:
        return {"cite_key": self.cite_key, "state": self.state.value, "detail": self.detail}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetractionRecord:
        try:
            state = RetractionState(str(data.get("state", "unknown")))
        except ValueError:
            state = RetractionState.UNKNOWN
        return cls(
            cite_key=str(data.get("cite_key", "")),
            state=state,
            detail=str(data.get("detail", ""))[:_MAX_FIELD_CHARS],
        )


def _truncate(value: Any) -> str:
    return str(value)[:_MAX_FIELD_CHARS] if value is not None else ""


def _from_crossref(message: dict[str, Any] | None) -> tuple[RetractionState, str]:
    if not isinstance(message, dict):
        return RetractionState.UNKNOWN, ""
    updates = message.get("update-to")
    if not isinstance(updates, list) or not updates:
        return RetractionState.NONE, ""

    best_state = RetractionState.NONE
    best_detail = ""
    for entry in updates[:_MAX_EVENTS]:
        if not isinstance(entry, dict):
            continue
        raw_type = str(entry.get("type", "")).strip().lower()
        state = _ADVERSE_TYPES.get(raw_type)
        if state is None:
            continue
        if _STATE_RANK[state] > _STATE_RANK[best_state]:
            best_state = state
            updated = entry.get("updated", {})
            date_str = ""
            if isinstance(updated, dict):
                parts = updated.get("date-parts")
                if isinstance(parts, list) and parts and isinstance(parts[0], list):
                    date_str = "-".join(str(p) for p in parts[0])
            best_detail = _truncate(f"Crossref update-to: {raw_type} ({date_str})".strip())
    return best_state, best_detail


def _from_openalex(work: dict[str, Any] | None) -> tuple[RetractionState, str]:
    if not isinstance(work, dict):
        return RetractionState.UNKNOWN, ""
    if "is_retracted" not in work:
        return RetractionState.UNKNOWN, ""
    if bool(work.get("is_retracted")):
        return RetractionState.RETRACTED, "OpenAlex is_retracted=true"
    return RetractionState.NONE, ""


def parse_retraction(
    cite_key: str,
    *,
    crossref: dict[str, Any] | None = None,
    openalex: dict[str, Any] | None = None,
) -> RetractionRecord:
    """Resolve retraction status from whichever payload(s) are available.

    Pure and total: malformed input degrades to ``UNKNOWN`` fields rather
    than raising. When both sources report, the worse (higher-severity)
    state wins, since either index can independently miss an event.
    """
    cr_state, cr_detail = _from_crossref(crossref)
    oa_state, oa_detail = _from_openalex(openalex)

    if _STATE_RANK[oa_state] >= _STATE_RANK[cr_state]:
        state, detail = oa_state, oa_detail or cr_detail
    else:
        state, detail = cr_state, cr_detail

    return RetractionRecord(cite_key=cite_key, state=state, detail=detail)


def screen_bibliography(
    records: dict[str, RetractionRecord],
    *,
    acknowledged: frozenset[str] = frozenset(),
) -> tuple[Finding, ...]:
    """Turn resolved records into findings.

    ``acknowledged`` is the explicit, config-declared override for citations
    the author knowingly keeps despite an adverse event (e.g. discussing the
    retraction itself). It suppresses the *gate*, not the *record* — the
    finding is still emitted at INFO so the acknowledgement is auditable.
    """
    findings: list[Finding] = []
    for cite_key, record in sorted(records.items()):
        if record.state in (RetractionState.NONE, RetractionState.UNKNOWN):
            continue
        severity = _STATE_SEVERITY[record.state]
        if cite_key in acknowledged:
            severity = Severity.INFO
            message = f"{cite_key}: {record.state.value} (acknowledged in config)"
        else:
            message = f"{cite_key}: {record.state.value}"
        findings.append(
            Finding(
                check=CheckId.RETRACTION,
                severity=severity,
                message=message,
                locator=cite_key,
                evidence=(record.detail,) if record.detail else (),
                remediation=(
                    "Remove or replace this citation, or add it to "
                    "integrity.retraction_ack if the citation is intentional "
                    "(e.g. discussing the retraction)."
                    if severity != Severity.INFO
                    else ""
                ),
            )
        )
    return tuple(findings)


# ---------------------------------------------------------------------------
# Cache shell (impure) — reuses berb.literature.cache's on-disk format.
# ---------------------------------------------------------------------------


def cached_lookup(cite_key: str, *, cache_base: Path | None = None) -> RetractionRecord | None:
    """Return a cached retraction record, or None on miss/expiry."""
    cached = _cache.get_cached(
        cite_key, _CACHE_SOURCE, 1, cache_base=cache_base, ttl=RETRACTION_TTL_SEC
    )
    if not cached:
        return None
    try:
        return RetractionRecord.from_dict(cached[0])
    except (IndexError, TypeError, ValueError, KeyError):
        return None


def store_lookup(record: RetractionRecord, *, cache_base: Path | None = None) -> None:
    """Persist a resolved record for ``RETRACTION_TTL_SEC``."""
    _cache.put_cache(record.cite_key, _CACHE_SOURCE, 1, [record.to_dict()], cache_base=cache_base)


def _fetch_crossref_message(doi: str) -> dict[str, Any] | None:
    """GET the Crossref work record for *doi*. Returns the raw ``message``
    dict (the same shape ``berb.literature.verify.verify_by_doi`` already
    parses), or None on any failure — network, 404, or malformed JSON.
    Never raises."""
    encoded = urllib.parse.quote(doi, safe="")
    url = f"{_CROSSREF_WORKS_URL}/{encoded}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Berb/0.1 (mailto:berb@example.com)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SEC) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        logger.debug("Crossref retraction lookup failed for %s: %s", doi, exc)
        return None
    message = body.get("message") if isinstance(body, dict) else None
    return message if isinstance(message, dict) else None


def _fetch_openalex_work(doi: str, *, email: str = _POLITE_EMAIL) -> dict[str, Any] | None:
    """GET the OpenAlex work record for *doi* via its ``doi:`` shorthand
    path. Returns the raw work dict, or None on any failure. Never raises."""
    encoded = urllib.parse.quote(doi, safe="")
    params = urllib.parse.urlencode({"mailto": email})
    url = f"{_OPENALEX_WORKS_URL}/doi:{encoded}?{params}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SEC) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        logger.debug("OpenAlex retraction lookup failed for %s: %s", doi, exc)
        return None
    return body if isinstance(body, dict) else None


def resolve_retraction(
    cite_key: str,
    doi: str,
    *,
    cache_base: Path | None = None,
    email: str = _POLITE_EMAIL,
) -> RetractionRecord:
    """Cache-first retraction lookup: the only impure entry point stages
    should call. An empty/missing DOI short-circuits to UNKNOWN with no
    network call — there is nothing to look up, and UNKNOWN is exactly the
    right signal (never rendered as "clean" by ``screen_bibliography``)."""
    doi = (doi or "").strip()
    if not doi:
        return RetractionRecord(cite_key, RetractionState.UNKNOWN)

    cached = cached_lookup(cite_key, cache_base=cache_base)
    if cached is not None:
        return cached

    crossref = _fetch_crossref_message(doi)
    openalex = _fetch_openalex_work(doi, email=email)
    record = parse_retraction(cite_key, crossref=crossref, openalex=openalex)
    store_lookup(record, cache_base=cache_base)
    return record
