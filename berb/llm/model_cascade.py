"""Sequential model cascading: try a cheap model, escalate only if it is not good enough.

Restored 2026-09-02 from commit ``9d026a1``, which deleted this module together
with ``model_router.py`` as an unused duplicate pair. ``model_cascade.py`` was
the superset of the two; only it came back, and it came back trimmed. What was
dropped and why:

* **The in-process response cache.** It memoised byte-identical repeat calls —
  exactly the mechanism that was removed from ``prompt_cache.py`` for having no
  such calls anywhere in the live pipeline. Re-introducing it here would have
  quietly undone that decision and added a second cache layer beside the wired
  provider-side one.
* **``MODEL_COSTS`` and ``cost_saved_estimate``.** The cost table duplicated
  ``berb/llm/pricing.py`` and was read by nothing; the savings figure was never
  computed, so ``get_stats()["estimated_savings"]`` reported ``0.0`` as though
  it were a measurement. Real spend is recorded by ``llm/cost_tracker.py``.
* **The async ``chat``.** It awaited ``base_client.chat(...)``, but every client
  in this repo is synchronous. The cascade now matches the seam it wraps.

**The cascade is only as good as its evaluator.** :meth:`CascadingLLMClient
._default_evaluator` is a heuristic, not a judge: score it too harshly and every
call escalates (no saving, extra latency); too leniently and quality drops
silently. That is why cascading is off by default and why :meth:`get_stats`
reports the per-step exit distribution — that distribution is the measurement
that tells you whether the evaluator is calibrated for your workload.

Usage:
    config = CascadeConfig(
        cascade=[
            CascadeStep("deepseek/deepseek-v3.2", min_score=0.80),
            CascadeStep("anthropic/claude-sonnet-4.6", min_score=0.0),
        ],
    )
    client = CascadingLLMClient(base_client=llm_client, config=config)
    response = client.chat(messages)
"""

# Author: Georgios-Chrysovalantis Chatzivantsidis

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "CascadeConfig",
    "CascadeStep",
    "CascadingLLMClient",
    "get_cascade_for_stage",
]


@dataclass(frozen=True)
class CascadeStep:
    """One rung of the cascade.

    Attributes:
        model: Model id to try at this rung.
        min_score: Accept this rung's response when the evaluator scores it at
            least this high. The last rung should use ``0.0`` — it is the
            "always accept" backstop, without which a low score at the end
            falls through to the fallback model or an error.
        max_tokens: Per-rung token cap; ``None`` uses the client's default.
        temperature: Per-rung sampling temperature.
    """

    model: str
    min_score: float
    max_tokens: int | None = None
    temperature: float = 0.7


@dataclass(frozen=True)
class CascadeConfig:
    """Configuration for model cascading."""

    cascade: tuple[CascadeStep, ...] = ()
    quick_eval_enabled: bool = True

    # Used only when every rung failed or was rejected.
    fallback_model: str | None = None


