"""Cross-model verification policy (tasks/ars_integration_plan.md W5).

Berb self-checks integrity judgments with the same model family that
generated the text under review — same training distribution, same blind
spots, by construction. This module is the *policy* layer for using a
second, different-family provider as an adversarial check: consent
gating, provider-family disjointness, a minimal-payload allowlist, a cost
ceiling, and a typed (never eval/exec'd) verdict parse.

This module resolves *which* adversarial provider/model to use
(``resolve_adversarial_llm_config``, pure and injectable, never touches a
real secret value) and builds the request payload, cost ceiling, and
verdict parsing around it. Only ``build_adversarial_client_config`` reads
a real API key value, and only to build the one-shot config an
``LLMClient`` is constructed from immediately — the caller
(``berb/pipeline/stage_impls/_export.py``) never stores or logs that
result.

Design note: the plan originally pointed at extending
``berb/llm/extended_router.py``'s ``ExtendedRouter``. That module was
deleted on 2026-09-02 (W4) precisely because it was never live
infrastructure: its ``_create_provider`` returned a ``_MockProvider``
("In production, this would create the actual provider instance") and
nothing under ``berb/pipeline/`` imported it. The real,
reachable constructor is ``berb.llm.client.LLMClient(LLMConfig)``, which
needs ``berb.llm.client.LLMConfig`` (the client's own runtime config
type — resolved rate-limit fields, real API key, etc.), a distinct
dataclass from ``berb.config.LlmConfig``'s declarative YAML-section type
that this module's public resolver returns. ``build_adversarial_client_config``
is the bridge between the two, built from environment variables the same
way the rest of Berb's optional-provider switches already work (see
``berb/literature/search.py``'s Perplexity top-up for the same
env-var-gated-optional-feature shape).

Security (tasks/ars_integration_plan.md W5, "largest new attack surface"):

1. Off by default, two independent flags — see
   ``berb.config.SecurityConfig``. Enabling ``cross_model_verification``
   alone is a configuration intent, not consent.
2. Disclosure — ``disclosure_record()`` returns exactly what a caller
   should log/persist to the run artifact before the first cross-model
   call: provider, model, content class. Never emitted implicitly.
3. Minimal payload — ``build_cross_model_payload()`` is an allowlist
   (claim text, anchor quotes, reference metadata only), not a denylist.
   Never the full manuscript, file paths, config, environment, or keys.
4. Cost ceiling — ``cost_ceiling_exceeded()`` is a pure comparison against
   ``SecurityConfig.cross_model_max_usd_per_run``; a caller must check it
   before every call and downgrade to ``CROSS_MODEL_UNVERIFIED`` rather
   than continuing to spend.
5. Untrusted both directions — outgoing claim/quote text should be wrapped
   with ``berb.utils.sanitize.wrap_untrusted`` by the caller before
   embedding in a prompt (this module doesn't build prompts, so it can't
   do this itself). Incoming: ``parse_cross_model_verdict`` only ever
   parses JSON into a typed ``CrossModelResult`` — never ``eval``/``exec``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from berb.config import LlmConfig as DeclaredLlmConfig
from berb.config import SecurityConfig
from berb.integrity.findings import CheckId, Finding, Severity
from berb.llm import PROVIDER_PRESETS
from berb.llm.client import LLMConfig

# Untrusted, paper/claim-derived text bounds — small on purpose. A cross-
# model call's whole point is a bounded adversarial check, not a second
# full manuscript upload.
MAX_CLAIM_CHARS: Final = 2000
MAX_QUOTE_CHARS: Final = 500
MAX_QUOTES: Final = 10
MAX_METADATA_VALUE_CHARS: Final = 200

_ALLOWED_METADATA_KEYS: Final = frozenset({"cite_key", "title", "year", "venue", "doi"})

_ENV_PROVIDER: Final = "BERB_CROSS_MODEL_PROVIDER"
_ENV_MODEL: Final = "BERB_CROSS_MODEL_MODEL"
_ENV_API_KEY_ENV: Final = "BERB_CROSS_MODEL_API_KEY_ENV"


def provider_family(provider_or_model_id: str) -> str:
    """Normalize a provider name or an OpenRouter-style ``family/model`` id
    down to its family: ``"anthropic"``, ``"openai"``, ``"deepseek"``, etc.
    Bare provider names (Berb's ``LlmConfig.provider`` values) already are
    their own family and pass through unchanged (lowercased)."""
    normalized = provider_or_model_id.strip().lower()
    if "/" in normalized:
        return normalized.split("/", 1)[0]
    return normalized


def cross_model_enabled(security: SecurityConfig) -> bool:
    """Both flags must be true. Enabling verification without granting
    consent (or vice versa) is treated as disabled, not as a partial
    feature — see ``SecurityConfig.cross_model_consent_granted``."""
    return bool(security.cross_model_verification and security.cross_model_consent_granted)


def cost_ceiling_exceeded(spent_usd: float, max_usd_per_run: float) -> bool:
    """True if cross-model spend should stop. A ceiling of zero or less
    means no budget was ever granted (``SecurityConfig``'s documented
    default) and is treated as already exceeded — fail closed, not open."""
    if max_usd_per_run <= 0:
        return True
    return spent_usd >= max_usd_per_run


def resolve_adversarial_llm_config(
    primary_provider: str,
    *,
    env: Mapping[str, str] | None = None,
) -> DeclaredLlmConfig | None:
    """Resolve a second provider's ``berb.config.LlmConfig`` (the
    declarative YAML-section type — carries ``api_key_env``, the
    environment variable *name*, never the secret value itself) whose
    family differs from *primary_provider*, read from environment
    variables (``BERB_CROSS_MODEL_PROVIDER`` / ``_MODEL`` /
    ``_API_KEY_ENV``).

    Returns ``None`` — never a same-family fallback — when: no adversarial
    provider is configured, it resolves to the same family as the primary
    provider, or the named API key environment variable isn't actually
    set. The caller MUST treat ``None`` as "cross-model verification is
    unavailable right now" (``CROSS_MODEL_UNVERIFIED``), never retry with
    the primary provider instead.

    ``env`` defaults to ``os.environ``; injectable for testing without
    real environment variables or API keys.

    This value is never resolved into ``berb.llm.client.LLMConfig``
    directly — that type needs the real key, which must never live on an
    object that could end up logged or disclosed. Use
    ``build_adversarial_client_config()`` right at the point an
    ``LLMClient`` is actually constructed.
    """
    source = env if env is not None else os.environ

    provider = source.get(_ENV_PROVIDER, "").strip()
    if not provider:
        return None
    if provider_family(provider) == provider_family(primary_provider):
        return None

    api_key_env = source.get(_ENV_API_KEY_ENV, "").strip()
    if not api_key_env or not source.get(api_key_env, "").strip():
        return None

    model = source.get(_ENV_MODEL, "").strip()
    if not model:
        return None

    return DeclaredLlmConfig(provider=provider, api_key_env=api_key_env, primary_model=model)


def build_adversarial_client_config(
    config: DeclaredLlmConfig,
    *,
    env: Mapping[str, str] | None = None,
) -> LLMConfig | None:
    """Resolve *config* (as returned by ``resolve_adversarial_llm_config``)
    into the ``berb.llm.client.LLMConfig`` that ``LLMClient`` actually
    needs — this is the one place the real API key value is read, and the
    result must be used immediately to construct the client, never stored
    on a field that could be logged or disclosed.

    Returns ``None`` if the named environment variable is no longer set
    (treat identically to ``resolve_adversarial_llm_config`` returning
    ``None``).
    """
    source = env if env is not None else os.environ
    api_key = source.get(config.api_key_env, "").strip()
    if not api_key:
        return None
    base_url = PROVIDER_PRESETS.get(config.provider, {}).get("base_url", "")
    return LLMConfig(
        base_url=base_url,
        api_key=api_key,
        primary_model=config.primary_model,
        provider_name=config.provider,
    )


def build_cross_model_payload(
    *,
    claim_text: str,
    anchor_quotes: Sequence[str] = (),
    reference_metadata: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the exact, allowlisted payload sent to the adversarial
    provider. Every field is capped; any metadata key not in
    ``_ALLOWED_METADATA_KEYS`` is silently dropped rather than passed
    through — this is an allowlist, not a denylist, by construction."""
    metadata = reference_metadata or {}
    return {
        "claim_text": claim_text[:MAX_CLAIM_CHARS],
        "anchor_quotes": [q[:MAX_QUOTE_CHARS] for q in anchor_quotes[:MAX_QUOTES]],
        "reference_metadata": {
            key: str(value)[:MAX_METADATA_VALUE_CHARS]
            for key, value in metadata.items()
            if key in _ALLOWED_METADATA_KEYS
        },
    }


