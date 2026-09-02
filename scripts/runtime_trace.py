#!/usr/bin/env python3
"""Runtime reachability trace — the dynamic counterpart to check_reachability.py.

Static import reachability answers "is this module imported?". It cannot answer
"is this module ever USED?": a module imported by a reachable parent but whose
functions are never called is live to the import graph and dead in practice.
This script measures the second thing, by running a real command under
coverage.py and reporting which berb modules actually executed.

Usage:
    python scripts/runtime_trace.py -- berb run --config configs/config.trace.yaml --auto-approve
    python scripts/runtime_trace.py --json trace.json -- pytest tests/ -m "not slow"

Output, per module, one of:
    EXECUTED            imported and ran code
    IMPORTED-NOT-RUN    statically reachable, but no line executed
    UNREACHABLE         static checker already calls it dead

The IMPORTED-NOT-RUN set is the finding this script exists for: dead code that
static analysis cannot see. Treat it as input to triage, not as a verdict — a
single run exercises one path, so absence of execution is weaker evidence than
absence of an import. Run several configs before deleting anything on its say-so.
"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))


def _static_sets():
    """Return (all_modules, reachable) from the static checker."""
    spec = importlib.util.spec_from_file_location(
        "check_reachability", os.path.join(HERE, "check_reachability.py")
    )
    cr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cr)
    all_mods, is_pkg = cr.discover_modules(cr.ROOT, cr.PKG)
    edges = cr.build_import_graph(all_mods, is_pkg, cr.PKG)
    return all_mods, cr.compute_reachable(all_mods, edges)


def _path_to_module(path, all_mods):
    rel = os.path.relpath(os.path.abspath(path), ROOT).replace(os.sep, "/")
    if not rel.endswith(".py"):
        return None
    name = rel[: -len("/__init__.py")].replace("/", ".") if rel.endswith("/__init__.py") else rel[:-3].replace("/", ".")
    return name if name in all_mods else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", help="Write the full classification to this JSON file.")
    ap.add_argument("--data-file", default=".coverage.trace", help="coverage data file.")
    ap.add_argument("command", nargs=argparse.REMAINDER, help="-- followed by the command to trace.")
    args = ap.parse_args()

    cmd = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not cmd:
        ap.error("no command given; pass it after `--`")

    try:
        import coverage  # noqa: F401
    except ImportError:
        sys.exit("coverage.py is required: pip install coverage (it ships with the dev extra)")

    env = dict(os.environ, COVERAGE_FILE=args.data_file)
    # sys.executable, not "python": the tracer must run in the SAME interpreter
    # this script runs in, or it will miss coverage installed only in a venv.
    traced = [sys.executable, "-m", "coverage", "run", "--source", "berb", "--parallel-mode", "-m"]
    # `berb run ...` -> `-m berb.cli run ...`; anything else runs as given.
    if cmd[0] == "berb":
        proc = subprocess.run(traced + ["berb.cli"] + cmd[1:], cwd=ROOT, env=env)
    else:
        proc = subprocess.run(traced + cmd, cwd=ROOT, env=env)
    print(f"\ntraced command exited {proc.returncode}", file=sys.stderr)

    subprocess.run([sys.executable, "-m", "coverage", "combine"], cwd=ROOT, env=env, check=False)

    import coverage as cov_mod

    cov = cov_mod.Coverage(data_file=args.data_file)
    cov.load()
    data = cov.get_data()

    all_mods, reachable = _static_sets()
    executed = set()
    for f in data.measured_files():
        mod = _path_to_module(f, all_mods)
        if mod and data.lines(f):
            executed.add(mod)

    rows = {}
    for m in sorted(all_mods):
        if m in executed and m in reachable:
            rows[m] = "EXECUTED"
        elif m in executed:
            # Ran, yet the static checker calls it dead. Either the checker is
            # missing an edge (a real instrument bug) or the caller was a test
            # rather than the pipeline. Always worth reading individually.
            rows[m] = "EXECUTED-BUT-UNREACHABLE"
        elif m in reachable:
            rows[m] = "IMPORTED-NOT-RUN"
        else:
            rows[m] = "UNREACHABLE"

    kinds = ("EXECUTED", "EXECUTED-BUT-UNREACHABLE", "IMPORTED-NOT-RUN", "UNREACHABLE")
    counts = {k: sum(1 for v in rows.values() if v == k) for k in kinds}
    print(f"\nmodules {len(all_mods)} | executed {counts['EXECUTED']} | "
          f"executed-but-unreachable {counts['EXECUTED-BUT-UNREACHABLE']} | "
          f"imported-not-run {counts['IMPORTED-NOT-RUN']} | unreachable {counts['UNREACHABLE']}\n")
    if counts["EXECUTED-BUT-UNREACHABLE"]:
        print("--- EXECUTED-BUT-UNREACHABLE (static checker missed an edge, or a test called it) ---")
        for m, v in sorted(rows.items()):
            if v == "EXECUTED-BUT-UNREACHABLE":
                print(f"  {m}")
        print()
    print("--- IMPORTED-NOT-RUN (statically live, never executed in this run) ---")
    for m, v in sorted(rows.items()):
        if v == "IMPORTED-NOT-RUN":
            print(f"  {m}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"counts": counts, "modules": rows}, fh, indent=2, sort_keys=True)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
