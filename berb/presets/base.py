"""PipelinePreset — complete configuration bundle for a research domain.

Each preset captures every tuneable parameter needed to run Berb for a
specific discipline: literature sources, model routing, experiment setup,
paper format, quality thresholds, and per-stage overrides.

Presets are defined as YAML files in ``berb/presets/catalog/`` and
loaded at runtime via :class:`~berb.presets.registry.PresetRegistry`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PipelinePreset(BaseModel):
    """Complete configuration preset for a research domain."""

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Literature search
    # ------------------------------------------------------------------
    primary_sources: list[str] = Field(
        default=["semantic_scholar", "openalex"],
        description="Academic database backends to query.",
    )
    search_engines: list[str] = Field(
        default=["google_scholar"],
        description="SearXNG engine overrides for web search.",
    )
    grey_sources: list[str] = Field(
        default_factory=list,
        description="Grey literature sources (preprints, reports, github).",
    )
    full_text_access: list[str] = Field(
        default=["arxiv"],
        description="Sources where full-text is freely available.",
    )

    # ------------------------------------------------------------------
    # Model routing
    # ------------------------------------------------------------------
    primary_model: str = "claude-sonnet-4-6"
    fallback_models: list[str] = Field(default_factory=list)
    reasoning_model: str = "claude-opus-4-6"
    budget_model: str = "claude-haiku-4-5-20251001"

    # ------------------------------------------------------------------
    # Pipeline behaviour
    # ------------------------------------------------------------------
    enabled_stages: list[int] = Field(
        default=list(range(1, 24)),
        description="Which of the 23 stages to execute (default: all).",
    )
    stage_overrides: dict[int, dict] = Field(
        default_factory=dict,
        description="Per-stage config overrides keyed by stage number.",
    )

    # ------------------------------------------------------------------
    # Experiment execution
    # ------------------------------------------------------------------
    experiment_mode: Literal[
        "simulated", "sandbox", "docker", "ssh_remote", "colab_drive"
    ] = "docker"
    experiment_frameworks: list[str] = Field(default_factory=list)
    validation_methods: list[str] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Paper writing
    # ------------------------------------------------------------------
    paper_format: str = "neurips"
    target_venue: str | None = None
    max_pages: int = 10
    style_profile: str | None = "auto"
    citation_style: Literal["numeric", "author-year", "footnote"] = "numeric"

    # ------------------------------------------------------------------
    # Quality thresholds
    # ------------------------------------------------------------------
    min_literature_papers: int = 30
    min_quality_score: float = 7.5
    min_novelty_score: float = 6.5

    # ------------------------------------------------------------------
    # Budget
    # ------------------------------------------------------------------
    max_budget_usd: float = 1.50
    cost_optimization: Literal["aggressive", "balanced", "quality-first"] = "balanced"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """One-line human-readable summary."""
        tag_str = ", ".join(self.tags) if self.tags else "—"
        return (
            f"{self.name}: {self.description} "
            f"[tags: {tag_str}] "
            f"[budget: ${self.max_budget_usd:.2f}] "
            f"[format: {self.paper_format}]"
        )
