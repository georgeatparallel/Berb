"""Model registry (SSOT) contract tests.

The load-bearing test here is ``test_every_registered_id_exists_in_catalogue``:
a registry entry naming a model that is not in the catalogue fails only at
request time, on the one call that used it.
"""

from __future__ import annotations

import pytest

from berb.config import _parse_models_config
from berb.llm.openrouter_models_data import OPENROUTER_MODELS
from berb.llm.registry import (
    TASK_PROFILES,
    ModelsConfig,
    bare,
    model_pins_temperature,
    model_uses_max_completion_tokens,
    price_sorted_chain,
    resolve,
    resolve_chain,
    temperature_for,
)


@pytest.mark.parametrize("task", sorted(TASK_PROFILES))
def test_every_registered_id_exists_in_catalogue(task: str) -> None:
    for model_id in TASK_PROFILES[task].chain:
        assert model_id in OPENROUTER_MODELS, (
            f"{task!r} references {model_id!r}, absent from OPENROUTER_MODELS"
        )


@pytest.mark.parametrize("task", ["vision", "image_gen"])
def test_vision_tasks_use_vision_capable_models(task: str) -> None:
    for model_id in TASK_PROFILES[task].chain:
        assert OPENROUTER_MODELS[model_id].supports_vision, (
            f"{task!r} routes to {model_id!r}, which the catalogue marks text-only"
        )


def test_every_task_has_a_fallback() -> None:
    for task, profile in TASK_PROFILES.items():
        assert profile.fallbacks, f"{task!r} has no fallback chain"


def test_fallbacks_are_distinct_from_primary() -> None:
    for task, profile in TASK_PROFILES.items():
        assert len(set(profile.chain)) == len(profile.chain), f"{task!r} repeats a model"


class _Llm:
    primary_model = "openai/gpt-4o"
    fallback_models = ("openai/gpt-4o-mini",)


class _Cfg:
    def __init__(self, models: ModelsConfig | None = None) -> None:
        self.llm = _Llm()
        self.models = models or ModelsConfig()


def test_resolve_returns_registered_default() -> None:
    assert resolve("fast", None) == TASK_PROFILES["fast"].primary


def test_override_replaces_primary_but_keeps_fallbacks() -> None:
    cfg = _Cfg(ModelsConfig(fast="anthropic/claude-sonnet-5"))
    chain = resolve_chain("fast", cfg)  # type: ignore[arg-type]
    assert chain[0] == "anthropic/claude-sonnet-5"
    # The safety net survives the override.
    assert TASK_PROFILES["fast"].chain == chain[1:]


def test_unregistered_task_falls_back_to_global_llm_chain() -> None:
    chain = resolve_chain("nonexistent_task", _Cfg())  # type: ignore[arg-type]
    assert chain == ("openai/gpt-4o", "openai/gpt-4o-mini")


def test_unregistered_task_without_config_raises() -> None:
    with pytest.raises(ValueError, match="No model registered"):
        resolve("nonexistent_task", None)


@pytest.mark.parametrize(
    "model_id",
    ["openai/o1", "openai/o3", "openai/o4-mini", "openai/o3-mini:batch", "openai/gpt-5-pro"],
)
def test_reasoning_family_pins_temperature(model_id: str) -> None:
    assert model_pins_temperature(model_id)
    assert temperature_for("reasoning", model_id) is None


@pytest.mark.parametrize("model_id", ["openai/gpt-4o", "anthropic/claude-opus-5", "qwen/qwen3.7-flash"])
def test_chat_models_accept_temperature(model_id: str) -> None:
    """The pin is a reasoning-family trait, not a vendor-wide one."""
    assert not model_pins_temperature(model_id)
    assert temperature_for("code", model_id) == pytest.approx(0.1)


def test_deterministic_tasks_are_cold_and_prose_is_warm() -> None:
    assert TASK_PROFILES["fast"].temperature == 0.0
    assert TASK_PROFILES["code"].temperature <= 0.2
    assert TASK_PROFILES["writing"].temperature >= 0.6


def test_config_temperature_override_wins() -> None:
    cfg = _Cfg(ModelsConfig(temperatures=(("code", 0.4),)))
    assert temperature_for("code", "openai/gpt-4o", cfg) == pytest.approx(0.4)  # type: ignore[arg-type]


def test_pinned_model_ignores_config_temperature_override() -> None:
    """A configured temperature must not resurrect a parameter the API rejects."""
    cfg = _Cfg(ModelsConfig(temperatures=(("reasoning", 0.4),)))
    assert temperature_for("reasoning", "openai/o3", cfg) is None  # type: ignore[arg-type]


def test_parse_models_config_reads_yaml_block() -> None:
    cfg = _parse_models_config(
        {"fast": "openai/gpt-4o-mini", "temperatures": {"fast": 0.25}}
    )
    assert cfg.fast == "openai/gpt-4o-mini"
    assert cfg.temperature_for("fast") == pytest.approx(0.25)
    assert cfg.literature == ""


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("google/gemini-2.5-flash-image", "gemini-2.5-flash-image"),
        ("gemini-2.5-flash-image", "gemini-2.5-flash-image"),  # already bare
        ("openrouter/anthropic/claude-sonnet-5", "anthropic/claude-sonnet-5"),
    ],
)
def test_bare_strips_one_provider_prefix(model_id: str, expected: str) -> None:
    assert bare(model_id) == expected


@pytest.mark.parametrize(
    "model_id", ["o1", "o3", "o4-mini", "gpt-5", "gpt-5.4", "openai/o3", "openai/gpt-5.2"]
)
def test_reasoning_family_uses_max_completion_tokens(model_id: str) -> None:
    assert model_uses_max_completion_tokens(model_id)


@pytest.mark.parametrize("model_id", ["gpt-4o", "gpt-4.1", "anthropic/claude-opus-5"])
def test_chat_models_use_max_tokens(model_id: str) -> None:
    assert not model_uses_max_completion_tokens(model_id)


def test_prefixed_and_bare_ids_agree_on_capabilities() -> None:
    """A direct-OpenAI base_url passes bare ids; both forms must match."""
    for bare_id in ("o3", "gpt-5-pro"):
        assert model_pins_temperature(bare_id) == model_pins_temperature(f"openai/{bare_id}")


@pytest.mark.parametrize("task", sorted(TASK_PROFILES))
def test_price_sorted_chain_is_a_permutation_ordered_by_price(task: str) -> None:
    from berb.llm.openrouter_models_data import OPENROUTER_MODELS

    ordered = price_sorted_chain(task)
    assert sorted(ordered) == sorted(TASK_PROFILES[task].chain)
    prices = [OPENROUTER_MODELS[m].input_price for m in ordered]
    assert prices == sorted(prices)


def test_price_sorted_chain_keeps_uncatalogued_models_last() -> None:
    """An unknown id must sort last, never vanish from the chain."""
    cfg = _Cfg(ModelsConfig(fast="not-a-real/model"))
    ordered = price_sorted_chain("fast", cfg)  # type: ignore[arg-type]
    assert ordered[-1] == "not-a-real/model"
    assert set(ordered) == {"not-a-real/model", *TASK_PROFILES["fast"].chain}


def test_parse_models_config_ignores_unknown_task() -> None:
    cfg = _parse_models_config({"not_a_task": "x", "temperatures": {"not_a_task": 0.5}})
    assert cfg.temperature_for("not_a_task") is None
