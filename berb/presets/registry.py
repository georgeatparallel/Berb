"""Preset registry for domain-specific pipeline configurations.

This module provides loading, validation, and management of research domain
presets that configure the entire Berb pipeline for specific disciplines.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from berb.presets.base import PipelinePreset

logger = logging.getLogger(__name__)


class PresetRegistry:
    """Registry for pipeline presets.

    This class handles:
    - Loading presets from YAML files
    - Validating preset configurations
    - Providing preset listings and details
    - Merging presets with runtime configuration

    Attributes:
        catalog_path: Path to preset catalog directory
        presets: Loaded preset dictionary
    """

    DEFAULT_CATALOG_PATH = Path(__file__).parent / "catalog"

    def __init__(self, catalog_path: Path | str | None = None):
        """Initialize preset registry.

        Args:
            catalog_path: Path to preset catalog directory
        """
        self.catalog_path = Path(catalog_path) if catalog_path else self.DEFAULT_CATALOG_PATH
        self.presets: dict[str, PipelinePreset] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all presets from catalog directory."""
        if not self.catalog_path.exists():
            logger.warning(f"Preset catalog not found at {self.catalog_path}")
            return

        yaml_files = list(self.catalog_path.glob("*.yaml")) + list(
            self.catalog_path.glob("*.yml")
        )

        for yaml_file in yaml_files:
            try:
                preset = self._load_preset_file(yaml_file)
                if preset:
                    self.presets[preset.name] = preset
                    logger.debug(f"Loaded preset: {preset.name}")
            except Exception as e:
                logger.error(f"Failed to load preset {yaml_file.name}: {e}")

        logger.info(f"Loaded {len(self.presets)} presets from catalog")

    def _load_preset_file(self, yaml_file: Path) -> PipelinePreset | None:
        """Load a single preset from YAML file.

        Args:
            yaml_file: Path to YAML file

        Returns:
            Loaded PipelinePreset or None
        """
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                logger.warning(f"Empty preset file: {yaml_file}")
                return None

            return PipelinePreset(**data)
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error in {yaml_file}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load preset {yaml_file}: {e}")
            return None

    def get_preset(self, name: str) -> PipelinePreset | None:
        """Get preset by name.

        Args:
            name: Preset name

        Returns:
            PipelinePreset or None if not found
        """
        return self.presets.get(name)

    def get_preset_or_default(self, name: str | None = None) -> PipelinePreset:
        """Get preset by name or return default.

        Args:
            name: Preset name (optional)

        Returns:
            PipelinePreset (defaults to ml-conference if available)
        """
        if name:
            preset = self.get_preset(name)
            if preset:
                return preset
            logger.warning(f"Preset '{name}' not found, using default")

        # Try ml-conference as default
        default = self.get_preset("ml-conference")
        if default:
            return default

        # Return minimal default
        return PipelinePreset(
            name="default",
            description="Default pipeline configuration",
        )

    def list_presets(self) -> list[str]:
        """List all available preset names.

        Returns:
            List of preset names
        """
        return sorted(self.presets.keys())

    def list_presets_with_description(self) -> list[tuple[str, str]]:
        """List all presets with descriptions.

        Returns:
            List of (name, description) tuples
        """
        return [(name, preset.description) for name, preset in sorted(self.presets.items())]

    def get_preset_tags(self, name: str) -> list[str]:
        """Get tags for a preset.

        Args:
            name: Preset name

        Returns:
            List of tags
        """
        preset = self.get_preset(name)
        return preset.tags if preset else []

    def find_presets_by_tag(self, tag: str) -> list[str]:
        """Find presets with a specific tag.

        Args:
            tag: Tag to search for

        Returns:
            List of matching preset names
        """
        return [
            name
            for name, preset in self.presets.items()
            if tag in preset.tags
        ]

    def validate_preset(self, name: str) -> tuple[bool, list[str]]:
        """Validate a preset configuration.

        Args:
            name: Preset name

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        preset = self.get_preset(name)
        if not preset:
            return False, [f"Preset '{name}' not found"]

        errors = []

        # Validate stage numbers
        for stage_num in preset.enabled_stages:
            if not 1 <= stage_num <= 23:
                errors.append(f"Invalid stage number: {stage_num}")

        # Validate stage overrides
        for stage_num, overrides in preset.stage_overrides.items():
            if not 1 <= stage_num <= 23:
                errors.append(f"Invalid override stage number: {stage_num}")
            if not isinstance(overrides, dict):
                errors.append(f"Stage {stage_num} overrides must be a dictionary")

        # Validate budget
        if preset.max_budget_usd < 0:
            errors.append("Budget cannot be negative")

        # Validate thresholds
        if not 0 <= preset.min_quality_score <= 10:
            errors.append("Quality score must be between 0 and 10")
        if not 0 <= preset.min_novelty_score <= 10:
            errors.append("Novelty score must be between 0 and 10")

        # Validate experiment mode
        valid_modes = {"simulated", "sandbox", "docker", "ssh_remote", "colab_drive"}
        if preset.experiment_mode not in valid_modes:
            errors.append(f"Invalid experiment mode: {preset.experiment_mode}")

        return len(errors) == 0, errors

    def merge_with_config(
        self,
        preset: PipelinePreset,
        user_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge preset with user configuration.

        User config takes precedence over preset values.

        Args:
            preset: Pipeline preset
            user_config: User-provided configuration

        Returns:
            Merged configuration dictionary
        """
        # Convert preset to dict
        preset_dict = preset.model_dump(mode="json", exclude_none=True)

        # Deep merge
        merged = self._deep_merge(preset_dict, user_config)

        logger.debug(f"Merged preset '{preset.name}' with user config")
        return merged

    def _deep_merge(
        self,
        base: dict[str, Any],
        override: dict[str, Any],
    ) -> dict[str, Any]:
        """Deep merge two dictionaries.

        Args:
            base: Base dictionary
            override: Dictionary to merge on top

        Returns:
            Merged dictionary
        """
        result = base.copy()

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def export_preset(self, name: str, output_path: Path | str) -> bool:
        """Export preset to YAML file.

        Args:
            name: Preset name
            output_path: Output file path

        Returns:
            True if successful
        """
        preset = self.get_preset(name)
        if not preset:
            logger.error(f"Preset '{name}' not found")
            return False

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    preset.model_dump(mode="json", exclude_none=True),
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
            logger.info(f"Exported preset '{name}' to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to export preset: {e}")
            return False

    def create_custom_preset(
        self,
        name: str,
        base_preset: str | None = None,
        **overrides: Any,
    ) -> PipelinePreset | None:
        """Create a custom preset based on an existing one.

        Args:
            name: New preset name
            base_preset: Base preset name (optional)
            **overrides: Configuration overrides

        Returns:
            New PipelinePreset or None if failed
        """
        try:
            if base_preset:
                base = self.get_preset(base_preset)
                if not base:
                    logger.error(f"Base preset '{base_preset}' not found")
                    return None
                # Create from base with overrides
                data = base.model_dump(mode="json", exclude_none=True)
                data = self._deep_merge(data, overrides)
                data["name"] = name
                data["description"] = overrides.get(
                    "description", f"Custom preset based on {base_preset}"
                )
            else:
                # Create from scratch
                data = {
                    "name": name,
                    "description": overrides.get("description", "Custom preset"),
                    **overrides,
                }

            preset = PipelinePreset(**data)
            logger.info(f"Created custom preset '{name}'")
            return preset
        except Exception as e:
            logger.error(f"Failed to create custom preset: {e}")
            return None


# Global registry instance
_registry: PresetRegistry | None = None


def get_registry(catalog_path: Path | str | None = None) -> PresetRegistry:
    """Get or create preset registry.

    Args:
        catalog_path: Optional custom catalog path

    Returns:
        PresetRegistry instance
    """
    global _registry
    if _registry is None or catalog_path is not None:
        _registry = PresetRegistry(catalog_path)
    return _registry


def get_preset(name: str) -> PipelinePreset | None:
    """Get preset by name from global registry.

    Args:
        name: Preset name

    Returns:
        PipelinePreset or None
    """
    return get_registry().get_preset(name)


def list_presets() -> list[str]:
    """List all available presets.

    Returns:
        List of preset names
    """
    return get_registry().list_presets()


def load_preset(name: str) -> PipelinePreset | None:
    """Load preset by name.

    Args:
        name: Preset name

    Returns:
        PipelinePreset or None
    """
    return get_preset(name)
