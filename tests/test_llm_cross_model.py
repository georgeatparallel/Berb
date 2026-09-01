"""Tests for berb.llm.cross_model (tasks/ars_integration_plan.md W5).

All fixtures use a fake ``env`` mapping — no real environment variables or
API keys, no network.
"""

from __future__ import annotations

from berb.config import SecurityConfig
from berb.integrity.findings import CheckId, Severity
from berb.llm.cross_model import (
    CrossModelVerdict,
    build_cross_model_payload,
    cost_ceiling_exceeded,
    cross_model_enabled,
    cross_model_unverified_finding,
    disclosure_record,
    parse_cross_model_verdict,
    provider_family,
    resolve_adversarial_llm_config,
)

# ---------------------------------------------------------------------------
# provider_family
# ---------------------------------------------------------------------------


def test_provider_family_bare_name() -> None:
    assert provider_family("anthropic") == "anthropic"
    assert provider_family("OpenAI") == "openai"


def test_provider_family_openrouter_style_id() -> None:
    assert provider_family("anthropic/claude-sonnet-4.6") == "anthropic"
    assert provider_family("openai/gpt-5.5") == "openai"


def test_provider_family_strips_whitespace() -> None:
    assert provider_family("  deepseek  ") == "deepseek"


# ---------------------------------------------------------------------------
# cross_model_enabled — consent gating
# ---------------------------------------------------------------------------


def test_disabled_by_default() -> None:
    assert cross_model_enabled(SecurityConfig()) is False


def test_verification_flag_alone_is_not_enough() -> None:
    cfg = SecurityConfig(cross_model_verification=True, cross_model_consent_granted=False)
    assert cross_model_enabled(cfg) is False


def test_consent_flag_alone_is_not_enough() -> None:
    cfg = SecurityConfig(cross_model_verification=False, cross_model_consent_granted=True)
    assert cross_model_enabled(cfg) is False


def test_both_flags_true_enables() -> None:
    cfg = SecurityConfig(cross_model_verification=True, cross_model_consent_granted=True)
    assert cross_model_enabled(cfg) is True


# ---------------------------------------------------------------------------
# cost_ceiling_exceeded
# ---------------------------------------------------------------------------


def test_zero_ceiling_is_treated_as_exceeded() -> None:
    assert cost_ceiling_exceeded(spent_usd=0.0, max_usd_per_run=0.0) is True


def test_negative_ceiling_is_treated_as_exceeded() -> None:
    assert cost_ceiling_exceeded(spent_usd=0.0, max_usd_per_run=-1.0) is True


def test_under_ceiling_is_not_exceeded() -> None:
    assert cost_ceiling_exceeded(spent_usd=0.5, max_usd_per_run=1.0) is False


def test_at_ceiling_is_exceeded() -> None:
    assert cost_ceiling_exceeded(spent_usd=1.0, max_usd_per_run=1.0) is True


def test_over_ceiling_is_exceeded() -> None:
    assert cost_ceiling_exceeded(spent_usd=1.5, max_usd_per_run=1.0) is True


# ---------------------------------------------------------------------------
# resolve_adversarial_llm_config — family disjointness is the whole point
# ---------------------------------------------------------------------------


def test_no_env_configured_returns_none() -> None:
    assert resolve_adversarial_llm_config("anthropic", env={}) is None


def test_same_family_as_primary_returns_none_never_same_family_fallback() -> None:
    env = {
        "BERB_CROSS_MODEL_PROVIDER": "anthropic",
        "BERB_CROSS_MODEL_MODEL": "claude-haiku-4.5",
        "BERB_CROSS_MODEL_API_KEY_ENV": "ANTHROPIC_API_KEY",
        "ANTHROPIC_API_KEY": "sk-fake-test-key",
    }
    assert resolve_adversarial_llm_config("anthropic", env=env) is None


def test_missing_api_key_env_value_returns_none() -> None:
    env = {
        "BERB_CROSS_MODEL_PROVIDER": "openai",
        "BERB_CROSS_MODEL_MODEL": "gpt-5.5",
        "BERB_CROSS_MODEL_API_KEY_ENV": "OPENAI_API_KEY",
        # OPENAI_API_KEY itself not set
    }
    assert resolve_adversarial_llm_config("anthropic", env=env) is None


