"""Interactive configuration wizard for Berb.

This module provides guided configuration setup:
- Interactive CLI wizard
- Domain-based preset recommendation
- LLM provider setup
- Budget/time constraints
- Generates config.berb.yaml

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class ConfigWizard:
    """Interactive configuration wizard.

    This wizard:
    1. Asks about research domain
    2. Recommends appropriate preset
    3. Configures LLM providers
    4. Sets budget/time constraints
    5. Generates config.berb.yaml

    Usage::

        wizard = ConfigWizard()
        config = await wizard.run()
        # Generates config.berb.yaml
    """

    # Domain to preset mapping
    DOMAIN_PRESETS = {
        "machine-learning": "ml-conference",
        "deep-learning": "ml-conference",
        "ai": "ml-conference",
        "biomedical": "biomedical",
        "clinical": "biomedical",
        "medicine": "biomedical",
        "nlp": "nlp",
        "linguistics": "nlp",
        "computer-vision": "computer-vision",
        "image-processing": "computer-vision",
        "physics": "physics",
        "chaos": "physics",
        "social-sciences": "social-sciences",
        "psychology": "social-sciences",
        "engineering": "engineering",
        "systems": "engineering",
        "humanities": "humanities",
        "philosophy": "humanities",
        "history": "humanities",
    }

    # Budget presets
    BUDGET_PRESETS = {
        "minimal": {"preset": "budget", "max_budget": 0.25},
        "balanced": {"preset": "ml-conference", "max_budget": 1.50},
        "quality": {"preset": "max-quality", "max_budget": 5.00},
    }

    def __init__(self):
        """Initialize configuration wizard."""
        self.responses: dict[str, Any] = {}

    async def run(self, output_path: Path | str | None = None) -> dict[str, Any]:
        """Run the configuration wizard.

        Args:
            output_path: Output file path (optional)

        Returns:
            Generated configuration dictionary
        """
        print("\n" + "=" * 60)
        print("  Berb Configuration Wizard")
        print("=" * 60 + "\n")

        # Collect responses
        self._ask_research_domain()
        self._ask_budget()
        self._ask_llm_providers()
        self._ask_collaborative_mode()
        self._ask_output_preferences()

        # Generate config
        config = self._generate_config()

        # Save to file
        if output_path:
            self._save_config(config, output_path)

        return config

    def _ask_research_domain(self) -> None:
        """Ask about research domain."""
        print("1. What is your primary research domain?")
        print("   Examples: machine-learning, biomedical, nlp, physics, etc.\n")

        # In production, would use interactive input
        # For now, use placeholder
        domain = input("   Your domain: ").strip().lower()

        # Recommend preset
        recommended_preset = self.DOMAIN_PRESETS.get(domain, "ml-conference")

        self.responses["domain"] = domain
        self.responses["recommended_preset"] = recommended_preset

        print(f"\n   → Recommended preset: {recommended_preset}\n")

    def _ask_budget(self) -> None:
        """Ask about budget constraints."""
        print("2. What is your budget per paper?")
        print("   [1] Minimal ($0.15-0.25)")
        print("   [2] Balanced ($1.00-2.00)")
        print("   [3] Quality-focused ($3.00-5.00)\n")

        choice = input("   Your choice (1-3): ").strip()

        budget_map = {"1": "minimal", "2": "balanced", "3": "quality"}
        budget_level = budget_map.get(choice, "balanced")

        self.responses["budget_level"] = budget_level
        self.responses["budget_preset"] = self.BUDGET_PRESETS[budget_level]["preset"]
        self.responses["max_budget"] = self.BUDGET_PRESETS[budget_level]["max_budget"]

        print(f"\n   → Selected: {budget_level} budget\n")

    def _ask_llm_providers(self) -> None:
        """Ask about LLM providers."""
        print("3. Which LLM providers do you have access to?")
        print("   Check all that apply:\n")

        providers = []

        provider_options = [
            ("openai", "OpenAI (GPT-4o, o1)"),
            ("anthropic", "Anthropic (Claude)"),
            ("google", "Google (Gemini)"),
            ("deepseek", "DeepSeek (V3, R1)"),
            ("openrouter", "OpenRouter (Multiple providers)"),
        ]

        for i, (provider_id, provider_name) in enumerate(provider_options, 1):
            print(f"   [{i}] {provider_name}")

        print("\n   Enter numbers separated by commas (e.g., 1,2,3)\n")
        choice = input("   Your choice: ").strip()

        if choice:
            for num in choice.split(","):
                num = num.strip()
                if num.isdigit() and 1 <= int(num) <= len(provider_options):
                    providers.append(provider_options[int(num) - 1][0])

        self.responses["llm_providers"] = providers if providers else ["openai"]

        print(f"\n   → Selected providers: {', '.join(providers)}\n")

    def _ask_collaborative_mode(self) -> None:
        """Ask about collaborative mode."""
        print("4. Do you want collaborative mode (human-in-the-loop)?")
        print("   [1] No, fully autonomous")
        print("   [2] Yes, pause at key stages\n")

        choice = input("   Your choice (1-2): ").strip()

        collaborative = choice == "2"

        self.responses["collaborative_mode"] = collaborative

        if collaborative:
            print("\n   → Collaborative mode enabled")
            print("   → Will pause at stages: 2, 6, 8, 9, 15, 18\n")
        else:
            print("\n   → Autonomous mode enabled\n")

    def _ask_output_preferences(self) -> None:
        """Ask about output preferences."""
        print("5. What is your preferred output format?")
        print("   [1] PDF only")
        print("   [2] LaTeX source")
        print("   [3] Multiple formats (PDF + LaTeX + Word)\n")

        choice = input("   Your choice (1-3): ").strip()

        format_map = {"1": ["pdf"], "2": ["latex"], "3": ["pdf", "latex", "word"]}
        formats = format_map.get(choice, ["pdf"])

        self.responses["output_formats"] = formats

        print(f"\n   → Output formats: {', '.join(formats)}\n")

    def _generate_config(self) -> dict[str, Any]:
        """Generate configuration from responses.

        Returns:
            Configuration dictionary
        """
        # Determine primary model based on providers
        providers = self.responses.get("llm_providers", ["openai"])
        primary_provider = providers[0]

        model_mapping = {
            "openai": {"primary": "gpt-4o", "fallback": "gpt-4o-mini"},
            "anthropic": {"primary": "claude-sonnet-4-6", "fallback": "claude-haiku-4-5"},
            "google": {"primary": "gemini-2.5-pro", "fallback": "gemini-2.5-flash"},
            "deepseek": {"primary": "deepseek-v3.2", "fallback": "deepseek-r1"},
        }

        models = model_mapping.get(primary_provider, model_mapping["openai"])

        # Build config
        config = {
            "project": {
                "name": "my-research",
                "mode": "collaborative" if self.responses.get("collaborative_mode") else "full-auto",
            },
            "research": {
                "topic": "Your research topic here",
                "domains": [self.responses.get("domain", "machine-learning")],
            },
            "runtime": {
                "timezone": "UTC",
                "max_parallel_tasks": 3,
            },
            "llm": {
                "provider": primary_provider,
                "api_key_env": f"{primary_provider.upper()}_API_KEY",
                "primary_model": models["primary"],
                "fallback_models": [models["fallback"]],
            },
            "experiment": {
                "mode": "docker",
            },
            "writing": {
                "polisher": {
                    "enabled": True,
                    "auto_apply_categories": ["grammar", "word_choice"],
                },
                "traceable_citations": {
                    "enabled": True,
                    "require_page_number": True,
                },
            },
        }

        # Add preset if different from default
        preset = self.responses.get("budget_preset", "ml-conference")
        if preset != "ml-conference":
            config["preset"] = preset

        # Add collaborative mode settings
        if self.responses.get("collaborative_mode"):
            config["collaborative"] = {
                "pause_after_stages": [2, 6, 8, 9, 15, 18],
                "approval_timeout_minutes": 60,
            }

        return config

    def _save_config(
        self,
        config: dict[str, Any],
        output_path: Path | str,
    ) -> None:
        """Save configuration to file.

        Args:
            config: Configuration dictionary
            output_path: Output file path
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Configuration saved to {output_path}")
        print(f"\n✓ Configuration saved to: {output_path}\n")


