"""Tests for berb.writing.disclosure (tasks/ars_integration_plan.md W8.2)."""

from __future__ import annotations

from berb.writing.disclosure import DisclosureFacts, generate_disclosure_statement


def test_basic_statement_includes_provider_and_model() -> None:
    facts = DisclosureFacts(provider="anthropic", model="claude-opus-5")
    statement = generate_disclosure_statement(facts)
    assert "anthropic" in statement
    assert "claude-opus-5" in statement


def test_statement_has_disclosure_heading() -> None:
    facts = DisclosureFacts(provider="openai", model="gpt-5.5")
    statement = generate_disclosure_statement(facts)
    assert statement.startswith("## AI Usage Disclosure")


def test_cross_model_mention_only_when_used() -> None:
    off = DisclosureFacts(provider="openai", model="gpt-5.5", cross_model_verification_used=False)
    on = DisclosureFacts(provider="openai", model="gpt-5.5", cross_model_verification_used=True)
    assert "independent" not in generate_disclosure_statement(off).lower()
    assert "independent" in generate_disclosure_statement(on).lower()


def test_statement_names_itself_as_a_starting_point_not_venue_policy() -> None:
    facts = DisclosureFacts(provider="openai", model="gpt-5.5")
    statement = generate_disclosure_statement(facts)
    assert "starting point" in statement
    assert "venue" in statement.lower()


def test_statement_is_deterministic() -> None:
    facts = DisclosureFacts(provider="openai", model="gpt-5.5")
    assert generate_disclosure_statement(facts) == generate_disclosure_statement(facts)


def test_statement_ends_with_single_trailing_newline() -> None:
    facts = DisclosureFacts(provider="openai", model="gpt-5.5")
    statement = generate_disclosure_statement(facts)
    assert statement.endswith("\n")
    assert not statement.endswith("\n\n")
