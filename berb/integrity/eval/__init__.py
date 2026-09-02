"""Hidden Consistent Evaluation (HCE) for Berb integrity.

This package provides evaluation capabilities that are kept separate from
the agent-visible pipeline to prevent gaming:
- ``hidden_eval`` — AIRA2-style three-way criteria split

``finding_reproduction`` (a known-finding reproduction harness) was
deleted 2026-09-01 as part of tasks/ars_integration_plan.md W7 — its
"reproduction" was a ``random.random()`` coin flip, not real execution,
and it measured something unrelated to what W7 actually needed. See
``tests/fixtures/seeded_defects.py`` for the seeded-defect corpus W7
built instead, and ``.reachability-allowlist``'s D-04 entry for the
closure note.
"""
