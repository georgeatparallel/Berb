"""A4-5: the eval/exec pair in berb/math/verification.py.

Mathematical claims verified here are extracted from paper text, which in
this pipeline comes from arXiv documents and LLM output. The original code
used ``eval(expr, {"__builtins__": {}}, namespace)``, which is not a
sandbox — emptying __builtins__ is defeated by walking the class hierarchy
off any literal.
"""

from __future__ import annotations

import math

import pytest

from berb.math.verification import VerifiableMathContent, _safe_eval_expr


class TestSafeEvalRejectsEscapes:
    """Each payload is a documented way out of an empty-__builtins__ eval."""

    @pytest.mark.parametrize(
        "payload",
        [
            # The canonical escape: reach object.__subclasses__() and from
            # there anything that imports os.
            "().__class__.__base__.__subclasses__()",
            "(1).__class__.__mro__[1].__subclasses__()",
            # Attribute access of any kind is the escape primitive.
            "sqrt.__globals__",
            # Subscripting can index into whatever an attribute walk found.
            "[1, 2][0].__class__",
            # Callable construction / deferred execution.
            "(lambda: 1)()",
            "[x for x in (1, 2)]",
            # Direct builtin reach, in case __builtins__ is ever repopulated.
            "__import__('os').system('echo pwned')",
            "open('/etc/passwd')",
            "eval('1+1')",
        ],
    )
    def test_escape_payloads_are_rejected(self, payload: str) -> None:
        with pytest.raises((ValueError, SyntaxError)):
            _safe_eval_expr(payload, {"sqrt": math.sqrt})

    def test_unknown_name_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown name"):
            _safe_eval_expr("os", {})

    def test_indirect_call_target_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            _safe_eval_expr("(sqrt)(4).__class__", {"sqrt": math.sqrt})


class TestSafeEvalStillEvaluatesMath:
    """The gate must not break the legitimate use case it exists to serve."""

    def test_arithmetic(self) -> None:
        assert _safe_eval_expr("2 + 3 * 4", {}) == 14.0

    def test_power_and_unary(self) -> None:
        assert _safe_eval_expr("-2 ** 2 + 8", {}) == 4.0

    def test_variables_from_namespace(self) -> None:
        assert _safe_eval_expr("a * b + 1", {"a": 3.0, "b": 4.0}) == 13.0

    def test_whitelisted_function_calls(self) -> None:
        ns = {"sqrt": math.sqrt, "sin": math.sin, "pi": math.pi}
        assert _safe_eval_expr("sqrt(16)", ns) == 4.0
        assert _safe_eval_expr("sin(pi)", ns) == pytest.approx(0.0, abs=1e-9)

    def test_comparison_returns_numeric(self) -> None:
        # float(True) is 1.0 — verify_equation_numerically relies on this.
        assert _safe_eval_expr("3 > 2", {}) == 1.0

    def test_evaluate_expression_survives_hostile_input(self) -> None:
        """The public path returns NaN rather than raising or executing."""
        verifier = VerifiableMathContent()
        result = verifier._evaluate_expression("().__class__.__base__.__subclasses__()", {})
        assert math.isnan(result)

    def test_evaluate_expression_computes_real_equations(self) -> None:
        verifier = VerifiableMathContent()
        result = verifier._evaluate_expression("sqrt(a**2 + b**2)", {"a": 3.0, "b": 4.0})
        assert result == pytest.approx(5.0)


class TestAlgorithmExecIsGated:
    """_run_algorithm exec()s paper-derived code in *this* process — no
    subprocess, no sandbox boundary. It must apply the same AST gate every
    sandbox backend applies before spawning."""

    async def test_malicious_algorithm_is_rejected_before_exec(self) -> None:
        verifier = VerifiableMathContent()
        result = await verifier._run_algorithm(
            "import os\nos.system('echo pwned')\n",
            {},
        )
        assert result["converged"] is False
        assert "security gate" in result["error_msg"]

    async def test_benign_algorithm_still_runs(self) -> None:
        verifier = VerifiableMathContent()
        result = await verifier._run_algorithm(
            "result = 1 + 1\nconverged = True\n",
            {},
        )
        # Reaches exec (no security-gate rejection); whatever the
        # instrumentation reports afterwards is not this test's concern.
        assert "security gate" not in str(result.get("error_msg", ""))
