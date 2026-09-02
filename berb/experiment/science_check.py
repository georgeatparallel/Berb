"""Domain-correctness checks for generated experiment code.

The other validators in this package ask whether the code will *run*:
syntax, dangerous calls, import availability. These ask whether the
science is *right* — the class of bug that executes cleanly and produces
a plausible, wrong number.

Design notes, and why each one is here:

* **Rules favour precision.** An ambiguous unit suffix, a single
  significance test, or an already-corrected family of tests stays
  silent. A false positive costs an LLM repair round-trip on correct
  code, so silence is the safer default.
* **Checks read the AST of the code the model actually wrote.** They
  never ask a model whether the science is right.
* **Findings carry ``category="science"``.** Stage 10's blocking check in
  ``pipeline/stage_impls/_code_generation.py`` is scoped to the
  "syntax", "import" and "security" categories, so a science finding
  drives the repair loop without ever failing the stage. That split is
  deliberate: the model gets asked to fix wrong science, and a false
  positive cannot kill a run.

Scope is deliberately narrow. ``check_units`` looks at binary arithmetic
and ordering comparisons only, not augmented assignment or function
arguments, because widening it costs precision faster than it buys
coverage.

Add a check by writing ``check_<name>(tree, code) -> list[ValidationIssue]``
and appending it to :data:`CHECKS`. Nothing else needs to change.

Prior art: the ``domain-check`` gate in ai4s-research/open-science, read
and compared against Berb in ``tasks/open_science_research.md``.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from berb.experiment.validator import ValidationIssue

# ---------------------------------------------------------------------------
# check_multiple_comparisons
# ---------------------------------------------------------------------------

# Bare function names of significance tests, matched on the final
# attribute so an alias or module path does not matter:
# `stats.ttest_ind`, `scipy.stats.ttest_ind` and `ttest_ind` all match.
SIGNIFICANCE_TESTS: Final[frozenset[str]] = frozenset(
    {
        "ttest_ind",
        "ttest_rel",
        "ttest_1samp",
        "pearsonr",
        "spearmanr",
        "kendalltau",
        "f_oneway",
        "chi2_contingency",
        "mannwhitneyu",
        "wilcoxon",
        "kruskal",
        "ranksums",
        "fisher_exact",
    }
)

# If any of these appears anywhere in the source, the family is treated as
# corrected and the check stays silent. Matched against the raw text rather
# than the AST so an import, a keyword argument, a string method name or a
# comment all count. Over-suppressing is the intended failure direction.
CORRECTION_MARKERS: Final[tuple[str, ...]] = (
    "multipletests",
    "fdrcorrection",
    "fdr_bh",
    "fdr_by",
    "bonferroni",
    "holm",
    "sidak",
    "benjamini",
    "hochberg",
    "false_discovery",
    "p_adjust",
    "padjust",
)

# Firing threshold for the no-loop case. Two tests is a comparison; three
# is a family.
_MIN_UNCORRECTED_TESTS: Final = 3


def _called_name(node: ast.Call) -> str | None:
    """Return the final name of a call target, or None if it is not a plain
    name or attribute access (a call on a subscript or another call)."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def check_multiple_comparisons(tree: ast.AST, code: str) -> list[ValidationIssue]:
    """Flag a family of significance tests run with no correction.

    Fires when a significance test runs inside a loop, or when three or
    more run anywhere, and no correction marker appears in the source.
    An uncorrected family inflates the family-wise false-positive rate,
    which is the silent form of p-hacking.
    """
    from berb.experiment.validator import ValidationIssue

    lowered = code.lower()
    if any(marker in lowered for marker in CORRECTION_MARKERS):
        return []

    test_calls: list[ast.Call] = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) in SIGNIFICANCE_TESTS
    ]
    if not test_calls:
        return []

    # A test inside a loop is a family regardless of how many literal call
    # sites appear, so look for that first and report the innermost one.
    for loop in ast.walk(tree):
        if not isinstance(loop, ast.For | ast.While):
            continue
        for node in ast.walk(loop):
            if isinstance(node, ast.Call) and _called_name(node) in SIGNIFICANCE_TESTS:
                name = _called_name(node)
                return [
                    ValidationIssue(
                        severity="error",
                        category="science",
                        message=(
                            f"'{name}' runs inside a loop with no multiple-comparison "
                            f"correction. Repeated significance tests inflate the "
                            f"family-wise false-positive rate. Collect the p-values and "
                            f"correct them, for example with "
                            f"statsmodels.stats.multitest.multipletests(pvals, "
                            f"method='fdr_bh'), then report the corrected values."
                        ),
                        line=node.lineno,
                        col=node.col_offset,
                    )
                ]

    if len(test_calls) >= _MIN_UNCORRECTED_TESTS:
        first = test_calls[0]
        names = sorted({n for c in test_calls if (n := _called_name(c)) is not None})
        return [
            ValidationIssue(
                severity="error",
                category="science",
                message=(
                    f"{len(test_calls)} significance tests ({', '.join(names)}) run with "
                    f"no multiple-comparison correction. Correct the p-values as a "
                    f"family, for example with statsmodels.stats.multitest."
                    f"multipletests(pvals, method='fdr_bh'), then report the corrected "
                    f"values."
                ),
                line=first.lineno,
                col=first.col_offset,
            )
        ]
    return []


# ---------------------------------------------------------------------------
# check_units
# ---------------------------------------------------------------------------