class CascadingLLMClient:
    """Wraps a client and walks a cascade of models, cheapest first.

    Exposes the same ``chat``/``config`` seam the pipeline uses, so it can wrap
    an :class:`~berb.llm.client.LLMClient`, a ``MultiProviderLLMClient`` or a
    :class:`~berb.llm.smart_client.SmartLLMClient` interchangeably. The
    per-rung ``model`` is passed explicitly and therefore outranks any routing
    the wrapped client would otherwise do.
    """

    def __init__(
        self,
        base_client: Any,
        config: CascadeConfig,
        quality_evaluator: Callable[[Any, list[dict[str, Any]]], float] | None = None,
    ) -> None:
        """Build a cascading client.

        Args:
            base_client: The client to delegate each rung's call to.
            config: The cascade to walk.
            quality_evaluator: ``(response, messages) -> score in [0, 1]``.
                Defaults to :meth:`_default_evaluator`. Supply your own when
                you have a task-specific notion of "good enough" — the default
                only detects generic failure shapes.

        Raises:
            ValueError: The cascade is empty. An empty cascade would make
                every call fall straight through to the fallback model or to
                an error, which is never what the caller meant.
        """
        if not config.cascade:
            raise ValueError("CascadeConfig.cascade is empty; nothing to try")

        self._base_client = base_client
        self._config = config
        self._evaluator = quality_evaluator or self._default_evaluator

        # A threading.Lock, not asyncio.Lock: this object may be built outside
        # any event loop and used from several stage threads, and an
        # asyncio.Lock binds to the loop that created it.
        self._stats_lock = threading.Lock()
        self._total_requests = 0
        self._cascade_exits: dict[int, int] = {}

    @property
    def config(self) -> Any:
        """The wrapped client's LLM config, for callers that reach through."""
        return self._base_client.config

    @property
    def cascade_config(self) -> CascadeConfig:
        """This wrapper's own cascade configuration."""
        return self._config

    def chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> Any:
        """Send a chat request down the cascade and return the first acceptable response.

        Args:
            messages: Message dicts, as for ``LLMClient.chat``.
            **kwargs: Passed to the base client on every rung. A ``model``
                here is dropped — naming one model contradicts asking for a
                cascade, and silently honouring it would make the cascade a
                no-op.

        Returns:
            The response from the first rung whose score met its threshold; if
            none did, the last response received; if no rung returned at all,
            the fallback model's response.

        Raises:
            RuntimeError: Every rung failed and no fallback succeeded.
        """
        kwargs.pop("model", None)

        with self._stats_lock:
            self._total_requests += 1

        last_response: Any | None = None
        last_error: Exception | None = None

        for step_idx, step in enumerate(self._config.cascade):
            try:
                response = self._base_client.chat(
                    messages,
                    model=step.model,
                    max_tokens=step.max_tokens,
                    temperature=step.temperature,
                    **kwargs,
                )
            except Exception as exc:  # noqa: BLE001 — try the next rung
                logger.warning("Cascade step %d (%s) failed: %s", step_idx + 1, step.model, exc)
                last_error = exc
                continue

            if not self._config.quick_eval_enabled:
                self._record_exit(step_idx)
                return response

            score = self._evaluator(response, messages)
            if score >= step.min_score:
                logger.info(
                    "Cascade exit at step %d: %s (score=%.2f >= %.2f)",
                    step_idx + 1,
                    step.model,
                    score,
                    step.min_score,
                )
                self._record_exit(step_idx)
                return response

            logger.debug(
                "Cascade continue: %s scored %.2f < %.2f",
                step.model,
                score,
                step.min_score,
            )
            last_response = response

        # Every rung answered but none cleared its bar: the last (most capable)
        # answer is still the best one we have.
        if last_response is not None:
            logger.warning("All cascade steps below threshold; returning the last response")
            return last_response

        if self._config.fallback_model is not None:
            logger.warning(
                "All cascade steps failed; trying fallback model: %s",
                self._config.fallback_model,
            )
            try:
                return self._base_client.chat(messages, model=self._config.fallback_model, **kwargs)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"All cascade steps and fallback model "
                    f"({self._config.fallback_model}) failed. Last error: {exc}"
                ) from exc

        raise RuntimeError(f"All cascade steps failed: {last_error}")

    def get_stats(self) -> dict[str, Any]:
        """Return the exit distribution — the measurement that calibrates the cascade.

        ``cascade_exits`` maps a zero-based step index to how often the cascade
        accepted at that step. Everything exiting at step 0 means the evaluator
        is too lenient (or the cheap model really is enough); nothing exiting
        before the last step means it is too harsh and you are paying for the
        cheap calls on top of the expensive ones.
        """
        with self._stats_lock:
            exits = dict(self._cascade_exits)
            total_requests = self._total_requests

        accepted = sum(exits.values())
        avg_exit = sum(idx * count for idx, count in exits.items()) / accepted if accepted else 0.0
        return {
            "total_requests": total_requests,
            "cascade_exits": exits,
            "average_exit_step": avg_exit,
        }

    def _record_exit(self, step_idx: int) -> None:
        with self._stats_lock:
            self._cascade_exits[step_idx] = self._cascade_exits.get(step_idx, 0) + 1

    def _default_evaluator(self, response: Any, messages: list[dict[str, Any]]) -> float:
        """Heuristic quality score in [0, 1]. Detects failure shapes, not correctness.

        Scores five independent axes:

        1. Hard refusal — an outright refusal is useless regardless of length.
        2. Soft hedging — penalised, not disqualifying.
        3. Completeness — suspiciously short relative to the prompt.
        4. Truncation — ends mid-sentence, so probably cut off.
        5. Structure — JSON delivered when JSON was asked for.

        It cannot tell a confident wrong answer from a right one. Supply a
        task-specific evaluator wherever that distinction is what decides
        whether to escalate.
        """
        from berb.llm.vision import content_to_text

        content = getattr(response, "content", "")
        if not content:
            return 0.0

        score = 1.0
        stripped = content.strip()
        lowered = stripped.lower()

        hard_refusals = (
            "i cannot",
            "i'm unable to",
            "i am not able to",
            "i'm not able to",
            "as an ai language model, i cannot",
            "i must decline",
            "i won't be able to",
        )
        if any(p in lowered for p in hard_refusals):
            return 0.05

        soft_hedges = (
            "as an ai",
            "i don't have access",
            "i don't have the ability",
            "i'm just an ai",
        )
        score -= min(0.3, sum(1 for p in soft_hedges if p in lowered) * 0.15)

        # content_to_text, not len(m["content"]): multimodal content is a part
        # list and an image contributes no prompt characters.
        prompt_chars = sum(len(content_to_text(m.get("content", ""))) for m in messages)
        min_expected = max(20, prompt_chars * 0.05)
        if len(stripped) < min_expected:
            shortfall = 1.0 - len(stripped) / min_expected
            score -= min(0.4, shortfall * 0.5)

        if stripped[-1] not in {".", "!", "?", "}", "]", "`", '"', "'", ":", ";"}:
            score -= 0.15

        json_requested = any(
            "json" in content_to_text(m.get("content", "")).lower() for m in messages
        )
        if json_requested:
            if stripped.startswith(("{", "[")):
                try:
                    json.loads(stripped)
                    score += 0.1
                except ValueError:
                    score -= 0.2
            else:
                score -= 0.15

        return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Stage-shaped cascade recommendations
