"""Verification-First Mathematical Content.

Based on HorizonMath (arXiv:2603.15617) principle:
"Discovery is hard, verification is easy."

Key Insight: Generate mathematical claims, then verify computationally.
Separate the "insight" step from the "verification" step.

This prevents:
- False theorem claims
- Incorrect equations
- Unverified convergence claims
- Hallucinated proofs

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.math import VerifiableMathContent, verify_theorem

    verifier = VerifiableMathContent()
    theorem = await verifier.generate_and_verify_theorem(
        statement="Pythagorean theorem",
        context="right triangle geometry",
    )
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Safe expression evaluation
# ---------------------------------------------------------------------------
#
# Mathematical claims verified here are extracted from paper text, which in
# this pipeline originates from arXiv documents and LLM output. Evaluating
# them with eval() — even with __builtins__ emptied — is a remote code
# execution primitive, because attribute access on any literal reaches the
# class hierarchy:
#
#     ().__class__.__base__.__subclasses__()   -> arbitrary classes -> os
#
# The allowlist below is expressed over AST node *types*, so anything not
# explicitly permitted is rejected by construction rather than by pattern
# matching on the source text (which is bypassable).

_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.BoolOp,
    ast.IfExp,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Tuple,
    ast.List,
    # Operators
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.And,
    ast.Or,
)
"""AST nodes permitted inside a verifiable mathematical expression.

Deliberately excluded: ast.Attribute (the __class__ escape), ast.Subscript,
ast.Starred, lambdas, comprehensions, assignments, and f-strings.
"""


def _safe_eval_expr(expr: str, namespace: dict[str, Any]) -> float:
    """Evaluate a mathematical expression without exposing an RCE primitive.

    Only the node types in ``_ALLOWED_NODES`` are permitted, and calls may
    only target plain names already bound in *namespace* — so ``sqrt(2)``
    works while ``__import__('os')`` or ``().__class__`` do not.

    Raises:
        ValueError: if the expression uses a disallowed construct or an
            unknown name. Never returns a partially-evaluated result.
    """
    tree = ast.parse(expr, mode="eval")

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"disallowed expression construct: {type(node).__name__}")
        if isinstance(node, ast.Call):
            # Only direct calls to whitelisted names; no obj.method(), no
            # computed callees.
            if not isinstance(node.func, ast.Name):
                raise ValueError("only direct calls to named functions are allowed")
            if node.keywords:
                raise ValueError("keyword arguments are not allowed")
        if isinstance(node, ast.Name) and node.id not in namespace:
            raise ValueError(f"unknown name in expression: {node.id!r}")

    # __builtins__ is still emptied: belt and braces, since the allowlist
    # above has already made the builtins unreachable.
    # Reason for nosec: every node was allowlisted above, so no attribute
    # access, subscript, or non-whitelisted call can reach this point.
    result = eval(  # noqa: S307  # nosec B307
        compile(tree, "<equation>", "eval"),
        {"__builtins__": {}},
        namespace,
    )
    return float(result)


@dataclass
class VerifiedTheorem:
    """Computationally verified theorem.

    Attributes:
        statement: Theorem statement
        proof: Proof text
        verification_status: "verified", "failed", or "partial"
        numerical_tests: List of numerical test results
        boundary_conditions: List of boundary condition checks
        confidence: Confidence score (0-1)
    """

    statement: str
    proof: str
    verification_status: str  # "verified", "failed", "partial"
    numerical_tests: list[dict[str, Any]] = field(default_factory=list)
    boundary_conditions: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "statement": self.statement,
            "proof": self.proof,
            "verification_status": self.verification_status,
            "numerical_tests": self.numerical_tests,
            "boundary_conditions": self.boundary_conditions,
            "confidence": self.confidence,
        }


@dataclass
class VerificationReport:
    """Verification report for mathematical content.

    Attributes:
        theorem: Verified theorem
        test_results: List of test results
        overall_status: Overall verification status
        issues: List of identified issues
    """

    theorem: VerifiedTheorem
    test_results: list[dict[str, Any]] = field(default_factory=list)
    overall_status: str = "unknown"
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "theorem": self.theorem.to_dict(),
            "test_results": self.test_results,
            "overall_status": self.overall_status,
            "issues": self.issues,
        }


class VerifiableMathContent:
    """HorizonMath-style computational verification.

    Features:
    - Generate theorem + proof, then verify computationally
    - Numerical equation testing
    - Convergence claim validation
    - Boundary condition checking

    Usage:
        verifier = VerifiableMathContent()
        theorem = await verifier.generate_and_verify_theorem(
            statement="a^2 + b^2 = c^2 for right triangles",
            context="Euclidean geometry",
        )
    """

    def __init__(self, model: str = "claude-3-opus"):
        """Initialize math verifier.

        Args:
            model: LLM model for theorem generation
        """
        self.model = model
        logger.info(f"Initialized VerifiableMathContent with {model}")

    async def generate_and_verify_theorem(
        self,
        statement: str,
        context: str,
    ) -> VerifiedTheorem:
        """Generate theorem + proof, then verify computationally.

        Process:
        1. Generate theorem + proof (reasoning model)
        2. Extract testable claims
        3. Run numerical verification
        4. Check boundary conditions
        5. Compute confidence score

        Args:
            statement: Theorem statement
            context: Mathematical context

        Returns:
            Verified theorem with test results
        """
        from berb.llm.client import get_llm_client

        # Step 1: Generate theorem + proof
        client = get_llm_client(model=self.model)

        proof_prompt = f"""
