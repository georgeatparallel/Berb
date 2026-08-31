"""Tests for berb.integrity.anchors (tasks/ars_integration_plan.md W1)."""

from __future__ import annotations

import time

from berb.integrity.anchors import (
    MAX_ANCHOR_VALUE_CHARS,
    Anchor,
    AnchorKind,
    make_anchor,
    parse_markers,
    strip_markers,
    verify_anchors,
)
from berb.integrity.findings import CheckId, Severity

# ---------------------------------------------------------------------------
# make_anchor — smart constructor
# ---------------------------------------------------------------------------


def test_make_anchor_valid_quote() -> None:
    anchor = make_anchor("he2016deep", "quote", "Deep residual learning framework")
    assert anchor is not None
    assert anchor.cite_key == "he2016deep"
    assert anchor.kind is AnchorKind.QUOTE
    assert anchor.value == "Deep residual learning framework"
    assert len(anchor.anchor_id) == 6
    assert all(c in "0123456789abcdef" for c in anchor.anchor_id)


def test_make_anchor_rejects_bad_cite_key() -> None:
    assert make_anchor("has spaces", "quote", "x") is None
    assert make_anchor("", "quote", "x") is None
    assert make_anchor("a" * 65, "quote", "x") is None
    assert make_anchor("../../etc/passwd", "quote", "x") is None


def test_make_anchor_rejects_unknown_kind() -> None:
    assert make_anchor("he2016deep", "footnote", "x") is None
    assert make_anchor("he2016deep", "", "x") is None


def test_make_anchor_rejects_empty_value() -> None:
    assert make_anchor("he2016deep", "quote", "") is None
    assert make_anchor("he2016deep", "quote", "   ") is None


def test_make_anchor_rejects_overlength_value() -> None:
    too_long = "x" * (MAX_ANCHOR_VALUE_CHARS + 1)
    assert make_anchor("he2016deep", "quote", too_long) is None


def test_make_anchor_accepts_max_length_value() -> None:
    exactly = "x" * MAX_ANCHOR_VALUE_CHARS
    anchor = make_anchor("he2016deep", "quote", exactly)
    assert anchor is not None


def test_make_anchor_strips_surrounding_whitespace() -> None:
    anchor = make_anchor("he2016deep", "page", "  42  ")
    assert anchor is not None
    assert anchor.value == "42"


def test_make_anchor_id_is_deterministic() -> None:
    a1 = make_anchor("he2016deep", "quote", "same text")
    a2 = make_anchor("he2016deep", "quote", "same text")
    assert a1 is not None and a2 is not None
    assert a1.anchor_id == a2.anchor_id


def test_make_anchor_id_ignores_whitespace_differences() -> None:
    a1 = make_anchor("he2016deep", "quote", "same   text")
    a2 = make_anchor("he2016deep", "quote", "same text")
    assert a1 is not None and a2 is not None
    assert a1.anchor_id == a2.anchor_id


def test_make_anchor_id_differs_by_cite_key() -> None:
    a1 = make_anchor("he2016deep", "quote", "same text")
    a2 = make_anchor("other2020key", "quote", "same text")
    assert a1 is not None and a2 is not None
    assert a1.anchor_id != a2.anchor_id


def test_make_anchor_id_differs_by_kind() -> None:
    a1 = make_anchor("he2016deep", "quote", "same text")
    a2 = make_anchor("he2016deep", "page", "same text")
    assert a1 is not None and a2 is not None
    assert a1.anchor_id != a2.anchor_id


def test_llm_cannot_forge_an_anchor_id() -> None:
    # make_anchor's signature has no id parameter at all — an LLM emitting
    # key/kind/value cannot supply a mismatched id even if it tried.
    import inspect

    sig = inspect.signature(make_anchor)
    assert "anchor_id" not in sig.parameters
    assert "id" not in sig.parameters


# ---------------------------------------------------------------------------
# Anchor.to_dict / from_dict — manifest (de)serialization
# ---------------------------------------------------------------------------


def test_anchor_round_trips_through_dict() -> None:
    anchor = make_anchor("he2016deep", "quote", "some quoted text")
    assert anchor is not None
    restored = Anchor.from_dict(anchor.to_dict())
    assert restored == anchor


def test_anchor_from_dict_rejects_unknown_kind() -> None:
    assert (
        Anchor.from_dict({"cite_key": "k", "kind": "footnote", "value": "v", "anchor_id": "abc123"})
        is None
    )