# ---------------------------------------------------------------------------
#
# These name concrete models, so they are a starting point to copy into config,
# not a default the pipeline applies on its own: a model listed here need not
# exist for the provider a given deployment uses. The wired path builds its
# cascade from `config.cascade.steps` only.

_SIMPLE_STAGES = frozenset({"TOPIC_INIT", "LITERATURE_COLLECT", "KNOWLEDGE_EXTRACT"})
_REASONING_STAGES = frozenset({"HYPOTHESIS_GEN", "RESEARCH_DECISION", "RESULT_ANALYSIS"})
_WRITING_STAGES = frozenset({"PAPER_OUTLINE", "PAPER_DRAFT"})
_CRITICAL_STAGES = frozenset({"PEER_REVIEW", "QUALITY_GATE", "CITATION_VERIFY"})


def get_cascade_for_stage(stage_name: str) -> CascadeConfig:
    """Return a suggested cascade shape for a pipeline stage.

    Args:
        stage_name: Stage name, case-insensitive.

    Returns:
        A :class:`CascadeConfig`. Critical stages get a single premium rung —
        cascading a peer review to save cents is a bad trade.
    """
    name = stage_name.upper()

    if name in _SIMPLE_STAGES:
        return CascadeConfig(
            cascade=(
                CascadeStep("deepseek/deepseek-v3.2", min_score=0.70),
                CascadeStep("anthropic/claude-sonnet-4.6", min_score=0.0),
            )
        )
    if name in _REASONING_STAGES:
        return CascadeConfig(
            cascade=(
                CascadeStep("anthropic/claude-sonnet-4.6", min_score=0.80),
                CascadeStep("anthropic/claude-opus-4.6", min_score=0.0),
            )
        )
    if name in _WRITING_STAGES:
        return CascadeConfig(
            cascade=(
                CascadeStep("deepseek/deepseek-v3.2", min_score=0.75),
                CascadeStep("anthropic/claude-sonnet-4.6", min_score=0.0),
            )
        )
    if name in _CRITICAL_STAGES:
        return CascadeConfig(cascade=(CascadeStep("anthropic/claude-sonnet-4.6", min_score=0.0),))

    return CascadeConfig(
        cascade=(
            CascadeStep("deepseek/deepseek-v3.2", min_score=0.75),
            CascadeStep("anthropic/claude-sonnet-4.6", min_score=0.0),
        )
    )
