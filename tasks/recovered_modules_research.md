# Recovered modules — what they are and how to use them

Two deletions from **2026-08-20** were recovered and researched on request. Both were
deliberate removals of unreachable code; nothing has been re-added to the tree. This
records what each does, whether its seam is occupied *today*, and what wiring it would
actually cost.

Recover with `git show <commit>^:<path> > <path>`.

---

## The finding that governs several of these

**`berb/llm/` cannot send an image to any provider.** No `image_url`, no base64 media
block, no `input_image` — nothing, in any adapter. Verified by grep across `berb/llm/`.

At the same time `openrouter_models_data.py` declares **`supports_vision=True` on 173 of
its 335 models**, and that flag is **read by no code anywhere in `berb/`**.

So Berb catalogues 173 vision models and cannot send an image to one of them. Three
separate threads converge here:

- **"Add the 2026 vision models"** — the *data* is largely present already (gpt-5.6,
  gemini-3.6, claude-opus-5, grok-4.20, qwen3.7 generations are all in the catalogue).
  What is missing is the *capability*.
- **`vision/figure_generator.py`** (candidate B) converts figure sketches to plotting
  code "using vision models like Gemini". It cannot run.
- **`plot_verdict.verify_plots`** (wired in W1) expects an `analyze_figure` VLM critic
  that never existed, which is why W1 shipped a pixel-analysis critic instead.

**Recommended order: add image support to `berb/llm/` first.** It is the prerequisite for
the figure work and it makes an already-declared 173-model surface real. Concretely: a
content-parts message shape in `LLMClient`, per-provider encoding in the Anthropic /
OpenAI / OpenRouter adapters, and a guard that refuses an image for a model whose
`supports_vision` is False — which finally gives that flag a reader.

---

## A — `model_router.py` (341) + `model_cascade.py` (511)

Commit `9d026a1`, *"delete dead model_router/model_cascade duplication"*.

**What they do.** Cost cascading: try a cheap model, evaluate the response, escalate to a
premium model only if quality is insufficient. Per-stage cascade configuration, an
evaluator hook, and exit statistics.

**They duplicate each other, not something else.** `model_cascade.py` is a strict superset
of `model_router.py`: identical `CascadeStep`, `CascadeConfig`, `CascadeStats`,
`CascadingLLMClient` and identical methods, plus a response cache (`_generate_cache_key`,
`_get_from_cache`, `_set_cache`, `get_cache_stats`, `clear_cache`). That is what the
deletion commit meant. **Restore at most one — `model_cascade.py`.**

**Is the capability absent today? Yes.** `nadirclaw_router.select_model()` picks a model
once from prompt complexity and never escalates. The parked `llm/speculative_gen.py` runs
cheap and premium *in parallel* and takes the cheap answer if good enough — that buys
latency at the cost of always paying for both. Sequential cascading is the opposite trade
and nothing implements it.

**How to wire it.** `berb/llm/smart_client.py` is the seam: it already chooses between the
plain client and the nadirclaw router on `config.nadirclaw.enabled`. A cascade would sit
at the same level behind its own config flag, wrapping the client the router selects.

**Two cautions.**
1. Its built-in cache overlaps the wired `berb/llm/prompt_cache.py`. Prefer deleting the
   cascade's cache and reusing the wired one, or you re-introduce a second cache layer.
2. The cascade's value rests entirely on `_default_evaluator` — an unreliable quality
   judge makes it escalate always (no saving) or never (quality loss). Wire it with the
   evaluator measured, not assumed.

---

## B — `berb/research/` (2,566) + `berb/vision/` (793)

Commit `24eefec`, *"delete the two genuinely orphaned subsystems"*. This is the larger
recovery (3,442 loc) and the better fit for "a lot of code lines".

| Module | LOC | Seam today |
|---|---:|---|
| `research/discovery_loop.py` | 326 | **Unoccupied.** See below |
| `research/world_model.py` | 283 | Unoccupied; pure typed state, no LLM calls |
| `research/gap_analysis.py` | 860 | Nominally occupied — a wired stage's DoD is *"Topic clusters + >=2 research gaps identified"*, done by prompting |
| `research/idea_scorer.py` | 498 | Adjacent to Stage 1-2 scoping and `literature/novelty.py` |
| `research/open_ended_discovery.py` | 599 | Adjacent to `idea_scorer`; template-free ideation |
| `vision/figure_generator.py` | 793 | Blocked — needs image support (above) |

**The one worth acting on: `discovery_loop` + `world_model` (609 loc together).**

`discovery_loop` wraps **stages 7→15** into a re-entrant cycle, using `world_model` to
track what the system knows, has ruled out, and still needs to explore. The wired
`pipeline/iterative.py` covers **stages 16-22** — paper writing and finalisation, re-run
against review feedback until a quality threshold.

Different halves of the pipeline. **Berb can iterate on how it writes a result, but not on
which result to pursue.** That is a genuine architectural gap, and it is the loop the AI
Research Preference Model paper assumes its agent has: propose, execute, observe, re-decide
direction. It is also the natural home for the RPM work — the candidate-selection decision
belongs inside a research loop, not a writing loop.

