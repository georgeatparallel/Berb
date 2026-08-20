#!/usr/bin/env python3
"""Reachability v2 — static import-graph reachability checker with CI support.

Usage:
    python scripts/check_reachability.py
    python scripts/check_reachability.py --max-unreachable-loc 15000
    python scripts/check_reachability.py --allowlist .reachability-allowlist

Exit code 1 when unreachable LOC (after allowlist exclusion) exceeds threshold.
"""
import argparse
import ast
import os
import sys
from collections import deque

# Resolve root relative to this script's location
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
PKG = "berb"


def discover_modules(root, pkg):
    """Walk the package tree and return (all_mods, is_pkg)."""
    all_mods = {}
    is_pkg = set()
    pkg_path = os.path.join(root, pkg)
    if not os.path.isdir(pkg_path):
        print(f"ERROR: package directory not found: {pkg_path}", file=sys.stderr)
        sys.exit(1)
    for dirpath, dirnames, filenames in os.walk(pkg_path):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "node_modules")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root).replace("\\", "/")
            if rel.endswith("/__init__.py"):
                name = rel[: -len("/__init__.py")].replace("/", ".")
                is_pkg.add(name)
            else:
                name = rel[:-3].replace("/", ".")
            all_mods[name] = p
    return all_mods, is_pkg


def resolve(cur, level, module, is_pkg):
    """PEP 328 relative import resolution."""
    base = cur if cur in is_pkg else ".".join(cur.split(".")[:-1])
    parts = base.split(".")
    if level > 1:
        parts = parts[: -(level - 1)]
    pref = ".".join(parts)
    return f"{pref}.{module}" if module else pref


def build_import_graph(all_mods, is_pkg, pkg_prefix):
    """Build import dependency edges from AST analysis."""
    edges = {m: set() for m in all_mods}
    for m, p in all_mods.items():
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                tree = ast.parse(f.read())
        except Exception:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.split(".")[0] == pkg_prefix:
                        edges[m].add(a.name)
            elif isinstance(n, ast.ImportFrom):
                tgt = resolve(m, n.level, n.module, is_pkg) if n.level else (n.module or "")
                if not tgt or not tgt.startswith(pkg_prefix):
                    continue
                if tgt in all_mods:
                    edges[m].add(tgt)
                for a in n.names:
                    cand = f"{tgt}.{a.name}"
                    if cand in all_mods:
                        edges[m].add(cand)
    return edges


def compute_reachable(all_mods, edges):
    """BFS from entry points. Returns set of reachable module names."""
    ENTRY_PREFIX = (
        "berb.pipeline.stage_impls", "berb.server", "berb.api", "berb.mcp",
        "berb.benchmarks", "berb.ui", "berb.web", "berb.plugins", "berb.skills",
        "berb.presets", "berb.commands", "berb.dashboard", "berb.copilot",
        "berb.wizard", "berb.servers", "berb.collaboration", "berb.hooks",
    )
    ENTRY_EXACT = (
        "berb.cli", "berb.__main__", "berb.health", "berb.config",
        "berb.pipeline.runner", "berb.pipeline.executor",
    )
    entry = [
        m for m in all_mods
        if m in ENTRY_EXACT or m.startswith(ENTRY_PREFIX)
    ]

    seen, q = set(), deque(entry)
    while q:
        cur = q.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        for nxt in edges.get(cur, ()):
            if nxt in all_mods and nxt not in seen:
                q.append(nxt)
    return seen


def loc_of(m, all_mods):
    try:
        return sum(1 for _ in open(all_mods[m], encoding="utf-8", errors="ignore"))
    except Exception:
        return 0


def load_allowlist(path):
    """Load allowlist file. Lines: module_name # justification comment."""
    allowed = set()
    if not path or not os.path.exists(path):
        return allowed
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Take everything before any inline comment
            mod = stripped.split("#")[0].strip()
            if mod:
                allowed.add(mod)
    return allowed


def main():
    parser = argparse.ArgumentParser(
        description="Static import-graph reachability checker for Berb."
    )
    parser.add_argument(
        "--max-unreachable-loc", type=int, default=0,
        help="Fail if unreachable LOC (after allowlist) exceeds this. 0 = no fail.",
    )
    parser.add_argument(
        "--allowlist", type=str, default="",
        help="Path to allowlist file of module names that may stay unreachable.",
    )
    args = parser.parse_args()

    all_mods, is_pkg = discover_modules(ROOT, PKG)
    edges = build_import_graph(all_mods, is_pkg, PKG)
    seen = compute_reachable(all_mods, edges)

    unreached = sorted(set(all_mods) - seen)
    total_loc = sum(loc_of(m, all_mods) for m in all_mods)
    un_loc = sum(loc_of(m, all_mods) for m in unreached)

    print(f"modules {len(all_mods)} | reachable {len(seen)} | UNREACHED {len(unreached)}")
    print(f"loc {total_loc} | UNREACHABLE {un_loc} ({100*un_loc/total_loc:.0f}%)\n")

    # Load allowlist and compute net unreachable
    allowlist = load_allowlist(args.allowlist) if args.allowlist else set()
    net_unreached = [m for m in unreached if m not in allowlist]
    net_un_loc = sum(loc_of(m, all_mods) for m in net_unreached)

    if allowlist:
        allowed_count = len(unreached) - len(net_unreached)
        allowed_loc = un_loc - net_un_loc
        print(f"Allowlisted: {allowed_count} modules ({allowed_loc} LOC)\n")

    # Group unreached by top-level package
    by = {}
    for u in unreached:
        by.setdefault(".".join(u.split(".")[:2]), []).append(u)
    rows = sorted(
        ((sum(loc_of(m, all_mods) for m in v), k, v) for k, v in by.items()),
        reverse=True,
    )

    SCI = {
        "berb.validation", "berb.reasoning", "berb.memory",
        "berb.review", "berb.integrity", "berb.self_evolve", "berb.learning",
        "berb.knowledge", "berb.audit", "berb.assessor", "berb.math",
        "berb.integrity.eval",
    }

    print("--- scientific-capability packages (the ones that matter) ---")
    for t, k, v in rows:
        if k in SCI:
            mods_str = ", ".join(
                sorted(x.split(".")[-1] for x in v)[:8]
            )
            print(f"  {k:24s} {t:6d} loc  ({len(v)} mods): {mods_str}")

    print("\n--- all other unreachable, by size ---")
    for t, k, v in rows:
        if k not in SCI and t >= 400:
            print(f"  {k:24s} {t:6d} loc  ({len(v)} mods)")

    # Fail if threshold exceeded
    if args.max_unreachable_loc > 0 and net_un_loc > args.max_unreachable_loc:
        print(
            f"\nFAIL: Net unreachable LOC {net_un_loc} exceeds "
            f"--max-unreachable-loc {args.max_unreachable_loc}",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\n[OK] Reachability check passed.")


if __name__ == "__main__":
    main()
