"""Tests for berb.literature.retraction (tasks/ars_integration_plan.md W2).

All fixtures below are synthetic, hand-built dicts shaped like real
OpenAlex/Crossref API responses — no network, no ARS code or data.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from berb.integrity.findings import CheckId, Severity
from berb.literature.retraction import (
    RETRACTION_TTL_SEC,
    RetractionRecord,
    RetractionState,
    cached_lookup,
    parse_retraction,
    resolve_retraction,
    screen_bibliography,
    store_lookup,
)


def _mock_response(payload: dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# parse_retraction
# ---------------------------------------------------------------------------


def test_no_payloads_is_unknown() -> None:
    record = parse_retraction("he2016deep")
    assert record.state is RetractionState.UNKNOWN
    assert record.cite_key == "he2016deep"


def test_malformed_payloads_are_unknown_not_clean() -> None:
    record = parse_retraction("k1", crossref="not-a-dict", openalex=123)  # type: ignore[arg-type]
    assert record.state is RetractionState.UNKNOWN


def test_openalex_missing_field_is_unknown() -> None:
    record = parse_retraction("k1", openalex={"title": "Some Paper"})
    assert record.state is RetractionState.UNKNOWN


def test_openalex_present_and_false_is_none() -> None:
    record = parse_retraction("k1", openalex={"is_retracted": False})
    assert record.state is RetractionState.NONE


def test_openalex_retracted_true() -> None:
    record = parse_retraction("k1", openalex={"is_retracted": True})
    assert record.state is RetractionState.RETRACTED
    assert "OpenAlex" in record.detail


def test_crossref_no_update_to_is_none() -> None:
    record = parse_retraction("k1", crossref={"title": ["Some Paper"]})
    assert record.state is RetractionState.NONE


def test_crossref_retraction_event() -> None:
    payload = {
        "update-to": [
            {"type": "retraction", "updated": {"date-parts": [[2026, 3, 1]]}},
        ]
    }
    record = parse_retraction("k1", crossref=payload)
    assert record.state is RetractionState.RETRACTED
    assert "retraction" in record.detail
    assert "2026-3-1" in record.detail


def test_crossref_expression_of_concern() -> None:
    payload = {"update-to": [{"type": "Expression of Concern", "updated": {}}]}
    record = parse_retraction("k1", crossref=payload)
    assert record.state is RetractionState.CONCERN


def test_crossref_unrelated_update_type_is_none() -> None:
    payload = {"update-to": [{"type": "correction", "updated": {}}]}
    record = parse_retraction("k1", crossref=payload)
    assert record.state is RetractionState.NONE


def test_crossref_multiple_events_worst_wins() -> None:
    payload = {
        "update-to": [
            {"type": "correction", "updated": {}},
            {"type": "expression of concern", "updated": {}},
            {"type": "retraction", "updated": {}},
        ]
    }
    record = parse_retraction("k1", crossref=payload)
    assert record.state is RetractionState.RETRACTED


def test_crossref_update_to_not_a_list_is_none() -> None:
    record = parse_retraction("k1", crossref={"update-to": "garbage"})
    assert record.state is RetractionState.NONE


def test_crossref_event_entries_not_dicts_are_skipped() -> None:
    record = parse_retraction("k1", crossref={"update-to": ["garbage", 42, None]})
    assert record.state is RetractionState.NONE


def test_both_sources_worse_state_wins_openalex_retracted() -> None:
    record = parse_retraction(
        "k1",
        crossref={"title": ["x"]},  # NONE
        openalex={"is_retracted": True},  # RETRACTED
    )
    assert record.state is RetractionState.RETRACTED


def test_both_sources_worse_state_wins_crossref_retracted() -> None:
    record = parse_retraction(
        "k1",
        crossref={"update-to": [{"type": "retraction", "updated": {}}]},
        openalex={"is_retracted": False},
    )
    assert record.state is RetractionState.RETRACTED


def test_one_source_unknown_other_none_reports_none() -> None:
    # OpenAlex has no coverage (missing field -> UNKNOWN) but Crossref says
    # clean. UNKNOWN must not silently override a real NONE reading.
    record = parse_retraction("k1", crossref={"title": ["x"]}, openalex=None)
    assert record.state is RetractionState.NONE


def test_excess_events_are_capped_and_do_not_crash() -> None:
    payload = {"update-to": [{"type": "correction", "updated": {}}] * 500}
    record = parse_retraction("k1", crossref=payload)
    assert record.state is RetractionState.NONE  # no adverse event among them


# ---------------------------------------------------------------------------
# screen_bibliography
# ---------------------------------------------------------------------------


def test_screen_bibliography_unknown_never_gates_as_clean() -> None:
    records = {"k1": RetractionRecord("k1", RetractionState.UNKNOWN)}
    findings = screen_bibliography(records)
    assert findings == ()  # UNKNOWN produces no finding at all — not "clean"


def test_screen_bibliography_none_produces_no_finding() -> None:
    records = {"k1": RetractionRecord("k1", RetractionState.NONE)}
    assert screen_bibliography(records) == ()


def test_screen_bibliography_retracted_is_block() -> None:
    records = {"k1": RetractionRecord("k1", RetractionState.RETRACTED, "detail")}
    findings = screen_bibliography(records)
    assert len(findings) == 1
    f = findings[0]
    assert f.check is CheckId.RETRACTION
    assert f.severity is Severity.BLOCK
    assert f.locator == "k1"
    assert f.remediation != ""


def test_screen_bibliography_concern_is_warn() -> None:
    records = {"k1": RetractionRecord("k1", RetractionState.CONCERN)}
    findings = screen_bibliography(records)
    assert findings[0].severity is Severity.WARN


def test_screen_bibliography_acknowledged_downgrades_to_info_but_still_reports() -> None:
    records = {"k1": RetractionRecord("k1", RetractionState.RETRACTED)}
    findings = screen_bibliography(records, acknowledged=frozenset({"k1"}))
    assert len(findings) == 1
    assert findings[0].severity is Severity.INFO
    assert "acknowledged" in findings[0].message


def test_screen_bibliography_sorted_by_cite_key() -> None:
    records = {
        "zeta": RetractionRecord("zeta", RetractionState.RETRACTED),
        "alpha": RetractionRecord("alpha", RetractionState.CONCERN),
    }
    findings = screen_bibliography(records)
    assert [f.locator for f in findings] == ["alpha", "zeta"]


# ---------------------------------------------------------------------------
# Cache round-trip (offline, tmp_path — no network)
# ---------------------------------------------------------------------------


def test_cache_round_trip(tmp_path) -> None:
    record = RetractionRecord("k1", RetractionState.RETRACTED, "Crossref update-to: retraction")
    assert cached_lookup("k1", cache_base=tmp_path) is None
    store_lookup(record, cache_base=tmp_path)
    fetched = cached_lookup("k1", cache_base=tmp_path)
    assert fetched == record


def test_cache_miss_for_different_key(tmp_path) -> None:
    store_lookup(RetractionRecord("k1", RetractionState.NONE), cache_base=tmp_path)
    assert cached_lookup("k2", cache_base=tmp_path) is None


def test_cache_expiry(tmp_path, monkeypatch) -> None:
    import time as _time

    from berb.literature import cache as cache_mod

    record = RetractionRecord("k1", RetractionState.RETRACTED)
    store_lookup(record, cache_base=tmp_path)

    # Jump time forward past the TTL.
    real_time = _time.time
    monkeypatch.setattr(cache_mod.time, "time", lambda: real_time() + RETRACTION_TTL_SEC + 1)
    assert cached_lookup("k1", cache_base=tmp_path) is None


def test_cache_survives_corrupt_record(tmp_path) -> None:
    from berb.literature import cache as cache_mod

    cache_mod.put_cache("k1", "retraction_status", 1, [{"cite_key": "k1"}], cache_base=tmp_path)
    result = cached_lookup("k1", cache_base=tmp_path)
    # Missing "state" key falls back to UNKNOWN via RetractionRecord.from_dict,
    # not a crash.
    assert result is not None
    assert result.state is RetractionState.UNKNOWN


# ---------------------------------------------------------------------------
# resolve_retraction (network shell, mocked — no real network)
# ---------------------------------------------------------------------------


def test_resolve_retraction_empty_doi_short_circuits_no_network(tmp_path) -> None:
    with patch("urllib.request.urlopen") as mock_urlopen:
        record = resolve_retraction("k1", "", cache_base=tmp_path)
    mock_urlopen.assert_not_called()
    assert record.state is RetractionState.UNKNOWN


def test_resolve_retraction_uses_cache_before_network(tmp_path) -> None:
    store_lookup(RetractionRecord("k1", RetractionState.RETRACTED), cache_base=tmp_path)
    with patch("urllib.request.urlopen") as mock_urlopen:
        record = resolve_retraction("k1", "10.1234/x", cache_base=tmp_path)
    mock_urlopen.assert_not_called()
    assert record.state is RetractionState.RETRACTED


def test_resolve_retraction_fetches_and_caches(tmp_path) -> None:
    crossref_resp = _mock_response(
        {"message": {"update-to": [{"type": "retraction", "updated": {}}]}}
    )
    openalex_resp = _mock_response({"is_retracted": False})

    def mock_urlopen(req: Any, **kwargs: Any) -> MagicMock:
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "crossref.org" in url:
            return crossref_resp
        if "openalex.org" in url:
            return openalex_resp
        raise OSError("unexpected URL")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        record = resolve_retraction("k1", "10.1234/x", cache_base=tmp_path)
    assert record.state is RetractionState.RETRACTED

    # Second call must hit the cache, not the network.
    with patch("urllib.request.urlopen") as mock_urlopen2:
        cached_record = resolve_retraction("k1", "10.1234/x", cache_base=tmp_path)
    mock_urlopen2.assert_not_called()
    assert cached_record == record


def test_resolve_retraction_network_failure_is_unknown_not_crash(tmp_path) -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        record = resolve_retraction("k1", "10.1234/x", cache_base=tmp_path)
    assert record.state is RetractionState.UNKNOWN


def test_resolve_retraction_doi_is_percent_encoded_not_injected(tmp_path) -> None:
    import urllib.parse

    captured_urls: list[str] = []

    def mock_urlopen(req: Any, **kwargs: Any) -> MagicMock:
        captured_urls.append(req.full_url if hasattr(req, "full_url") else str(req))
        raise OSError("stop after capturing URL")

    hostile_doi = "10.1234/x?evil=1&host=attacker.example"
    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        resolve_retraction("k1", hostile_doi, cache_base=tmp_path)

    assert captured_urls, "expected at least one request attempt"
    for url in captured_urls:
        # The DOI's own "/", "?", "&" must be percent-encoded, so the
        # hostile "host=attacker.example" fragment can never become the
        # actual network-request host — netloc must stay the fixed API host.
        netloc = urllib.parse.urlparse(url).netloc
        assert netloc in {"api.crossref.org", "api.openalex.org"}