`world_model` is the cheap half to validate: pure domain state, no LLM calls, so it is
unit-testable in isolation before any loop is wired.

**The rest need arguments they do not currently have.** `gap_analysis` (860) is a
structured multi-perspective engine for a job a prompt already nominally does — restoring
it means claiming the structured version is better, which should be measured, not
asserted. `idea_scorer` and `open_ended_discovery` overlap each other and Stage 1-2.

---

## Recommendation

1. **Image support in `berb/llm/`** — unblocks the vision catalogue, the figure work and a
   real VLM critic. Gives `supports_vision` its first reader.
2. **`discovery_loop` + `world_model`** (609 loc) — the research-direction loop Berb lacks,
   and the right host for the RPM candidate-selection work.
3. **`model_cascade.py` alone** (511) — a real absent capability, behind a config flag,
   with its cache dropped in favour of the wired `prompt_cache.py`.
4. **Leave the rest.** `model_router.py` is strictly redundant; `gap_analysis`,
   `idea_scorer` and `open_ended_discovery` need a measured case; `figure_generator` is
   blocked until (1).

Restoring anything re-adds unreachable code, so each should land wired, in its own change,
not restored en masse.


---

## Outcome — 2026-09-02

All four follow-ups from this document were executed. What was actually built
diverges from the recommendations above in three places, each recorded here so
the divergence is not silent.

### 1. Image support — done, `berb/llm/vision.py`

Built as recommended: a provider-neutral content-part shape, per-provider
encoders (`to_openai_content` / `to_anthropic_content` / `to_responses_content`),
and `ensure_vision_capable()` as the first reader of `supports_vision`.

**Divergence:** the Responses wire API needed a third encoder. The plan above
said "Anthropic / OpenAI / OpenRouter adapters"; `_messages_to_responses_input`
stringifies content, so a part list sent through it would have been serialised
as a Python repr and shipped as garbage. Caught before it shipped.

Consumers: `experiment/plot_verdict.VLMPlotCritic` is now buildable and is
selected over `PixelPlotCritic` when `experiment.figure_agent.vision_model` is
set. `vision/figure_generator.py` remains unrestored — see §4.

### 2. `discovery_loop` + `world_model` — done, but rewritten not restored

`world_model.py` came back verbatim; it was complete.

**Divergence:** `discovery_loop.py` did **not** come back verbatim, because its
task-execution step was a stub that recorded a dead end per task with the
reason "Task execution not yet wired into pipeline (E2 stub)". Restoring it
as-written would have added 326 lines that spin for `max_cycles` producing
nothing while looking like work. The stub is replaced by an injected
`TaskExecutor`; without one the loop returns `stop_reason="no_executor"`
immediately rather than pretending.

The pipeline-facing executor is new: `berb/pipeline/discovery.py`, which
re-runs stages 7-15 per candidate direction (needing a new `to_stage` bound on
`execute_pipeline`), reads each slice's stage-15 decision back as a
`TaskOutcome`, and promotes the winner's artifacts into the parent run so
stages 16-23 continue normally.

### 3. `model_cascade.py` — done, trimmed

Restored alone, as recommended; `model_router.py` stays deleted.

**Divergence from caution #1.** The plan said "reuse the wired
`prompt_cache.py`" instead of the cascade's own cache. That is not possible:
`prompt_cache.py` is a *provider-side* cache-control helper, a different object
from an in-process response cache. The stronger reading is that this repo had
already built an in-process response cache (`PromptCache`), judged it useless
because byte-identical repeat calls do not occur on the live path, and deleted
it — so the cascade's cache was dropped outright rather than swapped.

Also dropped: `MODEL_COSTS` (duplicated `pricing.py`, read by nothing) and
`cost_saved_estimate` (never computed, so `get_stats()["estimated_savings"]`
reported `0.0` as though it were a measurement). `chat` is synchronous, because
the original awaited a `base_client.chat` that no client in this repo has.

Caution #2 was honoured: cascading is off by default, and `get_stats()` reports
the per-rung exit distribution, which is the measurement that says whether the
evaluator is calibrated.

### 4. Still not restored, deliberately

`model_router.py` (strict subset of the cascade), `berb/research/gap_analysis.py`,
`idea_scorer.py`, `open_ended_discovery.py` (all need a measured case, not an
assertion), and `berb/vision/figure_generator.py`. The last is now *unblocked*
by §1 but was left out of scope: restoring 793 loc of figure-generation on the
same change as four other pieces of work would make none of them reviewable.
It is the natural next candidate.

### 5. Defects found on the way

Fixing the seam the cascade had to plug into surfaced six confirmed defects in
`berb/llm/` and its neighbours; they are inventoried in
`tasks/defect_hunt_plan.md` §5. One of them — `RCConfig` carries no `nadirclaw`
or `token_tracking` field, so `SmartLLMClient` is unreachable from config while
the example config advertises it — is **still open**, because switching that
subsystem on is a product decision rather than a bug fix.
