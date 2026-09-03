"""Single Source of Truth (SSOT) for per-task model selection.

Owns three things and nothing else:

* which model runs a given pipeline task, and its fallback chain
* the sampling temperature that task should use
* which models refuse a temperature at all

Price/context/capability metadata stays in ``openrouter_models_data.py``;
this module never duplicates it. Every id here is asserted to exist in that
catalogue by ``tests/test_model_registry.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from berb.config import RCConfig


@dataclass(frozen=True)
class TaskProfile:
    """Model chain and sampling policy for one pipeline task."""

    primary: str
    fallbacks: tuple[str, ...] = ()
    temperature: float = 0.7

    @property
    def chain(self) -> tuple[str, ...]:
        return (self.primary, *self.fallbacks)


# Temperature rationale, per task:
#   deterministic work (labels, code, extraction) -> near 0, because a
#   resampled answer that differs is a bug, not variety.
#   generative prose -> 0.7, the usual quality/diversity knee.
#   review -> 0.6: the ensemble wants *disagreeing* reviewers, so some
#   spread is the point; lower would collapse the personas together.
TASK_PROFILES: dict[str, TaskProfile] = {
    "fast": TaskProfile(
        primary="qwen/qwen3.7-flash",
        fallbacks=("google/gemini-2.5-flash-lite", "mistralai/mistral-nemo"),
        temperature=0.0,
    ),
    "literature": TaskProfile(
        primary="google/gemini-2.5-flash",
        fallbacks=("qwen/qwen3.7-flash", "openai/gpt-4o-mini"),
        temperature=0.2,
    ),
    "reasoning": TaskProfile(
        primary="anthropic/claude-opus-5",
        fallbacks=("openai/gpt-5.4", "google/gemini-2.5-pro"),
        temperature=0.3,
    ),
    "code": TaskProfile(
        primary="anthropic/claude-sonnet-5",
        fallbacks=("openai/gpt-4.1", "qwen/qwen3.7-flash"),
        temperature=0.1,
    ),
    "writing": TaskProfile(
        primary="anthropic/claude-sonnet-5",
        fallbacks=("openai/gpt-4.1", "google/gemini-2.5-pro"),
        temperature=0.7,
    ),
    "review": TaskProfile(
        primary="anthropic/claude-opus-5",
        fallbacks=("openai/gpt-5.4", "anthropic/claude-sonnet-5"),
        temperature=0.6,
    ),
    "vision": TaskProfile(
        primary="google/gemini-2.5-flash",
        fallbacks=("qwen/qwen3.7-flash", "google/gemini-2.5-pro"),
        temperature=0.2,
    ),
    "image_gen": TaskProfile(
        primary="google/gemini-2.5-flash-image",
        fallbacks=(
            "google/gemini-3.1-flash-image-preview",
            "google/gemini-3-pro-image-preview",
        ),
        temperature=1.0,
    ),
}

# Reasoning-family models pin sampling internally and reject an explicit
# temperature (the API errors rather than clamping). This is a property of
# the reasoning family, NOT of the vendor: openai/gpt-4o accepts temperature
# normally. Matched by pattern so newly-added o-series and reasoning
# variants are covered without editing this list.
# The ``openai/`` prefix is optional throughout: OpenRouter uses the slug
# form, while a direct OpenAI base_url takes the bare id ("o3"). Both reach
# the same model and both must be recognised.
_FIXED_TEMPERATURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?:openai/)?o\d"),  # o1, o3, o3-mini, o4-mini, ...
    re.compile(r"^(?:openai/)?gpt-5.*(-pro|-codex)"),  # gpt-5 reasoning variants
)

# Reasoning models also renamed the output-budget field: they take
# ``max_completion_tokens`` and reject ``max_tokens``.
_MAX_COMPLETION_TOKENS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?:openai/)?o\d"),
    re.compile(r"^(?:openai/)?gpt-5"),
)


def bare(model_id: str) -> str:
    """Strip the ``provider/`` slug prefix from *model_id*.

    Registry ids are OpenRouter slugs. Callers that talk to a vendor's own
    API (Google GenAI, for one) need the unprefixed id the vendor expects.
    """
    return model_id.split("/", 1)[-1]


def _normalize(model_id: str) -> str:
    return model_id.split(":", 1)[0]  # drop :batch / :free variant suffix


def model_pins_temperature(model_id: str) -> bool:
    """True when *model_id* refuses an explicit temperature parameter.

    Callers must omit the field entirely for these models; sending even the
    model's own effective value is rejected by the API.
    """
    base = _normalize(model_id)
    return any(p.search(base) for p in _FIXED_TEMPERATURE_PATTERNS)


def model_uses_max_completion_tokens(model_id: str) -> bool:
    """True when *model_id* wants ``max_completion_tokens``, not ``max_tokens``."""
    base = _normalize(model_id)
    return any(p.search(base) for p in _MAX_COMPLETION_TOKENS_PATTERNS)


@dataclass(frozen=True)
class ModelsConfig:
    """Per-task overrides from the ``models:`` config block.

    An empty string means "no override" and falls through to TASK_PROFILES.
    """

    fast: str = ""
    literature: str = ""
    reasoning: str = ""
    code: str = ""
    writing: str = ""
    review: str = ""
    vision: str = ""
    image_gen: str = ""
    temperatures: tuple[tuple[str, float], ...] = field(default=())

    def override_for(self, task: str) -> str:
        return getattr(self, task, "") if task in TASK_PROFILES else ""

    def temperature_for(self, task: str) -> float | None:
        return dict(self.temperatures).get(task)


def resolve(task: str, cfg: RCConfig | None = None) -> str:
    """Return the model id for *task* (config override wins over the default)."""
    return resolve_chain(task, cfg)[0]


def resolve_chain(task: str, cfg: RCConfig | None = None) -> tuple[str, ...]:
    """Return the full ``(primary, *fallbacks)`` chain for *task*.

    A config override replaces the primary but keeps the curated fallbacks
    behind it, so overriding one model never leaves a task without a safety
    net. Unregistered tasks fall back to the global primary/fallback models.
    """
    profile = TASK_PROFILES.get(task)
    models_cfg = getattr(cfg, "models", None)
    override = models_cfg.override_for(task) if models_cfg else ""

    if profile is None:
        llm = getattr(cfg, "llm", None)
        if llm and llm.primary_model:
            return (llm.primary_model, *tuple(llm.fallback_models))
        raise ValueError(
            f"No model registered for task {task!r} and no llm.primary_model configured. "
            f"Known tasks: {', '.join(sorted(TASK_PROFILES))}"
        )

    if override:
        return (override, *profile.chain)
    return profile.chain


def price_sorted_chain(task: str, cfg: RCConfig | None = None) -> tuple[str, ...]:
    """*task*'s chain reordered cheapest-input-price first.

    Prices come from the catalogue, which is their SSOT — this function adds
    no price data of its own. Models the catalogue does not list sort last
    rather than being dropped, so an unknown id never silently disappears
    from a chain.
    """
    from berb.llm.openrouter_models_data import OPENROUTER_MODELS

    def key(model_id: str) -> tuple[int, float]:
        entry = OPENROUTER_MODELS.get(model_id)
        return (1, 0.0) if entry is None else (0, entry.input_price)

    return tuple(sorted(resolve_chain(task, cfg), key=key))


def temperature_for(task: str, model_id: str, cfg: RCConfig | None = None) -> float | None:
    """Sampling temperature for *task*, or None if *model_id* forbids one.

    None means "omit the parameter from the request" — it is not a synonym
    for 0.0, and callers must not substitute a default.
    """
    if model_pins_temperature(model_id):
        return None
    models_cfg = getattr(cfg, "models", None)
    if models_cfg and (override := models_cfg.temperature_for(task)) is not None:
        return override
    profile = TASK_PROFILES.get(task)
    return profile.temperature if profile else 0.7


__all__ = [
    "TASK_PROFILES",
    "ModelsConfig",
    "TaskProfile",
    "bare",
    "model_pins_temperature",
    "model_uses_max_completion_tokens",
    "price_sorted_chain",
    "resolve",
    "resolve_chain",
    "temperature_for",
]
