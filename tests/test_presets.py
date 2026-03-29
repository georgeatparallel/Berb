"""Unit tests for Berb preset system.

Tests for PipelinePreset, PresetRegistry, and domain-specific presets.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import pytest
from pathlib import Path

from berb.presets import (
    PipelinePreset,
    PresetRegistry,
    get_preset,
    list_presets,
    get_registry,
    load_preset,
)


class TestPipelinePreset:
    """Test PipelinePreset model."""

    def test_create_minimal_preset(self):
        """Test creating preset with minimal fields."""
        preset = PipelinePreset(
            name="test-preset",
            description="Test preset",
        )
        assert preset.name == "test-preset"
        assert preset.description == "Test preset"
        assert preset.max_budget_usd == 1.50  # default
        assert preset.experiment_mode == "docker"  # default

    def test_create_full_preset(self):
        """Test creating preset with all fields."""
        preset = PipelinePreset(
            name="ml-test",
            description="ML test preset",
            tags=["ml", "test"],
            primary_sources=["semantic_scholar", "arxiv"],
            primary_model="claude-sonnet-4-6",
            experiment_mode="docker",
            paper_format="neurips",
            min_literature_papers=50,
            max_budget_usd=2.00,
        )
        assert preset.tags == ["ml", "test"]
        assert "arxiv" in preset.primary_sources
        assert preset.primary_model == "claude-sonnet-4-6"
        assert preset.max_budget_usd == 2.00

    def test_preset_validation(self):
        """Test preset validation."""
        # Invalid experiment mode should fail
        with pytest.raises(Exception):
            PipelinePreset(
                name="invalid",
                description="Invalid preset",
                experiment_mode="invalid_mode",
            )

    def test_enabled_stages_default(self):
        """Test default enabled stages."""
        preset = PipelinePreset(
            name="test",
            description="Test",
        )
        # Should have all 23 stages by default
        assert len(preset.enabled_stages) == 23
        assert 1 in preset.enabled_stages
        assert 23 in preset.enabled_stages

    def test_stage_overrides(self):
        """Test stage overrides."""
        preset = PipelinePreset(
            name="test",
            description="Test",
            stage_overrides={
                8: {"reasoning_method": "multi_perspective"},
                9: {"require_ablation": True},
            },
        )
        assert 8 in preset.stage_overrides
        assert preset.stage_overrides[8]["reasoning_method"] == "multi_perspective"


class TestPresetRegistry:
    """Test PresetRegistry."""

    def test_create_registry(self):
        """Test creating registry."""
        catalog_path = Path(__file__).parent.parent / "presets" / "catalog"
        registry = PresetRegistry(catalog_path)
        assert len(registry.presets) > 0

    def test_get_preset(self):
        """Test getting preset by name."""
        preset = get_preset("ml-conference")
        assert preset is not None
        assert preset.name == "ml-conference"
        assert "machine-learning" in preset.tags

    def test_get_nonexistent_preset(self):
        """Test getting nonexistent preset."""
        preset = get_preset("nonexistent-preset-xyz")
        assert preset is None

    def test_list_presets(self):
        """Test listing all presets."""
        presets = list_presets()
        assert len(presets) >= 14  # We created 14 presets
        assert "ml-conference" in presets
        assert "biomedical" in presets
        assert "physics" in presets

    def test_load_preset(self):
        """Test loading preset."""
        preset = load_preset("nlp")
        assert preset is not None
        assert preset.paper_format == "acl"
        assert preset.citation_style == "author-year"


class TestDomainPresets:
    """Test specific domain presets."""

    def test_ml_conference_preset(self):
        """Test ML conference preset."""
        preset = get_preset("ml-conference")
        assert preset is not None
        assert preset.paper_format == "neurips"
        assert preset.experiment_mode == "docker"
        assert "pytorch" in preset.experiment_frameworks
        assert 8 in preset.stage_overrides
        assert preset.stage_overrides[8].get("reasoning_method") == "multi_perspective"

    def test_biomedical_preset(self):
        """Test biomedical preset."""
        preset = get_preset("biomedical")
        assert preset is not None
        assert preset.paper_format == "nature"
        assert "pubmed" in preset.primary_sources
        assert preset.min_literature_papers == 60
        assert preset.cost_optimization == "quality-first"

    def test_nlp_preset(self):
        """Test NLP preset."""
        preset = get_preset("nlp")
        assert preset is not None
        assert preset.paper_format == "acl"
        assert preset.citation_style == "author-year"
        assert preset.max_pages == 8
        assert "transformers" in preset.experiment_frameworks

    def test_computer_vision_preset(self):
        """Test computer vision preset."""
        preset = get_preset("computer-vision")
        assert preset is not None
        assert preset.paper_format == "cvpr"
        assert preset.max_budget_usd == 2.50
        assert preset.stage_overrides[12].get("gpu_required") is True

    def test_physics_preset(self):
        """Test physics preset."""
        preset = get_preset("physics")
        assert preset is not None
        assert preset.paper_format == "revtex"
        assert "sympy" in preset.experiment_frameworks
        assert preset.stage_overrides[12].get("self_correcting_enabled") is True

    def test_social_sciences_preset(self):
        """Test social sciences preset."""
        preset = get_preset("social-sciences")
        assert preset is not None
        assert preset.paper_format == "apa"
        assert preset.citation_style == "author-year"
        assert preset.max_pages == 30

    def test_systematic_review_preset(self):
        """Test systematic review preset."""
        preset = get_preset("systematic-review")
        assert preset is not None
        assert preset.paper_format == "prisma"
        assert preset.min_literature_papers == 100
        # Should skip experiment stages
        assert 8 not in preset.enabled_stages
        assert 12 not in preset.enabled_stages

    def test_engineering_preset(self):
        """Test engineering preset."""
        preset = get_preset("engineering")
        assert preset is not None
        assert preset.paper_format == "acm"
        assert "docker_compose" in preset.experiment_frameworks
        assert "load_testing" in preset.validation_methods

    def test_humanities_preset(self):
        """Test humanities preset."""
        preset = get_preset("humanities")
        assert preset is not None
        assert preset.paper_format == "chicago"
        assert preset.citation_style == "footnote"
        assert preset.stage_overrides[7].get("reasoning_method") == "dialectical"

    def test_eu_sovereign_preset(self):
        """Test EU sovereign preset."""
        preset = get_preset("eu-sovereign")
        assert preset is not None
        assert preset.primary_model == "mistral-large-3"
        assert preset.stage_overrides[1].get("gdpr_compliance") is True

    def test_rapid_draft_preset(self):
        """Test rapid draft preset."""
        preset = get_preset("rapid-draft")
        assert preset is not None
        assert preset.paper_format == "markdown"
        assert preset.max_budget_usd == 0.15
        assert preset.cost_optimization == "aggressive"
        # Should skip many stages
        assert len(preset.enabled_stages) < 15

    def test_budget_preset(self):
        """Test budget preset."""
        preset = get_preset("budget")
        assert preset is not None
        assert preset.max_budget_usd == 0.25
        assert preset.primary_model == "deepseek-v3.2"

    def test_max_quality_preset(self):
        """Test max quality preset."""
        preset = get_preset("max-quality")
        assert preset is not None
        assert preset.max_budget_usd == 5.00
        assert preset.primary_model == "claude-opus-4-6"
        assert preset.min_literature_papers == 80

    def test_research_groundedin_preset(self):
        """Test research-grounded preset."""
        preset = get_preset("research-grounded")
        assert preset is not None
        assert preset.min_literature_papers == 200
        assert preset.primary_model == "sonar-pro"


class TestPresetValidation:
    """Test preset validation."""

    def test_validate_valid_preset(self):
        """Test validating valid preset."""
        registry = get_registry()
        is_valid, errors = registry.validate_preset("ml-conference")
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_nonexistent_preset(self):
        """Test validating nonexistent preset."""
        registry = get_registry()
        is_valid, errors = registry.validate_preset("nonexistent")
        assert is_valid is False
        assert "not found" in errors[0]

    def test_validate_budget(self):
        """Test budget validation."""
        preset = PipelinePreset(
            name="test",
            description="Test",
            max_budget_usd=-10,
        )
        registry = get_registry()
        registry.presets["test"] = preset
        is_valid, errors = registry.validate_preset("test")
        assert is_valid is False
        assert "Budget cannot be negative" in errors


class TestPresetMerging:
    """Test preset merging with user config."""

    def test_merge_with_user_config(self):
        """Test merging preset with user config."""
        registry = get_registry()
        preset = get_preset("ml-conference")
        
        user_config = {
            "max_budget_usd": 3.00,
            "primary_model": "gpt-4o",
        }
        
        merged = registry.merge_with_config(preset, user_config)
        
        # User config should override
        assert merged["max_budget_usd"] == 3.00
        assert merged["primary_model"] == "gpt-4o"
        # Preset values should remain
        assert merged["paper_format"] == "neurips"

    def test_deep_merge(self):
        """Test deep merge of nested dicts."""
        registry = get_registry()
        preset = get_preset("ml-conference")
        
        user_config = {
            "stage_overrides": {
                8: {"num_hypotheses": 10},
            },
        }
        
        merged = registry.merge_with_config(preset, user_config)
        
        # User override should apply
        assert merged["stage_overrides"][8]["num_hypotheses"] == 10
        # Other stage overrides should remain
        assert "require_ablation" in merged["stage_overrides"][9]


class TestCustomPresets:
    """Test custom preset creation."""

    def test_create_custom_preset(self):
        """Test creating custom preset."""
        registry = get_registry()
        
        custom = registry.create_custom_preset(
            name="my-custom-ml",
            base_preset="ml-conference",
            description="My custom ML preset",
            max_budget_usd=2.00,
        )
        
        assert custom is not None
        assert custom.name == "my-custom-ml"
        assert custom.max_budget_usd == 2.00
        assert custom.paper_format == "neurips"  # From base

    def test_create_custom_from_scratch(self):
        """Test creating custom preset from scratch."""
        registry = get_registry()
        
        custom = registry.create_custom_preset(
            name="scratch-preset",
            description="Created from scratch",
            primary_model="gpt-4o",
            max_budget_usd=1.00,
        )
        
        assert custom is not None
        assert custom.name == "scratch-preset"
        assert custom.primary_model == "gpt-4o"