Prove this theorem rigorously:

Statement: {statement}
Context: {context}

Provide:
1. Formal statement with assumptions
2. Complete proof
3. Key equations/identities used
4. Boundary conditions
5. Testable numerical claims
"""

        proof_response = await client.chat(
            messages=[{"role": "user", "content": proof_prompt}],
            system="You are a mathematician providing rigorous proofs.",
        )

        # Step 2: Extract testable claims
        claims = await self._extract_testable_claims(
            proof_response.content,
            statement,
        )

        # Step 3: Run numerical tests
        test_results = []
        for claim in claims:
            test_result = await self._test_claim_numerically(claim)
            test_results.append(test_result)

        # Step 4: Check boundary conditions
        boundary_results = await self._check_boundary_conditions(
            statement,
            proof_response.content,
        )

        # Step 5: Compute confidence
        passed_tests = sum(1 for r in test_results if r.get("passed", False))
        total_tests = len(test_results)

        confidence = passed_tests / total_tests if total_tests > 0 else 0.0

        # Determine status
        if confidence == 1.0 and total_tests > 0:
            status = "verified"
        elif confidence >= 0.7:
            status = "partial"
        else:
            status = "failed"

        theorem = VerifiedTheorem(
            statement=statement,
            proof=proof_response.content,
            verification_status=status,
            numerical_tests=test_results,
            boundary_conditions=boundary_results,
            confidence=confidence,
        )

        logger.info(
            f"Theorem verification: {statement[:50]}... → {status} "
            f"({passed_tests}/{total_tests} tests passed, confidence={confidence:.2f})"
        )

        return theorem

    async def verify_equation_numerically(
        self,
        equation: str,
        test_values: dict[str, float],
        tolerance: float = 1e-6,
    ) -> bool:
        """Plug numbers into both sides of equation.

        If they don't match → equation is wrong.

        Args:
            equation: Equation to verify (e.g., "a^2 + b^2 = c^2")
            test_values: Test values for variables
            tolerance: Numerical tolerance

        Returns:
            True if equation holds for test values
        """
        import numpy as np

        # Parse equation
        if "=" not in equation:
            logger.warning(f"No '=' in equation: {equation}")
            return False

        lhs_str, rhs_str = equation.split("=")

        try:
            # Evaluate both sides
            lhs = self._evaluate_expression(lhs_str.strip(), test_values)
            rhs = self._evaluate_expression(rhs_str.strip(), test_values)

            # Compare
            if isinstance(lhs, np.ndarray) or isinstance(rhs, np.ndarray):
                return np.allclose(lhs, rhs, atol=tolerance)
            else:
                return abs(lhs - rhs) < tolerance

        except Exception as e:
            logger.warning(f"Failed to evaluate equation: {e}")
            return False

    async def verify_convergence_claim(
        self,
        algorithm_code: str,
        test_cases: list[dict[str, Any]],
        max_iterations: int = 1000,
    ) -> dict[str, Any]:
        """Run algorithm on known inputs, verify convergence.

        Args:
            algorithm_code: Algorithm Python code
            test_cases: Test cases with inputs and expected convergence
            max_iterations: Maximum iterations allowed

        Returns:
            Convergence report
        """
        import asyncio

        async def test_one(test_case: dict) -> dict:
            """Test single convergence case."""
            try:
                # Execute algorithm
                result = await self._run_algorithm(
                    algorithm_code,
                    test_case.get("input", {}),
                    max_iterations,
                )

                # Check convergence
                converged = result.get("converged", False)

                return {
                    "input": test_case.get("input", {}),
                    "converged": converged,
                    "iterations": result.get("iterations", 0),
                    "final_error": result.get("error", float("inf")),
                    "expected_rate": test_case.get("expected_rate", "unknown"),
                }
            except Exception as e:
                return {
                    "input": test_case.get("input", {}),
                    "converged": False,
                    "error": str(e),
                }

        # Run all tests in parallel
        results = await asyncio.gather(*[test_one(tc) for tc in test_cases])

        all_converged = all(r.get("converged", False) for r in results)
        convergence_rate = sum(1 for r in results if r.get("converged", False)) / len(
            results
        )

        return {
            "test_results": results,
            "all_converged": all_converged,
            "convergence_rate": convergence_rate,
            "total_tests": len(results),
        }

    async def _extract_testable_claims(
        self,
        proof: str,
        statement: str,
    ) -> list[dict[str, str]]:
        """Extract testable claims from proof.

        Args:
            proof: Proof text
            statement: Theorem statement

        Returns:
            List of testable claims
        """
        from berb.llm.client import get_llm_client

        client = get_llm_client(model=self.model)

        prompt = f"""
