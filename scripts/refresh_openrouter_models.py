#!/usr/bin/env python3
"""Refresh berb/llm/openrouter_models_data.py from OpenRouter's live catalogue.

Why this exists
---------------
``openrouter_models_data.py`` is ~3.5k lines of hand-written model rows: ids,
prices, context lengths and a ``supports_vision`` flag. Hand-maintaining a
vendor catalogue does not work — prices change, models are added and retired,
and a wrong id fails only at request time, in production, on the one call that
used it. The list should be *fetched*, not typed.

This script fetches https://openrouter.ai/api/v1/models and reports, or applies,
the difference against the committed catalogue. Vision capability is taken from
the API's own ``architecture.input_modalities`` containing ``"image"`` — the
vendor's answer, not a guess.

Usage
-----
    python scripts/refresh_openrouter_models.py --diff            # report only
    python scripts/refresh_openrouter_models.py --diff --vision   # vision only
    python scripts/refresh_openrouter_models.py --write           # apply
    python scripts/refresh_openrouter_models.py --diff --from-file models.json

``--from-file`` takes a saved API response, so the refresh can be run from a
machine with network access and applied anywhere:

    curl -s https://openrouter.ai/api/v1/models > models.json

No API key is needed; the models endpoint is public. Network egress is blocked
in some sandboxes, which is exactly why ``--from-file`` exists.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "berb" / "llm" / "openrouter_models_data.py"
API = "https://openrouter.ai/api/v1/models"


def fetch(from_file: str | None) -> list[dict]:
    """Return the raw model list, from the API or a saved response."""
    if from_file:
        payload = json.loads(Path(from_file).read_text(encoding="utf-8"))
    else:
        with urllib.request.urlopen(API, timeout=30) as r:  # noqa: S310 - fixed https URL
            payload = json.loads(r.read().decode("utf-8"))
    models = payload.get("data")
    if not isinstance(models, list):
        raise SystemExit("unexpected payload: no 'data' list")
    return models


def is_vision(model: dict) -> bool:
    """Vision capability per the vendor, not per our guess."""
    arch = model.get("architecture") or {}
    modalities = arch.get("input_modalities") or []
    if "image" in modalities:
        return True
    # Older payloads expose it as a "text+image->text" modality string.
    return "image" in (arch.get("modality") or "")


def committed_ids() -> tuple[set[str], set[str]]:
    """(all ids, ids flagged supports_vision=True) in the committed catalogue."""
    src = DATA.read_text(encoding="utf-8")
    entries = re.findall(r'"([^"]+)": OpenRouterModel\((.*?)\n    \),', src, re.S)
    return {k for k, _ in entries}, {k for k, b in entries if "supports_vision=True" in b}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diff", action="store_true", help="report the difference, change nothing")
    ap.add_argument("--write", action="store_true", help="apply additions and vision-flag corrections")
    ap.add_argument("--vision", action="store_true", help="restrict to vision-capable models")
    ap.add_argument("--from-file", help="a saved /api/v1/models response instead of fetching")
    args = ap.parse_args()
    if not (args.diff or args.write):
        ap.error("pass --diff or --write")

    try:
        live = fetch(args.from_file)
    except Exception as exc:
        print(f"could not fetch the catalogue: {exc}", file=sys.stderr)
        print("If egress is blocked, fetch elsewhere and pass --from-file:", file=sys.stderr)
        print(f"  curl -s {API} > models.json", file=sys.stderr)
        return 2

    live_vision = {m["id"] for m in live if is_vision(m)}
    live_ids = {m["id"] for m in live}
    have_ids, have_vision = committed_ids()

    scope_live = live_vision if args.vision else live_ids
    missing = sorted(scope_live - have_ids)
    retired_set = have_ids - live_ids
    retired = sorted(retired_set)
    wrong_flag = sorted((live_vision & have_ids) - have_vision)
    # A model we flag as vision but the vendor does not — excluding ones that
    # are simply gone, which the RETIRED bucket already reports.
    stale_flag = sorted(have_vision - live_vision - retired_set)

    print(f"live catalogue : {len(live_ids)} models, {len(live_vision)} vision-capable")
    print(f"committed      : {len(have_ids)} models, {len(have_vision)} flagged supports_vision\n")
    for label, rows in (
        ("MISSING (in OpenRouter, absent here)", missing),
        ("RETIRED (here, gone from OpenRouter)", retired),
        ("VISION FLAG MISSING (vendor says image-capable, we say not)", wrong_flag),
        ("VISION FLAG STALE (we say image-capable, vendor says not)", stale_flag),
    ):
        print(f"--- {label}: {len(rows)}")
        for r in rows:
            print(f"    {r}")
        print()

    if args.write:
        print("--write is not implemented yet: generating 3.5k lines of rows needs a")
        print("decision about whether this module stays hand-committed at all, or")
        print("becomes a generated artifact / a runtime fetch with a cached fallback.")
        print("Run with --diff and act on the report until that is settled.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