def test_missing_api_key_env_name_returns_none() -> None:
    env = {
        "BERB_CROSS_MODEL_PROVIDER": "openai",
        "BERB_CROSS_MODEL_MODEL": "gpt-5.5",
        # BERB_CROSS_MODEL_API_KEY_ENV itself not set
    }
    assert resolve_adversarial_llm_config("anthropic", env=env) is None


def test_missing_model_returns_none() -> None:
    env = {
        "BERB_CROSS_MODEL_PROVIDER": "openai",
        "BERB_CROSS_MODEL_API_KEY_ENV": "OPENAI_API_KEY",
        "OPENAI_API_KEY": "sk-fake-test-key",
    }
    assert resolve_adversarial_llm_config("anthropic", env=env) is None


def test_fully_configured_different_family_resolves() -> None:
    env = {
        "BERB_CROSS_MODEL_PROVIDER": "openai",
        "BERB_CROSS_MODEL_MODEL": "gpt-5.5",
        "BERB_CROSS_MODEL_API_KEY_ENV": "OPENAI_API_KEY",
        "OPENAI_API_KEY": "sk-fake-test-key",
    }
    cfg = resolve_adversarial_llm_config("anthropic", env=env)
    assert cfg is not None
    assert cfg.provider == "openai"
    assert cfg.primary_model == "gpt-5.5"
    assert cfg.api_key_env == "OPENAI_API_KEY"


def test_resolved_config_never_carries_the_key_value_itself() -> None:
    # The returned LlmConfig carries the *name* of the env var, not the
    # secret value — the same indirection Berb's own LlmConfig uses
    # everywhere else.
    env = {
        "BERB_CROSS_MODEL_PROVIDER": "openai",
        "BERB_CROSS_MODEL_MODEL": "gpt-5.5",
        "BERB_CROSS_MODEL_API_KEY_ENV": "OPENAI_API_KEY",
        "OPENAI_API_KEY": "sk-fake-test-key-should-not-leak",
    }
    cfg = resolve_adversarial_llm_config("anthropic", env=env)
    assert cfg is not None
    assert cfg.api_key == ""
    assert "sk-fake-test-key-should-not-leak" not in str(cfg)


def test_openrouter_style_primary_provider_id() -> None:
    # primary_provider can be a full "family/model" id (as OpenRouter
    # sometimes uses) -- family comparison still works.
    env = {
        "BERB_CROSS_MODEL_PROVIDER": "anthropic",
        "BERB_CROSS_MODEL_MODEL": "claude-haiku-4.5",
        "BERB_CROSS_MODEL_API_KEY_ENV": "ANTHROPIC_API_KEY",
        "ANTHROPIC_API_KEY": "sk-fake",
    }
    assert resolve_adversarial_llm_config("openai/gpt-5.5", env=env) is not None
    assert resolve_adversarial_llm_config("anthropic/claude-sonnet-4.6", env=env) is None


# ---------------------------------------------------------------------------
# build_cross_model_payload — allowlist, not denylist
# ---------------------------------------------------------------------------


def test_payload_includes_only_allowlisted_metadata_keys() -> None:
    payload = build_cross_model_payload(
        claim_text="Accuracy improved by 34%.",
        anchor_quotes=("some quote",),
        reference_metadata={
            "cite_key": "he2016deep",
            "title": "Deep Residual Learning",
            "api_key": "sk-should-never-appear",
            "file_path": "/etc/passwd",
        },
    )
    assert set(payload["reference_metadata"]) == {"cite_key", "title"}
    assert "api_key" not in payload["reference_metadata"]
    assert "file_path" not in payload["reference_metadata"]


def test_payload_caps_claim_text_length() -> None:
    from berb.llm.cross_model import MAX_CLAIM_CHARS

    huge = "x" * (MAX_CLAIM_CHARS + 500)
    payload = build_cross_model_payload(claim_text=huge)
    assert len(payload["claim_text"]) == MAX_CLAIM_CHARS