Extract testable mathematical claims from this proof:

Statement: {statement}
Proof: {proof}

For each claim, provide:
1. The claim (equation or identity)
2. Variables involved
3. Test values to use

Format as JSON list:
[
    {{"claim": "a^2 + b^2 = c^2", "variables": ["a", "b", "c"], "test_values": {{"a": 3, "b": 4, "c": 5}}}}
]
"""

        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
        )

        import json

        try:
            # Extract JSON
            content = response.content
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                return json.loads(json_str)
        except Exception as e:
            logger.warning(f"Failed to extract claims: {e}")

        return []

    async def _test_claim_numerically(
        self,
        claim: dict[str, str],
    ) -> dict[str, Any]:
        """Test single claim numerically.

        Args:
            claim: Claim dictionary

        Returns:
            Test result
        """
        equation = claim.get("claim", "")
        test_values = claim.get("test_values", {})

        passed = await self.verify_equation_numerically(equation, test_values)

        return {
            "claim": equation,
            "test_values": test_values,
            "passed": passed,
        }

    async def _check_boundary_conditions(
        self,
        statement: str,
        proof: str,
    ) -> list[str]:
        """Check boundary conditions.

        Args:
            statement: Theorem statement
            proof: Proof text

        Returns:
            List of boundary condition results
        """
        from berb.llm.client import get_llm_client

        client = get_llm_client(model=self.model)

        prompt = f"""
Identify boundary conditions for this theorem:

Statement: {statement}
Proof: {proof}