# Variable-name suffix -> physical dimension. Every entry must be
# unambiguous in ordinary scientific code. Short forms such as `_m`, `_s`
# and `_g` are deliberately absent: `loss_m` is far more likely to be a
# mean than a length, and a wrong flag here costs a repair round-trip on
# correct code.
UNIT_SUFFIXES: Final[dict[str, str]] = {
    # time
    "_seconds": "time",
    "_secs": "time",
    "_milliseconds": "time",
    "_millis": "time",
    "_microseconds": "time",
    "_minutes": "time",
    "_hours": "time",
    "_days": "time",
    # length
    "_meters": "length",
    "_metres": "length",
    "_kilometers": "length",
    "_kilometres": "length",
    "_centimeters": "length",
    "_millimeters": "length",
    "_miles": "length",
    "_feet": "length",
    "_inches": "length",
    # mass
    "_kilograms": "mass",
    "_grams": "mass",
    "_pounds": "mass",
    "_tonnes": "mass",
    # angle
    "_radians": "angle",
    "_degrees": "angle",
    # temperature
    "_celsius": "temperature",
    "_kelvin": "temperature",
    "_fahrenheit": "temperature",
    # digital storage
    "_bytes": "storage",
    "_kilobytes": "storage",
    "_megabytes": "storage",
    "_gigabytes": "storage",
}

# Trigonometric functions whose argument must already be in radians.
TRIG_FUNCTIONS: Final[frozenset[str]] = frozenset(
    {"sin", "cos", "tan", "asin", "acos", "atan", "arcsin", "arccos", "arctan"}
)

# Degree-valued suffixes for the trig check only. `_deg` is ambiguous in
# general but not as the sole argument of a trig call, so it is admitted
# here and nowhere else.
_DEGREE_SUFFIXES: Final[tuple[str, ...]] = ("_degrees", "_degs", "_deg")

# Comparison operators that assert an ordering, and so require both sides
# to share a dimension. Equality is excluded: `a_seconds == b_meters` is
# well-defined, always False, and not worth a repair round-trip.
_ORDERING_OPS: Final = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def _dimension_of(node: ast.expr) -> tuple[str, str] | None:
    """Return ``(variable_name, dimension)`` for a plain name carrying a
    known unit suffix, else None.

    Only bare ``Name`` nodes qualify. An attribute, a call result or a
    subscript carries no reliable dimension claim in its own text.
    """
    if not isinstance(node, ast.Name):
        return None
    lowered = node.id.lower()
    for suffix, dimension in UNIT_SUFFIXES.items():
        if lowered.endswith(suffix):
            return node.id, dimension
    return None


def _mismatch_issue(
    left: tuple[str, str], right: tuple[str, str], node: ast.AST, action: str
) -> ValidationIssue:
    from berb.experiment.validator import ValidationIssue

    return ValidationIssue(
        severity="error",
        category="science",
        message=(
            f"{action} '{left[0]}' ({left[1]}) and '{right[0]}' ({right[1]}): the two "
            f"quantities have different physical dimensions. Convert one to the "
            f"other's unit first, or drop the unit suffix if the name is misleading."
        ),
        line=getattr(node, "lineno", None),
        col=getattr(node, "col_offset", None),
    )


def check_units(tree: ast.AST, code: str) -> list[ValidationIssue]:
    """Flag arithmetic or ordering across mismatched physical dimensions,
    and trigonometry applied to a degree-valued angle.

    Both operands must be plain variable names carrying an unambiguous
    unit suffix. Anything else stays silent.
    """
    del code  # this check reads the AST only
    issues: list[ValidationIssue] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Sub):
            left = _dimension_of(node.left)
            right = _dimension_of(node.right)
            if left and right and left[1] != right[1]:
                verb = "Adding" if isinstance(node.op, ast.Add) else "Subtracting"
                issues.append(_mismatch_issue(left, right, node, verb))

        elif isinstance(node, ast.Compare) and len(node.ops) == 1:
            if not isinstance(node.ops[0], _ORDERING_OPS):
                continue
            left = _dimension_of(node.left)
            right = _dimension_of(node.comparators[0])
            if left and right and left[1] != right[1]:
                issues.append(_mismatch_issue(left, right, node, "Comparing"))

        elif isinstance(node, ast.Call) and _called_name(node) in TRIG_FUNCTIONS:
            # One positional argument, a bare name, named in degrees. A
            # wrapped argument such as sin(radians(x_degrees)) is a Call,
            # not a Name, so it never reaches this branch.
            if len(node.args) != 1 or node.keywords:
                continue
            arg = node.args[0]
            if not isinstance(arg, ast.Name):
                continue
            if arg.id.lower().endswith(_DEGREE_SUFFIXES):
                from berb.experiment.validator import ValidationIssue

                fname = _called_name(node)
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="science",
                        message=(
                            f"'{fname}' is applied to '{arg.id}', which is named in "
                            f"degrees. Trigonometric functions take radians. Convert "
                            f"first, for example with math.radians({arg.id}) or "
                            f"numpy.deg2rad({arg.id})."
                        ),
                        line=node.lineno,
                        col=node.col_offset,
                    )
                )

    return issues


# ---------------------------------------------------------------------------
# Registry and entry point
# ---------------------------------------------------------------------------

CHECKS: Final[tuple[Callable[[ast.AST, str], list[ValidationIssue]], ...]] = (
    check_multiple_comparisons,
    check_units,
)


def check_science(code: str) -> list[ValidationIssue]:
    """Run every registered domain-correctness check over *code*.

    Returns an empty list if *code* does not parse. Syntax is reported by
    :func:`berb.experiment.validator.validate_syntax`, and reporting it
    twice would send the repair loop a duplicate.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    issues: list[ValidationIssue] = []
    for check in CHECKS:
        issues.extend(check(tree, code))
    return issues
