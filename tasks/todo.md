# Token Consumption Reduction Plan

Audit date: 2026-08-06. Target: Berb's own LLM spend during `berb run`.

Ranked by (impact ÷ effort). Steps 1, 3, 6 are capping bugs — cheap and they cut
worst-case hard. Step 2 is where sustained savings live. Steps 4–5 only pay off
after step 2 ships.

---

## Verified findings

- **`berb/llm/prompt_cache.py` is 100% dead code.** Every reference to
  `PromptCache` (:50), `CacheWarmer` (:242), `get_cache_control_header` (:305),
  `apply_cache_control_to_messages` (:326), and `cached_completion` (:364)
  lives inside that file — the module docstring example plus the definitions.
  Zero external callers. Berb has never sent a `cache_control` breakpoint.
- **`ProviderRouting` is defined but never passed.** `provider_routing` defaults
  to `None` at `berb/llm/openrouter_adapter.py:3767`, so all traffic runs on
  OpenRouter's default cross-provider load balancing.
- **Docs claim caching works.** `docs/HOW_BERB_WORKS.md:376` shows
  `cache_control = {"type": "ephemeral"}` as live behavior. It is not.
  (honesty-pass candidate)

### Corrections to CLAUDE.md

- `prompts.default.yaml` is **22.5 KB, not ~150 KB**, and is loaded **once** at
  `berb/prompts.py:107`, rendering only the requested key. It is not a per-call
  cost. The real static bulk is hardcoded in `prompts.py`: `_DEFAULT_STAGES`
  ~12.9k tok, `_DEFAULT_BLOCKS` ~9k tok.
- The Area Chair makes **no LLM call** — `berb/review/ensemble.py:387` is pure
  Python arithmetic. It is a 5-model ensemble, not "5 + Area Chair".

---

## 1. Cap the code-repair context

Biggest single sink. Est. **200–560k tokens for one stage** worst case.

`berb/pipeline/stage_impls/_code_generation.py:734` rebuilds `all_files_ctx`
from every generated file, uncapped, *inside* the
`while repair_attempt < max_repair` loop (`max_repair = 5`, :97), once per file.

`files[fname]` mutates at :744, so the context differs every attempt — **this
sink is cache-hostile by construction. Caching cannot fix it. Only capping can.**

- [x] Send only the failing file + its direct imports, not all files —
      `_build_repair_context()` in `_code_generation.py:734`
- [x] If sibling context is needed, order it `[other files — stable] + [target file — volatile]` so the stable half becomes cacheable in step 2 — same helper
- [x] Add a hard char/token ceiling on `all_files_ctx` with explicit truncation logging — `_REPAIR_CTX_CHAR_LIMIT = 24_000` chars, drop-siblings-then-truncate-target, both paths logged
- [x] Check the compounding loops: `code_agent.py:66` `hard_validation_max_repairs=4`,
      `code_agent.py:69` `exec_fix_max_iterations=3` — found `_repair_critical_issues`
      (called from the `hard_validation_max_repairs` loop) had the identical
      uncapped-`_format_files(files)` pattern and is on the *primary* CodeAgent
      path (`_code_generation.py:635`), not a fallback. Fixed with
      `CodeAgent._format_files_scoped()`. Left two other `_format_files()`
      call sites alone: `_fix_runtime_error` (:1083) already tries targeted
      single-file repair first and only falls back to full-file on parse
      failure; `_phase4_review` (:1338) is a holistic code review, not a
      targeted repair, so it legitimately needs every file.

## 2. Wire `berb/llm/prompt_cache.py`

Where sustained savings live. Cache reads bill at **0.1× input**.

Targets in value order:

- [x] **Review ensemble** — `berb/review/ensemble.py` fanned the same
      paper to 5 personas with the paper text embedded in each persona's
      (varying) user message, so nothing was byte-identical across calls.
      Restructured: paper text now goes through `chat(cached_prefix=...,
      cache_ttl="1h")`, landing in a `system` block **before** the
      persona-specific system prompt, so the breakpoint covers the
      identical part regardless of which persona is calling. Also fixed
      #3 below in the same edit (they touched the same lines).
