#!/usr/bin/env python3
"""Append newly-released OpenRouter models to the committed catalogue.

Append-only by design. Existing rows are left byte-identical: they carry
hand-curated ``tier``/``name``/``supports_json`` values the API cannot
supply, and rewriting them silently changes routing (openrouter_adapter
filters on ``.tier``). Vision-flag drift is *reported*, never applied — it
is a behaviour change that needs a human call.

``--retire`` is the one destructive mode: it deletes rows OpenRouter no
longer serves. It refuses if the registry still names one of them, and
refuses if any row cannot be located, rather than deleting part of the set.

    python scripts/add_openrouter_models.py --diff
    python scripts/add_openrouter_models.py --write
    python scripts/add_openrouter_models.py --retire
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "berb" / "llm" / "openrouter_models_data.py"
API = "https://openrouter.ai/api/v1/models"

# Derived from the existing curation's price distribution: budget tops out
# at 0.455, mid spans 0.26-2.0, premium starts at 1.25. Applied to NEW rows
# only -- existing tiers are never recomputed.
TIER_BUDGET_MAX = 0.5
TIER_MID_MAX = 2.5


def fetch(from_file: str | None) -> list[dict]:
    if from_file:
        payload = json.loads(Path(from_file).read_text(encoding="utf-8"))
    else:
        with urllib.request.urlopen(API, timeout=30) as r:  # noqa: S310 - fixed https URL
            payload = json.loads(r.read().decode("utf-8"))
    return payload["data"]


def is_vision(model: dict) -> bool:
    arch = model.get("architecture") or {}
    if "image" in (arch.get("input_modalities") or []):
        return True
    return "image" in (arch.get("modality") or "")


def per_million(raw: object) -> float:
    """OpenRouter quotes USD per token as a string; the catalogue is per 1M."""
    try:
        return round(float(raw) * 1_000_000, 6)
    except (TypeError, ValueError):
        return 0.0


def tier_for(input_price: float) -> str:
    if input_price < TIER_BUDGET_MAX:
        return "budget"
    if input_price < TIER_MID_MAX:
        return "mid"
    return "premium"


def q(value: str) -> str:
    """Double-quoted Python literal.

    Must not be ``repr``: repr picks single quotes, and ``committed()`` used
    to match only double-quoted keys — which made every row this script wrote
    invisible to the next run, so it re-appended them all.
    """
    return json.dumps(value)


def render(model: dict) -> str:
    mid = model["id"]
    pricing = model.get("pricing") or {}
    inp = per_million(pricing.get("prompt"))
    out = per_million(pricing.get("completion"))
    ctx = int(model.get("context_length") or 128000)
    return (
        f"    {q(mid)}: OpenRouterModel(\n"
        f"        id={q(mid)},\n"
        f"        name={q(str(model.get('name') or mid))},\n"
        f"        provider={q(mid.split('/')[0])},\n"
        f"        input_price={inp},\n"
        f"        output_price={out},\n"
        f"        context_length={ctx},\n"
        f"        supports_vision={is_vision(model)},\n"
        f"        tier={q(tier_for(inp))},\n"
        f"    ),\n"
    )


# Accepts either quote style: rows written before the q() fix are single-quoted.
_ROW = r"""["']([^"']+)["']: OpenRouterModel\((.*?)\n    \),"""


def committed(src: str) -> tuple[set[str], set[str]]:
    rows = re.findall(_ROW, src, re.S)
    return {k for k, _ in rows}, {k for k, b in rows if "supports_vision=True" in b}


def drop_rows(src: str, ids: list[str]) -> tuple[str, list[str]]:
    """Delete the named rows from *src*, leaving every other byte untouched.

    Returns the new source and the ids actually removed, so the caller can
    report an id the pattern failed to match rather than assume success.
    """
    removed = []
    for mid in ids:
        pattern = re.compile(
            r"""    ["']""" + re.escape(mid) + r"""["']: OpenRouterModel\(.*?\n    \),\n""",
            re.S,
        )
        src, n = pattern.subn("", src, count=1)
        if n:
            removed.append(mid)
    return src, removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument(
        "--retire",
        action="store_true",
        help="delete rows OpenRouter no longer serves (destructive; run --diff first)",
    )
    ap.add_argument("--from-file")
    args = ap.parse_args()
    if not (args.diff or args.write or args.retire):
        ap.error("pass --diff, --write or --retire")

    live = fetch(args.from_file)
    src = DATA.read_text(encoding="utf-8")
    have, have_vision = committed(src)

    by_id = {m["id"]: m for m in live}
    live_ids = set(by_id)
    live_vision = {m["id"] for m in live if is_vision(m)}

    new = sorted(live_ids - have)
    retired = sorted(have - live_ids)
    vision_drift = sorted(((live_vision & have) - have_vision) | (have_vision - live_vision - set(retired)))

    print(f"committed {len(have)} -> +{len(new)} new")
    print(f"reported only (not applied): {len(retired)} retired, {len(vision_drift)} vision-flag drift")

    if args.diff:
        for label, rows in (("NEW", new), ("RETIRED", retired), ("VISION DRIFT", vision_drift)):
            print(f"\n--- {label}: {len(rows)}")
            for r in rows:
                print(f"    {r}")
        return 0

    if args.retire:
        if not retired:
            print("nothing to retire")
            return 0
        # A retired id that a task profile still names would break that task
        # at request time, on the one call that used it. Refuse the whole
        # operation rather than delete half of it.
        from berb.llm.registry import TASK_PROFILES

        referenced = {m for p in TASK_PROFILES.values() for m in p.chain} & set(retired)
        if referenced:
            print(f"REFUSED: registry still references {sorted(referenced)}")
            return 1
        src, removed = drop_rows(src, retired)
        missed = sorted(set(retired) - set(removed))
        if missed:
            print(f"REFUSED: could not locate rows for {missed}")
            return 1
        DATA.write_text(src, encoding="utf-8")
        print(f"retired {len(removed)} models")
        return 0

    if not new:
        print("nothing to add")
        return 0

    marker = "\n}\n"
    idx = src.rindex(marker)
    block = "\n    # --- appended from OpenRouter live catalogue ---\n" + "".join(
        render(by_id[i]) for i in new
    )
    DATA.write_text(src[:idx] + "\n" + block.rstrip("\n") + marker + src[idx + len(marker):], encoding="utf-8")
    print(f"appended {len(new)} models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