def test_anchor_from_dict_rejects_bad_cite_key() -> None:
    assert (
        Anchor.from_dict(
            {"cite_key": "../evil", "kind": "quote", "value": "v", "anchor_id": "abc123"}
        )
        is None
    )


def test_anchor_from_dict_rejects_missing_fields() -> None:
    assert Anchor.from_dict({}) is None
    assert Anchor.from_dict({"cite_key": "k", "kind": "quote"}) is None


def test_anchor_from_dict_never_raises_on_garbage() -> None:
    garbage_inputs = [
        {"cite_key": 123, "kind": None, "value": [], "anchor_id": {}},
        {"cite_key": "k", "kind": "quote", "value": "v", "anchor_id": ""},
    ]
    for g in garbage_inputs:
        result = Anchor.from_dict(g)  # must not raise
        assert result is None or isinstance(result, Anchor)


# ---------------------------------------------------------------------------
# parse_markers / strip_markers
# ---------------------------------------------------------------------------


def _marker(cite_key: str = "he2016deep", kind: str = "quote", anchor_id: str = "a3f19c") -> str:
    return f"<!--berb-cite key={cite_key} kind={kind} id={anchor_id}-->"


def test_parse_markers_round_trip() -> None:
    text = f"Some claim {_marker()} continues here."
    refs = parse_markers(text)
    assert len(refs) == 1
    assert refs[0].cite_key == "he2016deep"
    assert refs[0].kind is AnchorKind.QUOTE
    assert refs[0].anchor_id == "a3f19c"


def test_parse_markers_multiple() -> None:
    text = f"{_marker('a2020x', 'page', '123abc')} and {_marker('b2021y', 'quote', 'def456')}"
    refs = parse_markers(text)
    assert len(refs) == 2
    assert refs[0].cite_key == "a2020x"
    assert refs[1].cite_key == "b2021y"


def test_parse_markers_no_markers_returns_empty() -> None:
    assert parse_markers("Plain text with no markers.") == ()


def test_parse_markers_malformed_marker_ignored() -> None:
    assert parse_markers("<!--berb-cite key=x kind=bogus id=123456-->") == ()
    assert parse_markers("<!--berb-cite key= kind=quote id=abc123-->") == ()
    assert parse_markers("<!--berb-cite key=x kind=quote id=ZZZZZZ-->") == ()  # not hex


def test_strip_markers_removes_all() -> None:
    text = f"Before {_marker()} after."
    stripped = strip_markers(text)
    assert "berb-cite" not in stripped
    assert stripped == "Before  after."


def test_strip_markers_is_idempotent() -> None:
    text = f"Before {_marker()} after."
    once = strip_markers(text)
    twice = strip_markers(once)
    assert once == twice


def test_strip_markers_no_markers_is_unchanged() -> None:
    text = "Nothing to strip here."
    assert strip_markers(text) == text


# ---------------------------------------------------------------------------
# verify_anchors — the full pipeline
# ---------------------------------------------------------------------------


def test_verify_anchors_unresolved_cite_key() -> None:
    findings = verify_anchors({}, frozenset(), _marker("unknown2024"), {})
    assert len(findings) == 1
    assert findings[0].check is CheckId.ANCHOR_UNRESOLVED
    assert findings[0].severity is Severity.WARN


def test_verify_anchors_unresolved_anchor_id() -> None:
    findings = verify_anchors({}, frozenset({"he2016deep"}), _marker("he2016deep"), {})
    assert len(findings) == 1
    assert findings[0].check is CheckId.ANCHOR_UNRESOLVED


def test_verify_anchors_quote_match_is_clean() -> None:
    anchor = make_anchor("he2016deep", "quote", "deep residual learning")
    assert anchor is not None
    marker = f"<!--berb-cite key=he2016deep kind=quote id={anchor.anchor_id}-->"
    findings = verify_anchors(
        {anchor.anchor_id: anchor},
        frozenset({"he2016deep"}),
        marker,
        {"he2016deep": "This paper introduces deep residual learning for images."},
    )
    assert findings == ()


def test_verify_anchors_quote_match_ignores_whitespace_and_case() -> None:
    anchor = make_anchor("he2016deep", "quote", "Deep   Residual Learning")
    assert anchor is not None
    marker = f"<!--berb-cite key=he2016deep kind=quote id={anchor.anchor_id}-->"
    findings = verify_anchors(
        {anchor.anchor_id: anchor},
        frozenset({"he2016deep"}),
        marker,
        {"he2016deep": "...introduces deep residual learning..."},
    )
    assert findings == ()


