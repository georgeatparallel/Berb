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


def _lazy_export_map(tree):
    """Extract a package's PEP 562 lazy re-export map, or None.

    berb/_lazy.py's ``lazy_exports`` lets ``from berb.llm import PROVIDER_PRESETS``
    import berb/llm/presets.py only when the attribute is read. No import
    statement names the submodule, so the map is the only static record of the
    edge. Returns {public_name: submodule}.
    """
    if not any(
        isinstance(n, ast.Name) and n.id == "lazy_exports" for n in ast.walk(tree)
    ) and not any(
        isinstance(n, ast.Attribute) and n.attr == "lazy_exports" for n in ast.walk(tree)
    ):
        return None
    mapping = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                continue
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                mapping[k.value] = v.value
            elif (
                isinstance(v, ast.Tuple)
                and v.elts
                and isinstance(v.elts[0], ast.Constant)
                and isinstance(v.elts[0].value, str)
            ):
                mapping[k.value] = v.elts[0].value
    return mapping or None


def public_api_modules(all_mods, is_pkg):
    """Modules backing a PACKAGE's declared public API.

    ``from berb.literature import CitationClassifier`` is a supported contract
    (decision, 2026-09-02), so the module behind an exported name is an entry
    point in its own right — the same standing as berb.cli. Without this the
    checker reports a published, working API as dead because no *internal*
    caller happens to use it.

    Deliberately narrow, twice over:

    1. Only packages in ``PUBLIC_API_PACKAGES`` below. Whether a package's
       surface is a supported contract is a product decision, not something to
       infer from the presence of an ``__all__`` — five packages in this repo
       declare one, and crediting all of them would un-park modules that were
       triaged as dead on their merits. Adding a package here is that decision
       being made; do not add one to quieten the gate.
    2. Only ``__all__`` on the package ``__init__.py``, resolved through that
       package's ``lazy_exports`` map. ``__all__`` on an ordinary module is
       re-export hygiene, not a public surface.

    tests/test_public_api_contract.py asserts every one of these names actually
    resolves, so the contract cannot rot quietly now that it is exempt from the
    dead-code gate.
    """
    # Approved contracts. `from berb.literature import ...` was confirmed as a
    # supported public API on 2026-09-02; see tasks/w2_untested_triage.md #4.
    PUBLIC_API_PACKAGES = ("berb.literature",)

    roots = set()
    for m, p in all_mods.items():
        if m not in PUBLIC_API_PACKAGES or m not in is_pkg:
            continue
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                tree = ast.parse(f.read())
        except Exception:
            continue
        mapping = _lazy_export_map(tree)
        if not mapping:
            continue
        exported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "__all__" for t in node.targets
            ):
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    exported = {
                        e.value for e in node.value.elts if isinstance(e, ast.Constant)
                    }
        for name, sub in mapping.items():
            if name in exported and f"{m}.{sub}" in all_mods:
                roots.add(f"{m}.{sub}")
    return roots


def _type_checking_imports(tree):
    """Collect import nodes that live inside an ``if TYPE_CHECKING:`` block.

    These never execute at runtime — they exist so type checkers can see names
    that are otherwise resolved lazily (see berb/_lazy.py). Crediting them as
    edges makes a lazily-exported submodule look live merely because its parent
    package is imported, which is the opposite of the truth: PEP 562 exports are
    imported only when the attribute is actually read.
    """
    excluded = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        guarded = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if not guarded:
            continue
        for stmt in node.body:
            for sub in ast.walk(stmt):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    excluded.add(id(sub))
    return excluded


def _literal_import_module_target(node):
    """Return the literal module name of an ``import_module("...")`` call.

    Matches both ``importlib.import_module("x")`` and a bare
    ``import_module("x")``. Returns None for anything computed — a variable, an
    f-string, or a relative import with a ``package`` argument — because those
    cannot be resolved statically.
    """
    fn = node.func
    is_call = (isinstance(fn, ast.Attribute) and fn.attr == "import_module") or (
        isinstance(fn, ast.Name) and fn.id == "import_module"
    )
    if not is_call or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def build_import_graph(all_mods, is_pkg, pkg_prefix):
    """Build import dependency edges from AST analysis."""
    edges = {m: set() for m in all_mods}

    # Ancestor packages. Python executes every parent __init__.py on the way to
    # a submodule — importing berb.experiment.factory runs berb/__init__.py and
    # berb/experiment/__init__.py first — but no import statement names them,
    # so without this a package whose submodules are reachable was itself
    # reported dead. Its own pass, so a file that fails to parse still
    # contributes its ancestors.
    for m in all_mods:
        parts = m.split(".")
        for i in range(1, len(parts)):
            anc = ".".join(parts[:i])
            if anc != m and anc in is_pkg and anc in all_mods:
                edges[m].add(anc)

    # Lazy re-export maps, keyed by package. Built first because an importer is
    # usually parsed before the package it imports from.
    lazy_maps = {}
    for m, p in all_mods.items():
        if m not in is_pkg:
            continue
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                mapping = _lazy_export_map(ast.parse(f.read()))
        except Exception:
            continue
        if mapping:
            lazy_maps[m] = mapping

    for m, p in all_mods.items():
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                tree = ast.parse(f.read())
        except Exception:
            continue
        type_only = _type_checking_imports(tree)
        for n in ast.walk(tree):
            if id(n) in type_only:
                continue
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
                    # `from berb.llm import PROVIDER_PRESETS` resolves through
                    # the package's lazy map to berb.llm.presets at runtime.
                    sub = lazy_maps.get(tgt, {}).get(a.name)
                    if sub and f"{tgt}.{sub}" in all_mods:
                        edges[m].add(f"{tgt}.{sub}")
            elif isinstance(n, ast.Call):
                # Dynamic-but-literal imports, e.g. berb/pipeline/summary.py's
                # importlib.import_module("berb.quality"). A plain import walk
                # misses these and reports a live module dead.
                tgt = _literal_import_module_target(n)
                if tgt and tgt.startswith(pkg_prefix) and tgt in all_mods:
                    edges[m].add(tgt)
    return edges


def compute_reachable(all_mods, edges, is_pkg=None):
    """BFS from entry points. Returns set of reachable module names.

    Entry points are the CLI and server surfaces below, plus — when ``is_pkg``
    is supplied — the modules backing each package's declared public API. See
    :func:`public_api_modules`.
    """
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
    if is_pkg is not None:
        entry.extend(public_api_modules(all_mods, is_pkg))

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
    seen = compute_reachable(all_mods, edges, is_pkg)

    unreached = sorted(set(all_mods) - seen)
    total_loc = sum(loc_of(m, all_mods) for m in all_mods)
    un_loc = sum(loc_of(m, all_mods) for m in unreached)

    print(f"modules {len(all_mods)} | reachable {len(seen)} | UNREACHED {len(unreached)}")
    print(f"loc {total_loc} | UNREACHABLE {un_loc} ({100*un_loc/total_loc:.0f}%)\n")

    # Load allowlist and compute net unreachable
    allowlist = load_allowlist(args.allowlist) if args.allowlist else set()
    # An allowlist entry covers the module and everything under it: the file's
    # entries are package names ("berb.hyperagent  # Parked"), and exact-name
    # matching quietly parked only the package __init__ — 156 LOC of the ~4.6k
    # those three entries were meant to cover.
    def _allowed(mod):
        return any(mod == a or mod.startswith(a + ".") for a in allowlist)

    net_unreached = [m for m in unreached if not _allowed(m)]
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
