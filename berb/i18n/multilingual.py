"""Multi-language support for Berb pipeline.

This module provides language detection, translation, and multilingual
prompt generation for the Berb research pipeline.

Features:
- Language detection from topic/research idea
- Dynamic prompt translation
- Support for 6+ languages (Greek, Chinese, Japanese, German, French, Spanish)
- Multilingual literature search

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.i18n import LanguageDetector, PromptTranslator
    
    detector = LanguageDetector()
    lang = detector.detect("Η ιδέα της έρευνάς μου είναι...")
    
    translator = PromptTranslator()
    prompt = translator.translate_prompt("topic_init", lang="el")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SupportedLanguage(str, Enum):
    """Supported languages."""
    ENGLISH = "en"
    GREEK = "el"
    CHINESE = "zh"
    JAPANESE = "ja"
    GERMAN = "de"
    FRENCH = "fr"
    SPANISH = "es"
    KOREAN = "ko"
    PORTUGUESE = "pt"
    ITALIAN = "it"
    DUTCH = "nl"
    RUSSIAN = "ru"
    ARABIC = "ar"
    HINDI = "hi"


# Language names in their native script
LANGUAGE_NAMES = {
    SupportedLanguage.ENGLISH: "English",
    SupportedLanguage.GREEK: "Ελληνικά",
    SupportedLanguage.CHINESE: "中文",
    SupportedLanguage.JAPANESE: "日本語",
    SupportedLanguage.GERMAN: "Deutsch",
    SupportedLanguage.FRENCH: "Français",
    SupportedLanguage.SPANISH: "Español",
    SupportedLanguage.KOREAN: "한국어",
    SupportedLanguage.PORTUGUESE: "Português",
    SupportedLanguage.ITALIAN: "Italiano",
    SupportedLanguage.DUTCH: "Nederlands",
    SupportedLanguage.RUSSIAN: "Русский",
    SupportedLanguage.ARABIC: "العربية",
    SupportedLanguage.HINDI: "हिन्दी",
}

# Language-specific keywords for detection
LANGUAGE_KEYWORDS = {
    SupportedLanguage.GREEK: [
        "και", "το", "η", "ο", "σε", "για", "από", "με", "είναι",
        "έρευνα", "μελέτη", "ανάλυση",
    ],
    SupportedLanguage.CHINESE: [
        "的", "是", "在", "了", "和", "与", "及", "等",
        "研究", "分析", "调查", "实验",
    ],
    SupportedLanguage.JAPANESE: [
        "の", "は", "に", "を", "が", "で", "と", "し",
        "研究", "分析", "調査", "実験",
    ],
    SupportedLanguage.GERMAN: [
        "der", "die", "das", "und", "ist", "in", "mit", "von",
        "Forschung", "Studie", "Analyse", "Untersuchung",
    ],
    SupportedLanguage.FRENCH: [
        "le", "la", "les", "de", "et", "est", "dans", "avec",
        "recherche", "étude", "analyse",
    ],
    SupportedLanguage.SPANISH: [
        "el", "la", "los", "las", "de", "y", "es", "en", "con",
        "investigación", "estudio", "análisis",
    ],
    SupportedLanguage.KOREAN: [
        "의", "는", "을", "를", "에", "와", "과", "이",
        "연구", "분석", "조사", "실험",
    ],
    SupportedLanguage.PORTUGUESE: [
        "o", "a", "os", "as", "de", "e", "é", "em", "com",
        "pesquisa", "estudo", "análise",
    ],
    SupportedLanguage.RUSSIAN: [
        "и", "в", "не", "на", "я", "что", "этот", "быть",
        "исследование", "анализ", "изучение",
    ],
    SupportedLanguage.ARABIC: [
        "و", "في", "من", "إلى", "على", "هو", "هي", "أن",
        "بحث", "دراسة", "تحليل",
    ],
}


@dataclass
class LanguageDetectionResult:
    """Result of language detection."""
    
    language: SupportedLanguage
    confidence: float
    detected_keywords: list[str]
    is_supported: bool


class LanguageDetector:
    """Detect language from text."""
    
    def __init__(self) -> None:
        """Initialize language detector."""
        self._supported = set(SupportedLanguage)
    
    def detect(self, text: str, top_n: int = 1) -> LanguageDetectionResult | list[LanguageDetectionResult]:
        """Detect language from text.
        
        Args:
            text: Text to analyze
            top_n: Number of top results to return
            
        Returns:
            Language detection result(s)
        """
        text_lower = text.lower()
        
        results = []
        
        for lang, keywords in LANGUAGE_KEYWORDS.items():
            matches = []
            for keyword in keywords:
                if keyword in text_lower:
                    matches.append(keyword)
            
            if matches:
                confidence = len(matches) / len(keywords)
                results.append(LanguageDetectionResult(
                    language=lang,
                    confidence=confidence,
                    detected_keywords=matches,
                    is_supported=lang in self._supported,
                ))
        
        # Sort by confidence
        results.sort(key=lambda x: x.confidence, reverse=True)
        
        # Return top result or top N
        if not results:
            # Default to English
            return LanguageDetectionResult(
                language=SupportedLanguage.ENGLISH,
                confidence=0.5,
                detected_keywords=[],
                is_supported=True,
            )
        
        if top_n == 1:
            return results[0]
        return results[:top_n]
    
    def is_supported(self, language: str | SupportedLanguage) -> bool:
        """Check if language is supported.
        
        Args:
            language: Language code or enum
            
        Returns:
            True if supported
        """
        if isinstance(language, str):
            try:
                lang_enum = SupportedLanguage(language)
                return lang_enum in self._supported
            except ValueError:
                return False
        return language in self._supported
    
    def get_language_name(self, language: str | SupportedLanguage) -> str:
        """Get language name in native script.
        
        Args:
            language: Language code or enum
            
        Returns:
            Native language name
        """
        if isinstance(language, str):
            try:
                language = SupportedLanguage(language)
            except ValueError:
                return language
        
        return LANGUAGE_NAMES.get(language, language.value)


class PromptTranslator:
    """Translate prompts to different languages."""
    
    def __init__(self, translations_dir: str | Path | None = None) -> None:
        """Initialize translator.
        
        Args:
            translations_dir: Directory with translation files
        """
        self._translations_dir = Path(translations_dir) if translations_dir else None
        self._translations: dict[str, dict[str, str]] = {}
        
        # Load translations
        self._load_translations()
    
    def _load_translations(self) -> None:
        """Load translation files."""
        if self._translations_dir and self._translations_dir.exists():
            for lang_file in self._translations_dir.glob("*.json"):
                lang_code = lang_file.stem
                try:
                    import json
                    with open(lang_file, "r", encoding="utf-8") as f:
                        self._translations[lang_code] = json.load(f)
                    logger.info(f"Loaded translations for {lang_code}")
                except Exception as e:
                    logger.error(f"Failed to load {lang_file}: {e}")
        
        # Add built-in translations
        self._add_builtin_translations()
    
    def _add_builtin_translations(self) -> None:
        """Add built-in translations for common prompts."""
        # Greek translations
        self._translations["el"] = {
            "topic_init": "Αρχικοποίηση θέματος έρευνας",
            "problem_decompose": "Ανάλυση προβλήματος σε υπο-εργασίες",
            "search_strategy": "Στρατηγική αναζήτησης βιβλιογραφίας",
            "literature_collect": "Συλλογή βιβλιογραφίας",
            "hypothesis_gen": "Δημιουργία υποθέσεων",
            "experiment_design": "Σχεδιασμός πειράματος",
            "code_generation": "Δημιουργία κώδικα",
            "paper_draft": "Συγγραφή άρθρου",
            "quality_gate": "Έλεγχος ποιότητας",
            # Common terms
            "research": "έρευνα",
            "experiment": "πείραμα",
            "analysis": "ανάλυση",
            "results": "αποτελέσματα",
            "conclusion": "συμπέρασμα",
        }
        
        # Chinese translations
        self._translations["zh"] = {
            "topic_init": "研究主题初始化",
            "problem_decompose": "问题分解为子任务",
            "search_strategy": "文献检索策略",
            "literature_collect": "文献收集",
            "hypothesis_gen": "假设生成",
            "experiment_design": "实验设计",
            "code_generation": "代码生成",
            "paper_draft": "论文草稿",
            "quality_gate": "质量检查",
            # Common terms
            "research": "研究",
            "experiment": "实验",
            "analysis": "分析",
            "results": "结果",
            "conclusion": "结论",
        }
        
        # Japanese translations
        self._translations["ja"] = {
            "topic_init": "研究トピックの初期化",
            "problem_decompose": "問題をサブタスクに分解",
            "search_strategy": "文献検索戦略",
            "literature_collect": "文献収集",
            "hypothesis_gen": "仮説生成",
            "experiment_design": "実験設計",
            "code_generation": "コード生成",
            "paper_draft": "論文ドラフト",
            "quality_gate": "品質チェック",
            # Common terms
            "research": "研究",
            "experiment": "実験",
            "analysis": "分析",
            "results": "結果",
            "conclusion": "結論",
        }
        
        # German translations
        self._translations["de"] = {
            "topic_init": "Forschungsthema initialisieren",
            "problem_decompose": "Problem in Teilaufgaben zerlegen",
            "search_strategy": "Literatursuchstrategie",
            "literature_collect": "Literatursammlung",
            "hypothesis_gen": "Hypothesengenerierung",
            "experiment_design": "Experimentdesign",
            "code_generation": "Codegenerierung",
            "paper_draft": "Papierentwurf",
            "quality_gate": "Qualitätsprüfung",
            # Common terms
            "research": "Forschung",
            "experiment": "Experiment",
            "analysis": "Analyse",
            "results": "Ergebnisse",
            "conclusion": "Fazit",
        }
        
        # French translations
        self._translations["fr"] = {
            "topic_init": "Initialisation du sujet de recherche",
            "problem_decompose": "Décomposition du problème",
            "search_strategy": "Stratégie de recherche bibliographique",
            "literature_collect": "Collecte de littérature",
            "hypothesis_gen": "Génération d'hypothèses",
            "experiment_design": "Conception d'expérience",
            "code_generation": "Génération de code",
            "paper_draft": "Ébauche d'article",
            "quality_gate": "Contrôle de qualité",
            # Common terms
            "research": "recherche",
            "experiment": "expérience",
            "analysis": "analyse",
            "results": "résultats",
            "conclusion": "conclusion",
        }
        
        # Spanish translations
        self._translations["es"] = {
            "topic_init": "Inicialización del tema de investigación",
            "problem_decompose": "Descomposición del problema",
            "search_strategy": "Estrategia de búsqueda bibliográfica",
            "literature_collect": "Recopilación de literatura",
            "hypothesis_gen": "Generación de hipótesis",
            "experiment_design": "Diseño experimental",
            "code_generation": "Generación de código",
            "paper_draft": "Borrador de artículo",
            "quality_gate": "Control de calidad",
            # Common terms
            "research": "investigación",
            "experiment": "experimento",
            "analysis": "análisis",
            "results": "resultados",
            "conclusion": "conclusión",
        }
    
    def translate_prompt(
        self,
        prompt_key: str,
        language: str | SupportedLanguage,
        default: str | None = None,
    ) -> str:
        """Translate a prompt to specified language.
        
        Args:
            prompt_key: Prompt key to translate
            language: Target language
            default: Default text if translation not found
            
        Returns:
            Translated prompt or default
        """
        if isinstance(language, SupportedLanguage):
            lang_code = language.value
        else:
            lang_code = language
        
        # Get translation
        translations = self._translations.get(lang_code, {})
        translation = translations.get(prompt_key)
        
        if translation:
            return translation
        
        # Return default or English version
        if default:
            return default
        
        # Fallback to English
        english_translations = self._translations.get("en", {})
        return english_translations.get(prompt_key, prompt_key)
    
    def translate_text(
        self,
        text: str,
        target_language: str | SupportedLanguage,
        source_language: str | SupportedLanguage = "en",
    ) -> str:
        """Translate arbitrary text.
        
        Note: For production use, integrate with translation API
        (Google Translate, DeepL, etc.)
        
        Args:
            text: Text to translate
            target_language: Target language
            source_language: Source language
            
        Returns:
            Translated text (or original if no translation available)
        """
        # For now, return original text
        # In production, call translation API
        logger.warning(
            f"Translation not available for arbitrary text. "
            f"Consider integrating with Google Translate or DeepL API."
        )
        return text
    
    def get_available_languages(self) -> list[SupportedLanguage]:
        """Get list of languages with available translations.
        
        Returns:
            List of supported languages
        """
        return [
            SupportedLanguage(code)
            for code in self._translations.keys()
            if code in SupportedLanguage.__members__
        ]


class MultilingualPipelineAdapter:
    """Adapter for multilingual pipeline execution."""
    
    def __init__(self) -> None:
        """Initialize multilingual adapter."""
        self._detector = LanguageDetector()
        self._translator = PromptTranslator()
        self._current_language: SupportedLanguage = SupportedLanguage.ENGLISH
    
    def detect_and_set_language(self, topic: str) -> SupportedLanguage:
        """Detect language from topic and set as current.
        
        Args:
            topic: Research topic text
            
        Returns:
            Detected language
        """
        result = self._detector.detect(topic)
        self._current_language = result.language
        
        logger.info(f"Detected language: {self._detector.get_language_name(result.language)}")
        logger.info(f"Confidence: {result.confidence:.0%}")
        
        return result.language
    
    def get_prompt(self, prompt_key: str, default: str | None = None) -> str:
        """Get prompt in current language.
        
        Args:
            prompt_key: Prompt key
            default: Default text
            
        Returns:
            Translated prompt
        """
        return self._translator.translate_prompt(
            prompt_key,
            self._current_language,
            default,
        )
    
    @property
    def current_language(self) -> SupportedLanguage:
        """Get current language."""
        return self._current_language
    
    @property
    def current_language_name(self) -> str:
        """Get current language name in native script."""
        return self._detector.get_language_name(self._current_language)


# Global instance
_adapter: MultilingualPipelineAdapter | None = None


def get_multilingual_adapter() -> MultilingualPipelineAdapter:
    """Get global multilingual adapter instance."""
    global _adapter
    if _adapter is None:
        _adapter = MultilingualPipelineAdapter()
    return _adapter
