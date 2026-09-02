"""Domain-correctness checks (berb/experiment/science_check.py).

Every check is tested in both directions. A rule that only ever fires is
not evidence of precision, and precision is the whole design constraint
here: a false positive costs an LLM repair round-trip on correct code.
"""

from __future__ import annotations

from berb.experiment.science_check import check_science
from berb.experiment.validator import validate_code

# ---------------------------------------------------------------------------
# check_multiple_comparisons
# ---------------------------------------------------------------------------

_LOOPED_TEST = """
from scipy import stats

pvals = []
for col in columns:
    t, p = stats.ttest_ind(a[col], b[col])
    pvals.append(p)
"""

_LOOPED_TEST_CORRECTED = """
from scipy import stats
from statsmodels.stats.multitest import multipletests

pvals = []
for col in columns:
    t, p = stats.ttest_ind(a[col], b[col])
    pvals.append(p)
reject, p_adj, _, _ = multipletests(pvals, method="fdr_bh")
"""

_THREE_TESTS = """
from scipy import stats

r1 = stats.pearsonr(x, y)
r2 = stats.spearmanr(x, z)
r3 = stats.f_oneway(g1, g2, g3)
"""

_TWO_TESTS = """
from scipy import stats

r1 = stats.pearsonr(x, y)
r2 = stats.spearmanr(x, z)
"""

_SINGLE_TEST = """
from scipy import stats

t, p = stats.ttest_ind(control, treatment)
"""


def test_significance_test_in_a_loop_is_flagged() -> None:
    issues = check_science(_LOOPED_TEST)
    assert len(issues) == 1
    assert issues[0].category == "science"
    assert issues[0].severity == "error"
    assert "ttest_ind" in issues[0].message
    assert "family-wise" in issues[0].message


def test_looped_test_with_correction_is_silent() -> None:
    assert check_science(_LOOPED_TEST_CORRECTED) == []


def test_three_uncorrected_tests_are_flagged() -> None:
    issues = check_science(_THREE_TESTS)
    assert len(issues) == 1
    assert "3 significance tests" in issues[0].message


def test_two_uncorrected_tests_are_silent() -> None:
    """Two tests is a comparison, not a family. The threshold is three."""
    assert check_science(_TWO_TESTS) == []


def test_single_test_is_silent() -> None:
    assert check_science(_SINGLE_TEST) == []


# ---------------------------------------------------------------------------
# check_units
# ---------------------------------------------------------------------------


def test_adding_different_dimensions_is_flagged() -> None:
    issues = check_science("total = t_seconds + d_meters\n")
    assert len(issues) == 1
    assert issues[0].category == "science"
    assert "t_seconds" in issues[0].message
    assert "d_meters" in issues[0].message


def test_adding_same_dimension_is_silent() -> None:
    assert check_science("total = start_seconds + elapsed_seconds\n") == []


def test_ordering_comparison_across_dimensions_is_flagged() -> None:
    issues = check_science("if timeout_seconds > distance_meters:\n    pass\n")
    assert len(issues) == 1
    assert "Comparing" in issues[0].message


def test_equality_across_dimensions_is_silent() -> None:
    """Equality is well-defined and always False. Not worth a repair round."""
    assert check_science("flag = timeout_seconds == distance_meters\n") == []


def test_ambiguous_short_suffixes_are_silent() -> None:
    """`loss_m` is a mean far more often than a length, so `_m`, `_g` and
    `_s` are deliberately absent from the suffix map."""
    assert check_science("x = loss_m + count_g\n") == []


def test_trig_on_degrees_is_flagged() -> None:
    issues = check_science("import math\ny = math.sin(angle_degrees)\n")
    assert len(issues) == 1
    assert "radians" in issues[0].message


def test_trig_on_converted_degrees_is_silent() -> None:
    """The argument is a Call, not a Name, so the rule never reaches it."""
    assert check_science("import math\ny = math.sin(math.radians(angle_degrees))\n") == []


def test_trig_on_radians_is_silent() -> None:
    assert check_science("import math\ny = math.sin(angle_radians)\n") == []


# ---------------------------------------------------------------------------
# Entry point and pipeline contract
# ---------------------------------------------------------------------------


def test_unparseable_code_yields_no_science_issues() -> None:
    """validate_syntax owns syntax errors. Reporting them twice would send
    the repair loop a duplicate."""
    assert check_science("def broken(:\n") == []


def test_clean_code_yields_no_issues() -> None:
    assert check_science("import numpy as np\nmean = np.mean(values)\n") == []


def test_validate_code_surfaces_science_issues() -> None:
    result = validate_code("total = t_seconds + d_meters\n")
    science = [i for i in result.issues if i.category == "science"]
    assert len(science) == 1
    assert not result.ok, "a science error must drive the Stage 10 repair loop"


def test_skip_science_suppresses_the_checks() -> None:
    result = validate_code("total = t_seconds + d_meters\n", skip_science=True)
    assert [i for i in result.issues if i.category == "science"] == []


def test_science_category_is_outside_the_stage_blocking_set() -> None:
    """The load-bearing invariant.

    Stage 10 blocks on ``severity == "error" and category in ("syntax",
    "import", "security")`` (pipeline/stage_impls/_code_generation.py).
    A science finding must stay outside that set, so a false positive
    costs a repair round-trip and never a failed run. If this assertion
    ever fails, a wrong unit heuristic can kill a pipeline run.
    """
    blocking = ("syntax", "import", "security")
    issues = check_science(_LOOPED_TEST) + check_science("total = t_seconds + d_meters\n")
    assert issues, "fixture must produce findings for this test to mean anything"
    for issue in issues:
        assert issue.severity == "error"
        assert issue.category not in blocking
