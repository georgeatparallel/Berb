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

- [ ] Send only the failing file + its direct imports, not all files
- [ ] If sibling context is needed, order it `[other files — stable] + [target file — volatile]` so the stable half becomes cacheable in step 2
- [ ] Add a hard char/token ceiling on `all_files_ctx` with explicit truncation logging
- [ ] Check the compounding loops: `code_agent.py:66` `hard_validation_max_repairs=4`, `code_agent.py:69` `exec_fix_max_iterations=3`

## 2. Wire `berb/llm/prompt_cache.py`

Where sustained savings live. Cache reads bill at **0.1× input**.

Targets in value order:

- [ ] **Review ensemble** — `berb/review/ensemble.py:258` fans the same
      12.5k-token paper (50k-char cap at :293) to 5 personas. Identical prefix,
      5× per round, repeated across rounds. Use **1-hour TTL** here (2× write)
      since reuse spans a round.
- [ ] **Static prompt blocks** — `writing_structure` (4,296 ch) +
      `academic_style_guide` (3,103 ch) + `narrative_writing_rules` (2,137 ch)
      resent on every writing call. ~2.4k tok combined; clears Sonnet's 1,024
      minimum together, but **not individually** — cache as one block.
- [ ] **Retry layers** — `_prompt_helpers.py:139/166` wraps `client.py:694`
      (`max_retries=3`) wraps model-fallback at `client.py:617`. One logical call
      can resend an identical 20k-token prompt 6+ times. Retries on cached
      content bill at 0.1×.

Mechanics that decide whether this pays off:

- [ ] Anthropic and Qwen require **explicit** `cache_control`; OpenAI, DeepSeek,
      Grok, Groq, Z.AI and Gemini 2.5 cache automatically. Berb's OpenRouter path
      sends nothing today, so Claude-routed calls get zero benefit.
- [ ] Order must be `tools → system → messages`, stable content first, breakpoint
      on the **last unchanging block**. Max 4 breakpoints, 20-block lookback.
- [ ] Never put a breakpoint on content carrying timestamps, run IDs, or rotating
      state — the prefix hash changes and you get 0% hits while still paying writes.
- [ ] Minimum cacheable: 512 tok (Opus 5) / 1,024 (Sonnet 5) / 4,096 (Haiku 4.5).
      Below the floor it silently does not cache — verify via
      `cache_read_input_tokens` in the response, not by assumption.
- [ ] Teach `berb/llm/cost_tracker.py` to read `cached_tokens` /
      `cache_discount` from `prompt_tokens_details` (OpenRouter returns these),
      otherwise cached tokens bill at full rate in reports and the savings signal
      is invisible.

## 3. Remove duplicated persona prompt

Trivial, pure waste. ~150 tok × 5 personas × every round.

- [ ] `berb/review/ensemble.py:297` embeds `persona.system_prompt` in the user
      message, then :330 passes it again as `system=`. Drop one.

## 4. Pin the OpenRouter provider

Config only. **Only matters after step 2** — pinning a cache you never populate
is a no-op.

- [ ] Pass `provider_routing` at the call sites (currently always `None`,
      `openrouter_adapter.py:3767`)
- [ ] Use `order` + `allow_fallbacks=False` (`ROUTING_EXACT` at :174) — note
      `ROUTING_ANTHROPIC_DIRECT` (:178) sets `allow_fallbacks=True`, which still
      permits silent reroutes
- [ ] Rationale: caches live on the upstream provider's infra. OpenRouter
      load-balances across Anthropic/Bedrock/Vertex by default; each reroute is a
      cold cache **plus** a repeated 1.25× write premium

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
