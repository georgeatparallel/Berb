#!/usr/bin/env python3
"""Generate openrouter_models_data.py from live OpenRouter API."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "berb" / "llm" / "openrouter_models_data.py"
API = "https://openrouter.ai/api/v1/models"


def is_vision(model: dict) -> bool:
    """Vision capability per the vendor."""
    arch = model.get("architecture") or {}
    modalities = arch.get("input_modalities") or []
    if "image" in modalities:
        return True
    return "image" in (arch.get("modality") or "")


def fetch_models() -> list[dict]:
    """Fetch live model catalog from OpenRouter."""
    try:
        with urllib.request.urlopen(API, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8"))
        models = payload.get("data")
        if not isinstance(models, list):
            raise SystemExit("unexpected payload: no 'data' list")
        return models
    except Exception as exc:
        print(f"Error fetching models: {exc}", file=sys.stderr)
        print(f"Fetch from {API} manually and pass --from-file if network is blocked", file=sys.stderr)
        raise


def generate_model_entry(model: dict) -> str:
    """Generate a single OpenRouterModel entry."""
    model_id = model["id"]
    name = model.get("name", model_id)
    pricing = model.get("pricing") or {}
    context = model.get("context_length", 128000)

    # Extract pricing (per 1M tokens in USD)
    input_price = pricing.get("prompt", 0)
    output_price = pricing.get("completion", 0)

    # Determine provider from model ID
    provider = model_id.split("/")[0]

    # Vision support
    vision = is_vision(model)

    # Format the entry
    vision_str = "True" if vision else "False"
    return (
        f'    "{model_id}": OpenRouterModel(\n'
        f'        name="{name}",\n'
        f'        provider="{provider}",\n'
        f'        input_price={input_price},\n'
        f'        output_price={output_price},\n'
        f'        context_length={context},\n'
        f'        supports_vision={vision_str},\n'
        f'    ),\n'
    )


def generate_catalog(models: list[dict]) -> str:
    """Generate the full openrouter_models_data.py file."""
    header = '''"""OpenRouter model catalog data.

Static registry of OpenRouter-hosted model definitions (pricing, context
length, capability flags). Extracted from openrouter_adapter.py, which
imports OPENROUTER_MODELS and OpenRouterModel from here and re-exports them
for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OpenRouterModel:
    """OpenRouter model configuration."""

    id: str
    """Model ID (e.g., 'anthropic/claude-3.5-sonnet')"""

    name: str
    """Human-readable name"""

    provider: str
    """Provider name (anthropic, openai, google, etc.)"""

    input_price: float = 0.0
    """Price per 1M input tokens (USD)"""

    output_price: float = 0.0
    """Price per 1M output tokens (USD)"""

    context_length: int = 128000
    """Maximum context length"""

    supports_vision: bool = False
    """Whether model supports vision input"""

    supports_json: bool = True
    """Whether model supports JSON output"""

    tier: str = "mid"
    """Model tier: budget, mid, premium"""


# Pre-configured models from OpenRouter.
# Prices are per 1M tokens in USD. Free models have 0 pricing.
# See https://openrouter.ai/docs/guides/routing/model-variants for variant suffixes.
OPENROUTER_MODELS: dict[str, OpenRouterModel] = {
'''

    # Generate model entries sorted by ID
    entries = []
    for model in sorted(models, key=lambda m: m["id"]):
        try:
            entries.append(generate_model_entry(model))
        except Exception as e:
            print(f"Warning: skipped {model.get('id', 'unknown')}: {e}", file=sys.stderr)

    footer = '''}\n\n__all__ = ["OpenRouterModel", "OPENROUTER_MODELS"]\n'''

    return header + "".join(entries) + footer


def main():
    """Fetch live models and generate catalog file."""
    print("Fetching OpenRouter catalog...")
    models = fetch_models()
    print(f"Got {len(models)} models")

    print("Generating openrouter_models_data.py...")
    content = generate_catalog(models)

    print(f"Writing to {DATA}...")
    DATA.write_text(content, encoding="utf-8")
    print(f"Updated {len(models)} models in {DATA}")


if __name__ == "__main__":
    main()