def test_payload_caps_number_and_length_of_quotes() -> None:
    from berb.llm.cross_model import MAX_QUOTE_CHARS, MAX_QUOTES

    quotes = tuple(f"quote number {i} " + "x" * 1000 for i in range(MAX_QUOTES + 5))
    payload = build_cross_model_payload(claim_text="c", anchor_quotes=quotes)
    assert len(payload["anchor_quotes"]) == MAX_QUOTES
    assert all(len(q) <= MAX_QUOTE_CHARS for q in payload["anchor_quotes"])


def test_payload_never_includes_arbitrary_keys() -> None:
    payload = build_cross_model_payload(claim_text="c")
    assert set(payload.keys()) == {"claim_text", "anchor_quotes", "reference_metadata"}


def test_payload_empty_metadata_is_fine() -> None:
    payload = build_cross_model_payload(claim_text="c", reference_metadata=None)
    assert payload["reference_metadata"] == {}


# ---------------------------------------------------------------------------
# disclosure_record
# ---------------------------------------------------------------------------


def test_disclosure_record_shape() -> None:
    record = disclosure_record("openai", "gpt-5.5", "claim text + quoted source spans")
    assert record == {
        "provider": "openai",
        "model": "gpt-5.5",
        "content_class": "claim text + quoted source spans",
    }


# ---------------------------------------------------------------------------
# parse_cross_model_verdict — typed, never eval/exec
# ---------------------------------------------------------------------------


def test_parse_valid_verdict() -> None:
    raw = '{"verdict": "disagrees", "rationale": "the quote does not match"}'
    result = parse_cross_model_verdict("openai", "gpt-5.5", raw)
    assert result is not None
    assert result.verdict is CrossModelVerdict.DISAGREES
    assert result.rationale == "the quote does not match"
    assert result.provider == "openai"
    assert result.model == "gpt-5.5"


def test_parse_verdict_case_insensitive() -> None:
    raw = '{"verdict": "AGREES"}'
    result = parse_cross_model_verdict("openai", "gpt-5.5", raw)
    assert result is not None
    assert result.verdict is CrossModelVerdict.AGREES


def test_parse_malformed_json_returns_none() -> None:
    assert parse_cross_model_verdict("openai", "gpt-5.5", "not json at all") is None


def test_parse_non_dict_json_returns_none() -> None:
    assert parse_cross_model_verdict("openai", "gpt-5.5", "[1, 2, 3]") is None
    assert parse_cross_model_verdict("openai", "gpt-5.5", '"just a string"') is None


def test_parse_unknown_verdict_value_returns_none() -> None:
    raw = '{"verdict": "definitely maybe"}'
    assert parse_cross_model_verdict("openai", "gpt-5.5", raw) is None


def test_parse_missing_verdict_key_returns_none() -> None:
    assert parse_cross_model_verdict("openai", "gpt-5.5", '{"rationale": "x"}') is None


def test_parse_never_executes_code() -> None:
    # A classic eval/exec-injection payload must be treated as inert data,
    # never executed -- this parser is JSON-only.
    payload = "{\"verdict\": \"__import__('os').system('echo pwned')\"}"
    assert parse_cross_model_verdict("openai", "gpt-5.5", payload) is None


def test_parse_caps_rationale_length() -> None:
    raw = '{"verdict": "uncertain", "rationale": "' + ("x" * 1000) + '"}'
    result = parse_cross_model_verdict("openai", "gpt-5.5", raw)
    assert result is not None
    assert len(result.rationale) == 500


# ---------------------------------------------------------------------------
# cross_model_unverified_finding — never reads as verified
# ---------------------------------------------------------------------------


def test_unverified_finding_shape() -> None:
    finding = cross_model_unverified_finding("he2016deep", "no adversarial provider configured")
    assert finding.check is CheckId.CROSS_MODEL_UNVERIFIED
    assert finding.severity is Severity.INFO
    assert finding.locator == "he2016deep"
    assert "unavailable" in finding.message
