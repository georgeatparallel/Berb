---
name: berb-i18n
description: Map of berb/i18n/ — multilingual research support: language detection, prompt translation, and 38-language academic writing profiles. Use when working on non-English paper generation, language detection, or academic writing conventions.
---

# berb/i18n

Multi-language support for the research pipeline: detects the language of a research topic, translates prompts, and carries per-language academic writing conventions (passive voice, citation placement, number/date formats, RTL) for 38 languages. **Unwired/dormant** — nothing outside `berb/i18n/` imports it; no pipeline stage, CLI command, or server route uses it. Entry points are `LanguageDetector` / `PromptTranslator` (multilingual.py) and `AcademicLanguageProfile` (academic_languages.py).

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | package exports from `academic_languages` (profiles, registry) and `multilingual` (detector, translator) |
| `multilingual.py` | `SupportedLanguage` enum (14 langs), `LanguageDetector` (detect language from topic text), `PromptTranslator` (render pipeline prompts in target language), multilingual literature-search helpers |
| `academic_languages.py` | 38-language registry of `AcademicLanguageProfile` pydantic models — writing direction (LTR/RTL), passive-voice and first-person conventions, sentence length, citation placement, date/number formats, bibliography sort locale |

## Wiring & entry points

- **No importers outside the package** — dormant; only tests exercise it.
- Public API: `LanguageDetector().detect(text)`, `PromptTranslator().translate_prompt(prompt_id, lang=...)`, profile lookup in `academic_languages`.
- No config keys reference i18n; prompts are English-only in the live pipeline (`prompts.default.yaml`).
