"""PresetRegistry — load and list PipelinePreset configurations from YAML catalog.

YAML files live in ``berb/presets/catalog/``.  Each file must define at least
``name`` and ``description``; all other fields fall back to PipelinePreset
defaults.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import yaml

from berb.presets.base import PipelinePreset

logger = logging.getLogger(__name__)

_CATALOG_DIR = Path(__file__).parent / "catalog"


class PresetRegistry:
    """Load and cache presets from the YAML catalog directory."""

    def __init__(self, catalog_dir: Path | None = None) -> None:
        self._catalog_dir = catalog_dir or _CATALOG_DIR
        self._cache: dict[str, PipelinePreset] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, name: str) -> PipelinePreset:
        """Load a preset by name (case-insensitive, ignores hyphens/underscores).

        Args:
            name: Preset name, e.g. ``"ml-conference"`` or ``"nutrition_bioactive"``.

        Returns:
            Loaded and validated :class:`PipelinePreset`.

        Raises:
            KeyError: If no matching preset YAML is found.
        """
        key = _normalise(name)
        if key in self._cache:
            return self._cache[key]

        for path in self._iter_yaml_paths():
            if _normalise(path.stem) == key:
                preset = self._load_path(path)
                self._cache[key] = preset
                return preset

        available = ", ".join(self.list_names())
        raise KeyError(
            f"Preset {name!r} not found. Available presets: {available}"
        )

    def list_names(self) -> list[str]:
        """Return sorted list of available preset names (from YAML ``name`` field)."""
        names: list[str] = []
        for path in self._iter_yaml_paths():
            try:
                raw = _read_yaml(path)
                names.append(raw.get("name", path.stem))
            except Exception:
                names.append(path.stem)
        return sorted(names)

    def list_all(self) -> list[PipelinePreset]:
        """Load and return all available presets."""
        presets: list[PipelinePreset] = []
        for path in self._iter_yaml_paths():
            try:
                presets.append(self._load_path(path))
            except Exception as exc:
                logger.warning("Failed to load preset %s: %s", path, exc)
        return sorted(presets, key=lambda p: p.name)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _iter_yaml_paths(self) -> Iterator[Path]:
        if not self._catalog_dir.is_dir():
            return
        yield from sorted(self._catalog_dir.glob("*.yaml"))
        yield from sorted(self._catalog_dir.glob("*.yml"))

    def _load_path(self, path: Path) -> PipelinePreset:
        raw = _read_yaml(path)
        try:
            preset = PipelinePreset(**raw)
        except Exception as exc:
            raise ValueError(f"Invalid preset YAML at {path}: {exc}") from exc
        return preset


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_default_registry = PresetRegistry()


def load_preset(name: str) -> PipelinePreset:
    """Load a preset by name from the default catalog.

    Args:
        name: Preset name or slug (e.g. ``"ml-conference"``).

    Returns:
        Validated :class:`PipelinePreset`.
    """
    return _default_registry.load(name)


def list_presets() -> list[str]:
    """Return sorted list of available preset names from the default catalog."""
    return _default_registry.list_names()


# ---------------------------------------------------------------------------
# Private utilities
# ---------------------------------------------------------------------------


def _normalise(s: str) -> str:
    """Lowercase and strip hyphens/underscores for loose name matching."""
    return s.lower().replace("-", "").replace("_", "").replace(" ", "")


def _read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping, got {type(data).__name__}")
    return data
