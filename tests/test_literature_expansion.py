"""Unit tests for P2-04's k=3 literature expansion helpers and the venue
boost / year_max additions to berb.literature.search.

ScholarPeer's literature expansion agent runs k=3 gap-driven search
rounds; its Fig. 5 shows quality declining past k=3 as tangential papers
dilute the context window — the cap here is a quality control, not a cost
one.
"""

from __future__ import annotations

from berb.literature.search import _venue_boost_factor
from berb.pipeline.stage_impls._literature import (
    _MAX_EXPANSION_ROUNDS,
    _MIN_NEW_CANDIDATES_TO_CONTINUE,
    _seed_expansion_queries,
)


class TestSeedExpansionQueries:
    def test_seeds_from_highest_cited_new_candidates(self) -> None:
        candidates = [
            {"title": "Low Cited Paper", "citation_count": 2},
            {"title": "High Cited Paper", "citation_count": 500},
            {"title": "Mid Cited Paper", "citation_count": 50},
        ]
        seen: set[str] = set()
        queries = _seed_expansion_queries(candidates, seen, max_new=2)
        assert queries == ["High Cited Paper", "Mid Cited Paper"]

    def test_skips_titles_already_used_as_a_query(self) -> None:
        candidates = [{"title": "Already Searched", "citation_count": 100}]
        seen = {"already searched"}
        assert _seed_expansion_queries(candidates, seen) == []

    def test_respects_max_new_cap(self) -> None:
        candidates = [
            {"title": f"Paper {i}", "citation_count": 100 - i} for i in range(10)
        ]
        queries = _seed_expansion_queries(candidates, set(), max_new=3)
        assert len(queries) == 3

    def test_empty_candidates_returns_empty(self) -> None:
        assert _seed_expansion_queries([], set()) == []

    def test_skips_candidates_without_title(self) -> None:
        candidates = [{"citation_count": 100}, {"title": "", "citation_count": 50}]
        assert _seed_expansion_queries(candidates, set()) == []

    def test_updates_seen_queries_in_place(self) -> None:
        candidates = [{"title": "New Paper", "citation_count": 10}]
        seen: set[str] = set()
        _seed_expansion_queries(candidates, seen)
        assert "new paper" in seen


def test_max_expansion_rounds_is_three() -> None:
    # ScholarPeer's own hyperparameter sensitivity result: k=3 is optimal,
    # quality declines past it.
    assert _MAX_EXPANSION_ROUNDS == 3


def test_min_new_candidates_threshold_is_positive() -> None:
    assert _MIN_NEW_CANDIDATES_TO_CONTINUE > 0


class TestVenueBoostFactor:
    def test_boosts_top_tier_venue(self) -> None:
        assert _venue_boost_factor("NeurIPS 2024") > 1.0

    def test_no_boost_for_unlisted_venue(self) -> None:
        assert _venue_boost_factor("Journal of Obscure Studies") == 1.0

    def test_no_boost_for_empty_venue(self) -> None:
        assert _venue_boost_factor("") == 1.0

    def test_case_insensitive(self) -> None:
        assert _venue_boost_factor("neurips") == _venue_boost_factor("NEURIPS")

    def test_boost_is_moderate_not_a_hard_override(self) -> None:
        # A near-zero-citation top-tier paper must never outrank a
        # heavily-cited paper from an unlisted venue.
        boosted = 1 * _venue_boost_factor("ICML")
        unboosted = 1000 * _venue_boost_factor("Some Regional Workshop")
        assert boosted < unboosted
