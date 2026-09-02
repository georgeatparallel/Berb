"""Research-direction state and the discovery loop that drives it.

`berb/pipeline/iterative.py` iterates stages 16-22 — it improves *how a result
is written up*. Nothing iterated on *which result to pursue*. That is what
:mod:`berb.research.discovery_loop` does, over the epistemic state tracked by
:mod:`berb.research.world_model`.

Both modules are pipeline-agnostic on purpose: the loop takes an executor
callable and never imports `berb.pipeline`. The pipeline-facing executor that
re-runs the stage 7-15 slice lives in `berb/pipeline/discovery.py`.
"""

from __future__ import annotations

__all__: list[str] = []