List edge cases and boundary conditions that should be checked.
Format as a list of conditions.
"""

        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse as list
        lines = response.content.strip().split("\n")
        conditions = [
            line.strip().lstrip("-*•").strip() for line in lines if line.strip()
        ]

        return conditions[:10]  # Limit to 10 conditions

    def _evaluate_expression(
        self,
        expr: str,
        values: dict[str, float],
    ) -> float:
        """Safely evaluate mathematical expression.

        Args:
            expr: Expression string
            values: Variable values

        Returns:
            Evaluated result
        """
        import numpy as np

        # Create safe namespace
        namespace = {
            **values,
            "np": np,
            "sin": np.sin,
            "cos": np.cos,
            "tan": np.tan,
            "exp": np.exp,
            "log": np.log,
            "log10": np.log10,
            "sqrt": np.sqrt,
            "abs": abs,
            "sum": sum,
            "pi": np.pi,
            "e": np.e,
        }

        # Evaluate.
        #
        # SECURITY: `expr` originates from claims extracted out of paper text
        # (see evaluation_framework._extract_math_claims), i.e. from arXiv
        # documents and LLM output — untrusted input. The previous
        # implementation used eval(expr, {"__builtins__": {}}, namespace),
        # which is NOT a sandbox: emptying __builtins__ is defeated by the
        # standard ().__class__.__base__.__subclasses__() walk, which reaches
        # arbitrary classes and from there os.system. _safe_eval_expr parses
        # the expression and rejects every construct that could escape
        # (attribute access, subscripts, comprehensions, lambdas, non-
        # whitelisted calls) before any evaluation happens.
        try:
            return _safe_eval_expr(expr, namespace)
        except (
            ValueError,
            SyntaxError,
            TypeError,
            ZeroDivisionError,
            AttributeError,
        ) as e:
            logger.warning("Expression evaluation failed: %s - %s", expr, e)
            return float("nan")

    async def _run_algorithm(
        self,
        algorithm_code: str,
        input_data: dict[str, Any],
        max_iterations: int = 1000,
    ) -> dict[str, Any]:
        """Run algorithm and collect metrics.

        Args:
            algorithm_code: Algorithm Python code
            input_data: Input data
            max_iterations: Maximum iterations

        Returns:
            Execution results
        """

        # Create execution context
        exec_globals = {
            "input": input_data,
            "result": None,
            "iterations": 0,
            "error": float("inf"),
            "converged": False,
            "max_iterations": max_iterations,
            "np": __import__("numpy"),
        }

        # SECURITY: algorithm_code is untrusted (paper- and LLM-derived), and
        # exec() runs it in *this* process — no subprocess, no sandbox
        # boundary. Route it through the same AST gate every sandbox backend
        # uses before spawning, so a banned import or __builtins__ escape is
        # rejected here too rather than only at the subprocess boundary.
        #
        # Gate the ORIGINAL code, not the instrumented version: the
        # convergence instrumentation this class appends calls globals(),
        # which the validator (correctly) rejects in untrusted input. Only
        # the caller-supplied half is untrusted.
        from berb.experiment.sandbox import check_code_security

        security_error = check_code_security(algorithm_code, label="algorithm")
        if security_error is not None:
            logger.warning("Algorithm rejected by security gate: %s", security_error)
            return {
                "converged": False,
                "error_msg": f"rejected by security gate: {security_error}",
            }

        # Instrument algorithm to track convergence (trusted: written here).
        instrumented_code = self._instrument_algorithm(algorithm_code)

        try:
            # Reason for nosec: check_code_security() above is the same AST
            # gate every sandbox backend applies before spawning.
            exec(instrumented_code, exec_globals)  # nosec B102
        except Exception as e:
            return {
                "converged": False,
                "error_msg": str(e),
            }

        return {
            "result": exec_globals.get("result"),
            "iterations": exec_globals.get("iterations", 0),
            "error": exec_globals.get("error", float("inf")),
            "converged": exec_globals.get("converged", False),
        }

    def _instrument_algorithm(self, algorithm_code: str) -> str:
        """Add instrumentation to algorithm for tracking.

        Args:
            algorithm_code: Algorithm code

        Returns:
            Instrumented code
        """
        # Add convergence tracking
        instrumentation = """
# Convergence tracking
if 'iterations' not in globals():
    iterations = 0
if 'error' not in globals():
    error = float('inf')
if 'converged' not in globals():
    converged = False
if 'tol' not in globals():
    tol = 1e-6

# Check convergence
if error < tol and iterations < max_iterations:
    converged = True
"""
        return algorithm_code + "\n" + instrumentation


async def verify_theorem(
    statement: str,
    context: str,
    model: str = "claude-3-opus",
) -> VerifiedTheorem:
    """Convenience function to verify a theorem.

    Args:
        statement: Theorem statement
        context: Mathematical context
        model: LLM model for generation

    Returns:
        Verified theorem
    """
    verifier = VerifiableMathContent(model=model)
    return await verifier.generate_and_verify_theorem(statement, context)


async def verify_equation(
    equation: str,
    test_values: dict[str, float],
    tolerance: float = 1e-6,
) -> bool:
    """Convenience function to verify an equation.

    Args:
        equation: Equation to verify
        test_values: Test values
        tolerance: Numerical tolerance

    Returns:
        True if equation holds
    """
    verifier = VerifiableMathContent()
    return await verifier.verify_equation_numerically(equation, test_values, tolerance)


__all__ = [
    "VerifiableMathContent",
    "VerifiedTheorem",
    "VerificationReport",
    "verify_theorem",
    "verify_equation",
]
