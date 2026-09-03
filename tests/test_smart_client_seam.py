"""Regression tests for the client seam create_llm_client hands to the pipeline.

Every stage calls ``llm.chat(...)`` and some reach through to ``llm.config``.
SmartLLMClient had neither: it exposed only an async ``complete()`` that awaited
a ``complete()`` no base client has. These tests pin the seam so a wrapper
cannot be added again without it.
"""

from __future__ import annotations

from typing import Any

import pytest

from berb.llm.client import LLMConfig, LLMResponse
from berb.llm.smart_client import SmartLLMClient


class _FakeBase:
    """Stands in for LLMClient / MultiProviderLLMClient / ACPClient."""

    def __init__(self) -> None:
        self.config = LLMConfig(base_url="https://api.example.com/v1", api_key="k")
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> LLMResponse:
        self.calls.append({"messages": messages, **kwargs})
        return LLMResponse(
            content="ok",
            model=kwargs.get("model") or "default",
            prompt_tokens=3,
            completion_tokens=2,
            total_tokens=5,
        )


def _client(base: _FakeBase) -> SmartLLMClient:
    return SmartLLMClient(config=base.config, base_client=base)


# ---------------------------------------------------------------------------
# The seam the pipeline actually uses
# ---------------------------------------------------------------------------


def test_smart_client_exposes_chat() -> None:
    """36 call sites do llm.chat(...); the wrapper had no chat at all."""
    assert callable(getattr(SmartLLMClient, "chat", None))


def test_chat_delegates_to_the_base_client() -> None:
    base = _FakeBase()
    resp = _client(base).chat([{"role": "user", "content": "hi"}])

    assert resp.content == "ok"
    assert len(base.calls) == 1


def test_chat_returns_an_llm_response_not_a_wrapper() -> None:
    """Callers read resp.content directly, so chat must not return SmartLLMResponse."""
    assert isinstance(_client(_FakeBase()).chat([{"role": "user", "content": "hi"}]), LLMResponse)


def test_an_explicit_model_is_honoured() -> None:
    base = _FakeBase()
    _client(base).chat([{"role": "user", "content": "hi"}], model="pinned-model")
    assert base.calls[0]["model"] == "pinned-model"


def test_without_a_model_the_configured_primary_is_used() -> None:
    base = _FakeBase()
    _client(base).chat([{"role": "user", "content": "hi"}])
    assert base.calls[0]["model"] == base.config.primary_model


def test_config_reaches_the_object_that_makes_the_request() -> None:
    """_prompt_helpers sets llm.config.timeout_sec for one call; it must land."""
    base = _FakeBase()
    smart = _client(base)

    smart.config.timeout_sec = 42

    assert base.config.timeout_sec == 42


def test_an_already_built_base_client_is_wrapped_not_rebuilt() -> None:
    """Passing only a config discarded multi-provider failover and ACP."""
    base = _FakeBase()
    assert _client(base)._base_client is base


def test_without_a_base_client_a_plain_llm_client_is_built() -> None:
    from berb.llm.client import LLMClient

    smart = SmartLLMClient(config=LLMConfig(base_url="https://x/v1", api_key="k"))
    assert isinstance(smart._base_client, LLMClient)


@pytest.mark.asyncio
async def test_complete_still_returns_routing_metadata() -> None:
    base = _FakeBase()
    result = await _client(base).complete([{"role": "user", "content": "hi"}])

    assert result.response.content == "ok"
    assert result.selected_model == base.config.primary_model
    assert result.selected_tier == "default"


# ---------------------------------------------------------------------------
# create_llm_client wiring
# ---------------------------------------------------------------------------


class _CascadeStep:
    def __init__(self, model: str, min_score: float) -> None:
        self.model = model
        self.min_score = min_score
        self.max_tokens = None
        self.temperature = 0.7


class _CascadeCfg:
    def __init__(self, enabled: bool, steps: tuple[_CascadeStep, ...]) -> None:
        self.enabled = enabled
        self.steps = steps
        self.quick_eval_enabled = True
        self.fallback_model = ""


class _RCConfigStub:
    def __init__(self, cascade: _CascadeCfg | None) -> None:
        self.cascade = cascade


def test_cascade_wrapper_is_a_noop_when_disabled() -> None:
    from berb.llm import _maybe_wrap_cascade

    base = _FakeBase()
    cfg = _RCConfigStub(_CascadeCfg(enabled=False, steps=(_CascadeStep("cheap", 0.0),)))
    assert _maybe_wrap_cascade(cfg, base) is base


def test_cascade_wrapper_is_a_noop_when_enabled_but_empty() -> None:
    """An enabled-but-stepless cascade must not raise on every later call."""
    from berb.llm import _maybe_wrap_cascade

    base = _FakeBase()
    cfg = _RCConfigStub(_CascadeCfg(enabled=True, steps=()))
    assert _maybe_wrap_cascade(cfg, base) is base


