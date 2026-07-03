"""Skill registry for the Berb autonomous research pipeline.

Loads skills from SKILL.md (agentskills.io) and legacy YAML files,
exposes match/query/export helpers used throughout the pipeline.

Usage:
    from berb.skills.registry import SkillRegistry

    registry = SkillRegistry()
    matched = registry.match("pytorch training cifar", stage=10, top_k=3)
    text = registry.export_for_prompt(matched)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from berb.skills.loader import (
    load_skillmd_from_directory,
    load_skills_from_directory,
)
from berb.skills.matcher import format_skills_for_prompt, match_skills
from berb.skills.schema import Skill

logger = logging.getLogger(__name__)

# Path to the built-in SKILL.md tree shipped with the package.
_BUILTIN_DIR = Path(__file__).parent / "builtin"


class SkillRegistry:
    """Registry for managing and retrieving skills.

    Loads builtins from the ``berb/skills/builtin/`` tree on construction.
    Additional directories can be supplied via *external_dirs* (SKILL.md) or
    *custom_dirs* (legacy YAML).

    Args:
        external_dirs: Extra directories to scan for SKILL.md files.
        custom_dirs: Extra directories to scan for YAML skill files.
        fallback_matching: Pass through to :func:`match_skills` — enables
            description-based matching for skills that have no trigger_keywords.
    """

    def __init__(
        self,
        external_dirs: list[str | Path] | None = None,
        custom_dirs: list[str | Path] | None = None,
        fallback_matching: bool = False,
    ) -> None:
        self._skills: dict[str, Skill] = {}
        self._fallback_matching = fallback_matching

        # Load built-in SKILL.md files
        for skill in load_skillmd_from_directory(_BUILTIN_DIR):
            self._skills[skill.name] = skill

        # Load extra SKILL.md directories
        for d in external_dirs or []:
            for skill in load_skillmd_from_directory(Path(d)):
                self._skills[skill.name] = skill

        # Load extra legacy YAML directories
        for d in custom_dirs or []:
            for skill in load_skills_from_directory(Path(d)):
                self._skills[skill.name] = skill

        logger.debug("SkillRegistry loaded %d skills", len(self._skills))

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def register(self, skill: Skill) -> None:
        """Register (or overwrite) a skill."""
        self._skills[skill.name] = skill
        logger.debug("Registered skill: %s", skill.name)

    def unregister(self, skill_id: str) -> bool:
        """Remove a skill by name/id.

        Returns:
            True if the skill was present and removed, False otherwise.
        """
        if skill_id in self._skills:
            del self._skills[skill_id]
            return True
        return False

    def get(self, skill_id: str) -> Skill | None:
        """Return skill by name/id, or None."""
        return self._skills.get(skill_id)

    # ── Counts / listings ────────────────────────────────────────────────────

    def count(self) -> int:
        """Return the number of registered skills."""
        return len(self._skills)

    def list_by_category(self, category: str) -> list[Skill]:
        """Return all skills in *category*."""
        return [s for s in self._skills.values() if s.category == category]

    def list_by_stage(self, stage: int | str) -> list[Skill]:
        """Return all skills applicable to *stage* (int or stage-name string).

        Skills with an empty ``applicable_stages`` list match every stage.
        """
        from berb.skills.matcher import _resolve_stage

        stage_num = _resolve_stage(stage)
        result = []
        for skill in self._skills.values():
            if not skill.applicable_stages or stage_num in skill.applicable_stages:
                result.append(skill)
        return result

    # ── Matching ─────────────────────────────────────────────────────────────

    def match(
        self,
        context: str,
        stage: int | str = -1,
        top_k: int = 3,
    ) -> list[Skill]:
        """Match skills to *context* and *stage*.

        Delegates to :func:`berb.skills.matcher.match_skills`.
        """
        return match_skills(
            list(self._skills.values()),
            context=context,
            stage=stage,
            top_k=top_k,
            fallback_matching=self._fallback_matching,
        )

    # ── Prompt export ─────────────────────────────────────────────────────────

    def export_for_prompt(
        self,
        skills: list[Skill],
        max_chars: int = 4000,
    ) -> str:
        """Format *skills* as LLM-injectable prompt text."""
        return format_skills_for_prompt(skills, max_chars=max_chars)

    # ── Legacy helpers kept for backward compatibility ─────────────────────

    def get_by_category(self, category: str) -> list[Skill]:
        """Alias for :meth:`list_by_category`."""
        return self.list_by_category(category)

    def get_applicable(self, stage_id: str) -> list[Skill]:
        """Return skills whose *applicable_stages* or trigger-keywords mention *stage_id*."""
        return [
            s for s in self._skills.values()
            if stage_id.lower() in (kw.lower() for kw in s.trigger_keywords)
            or stage_id in (str(n) for n in s.applicable_stages)
        ]

    def list_skills(self) -> list[str]:
        """Return all registered skill names."""
        return list(self._skills.keys())

    def list_categories(self) -> list[str]:
        """Return unique categories across all skills."""
        return list({s.category for s in self._skills.values()})

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full registry."""
        return {name: skill.to_dict() for name, skill in self._skills.items()}


# =============================================================================
# Module-level helpers
# =============================================================================


def apply_skills(
    context: dict[str, Any],
    stage_id: str,
    registry: SkillRegistry | None = None,
) -> dict[str, Any]:
    """Apply prompt injection from all applicable skills for *stage_id*.

    Args:
        context: Current pipeline context dict.
        stage_id: Stage name string (e.g. ``"code_generation"``).
        registry: Registry to use; a default one is created if None.

    Returns:
        Context dict (unchanged — skills inject into prompts, not context).
    """
    if registry is None:
        registry = SkillRegistry()

    applicable = registry.get_applicable(stage_id)
    logger.debug("apply_skills: %d skills for stage %s", len(applicable), stage_id)
    return context


def export_skills_for_metaclaw(output_dir: Path) -> None:
    """Export all builtin skills as SKILL.md files under *output_dir*.

    Args:
        output_dir: Destination directory.
    """
    registry = SkillRegistry()
    output_dir = Path(output_dir)

    for name, skill in registry._skills.items():
        skill_dir = output_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(skill.body or "", encoding="utf-8")
        logger.info("Exported skill: %s", name)

    logger.info("Exported %d skills to %s", registry.count(), output_dir)