async def run_config_wizard(output_path: Path | str | None = None) -> dict[str, Any]:
    """Convenience function to run config wizard.

    Args:
        output_path: Output file path

    Returns:
        Generated configuration
    """
    wizard = ConfigWizard()
    return await wizard.run(output_path)


def generate_example_config(
    domain: str = "machine-learning",
    budget: str = "balanced",
    providers: list[str] | None = None,
) -> dict[str, Any]:
    """Generate example config without interactive wizard.

    Args:
        domain: Research domain
        budget: Budget level
        providers: LLM providers

    Returns:
        Example configuration
    """
    wizard = ConfigWizard()

    # Set responses programmatically
    wizard.responses = {
        "domain": domain,
        "recommended_preset": wizard.DOMAIN_PRESETS.get(domain, "ml-conference"),
        "budget_level": budget,
        "budget_preset": wizard.BUDGET_PRESETS.get(budget, wizard.BUDGET_PRESETS["balanced"])[
            "preset"
        ],
        "max_budget": wizard.BUDGET_PRESETS.get(budget, wizard.BUDGET_PRESETS["balanced"])[
            "max_budget"
        ],
        "llm_providers": providers or ["openai"],
        "collaborative_mode": False,
        "output_formats": ["pdf"],
    }

    return wizard._generate_config()
