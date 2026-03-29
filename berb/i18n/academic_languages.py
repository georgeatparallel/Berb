"""38-language academic writing support.

This module expands Berb's multilingual support from 13 to 38 languages,
with language-specific academic writing conventions, formatting, and style.

Supported Languages:
- European: English, Spanish, French, German, Italian, Portuguese, Dutch,
  Polish, Russian, Ukrainian, Swedish, Norwegian, Danish, Finnish, Greek,
  Czech, Slovak, Hungarian, Romanian, Bulgarian, Serbian, Croatian
- Asian: Chinese, Japanese, Korean, Vietnamese, Thai, Indonesian, Malay,
  Hindi, Arabic, Persian, Hebrew, Turkish
- African: Afrikaans, Xhosa, Zulu
- Other: Icelandic, Albanian, Catalan, Basque

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WritingDirection(str, Enum):
    """Text writing direction.

    Attributes:
        LTR: Left-to-right
        RTL: Right-to-left
    """

    LTR = "ltr"
    RTL = "rtl"


class AcademicLanguageProfile(BaseModel):
    """Profile for an academic language.

    Attributes:
        code: ISO 639-1 language code
        name: Language name in English
        native_name: Language name in native script
        writing_direction: LTR or RTL
        passive_voice_convention: Preferred passive voice usage
        first_person_convention: First person usage convention
        typical_sentence_length: Typical sentence length range
        citation_placement: Where citations appear
        date_format: Date format string
        number_format: Number format (decimal separator)
        bibliography_sort_locale: Locale for bibliography sorting
        academic_conventions: List of academic conventions
    """

    code: str
    name: str
    native_name: str
    writing_direction: WritingDirection = WritingDirection.LTR
    passive_voice_convention: Literal[
        "preferred", "neutral", "discouraged"
    ] = "neutral"
    first_person_convention: Literal["we", "I", "impersonal", "varies"] = "varies"
    typical_sentence_length: tuple[int, int] = (15, 30)
    citation_placement: Literal["inline", "footnote", "endnote"] = "inline"
    date_format: str = "YYYY-MM-DD"
    number_format: Literal["1.000,50", "1,000.50"] = "1,000.50"
    bibliography_sort_locale: str = "en"
    academic_conventions: list[str] = Field(default_factory=list)


# Language profiles database
LANGUAGE_PROFILES: dict[str, AcademicLanguageProfile] = {
    # Germanic languages
    "en": AcademicLanguageProfile(
        code="en",
        name="English",
        native_name="English",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="YYYY-MM-DD",
        number_format="1,000.50",
        bibliography_sort_locale="en",
        academic_conventions=[
            "Abstract required",
            "Keywords: 4-6",
            "JEL/ACS codes optional",
        ],
    ),
    "de": AcademicLanguageProfile(
        code="de",
        name="German",
        native_name="Deutsch",
        passive_voice_convention="preferred",
        first_person_convention="impersonal",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="de",
        academic_conventions=[
            "Zusammenfassung required",
            "Schlüsselwörter: 4-6",
        ],
    ),
    "nl": AcademicLanguageProfile(
        code="nl",
        name="Dutch",
        native_name="Nederlands",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD-MM-YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="nl",
    ),
    "sv": AcademicLanguageProfile(
        code="sv",
        name="Swedish",
        native_name="Svenska",
        passive_voice_convention="discouraged",
        first_person_convention="we",
        citation_placement="inline",
        date_format="YYYY-MM-DD",
        number_format="1 000,50",
        bibliography_sort_locale="sv",
    ),
    "no": AcademicLanguageProfile(
        code="no",
        name="Norwegian",
        native_name="Norsk",
        passive_voice_convention="discouraged",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1 000,50",
        bibliography_sort_locale="no",
    ),
    "da": AcademicLanguageProfile(
        code="da",
        name="Danish",
        native_name="Dansk",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="da",
    ),
    "fi": AcademicLanguageProfile(
        code="fi",
        name="Finnish",
        native_name="Suomi",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1 000,50",
        bibliography_sort_locale="fi",
    ),
    "is": AcademicLanguageProfile(
        code="is",
        name="Icelandic",
        native_name="Íslenska",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="is",
    ),
    # Romance languages
    "es": AcademicLanguageProfile(
        code="es",
        name="Spanish",
        native_name="Español",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD/MM/YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="es",
        academic_conventions=[
            "Resumen required",
            "Palabras clave: 4-6",
        ],
    ),
    "fr": AcademicLanguageProfile(
        code="fr",
        name="French",
        native_name="Français",
        passive_voice_convention="preferred",
        first_person_convention="impersonal",
        citation_placement="inline",
        date_format="DD/MM/YYYY",
        number_format="1 000,50",
        bibliography_sort_locale="fr",
        academic_conventions=[
            "Résumé required",
            "Mots-clés: 4-6",
        ],
    ),
    "it": AcademicLanguageProfile(
        code="it",
        name="Italian",
        native_name="Italiano",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD/MM/YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="it",
    ),
    "pt": AcademicLanguageProfile(
        code="pt",
        name="Portuguese",
        native_name="Português",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD/MM/YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="pt",
    ),
    "ro": AcademicLanguageProfile(
        code="ro",
        name="Romanian",
        native_name="Română",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="ro",
    ),
    "ca": AcademicLanguageProfile(
        code="ca",
        name="Catalan",
        native_name="Català",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD/MM/YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="ca",
    ),
    # Slavic languages
    "pl": AcademicLanguageProfile(
        code="pl",
        name="Polish",
        native_name="Polski",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1 000,50",
        bibliography_sort_locale="pl",
    ),
    "ru": AcademicLanguageProfile(
        code="ru",
        name="Russian",
        native_name="Русский",
        passive_voice_convention="preferred",
        first_person_convention="impersonal",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1 000,50",
        bibliography_sort_locale="ru",
    ),
    "uk": AcademicLanguageProfile(
        code="uk",
        name="Ukrainian",
        native_name="Українська",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1 000,50",
        bibliography_sort_locale="uk",
    ),
    "cs": AcademicLanguageProfile(
        code="cs",
        name="Czech",
        native_name="Čeština",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1 000,50",
        bibliography_sort_locale="cs",
    ),
    "sk": AcademicLanguageProfile(
        code="sk",
        name="Slovak",
        native_name="Slovenčina",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1 000,50",
        bibliography_sort_locale="sk",
    ),
    "sr": AcademicLanguageProfile(
        code="sr",
        name="Serbian",
        native_name="Српски",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="sr",
    ),
    "hr": AcademicLanguageProfile(
        code="hr",
        name="Croatian",
        native_name="Hrvatski",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="hr",
    ),
    "bg": AcademicLanguageProfile(
        code="bg",
        name="Bulgarian",
        native_name="Български",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1 000,50",
        bibliography_sort_locale="bg",
    ),
    # Asian languages
    "zh": AcademicLanguageProfile(
        code="zh",
        name="Chinese",
        native_name="中文",
        writing_direction=WritingDirection.LTR,
        passive_voice_convention="discouraged",
        first_person_convention="impersonal",
        citation_placement="inline",
        date_format="YYYY年MM月DD日",
        number_format="1,000.50",
        bibliography_sort_locale="zh",
        academic_conventions=[
            "摘要 required",
            "关键词：4-6",
            "中图分类号 optional",
        ],
    ),
    "ja": AcademicLanguageProfile(
        code="ja",
        name="Japanese",
        native_name="日本語",
        writing_direction=WritingDirection.LTR,
        passive_voice_convention="preferred",
        first_person_convention="impersonal",
        citation_placement="inline",
        date_format="YYYY年MM月DD日",
        number_format="1,000.50",
        bibliography_sort_locale="ja",
    ),
    "ko": AcademicLanguageProfile(
        code="ko",
        name="Korean",
        native_name="한국어",
        writing_direction=WritingDirection.LTR,
        passive_voice_convention="neutral",
        first_person_convention="impersonal",
        citation_placement="inline",
        date_format="YYYY.MM.DD",
        number_format="1,000.50",
        bibliography_sort_locale="ko",
    ),
    "vi": AcademicLanguageProfile(
        code="vi",
        name="Vietnamese",
        native_name="Tiếng Việt",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD/MM/YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="vi",
    ),
    "th": AcademicLanguageProfile(
        code="th",
        name="Thai",
        native_name="ไทย",
        writing_direction=WritingDirection.LTR,
        passive_voice_convention="neutral",
        first_person_convention="impersonal",
        citation_placement="inline",
        date_format="DD/MM/YYYY",
        number_format="1,000.50",
        bibliography_sort_locale="th",
    ),
    "id": AcademicLanguageProfile(
        code="id",
        name="Indonesian",
        native_name="Bahasa Indonesia",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD/MM/YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="id",
    ),
    "ms": AcademicLanguageProfile(
        code="ms",
        name="Malay",
        native_name="Bahasa Melayu",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD/MM/YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="ms",
    ),
    "hi": AcademicLanguageProfile(
        code="hi",
        name="Hindi",
        native_name="हिन्दी",
        writing_direction=WritingDirection.LTR,
        passive_voice_convention="neutral",
        first_person_convention="impersonal",
        citation_placement="inline",
        date_format="DD/MM/YYYY",
        number_format="1,000.50",
        bibliography_sort_locale="hi",
    ),
    # Middle Eastern languages
    "ar": AcademicLanguageProfile(
        code="ar",
        name="Arabic",
        native_name="العربية",
        writing_direction=WritingDirection.RTL,
        passive_voice_convention="preferred",
        first_person_convention="impersonal",
        citation_placement="inline",
        date_format="DD/MM/YYYY",
        number_format="1,000.50",
        bibliography_sort_locale="ar",
        academic_conventions=[
            "ملخص required",
            "كلمات مفتاحية: 4-6",
        ],
    ),
    "fa": AcademicLanguageProfile(
        code="fa",
        name="Persian",
        native_name="فارسی",
        writing_direction=WritingDirection.RTL,
        passive_voice_convention="neutral",
        first_person_convention="impersonal",
        citation_placement="inline",
        date_format="YYYY/MM/DD",
        number_format="1,000.50",
        bibliography_sort_locale="fa",
    ),
    "he": AcademicLanguageProfile(
        code="he",
        name="Hebrew",
        native_name="עברית",
        writing_direction=WritingDirection.RTL,
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD/MM/YYYY",
        number_format="1,000.50",
        bibliography_sort_locale="he",
    ),
    "tr": AcademicLanguageProfile(
        code="tr",
        name="Turkish",
        native_name="Türkçe",
        passive_voice_convention="discouraged",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="tr",
    ),
    # Other European
    "el": AcademicLanguageProfile(
        code="el",
        name="Greek",
        native_name="Ελληνικά",
        passive_voice_convention="preferred",
        first_person_convention="impersonal",
        citation_placement="inline",
        date_format="DD/MM/YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="el",
        academic_conventions=[
            "Περίληψη required",
            "Λέξεις-κλειδιά: 4-6",
        ],
    ),
    "hu": AcademicLanguageProfile(
        code="hu",
        name="Hungarian",
        native_name="Magyar",
        passive_voice_convention="neutral",
        first_person_convention="impersonal",
        citation_placement="inline",
        date_format="YYYY.MM.DD",
        number_format="1 000,50",
        bibliography_sort_locale="hu",
    ),
    "sq": AcademicLanguageProfile(
        code="sq",
        name="Albanian",
        native_name="Shqip",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="DD.MM.YYYY",
        number_format="1.000,50",
        bibliography_sort_locale="sq",
    ),
    "eu": AcademicLanguageProfile(
        code="eu",
        name="Basque",
        native_name="Euskara",
        passive_voice_convention="neutral",
        first_person_convention="impersonal",
        citation_placement="inline",
        date_format="YYYY/MM/DD",
        number_format="1.000,50",
        bibliography_sort_locale="eu",
    ),
    # African languages
    "af": AcademicLanguageProfile(
        code="af",
        name="Afrikaans",
        native_name="Afrikaans",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="YYYY/MM/DD",
        number_format="1 000,50",
        bibliography_sort_locale="af",
    ),
    "xh": AcademicLanguageProfile(
        code="xh",
        name="Xhosa",
        native_name="isiXhosa",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="YYYY/MM/DD",
        number_format="1 000,50",
        bibliography_sort_locale="xh",
    ),
    "zu": AcademicLanguageProfile(
        code="zu",
        name="Zulu",
        native_name="isiZulu",
        passive_voice_convention="neutral",
        first_person_convention="we",
        citation_placement="inline",
        date_format="YYYY/MM/DD",
        number_format="1 000,50",
        bibliography_sort_locale="zu",
    ),
}


class MultilingualWritingAssistant:
    """Assistant for multilingual academic writing.

    Provides language-specific writing assistance including:
    - Academic convention guidance
    - Citation formatting
    - Number/date formatting
    - Section structure recommendations

    Usage::

        assistant = MultilingualWritingAssistant("zh")
        conventions = assistant.get_academic_conventions()
        formatted_date = assistant.format_date("2024-03-29")
    """

    def __init__(self, language_code: str):
        """Initialize assistant.

        Args:
            language_code: ISO 639-1 language code
        """
        self.language_code = language_code
        self.profile = LANGUAGE_PROFILES.get(language_code)

        if not self.profile:
            logger.warning(f"Language {language_code} not found, using English")
            self.profile = LANGUAGE_PROFILES["en"]

    def get_profile(self) -> AcademicLanguageProfile:
        """Get language profile.

        Returns:
            AcademicLanguageProfile
        """
        return self.profile

    def get_academic_conventions(self) -> list[str]:
        """Get academic conventions for this language.

        Returns:
            List of convention strings
        """
        return self.profile.academic_conventions

    def format_date(self, date_str: str) -> str:
        """Format date according to language convention.

        Args:
            date_str: Date string (YYYY-MM-DD)

        Returns:
            Formatted date string
        """
        # Simplified implementation
        # In production, would use babel or similar
        return date_str  # Return ISO format as default

    def format_number(self, number: float) -> str:
        """Format number according to language convention.

        Args:
            number: Number to format

        Returns:
            Formatted number string
        """
        if self.profile.number_format == "1.000,50":
            # European format
            return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            # US/UK format
            return f"{number:,.2f}"

    def get_section_names(self) -> dict[str, str]:
        """Get section names in this language.

        Returns:
            Dictionary of English -> native section names
        """
        section_translations = {
            "abstract": {
                "en": "Abstract",
                "de": "Zusammenfassung",
                "es": "Resumen",
                "fr": "Résumé",
                "zh": "摘要",
                "ja": "要旨",
                "el": "Περίληψη",
                "ar": "ملخص",
            },
            "introduction": {
                "en": "Introduction",
                "de": "Einleitung",
                "es": "Introducción",
                "fr": "Introduction",
                "zh": "引言",
                "ja": "序論",
                "el": "Εισαγωγή",
                "ar": "مقدمة",
            },
            "methods": {
                "en": "Methods",
                "de": "Methoden",
                "es": "Métodos",
                "fr": "Méthodes",
                "zh": "方法",
                "ja": "手法",
                "el": "Μέθοδοι",
                "ar": "الطرق",
            },
            "results": {
                "en": "Results",
                "de": "Ergebnisse",
                "es": "Resultados",
                "fr": "Résultats",
                "zh": "结果",
                "ja": "結果",
                "el": "Αποτελέσματα",
                "ar": "النتائج",
            },
            "discussion": {
                "en": "Discussion",
                "de": "Diskussion",
                "es": "Discusión",
                "fr": "Discussion",
                "zh": "讨论",
                "ja": "考察",
                "el": "Συζήτηση",
                "ar": "المناقشة",
            },
            "conclusion": {
                "en": "Conclusion",
                "de": "Fazit",
                "es": "Conclusión",
                "fr": "Conclusion",
                "zh": "结论",
                "ja": "結論",
                "el": "Συμπέρασμα",
                "ar": "الخاتمة",
            },
        }

        result = {}
        for en_name, translations in section_translations.items():
            result[en_name] = translations.get(
                self.language_code, translations["en"]
            )

        return result

    def get_keywords_label(self) -> str:
        """Get 'Keywords' label in this language.

        Returns:
            Translated label
        """
        labels = {
            "en": "Keywords",
            "de": "Schlüsselwörter",
            "es": "Palabras clave",
            "fr": "Mots-clés",
            "zh": "关键词",
            "ja": "キーワード",
            "el": "Λέξεις-κλειδιά",
            "ar": "كلمات مفتاحية",
        }
        return labels.get(self.language_code, "Keywords")


def get_language_profile(code: str) -> AcademicLanguageProfile:
    """Get language profile by code.

    Args:
        code: ISO 639-1 language code

    Returns:
        AcademicLanguageProfile
    """
    return LANGUAGE_PROFILES.get(code, LANGUAGE_PROFILES["en"])


def list_supported_languages() -> list[dict[str, str]]:
    """List all supported languages.

    Returns:
        List of language dictionaries
    """
    return [
        {"code": p.code, "name": p.name, "native_name": p.native_name}
        for p in LANGUAGE_PROFILES.values()
    ]


def detect_language_from_text(text: str) -> str | None:
    """Detect language from text content.

    Args:
        text: Text to analyze

    Returns:
        Detected language code or None
    """
    # Script-based detection
    import re

    # RTL scripts
    if re.search(r"[\u0600-\u06FF]", text):  # Arabic
        return "ar"
    if re.search(r"[\u0590-\u05FF]", text):  # Hebrew
        return "he"
    if re.search(r"[\u0780-\u07BF]", text):  # Persian/Arabic extended
        return "fa"

    # CJK scripts
    if re.search(r"[\u4E00-\u9FFF]", text):  # Chinese
        return "zh"
    if re.search(r"[\u3040-\u309F\u30A0-\u30FF]", text):  # Japanese
        return "ja"
    if re.search(r"[\uAC00-\uD7AF]", text):  # Korean
        return "ko"

    # Cyrillic
    if re.search(r"[\u0400-\u04FF]", text):
        # Could be Russian, Ukrainian, Bulgarian, etc.
        # Simple heuristic based on common words
        if "и" in text and "не" in text:
            return "ru"
        if "і" in text:
            return "uk"
        return "ru"  # Default to Russian

    # Greek
    if re.search(r"[\u0370-\u03FF]", text):
        return "el"

    # Thai
    if re.search(r"[\u0E00-\u0E7F]", text):
        return "th"

    # Default to English for Latin script
    return "en"