- [x] **Static prompt blocks** — `writing_structure` (4,296 ch) +
      `academic_style_guide` (3,103 ch) + `narrative_writing_rules` (2,137 ch)
      resent on every writing call. ~2.4k tok combined; clears Sonnet's 1,024
      minimum together, but **not individually** — cache as one block.
      Wired in `_write_paper_sections()` (`_paper_writing.py`): the 3
      sequential calls (title/abstract/intro, method/experiments,
      results/discussion) already shared one `system` string built once —
      `academic_style_guide`, `narrative_writing_rules`,
      `anti_hedging_rules`, and `anti_repetition_rules` were instead being
      re-embedded verbatim into each call's *user* message (same bytes,
      3x). Folded all four into `system` and dropped the per-call
      duplicates; `system` is now passed as `cached_prefix` to
      `_chat_with_prompt` for all 3 calls instead of as the plain system
      message, so it's identical across the round and gets the
      breakpoint. This also required threading `cached_prefix`/`cache_ttl`
      through `_chat_with_prompt` itself — see Retry layers below, same edit.
- [x] **Retry layers** — `_prompt_helpers.py:139/166` wraps `client.py:694`
      (`max_retries=3`) wraps model-fallback at `client.py:617`. One logical call
      can resend an identical 20k-token prompt 6+ times. Retries on cached
      content bill at 0.1×. Wired — added `cached_prefix`/`cache_ttl` params
      to `_chat_with_prompt()`, threaded straight to `llm.chat(...)`; the
      retry loop already reused the same `messages` object per attempt, so
      any caller passing `cached_prefix` (e.g. the writing stage above) now
      gets cache benefit on retries automatically, no extra plumbing.

Mechanics — now actually implemented in `berb/llm/prompt_cache.py`
(`model_needs_explicit_cache_control`, `build_cached_system_blocks`) and
wired through `LLMClient.chat(cached_prefix=..., cache_ttl=...)` →
`_apply_cached_prefix` → `_raw_call`, plus `AnthropicAdapter.chat_completion`
for the direct-Anthropic path and `MultiProviderLLMClient`/`ACPClient` for
signature compatibility:

- [x] Anthropic and Qwen require **explicit** `cache_control`; OpenAI, DeepSeek,
      Grok, Groq, Z.AI and Gemini 2.5 cache automatically. Berb's OpenRouter path
      sends nothing today, so Claude-routed calls get zero benefit. —
      `model_needs_explicit_cache_control()` gates on this; non-matching
      models get the stable text plainly prepended (no cache_control field)
      since it's a no-op for them anyway.
- [x] Order must be `tools → system → messages`, stable content first, breakpoint
      on the **last unchanging block**. Max 4 breakpoints, 20-block lookback. —
      `build_cached_system_blocks` puts `cached_prefix` first with the
      breakpoint, volatile `system` text after. Berb doesn't send `tools`
      today so that segment doesn't apply.
