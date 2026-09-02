"""Stage 22 cross-model adversarial double-check (tasks/ars_integration_plan.md W5).

Tests _run_cross_model_double_check directly rather than through the full
_execute_export_publish stage, since it only needs a HallucinationReport-
shaped object (duck-typed, .issues only) and an RCConfig. No real network
or API key anywhere in this file -- LLMClient.chat is monkeypatched.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from berb.config import RCConfig
from berb.pipeline.stage_impls._export import _run_cross_model_double_check

_BASE_CONFIG: dict[str, Any] = {
    "project": {"name": "rc-test", "mode": "docs-first"},
    "research": {"topic": "test topic", "domains": ["ml"], "quality_threshold": 8.0},
    "runtime": {"timezone": "UTC"},
    "notifications": {"channel": "local"},
    "openclaw_bridge": {"use_memory": True, "use_message": True},
    "security": {"hitl_required_stages": [5, 9, 20]},
    "experiment": {"mode": "sandbox"},
}


def _rc_config(
    tmp_path,
    *,
    provider: str = "anthropic",
    cross_model_verification: bool = True,
    cross_model_consent_granted: bool = True,
    cross_model_max_usd_per_run: float = 1.0,
) -> RCConfig:
    data = dict(_BASE_CONFIG)
    data["knowledge_base"] = {"backend": "markdown", "root": str(tmp_path / "kb")}
    data["llm"] = {
        "provider": provider,
        "base_url": "http://localhost:1234/v1",
        "api_key_env": "RC_TEST_KEY",
        "primary_model": "fake-model",
    }
    data["security"] = {
        **data["security"],
        "cross_model_verification": cross_model_verification,
        "cross_model_consent_granted": cross_model_consent_granted,
        "cross_model_max_usd_per_run": cross_model_max_usd_per_run,
    }
    return RCConfig.from_dict(data, project_root=tmp_path, check_paths=False, check_security=False)


def _report(*issues: dict[str, Any]) -> Any:
    return SimpleNamespace(issues=list(issues))


def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BERB_CROSS_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("BERB_CROSS_MODEL_MODEL", "gpt-5.5")
    monkeypatch.setenv("BERB_CROSS_MODEL_API_KEY_ENV", "OPENAI_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test-key")


def test_no_flagged_issues_returns_empty(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    report = _report({"type": "duplicated_figure", "description": "x"})
    records = _run_cross_model_double_check(report, _rc_config(tmp_path))
    assert records == []


def test_no_adversarial_provider_configured_returns_unverified(tmp_path) -> None:
    report = _report({"type": "unsupported_claim", "claim": "x", "citation": "he2016deep"})
    records = _run_cross_model_double_check(report, _rc_config(tmp_path))
    assert len(records) == 1
    assert records[0]["check"] == "cross_model_unverified"
    assert records[0]["severity"] == "info"


def test_successful_double_check_records_verdict(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)

    def _fake_chat(self, messages, **kwargs):
        from berb.llm.client import LLMResponse

        return LLMResponse(
            content='{"verdict": "disagrees", "rationale": "quote not found"}',
            model="gpt-5.5",
            prompt_tokens=10,
            completion_tokens=5,
        )

    monkeypatch.setattr("berb.llm.client.LLMClient.chat", _fake_chat)

    report = _report({"type": "unsupported_claim", "claim": "x", "citation": "he2016deep"})
    records = _run_cross_model_double_check(report, _rc_config(tmp_path))
    assert len(records) == 1
    assert records[0]["verdict"] == "disagrees"
    assert records[0]["provider"] == "openai"
    assert records[0]["locator"] == "he2016deep"


def test_unparseable_response_is_unverified(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)

    def _fake_chat(self, messages, **kwargs):
        from berb.llm.client import LLMResponse

        return LLMResponse(content="not json at all", model="gpt-5.5")

    monkeypatch.setattr("berb.llm.client.LLMClient.chat", _fake_chat)
    report = _report({"type": "unsupported_claim", "claim": "x", "citation": "he2016deep"})
    records = _run_cross_model_double_check(report, _rc_config(tmp_path))
    assert records[0]["check"] == "cross_model_unverified"
    assert "parsed" in records[0]["message"]


def test_provider_call_exception_is_unverified(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)

    def _fake_chat(self, messages, **kwargs):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr("berb.llm.client.LLMClient.chat", _fake_chat)
    report = _report({"type": "unsupported_claim", "claim": "x", "citation": "he2016deep"})
    records = _run_cross_model_double_check(report, _rc_config(tmp_path))
    assert records[0]["check"] == "cross_model_unverified"
    assert "failed" in records[0]["message"]


def test_cost_ceiling_stops_further_calls(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    call_count = {"n": 0}

    def _fake_chat(self, messages, **kwargs):
        from berb.llm.client import LLMResponse

        call_count["n"] += 1
        return LLMResponse(
            content='{"verdict": "agrees"}',
            model="gpt-5.5",
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
        )

    monkeypatch.setattr("berb.llm.client.LLMClient.chat", _fake_chat)
    cfg = _rc_config(tmp_path, cross_model_max_usd_per_run=0.0001)
    report = _report(
        {"type": "unsupported_claim", "claim": "a", "citation": "a2020x"},
        {"type": "unsupported_claim", "claim": "b", "citation": "b2021y"},
        {"type": "unsupported_claim", "claim": "c", "citation": "c2022z"},
    )
    records = _run_cross_model_double_check(report, cfg)
    # First call is allowed (ceiling not yet exceeded before any spend is
    # recorded), subsequent calls are blocked once its cost registers.
    assert call_count["n"] <= 1
    assert any(r.get("check") == "cross_model_unverified" for r in records)


def test_bounded_to_max_checks_per_run(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)

    def _fake_chat(self, messages, **kwargs):
        from berb.llm.client import LLMResponse

        return LLMResponse(content='{"verdict": "agrees"}', model="gpt-5.5")

    monkeypatch.setattr("berb.llm.client.LLMClient.chat", _fake_chat)
    import berb.pipeline.stage_impls._export as export_mod

    issues = [
        {"type": "unsupported_claim", "claim": f"c{i}", "citation": f"key{i}"}
        for i in range(export_mod._MAX_CROSS_MODEL_CHECKS + 5)
    ]
    report = _report(*issues)
    records = _run_cross_model_double_check(report, _rc_config(tmp_path))
    assert len(records) == export_mod._MAX_CROSS_MODEL_CHECKS


def test_same_family_env_provider_is_rejected(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Primary provider is anthropic; pointing the adversarial env vars at
    # anthropic too must never silently pass as a real cross-model check.
    monkeypatch.setenv("BERB_CROSS_MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("BERB_CROSS_MODEL_MODEL", "claude-haiku-4.5")
    monkeypatch.setenv("BERB_CROSS_MODEL_API_KEY_ENV", "ANTHROPIC_API_KEY")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")

    report = _report({"type": "unsupported_claim", "claim": "x", "citation": "he2016deep"})
    records = _run_cross_model_double_check(report, _rc_config(tmp_path, provider="anthropic"))
    assert records[0]["check"] == "cross_model_unverified"