def test_cascade_wrapper_wraps_when_configured() -> None:
    from berb.llm import _maybe_wrap_cascade
    from berb.llm.model_cascade import CascadingLLMClient

    base = _FakeBase()
    cfg = _RCConfigStub(
        _CascadeCfg(
            enabled=True,
            steps=(_CascadeStep("cheap", 0.9), _CascadeStep("premium", 0.0)),
        )
    )
    wrapped = _maybe_wrap_cascade(cfg, base)

    assert isinstance(wrapped, CascadingLLMClient)
    assert [s.model for s in wrapped.cascade_config.cascade] == ["cheap", "premium"]


def test_cascade_wrapper_tolerates_a_config_without_the_section() -> None:
    from berb.llm import _maybe_wrap_cascade

    base = _FakeBase()
    assert _maybe_wrap_cascade(_RCConfigStub(None), base) is base


def test_a_cascade_can_wrap_a_smart_client() -> None:
    """The two wrappers compose: cascade picks the model, smart client tracks it."""
    from berb.llm import _maybe_wrap_cascade

    base = _FakeBase()
    smart = _client(base)
    cfg = _RCConfigStub(_CascadeCfg(enabled=True, steps=(_CascadeStep("cheap", 0.0),)))

    _maybe_wrap_cascade(cfg, smart).chat([{"role": "user", "content": "hi"}])

    assert base.calls[0]["model"] == "cheap"


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------


def test_cascade_config_parses_steps() -> None:
    from berb.config import _parse_cascade_config

    cfg = _parse_cascade_config(
        {
            "enabled": True,
            "steps": [
                {"model": "cheap", "min_score": 0.8, "max_tokens": 100},
                {"model": "premium", "min_score": 0.0},
            ],
            "fallback_model": "backstop",
        }
    )
    assert cfg.enabled is True
    assert [s.model for s in cfg.steps] == ["cheap", "premium"]
    assert cfg.steps[0].max_tokens == 100
    assert cfg.steps[1].max_tokens is None
    assert cfg.fallback_model == "backstop"


def test_cascade_config_drops_a_step_without_a_model() -> None:
    from berb.config import _parse_cascade_config

    cfg = _parse_cascade_config({"steps": [{"min_score": 0.5}, {"model": "ok"}]})
    assert [s.model for s in cfg.steps] == ["ok"]


def test_cascade_config_defaults_to_off() -> None:
    from berb.config import LlmCascadeConfig, _parse_cascade_config

    assert _parse_cascade_config({}) == LlmCascadeConfig()
    assert LlmCascadeConfig().enabled is False


# ---------------------------------------------------------------------------
# NadirClaw: config.nadirclaw was previously unreadable (RCConfig had no such
# field), so create_llm_client's `hasattr(config, "nadirclaw")` check always
# failed and the router never engaged through the standard client path.
# ---------------------------------------------------------------------------


def test_nadirclaw_config_parses_overrides() -> None:
    from berb.config import _parse_nadirclaw_config

    cfg = _parse_nadirclaw_config(
        {
            "enabled": True,
            "simple_model": "google/gemini-2.5-flash-lite",
            "tier_thresholds": [0.2, 0.8],
            "cache_max_size": 10,
        }
    )
    assert cfg.enabled is True
    assert cfg.simple_model == "google/gemini-2.5-flash-lite"
    assert cfg.tier_thresholds == (0.2, 0.8)
    assert cfg.cache_max_size == 10


def test_nadirclaw_config_defaults_to_off() -> None:
    from berb.config import NadirClawConfig, _parse_nadirclaw_config

    assert _parse_nadirclaw_config({}) == NadirClawConfig()
    assert NadirClawConfig().enabled is False


def test_create_llm_client_wires_nadirclaw_when_enabled(tmp_path) -> None:
    """The regression this seam exists for: enabling nadirclaw in config must
    actually produce a routing SmartLLMClient, not a plain LLMClient."""
    from berb.config import RCConfig
    from berb.llm import create_llm_client

    from .test_berb_config import _valid_config_data

    data = _valid_config_data()
    data["nadirclaw"] = {"enabled": True}
    config = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)

    client = create_llm_client(config)

    assert isinstance(client, SmartLLMClient)
    assert client._nadirclaw_enabled is True
    assert client._router is not None


def test_create_llm_client_stays_plain_when_nadirclaw_disabled(tmp_path) -> None:
    from berb.config import RCConfig
    from berb.llm import create_llm_client
    from berb.llm.client import LLMClient

    from .test_berb_config import _valid_config_data

    config = RCConfig.from_dict(_valid_config_data(), project_root=tmp_path, check_paths=False)

    client = create_llm_client(config)

    assert isinstance(client, LLMClient)