- [ ] Never put a breakpoint on content carrying timestamps, run IDs, or rotating
      state — the prefix hash changes and you get 0% hits while still paying writes.
      Mechanically enforced only where `cached_prefix` is actually passed
      (ensemble.py's paper text is stable per round) — this is a caller
      discipline note for whoever wires the next two targets above, not
      something the plumbing itself can verify.
- [x] Minimum cacheable: 512 tok (Opus 5) / 1,024 (Sonnet 5) / 4,096 (Haiku 4.5).
      Below the floor it silently does not cache — verify via
      `cache_read_input_tokens` in the response, not by assumption. —
      `build_cached_system_blocks(min_chars=4000)` (~4 chars/token, so this
      clears Sonnet's floor; conservative for Opus, not quite Haiku's 4,096
      tok — fine since the explicit-cache-control path is Claude/Qwen only,
      and Haiku wasn't the target here). **The "verify, don't assume" part
      is still on you** — I have no live API access in this environment;
      run a real review round and check `response.cached_tokens` /
      OpenRouter's dashboard before trusting this saves anything.
- [x] Teach cost accounting to read `cached_tokens` / `cache_discount` so the
      savings signal is visible. **Correction to this plan**: `cost_tracker.py`
      turned out to be dead code too — `CostTracker.record_from_llm_response`
      has zero callers anywhere in `berb/`; live cost accounting happens via
      `PricingTable.compute_cost()` called directly from ~14 other sites, this
      class is never instantiated in the real pipeline. Teaching it to read
      cached tokens would've been teaching nothing. Instead added
      `LLMResponse.cached_tokens: int`, populated in
      `_parse_chat_completions_response` (reads OpenRouter/OpenAI's
      `prompt_tokens_details.cached_tokens`) and normalized from
      `AnthropicAdapter`'s `cache_read_input_tokens` — any caller can now
      read `response.cached_tokens` directly. Wiring `CostTracker` itself
      into the live pipeline is a separate, larger gap outside this plan's
      scope.

## 3. Remove duplicated persona prompt

Trivial, pure waste. ~150 tok × 5 personas × every round.

- [x] `berb/review/ensemble.py:297` embeds `persona.system_prompt` in the user
      message, then :330 passes it again as `system=`. Drop one. — Dropped
      from the user message (`system=` is the correct home for it); done in
      the same edit as section 2's ensemble restructuring.

## 4. Pin the OpenRouter provider

Config only. **Only matters after step 2** — pinning a cache you never populate
is a no-op.

- [x] Pass `provider_routing` at the call sites — **correction to this
      plan**: `openrouter_adapter.py:3767`'s `provider_routing` param
      belongs to `OpenRouterProvider.complete()`, which turned out to be
      dead code too (only instantiated in its own file and in tests, zero
      real callers — same category as the `prompt_cache.py` and
      `cost_tracker.py` findings above). The live OpenRouter call path is
      `LLMClient._raw_call()` in `client.py`, which built its request body
      with no `provider` field at all. Added `LLMConfig.provider_routing:
      dict | None`, populated in `from_rc_config()` from two new
      `RCConfig.llm` fields (`provider_routing_order`,
      `provider_routing_allow_fallbacks`; both default to today's
      behavior — empty order = field omitted entirely), and applied to the
      request body in `_raw_call()`'s chat_completions branch. Reused the
      existing `ProviderRouting` dataclass's `{order, allow_fallbacks}`
      shape (OpenRouter's own wire format) without importing the dead
      class itself. Documented in `configs/config.berb.example.yaml`.
- [x] Use `order` + `allow_fallbacks=False` — `provider_routing_allow_fallbacks`
      config field, default `True` (matches OpenRouter's own default, so
      unset = no behavior change); set `false` to get `ROUTING_EXACT`-equivalent
      strict pinning.
- [x] Rationale: caches live on the upstream provider's infra. OpenRouter
      load-balances across Anthropic/Bedrock/Vertex by default; each reroute is a
      cold cache **plus** a repeated 1.25× write premium — documented in both
      `config.py`'s field comment and the example config.

## 5. Batch API

50% discount, **stacks with prompt caching**. Available on both OpenRouter and
Anthropic direct. Larger refactor, so last.

- [ ] Evaluate the 5-persona review fan-out as the first batch unit — it is
      already async, non-interactive, and naturally parallel
- [ ] Confirm latency budget: most batches finish <1h, SLA is 24h

## 6. Cap the experiment-data leak

- [ ] `_prompt_helpers.py:223` injects `experiment_summary.json` untruncated
- [ ] `_execution.py:1128` writes up to 50,000 chars of stdout into that summary
- [ ] Net: ~12.5k-token leak into downstream analysis/writing prompts

---

## Not worth doing

- **Literature handling** — `_literature.py:706` already screens on
  title + abstract with keyword pre-filtering. No full PDF texts reach prompts.
- **`prompts.default.yaml` size** — loaded once, not per call. See corrections above.
- **Splitting to per-provider API keys** — the cache multipliers are identical
  either way. Direct keys buy a deterministic backend and no reseller margin, but
  cost you OpenRouter's failover. Do step 4 first and measure; revisit only if
  pinned hit rates still disappoint.

---

## Open questions

- [ ] Two audits (cost machinery in `berb/llm/`, provider-side features) were
      still running when this was written — fold in anything they surface
- [ ] Is `PromptCache` (local response cache) worth wiring at all, or is
      provider-side caching sufficient? Local cache only helps on exact repeat
      calls, which may be rare outside retries.

## Review

<!-- Fill in after implementation: what changed, measured before/after token
     counts per stage, and any findings that contradicted this plan. -->