def disclosure_record(provider: str, model: str, content_class: str) -> dict[str, str]:
    """What a caller must log and persist to the run artifact before the
    first cross-model call of a run. A user must be able to answer "what
    left this machine and where did it go" from the run directory alone."""
    return {"provider": provider, "model": model, "content_class": content_class}


class CrossModelVerdict(StrEnum):
    AGREES = "agrees"
    DISAGREES = "disagrees"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class CrossModelResult:
    provider: str
    model: str
    verdict: CrossModelVerdict
    rationale: str


def parse_cross_model_verdict(
    provider: str, model: str, raw_response_text: str
) -> CrossModelResult | None:
    """Typed parse of a cross-model provider's response. JSON-only —
    never ``eval``/``exec`` (see commit 334c7a0 for why that class of bug
    is taken seriously in this codebase). Returns ``None`` on any
    malformed input rather than raising; a caller should treat ``None``
    the same as an unavailable adversarial provider."""
    try:
        data = json.loads(raw_response_text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        verdict = CrossModelVerdict(str(data.get("verdict", "")).strip().lower())
    except ValueError:
        return None
    rationale = str(data.get("rationale", ""))[:500]
    return CrossModelResult(provider=provider, model=model, verdict=verdict, rationale=rationale)


def cross_model_unverified_finding(locator: str, reason: str) -> Finding:
    """The explicit, visible result when cross-model verification could
    not run: no adversarial provider configured, consent not granted, or
    the cost ceiling was reached. This must NEVER read as "verified" —
    that is the single most important behavioral property of this
    mechanism (tasks/ars_integration_plan.md W5)."""
    return Finding(
        check=CheckId.CROSS_MODEL_UNVERIFIED,
        severity=Severity.INFO,
        message=f"cross-model verification unavailable: {reason}",
        locator=locator,
    )