def test_verify_anchors_quote_mismatch_is_block() -> None:
    anchor = make_anchor("he2016deep", "quote", "this text does not appear anywhere")
    assert anchor is not None
    marker = f"<!--berb-cite key=he2016deep kind=quote id={anchor.anchor_id}-->"
    findings = verify_anchors(
        {anchor.anchor_id: anchor},
        frozenset({"he2016deep"}),
        marker,
        {"he2016deep": "completely unrelated source content"},
    )
    assert len(findings) == 1
    assert findings[0].check is CheckId.ANCHOR_QUOTE_MISMATCH
    assert findings[0].severity is Severity.BLOCK
    assert findings[0].evidence == ("this text does not appear anywhere",)


def test_verify_anchors_missing_source_text_is_info_not_pass() -> None:
    anchor = make_anchor("he2016deep", "quote", "some quote")
    assert anchor is not None
    marker = f"<!--berb-cite key=he2016deep kind=quote id={anchor.anchor_id}-->"
    findings = verify_anchors({anchor.anchor_id: anchor}, frozenset({"he2016deep"}), marker, {})
    assert len(findings) == 1
    assert findings[0].check is CheckId.ANCHOR_UNVERIFIABLE
    assert findings[0].severity is Severity.INFO


def test_verify_anchors_page_kind_is_always_unverifiable_info() -> None:
    anchor = make_anchor("he2016deep", "page", "42")
    assert anchor is not None
    marker = f"<!--berb-cite key=he2016deep kind=page id={anchor.anchor_id}-->"
    findings = verify_anchors(
        {anchor.anchor_id: anchor},
        frozenset({"he2016deep"}),
        marker,
        {"he2016deep": "full source text with page 42 in it somewhere"},
    )
    # Never claims a check that wasn't performed — INFO even though the
    # source text happens to contain "42".
    assert len(findings) == 1
    assert findings[0].check is CheckId.ANCHOR_UNVERIFIABLE
    assert findings[0].severity is Severity.INFO


def test_verify_anchors_no_markers_is_clean() -> None:
    assert verify_anchors({}, frozenset(), "Plain paper text.", {}) == ()


def test_verify_anchors_multiple_markers_independent() -> None:
    good = make_anchor("a2020x", "quote", "good quote")
    bad = make_anchor("b2021y", "quote", "bad quote text")
    assert good is not None and bad is not None
    text = (
        f"<!--berb-cite key=a2020x kind=quote id={good.anchor_id}--> and "
        f"<!--berb-cite key=b2021y kind=quote id={bad.anchor_id}-->"
    )
    findings = verify_anchors(
        {good.anchor_id: good, bad.anchor_id: bad},
        frozenset({"a2020x", "b2021y"}),
        text,
        {"a2020x": "this has the good quote in it", "b2021y": "unrelated text"},
    )
    assert len(findings) == 1
    assert findings[0].locator == "b2021y"


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


def test_cite_key_never_used_as_a_path() -> None:
    # A path-traversal cite_key is rejected outright by make_anchor, and
    # verify_anchors only ever does dict/set lookups by string key — never
    # Path construction — so this can't escape the run directory either way.
    assert make_anchor("../../../etc/passwd", "quote", "x") is None
    findings = verify_anchors(
        {}, frozenset({"../../../etc/passwd"}), _marker("../../../etc/passwd"), {}
    )
    # The marker regex itself rejects the traversal string (not in the
    # allowed cite_key character class), so it never even parses as a ref.
    assert findings == ()


def test_marker_regex_bounded_runtime_on_adversarial_input() -> None:
    adversarial = [
        "<!--berb-cite key=" + ("a" * 10000) + " kind=quote id=abc123-->",
        "<!--berb-cite " * 5000,
        ("x" * 50000) + _marker(),
    ]
    for text in adversarial:
        start = time.monotonic()
        parse_markers(text)
        strip_markers(text)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"took {elapsed:.2f}s on adversarial input"


def test_verify_anchors_large_source_text_bounded_runtime() -> None:
    anchor = make_anchor("he2016deep", "quote", "needle in a haystack")
    assert anchor is not None
    marker = f"<!--berb-cite key=he2016deep kind=quote id={anchor.anchor_id}-->"
    huge_source = ("filler text " * 200000) + "needle in a haystack"
    start = time.monotonic()
    findings = verify_anchors(
        {anchor.anchor_id: anchor},
        frozenset({"he2016deep"}),
        marker,
        {"he2016deep": huge_source},
    )
    elapsed = time.monotonic() - start
    assert elapsed < 2.0
    assert findings == ()
