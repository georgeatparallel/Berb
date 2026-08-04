"""Tests for berb.i18n number formatting and profile validation.

The package was unimportable before these existed: 14 language profiles declared
``number_format="1 000,50"`` while the field's Literal only allowed the dot and
comma variants, so building the profile database raised ValidationError at import.
"""

from __future__ import annotations

import typing

import pytest

from berb.i18n.academic_languages import (
    LANGUAGE_PROFILES,
    NUMBER_SEPARATORS,
    MultilingualWritingAssistant,
    NumberFormat,
)


def test_every_declared_format_has_separators() -> None:
    """The Literal and the separator map must not drift apart."""
    assert set(typing.get_args(NumberFormat)) == set(NUMBER_SEPARATORS)


def test_every_profile_uses_a_supported_format() -> None:
    """Building the profile database must not depend on import-time luck."""
    unsupported = {
        code: profile.number_format
        for code, profile in LANGUAGE_PROFILES.items()
        if profile.number_format not in NUMBER_SEPARATORS
    }

    assert not unsupported, f"profiles declare unmapped number formats: {unsupported}"


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "1,234.50"),  # US/UK
        ("de", "1.234,50"),  # European dot
        ("fr", "1 234,50"),  # space-separated — silently fell back to US before
    ],
)
def test_format_number_honours_language_convention(language: str, expected: str) -> None:
    assistant = MultilingualWritingAssistant(language)

    assert assistant.format_number(1234.5) == expected


def test_format_number_separators_do_not_clobber_each_other() -> None:
    """Naive sequential .replace() would turn 1,234.50 into 1.234.50 for German."""
    assistant = MultilingualWritingAssistant("de")

    assert assistant.format_number(1234567.89) == "1.234.567,89"
