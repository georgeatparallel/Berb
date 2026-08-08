"""Provider-side prompt caching helpers for LLM calls.

Builds Anthropic-style `cache_control` breakpoints (`build_cached_system_blocks`)
so a stable, reused prefix (e.g. a paper shared across a 5-persona review
round) is billed at ~0.1x on repeat reads instead of full input price.
`model_needs_explicit_cache_control` gates this per-model, since some
providers cache automatically without a breakpoint. Wired into
`LLMClient.chat(cached_prefix=...)` and
`AnthropicAdapter.chat_completion(cached_prefix=...)`.

A prior local in-process response cache (`PromptCache`/`CacheWarmer`/
`cached_completion`) lived in this module and was removed
(tasks/todo.md open question): it only memoized byte-identical repeat
calls, a case that doesn't occur anywhere in the live pipeline, and had
zero callers outside its own tests.
"""

# Author: Georgios-Chrysovalantis Chatzivantsidis

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Provider-Specific Cache Control
#
# This targets Anthropic's Messages API `cache_control` mechanic (also
# honored by OpenRouter for Claude/Qwen, which route to Anthropic-shaped
# backends). It requires content as an array of blocks — a bare
# `cache_control` key alongside a string `content` field, which an earlier
# version of this module produced, is not part of any provider's wire
# format and would be silently ignored.
# ─────────────────────────────────────────────────────────────────────────────

# Per OpenRouter's prompt-caching docs: these need an explicit cache_control
# breakpoint to get provider-side caching. OpenAI, DeepSeek, Grok, Groq,
# Z.AI and Gemini 2.5 cache automatically and don't need (or use) the field.
_EXPLICIT_CACHE_MODEL_MARKERS = ("claude", "anthropic", "qwen")

_VALID_TTLS = ("5m", "1h")

# Below Sonnet's 1,024-token floor (Opus is 512, Haiku is 4,096) a cached
# block silently never caches. ~4 chars/token is a conservative estimate.
_DEFAULT_MIN_CACHEABLE_CHARS = 4000


def model_needs_explicit_cache_control(model: str) -> bool:
    """Whether `model` needs an explicit `cache_control` breakpoint to get
    provider-side prompt caching, vs. providers that cache automatically.
    """
    m = model.lower()
    return any(marker in m for marker in _EXPLICIT_CACHE_MODEL_MARKERS)


def build_cached_system_blocks(
    cached_prefix: str,
    system: str | None,
    *,
    ttl: str = "5m",
    min_chars: int = _DEFAULT_MIN_CACHEABLE_CHARS,
) -> list[dict[str, Any]] | None:
    """Build system content blocks with a cache breakpoint on `cached_prefix`.

    `cached_prefix` should be the STABLE part of the prompt (e.g. shared
    document text reused across several calls); it becomes the first block
    with a `cache_control` breakpoint. `system` (if given) is the volatile,
    call-specific part and is appended as a second, uncached block — it
    comes after the breakpoint so it never has to match for the cached
    prefix to hit.

    Returns None when `cached_prefix` is shorter than `min_chars` — too
    short to clear the provider's minimum-cacheable-tokens floor, so
    callers should fall back to plain string concatenation rather than pay
    the cache-write premium (1.25x for 5m, 2x for 1h) for a block that will
    never register a cache hit.
    """
    if ttl not in _VALID_TTLS:
        raise ValueError(f"cache ttl must be one of {_VALID_TTLS}, got {ttl!r}")
    if len(cached_prefix) < min_chars:
        return None

    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": cached_prefix,
            "cache_control": {"type": "ephemeral", "ttl": ttl},
        }
    ]
    if system:
        blocks.append({"type": "text", "text": system})
    return blocks
