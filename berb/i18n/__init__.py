"""Internationalization module for Berb.

38-language academic writing support.
"""

from berb.i18n.academic_languages import (
    AcademicLanguageProfile,
    MultilingualWritingAssistant,
    WritingDirection,
    LANGUAGE_PROFILES,
    get_language_profile,
    list_supported_languages,
    detect_language_from_text,
)

__all__ = [
    "AcademicLanguageProfile",
    "MultilingualWritingAssistant",
    "WritingDirection",
    "LANGUAGE_PROFILES",
    "get_language_profile",
    "list_supported_languages",
    "detect_language_from_text",
]
