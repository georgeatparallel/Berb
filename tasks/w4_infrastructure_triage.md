# W4 — Infrastructure

**Wave:** W4 of `tasks/dead_code_wiring_plan.md`
**Scope:** 20 modules / 6,426 loc — the infrastructure remainder after W1–W3, excluding the
public-API group and the two items held by instruction.
**Disposal default:** PARK, 90-day horizon (2026-12-01), two strikes.

---

## 1. Two DELETEs, both genuine, neither self-contained

### 1.1 `llm/extended_router.py` (587) — a stub occupying a seam the wired router owns

`_create_provider` (`:466-478`) returns `_MockProvider(model)` with the comment *"In production,
this would create the actual provider instance"*. It never created a provider. CLAUDE.md already
documented this. The wired router is `llm/nadirclaw_router.py`, used by `llm/smart_client.py`.

**Zero AST-level importers anywhere in `berb/`.** The apparent references across `berb/reasoning/`
turned out to be *module-docstring usage examples* and trailing comments — text, not imports —
recommending a class that does not work. All eight files were corrected rather than left pointing
at a deleted stub.

The genuine consumer was in tests: `tests/test_reasoning_integration.py:18` imported it for
`MagicMock(spec=ExtendedNadirClawRouter)`. My first importer scan covered `berb/` but not `tests/`
and missed it — the kind of gap that turns a clean deletion into a broken build.

The spec was replaced with a plain `MagicMock()`. Worth being straight about the trade: `spec=`
constrains a mock to the real class's attribute surface, so removing it does weaken the test. But
the class it specced against was itself a stub returning `_MockProvider`, so the guarantee was
illusory — it proved nothing about `nadirclaw_router`. The fixture defines every attribute the 13
tests exercise, and all 13 still pass. **Re-speccing against the wired router is the worthwhile
follow-up**, and is a larger change than this deletion; it is noted in the test.

### 1.2 `pipeline/asyncio_utils.py` (144) — reimplemented inline by the runner

It offers `run_sync_stage` (wrap a sync stage via `asyncio.to_thread`) and `gather_stages` (run a
DAG level concurrently). `pipeline/runner.py` does both itself: `asyncio.gather()` at `:359`, and
`:494-497` is a function whose docstring reads *"Run a stage via asyncio.to_thread, write
checkpoint and heartbeat on success."*

Same package, same job, one of them wired. Zero importers in `berb/`; its only consumer was
`tests/test_asyncio_utils.py`, removed with it.

**It was in the mypy ratchet** (`pyproject.toml:232`), so someone had type-hardened it as
load-bearing. Its entry is removed because the module is gone — not to excuse a failure, which is
what the ratchet's own comment prohibits.

---

## 2. Two things in the ratchet but not wired

`asyncio_utils` and `writing/reporting_guidelines.py` were both in the mypy ratchet with no
importer. They are not the same case and are not disposed of the same way:

- `asyncio_utils` duplicates wired code → deleted.
- `reporting_guidelines` is **W8.1 of the ARS integration plan, written 2026-09-01** — one day
  before this triage (`tasks/ars_integration_plan.md:432`). It joined the ratchet immediately by
  that plan's convention. Recent, deliberate, roadmapped work whose consumer has not landed yet.
  → PARK, un-park trigger "ARS W8 lands its consumer".

Being in the ratchet is evidence of *intent*, not of *use*. It cuts both ways.

---

## 3. PARK — 18 modules / 5,695 loc

| Group | LOC | Note |
|---|---:|---|
| `literature.{grey_search, searxng_client, full_text, specification, trends}` | 2,168 | CLAUDE.md already documents grey_search and SearXNG as unwired. `docker-compose.searxng.yml` exists in-repo but nothing imports the client |
| `reasoner_bridge`, `mnemo_bridge` | 1,000 | External-integration bridges with no in-repo consumer |
| `llm.{batch_api, speculative_gen, eval_dataset, structured_outputs, adaptive_temp}` | 1,690 | Cost/robustness machinery; `smart_client` + `nadirclaw_router` own the wired path. `speculative_gen` is tied to the parked `speculative_router` — at most one should ever be un-parked |
| `pipeline.dependency_context` | 380 | Cross-task context injection; Stage 10 does not consume it |
| `domains.experiment_schema` | 258 | The wired domain adapters do not use it |
| `writing.reporting_guidelines` | 135 | ARS W8, see §2 |
| `voice.commands` | 49 | Pairs with the parked `voice/synthesizer` |
| `integrity.eval`, `experiment.evaluators` | 15 | Package shims for parked contents |

---

## 4. End state: the surface is fully accounted for

**13 modules / 10,977 loc remain, and every one is blocked on a decision, not on analysis:**

| Held | Modules | LOC | Blocked on |
|---|---:|---:|---|
| Exported public API | 10 | 9,455 | The `__all__` question — `tasks/w2_untested_triage.md` §4 |
| `experiment/code_agent` | 1 | 836 | User instruction; deletion also requires removing `config.experiment.cli_agent` |
| WIRE-pending | 2 | 686 | `split_policy` needs a `SplitEvidence` producer; `react_agent` waits on the candidate-generator work |

Nothing is left un-triaged. Ratchet: 17,403 → **10,977**.
