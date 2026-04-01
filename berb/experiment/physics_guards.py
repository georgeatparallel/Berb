"""Physics-Aware Code Quality Guards.

Based on PRBench (Peking U — arXiv:2603.27646) failure analysis:

Common Agent Failure Patterns in Computational Physics:
1. Dense matrices instead of sparse representations
2. Unvectorized Python loops instead of NumPy vectorization
3. Explicit Kronecker products instead of tensor reshaping
4. Missing numerical precision checks (float64)
5. No convergence tests
6. Loosely organized internal variables

This module prevents these failures via:
- Static AST analysis
- Pattern matching for anti-patterns
- LLM-based fix suggestions
- Domain-specific guards

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.experiment.physics_guards import PhysicsCodeGuard
    
    guard = PhysicsCodeGuard()
    issues = await guard.check_experiment_code(code, domain="physics")
    
    if issues:
        fixed_code = await guard.suggest_fixes(code, issues)
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CodeQualityIssue:
    """Identified code quality issue.
    
    Attributes:
        issue_type: Type of issue (e.g., "dense_matrix_for_sparse")
        severity: Severity level ("critical", "warning", "info")
        line_number: Line number where issue was found (if available)
        description: Human-readable description
        suggestion: Suggested fix
        anti_pattern: Anti-pattern name from PRBench
    """
    issue_type: str
    severity: str  # "critical", "warning", "info"
    line_number: int | None
    description: str
    suggestion: str
    anti_pattern: str
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "issue_type": self.issue_type,
            "severity": self.severity,
            "line_number": self.line_number,
            "description": self.description,
            "suggestion": self.suggestion,
            "anti_pattern": self.anti_pattern,
        }


class PhysicsCodeGuard:
    """Prevent common computational physics coding failures.
    
    Based on PRBench (Peking U) analysis of agent failure patterns
    in physics paper reproduction tasks.
    
    Anti-Patterns Detected:
    - dense_matrix_for_sparse: Using dense matrices for sparse problems
    - unvectorized_loops: Python loops instead of NumPy vectorization
    - explicit_kronecker_product: Explicit Kronecker product construction
    - missing_numerical_precision: Missing float64 dtype specification
    - no_convergence_test: Missing convergence criteria
    - loose_variable_organization: Poorly organized internal variables
    
    Usage:
        guard = PhysicsCodeGuard()
        issues = await guard.check_experiment_code(code, domain="physics")
        
        if issues:
            logger.warning(f"Found {len(issues)} issues")
            for issue in issues:
                logger.warning(f"  - {issue.issue_type}: {issue.description}")
    """
    
    # PRBench-identified anti-patterns with metadata
    ANTI_PATTERNS = {
        "dense_matrix_for_sparse": {
            "description": "Using dense matrices for sparse problems",
            "check": "_check_sparse_usage",
            "fix": "Use scipy.sparse.csr_matrix or csc_matrix for sparse matrices",
            "severity": "warning",
        },
        "unvectorized_loops": {
            "description": "Python loops instead of NumPy vectorization",
            "check": "_check_vectorization",
            "fix": "Use NumPy array operations instead of Python loops",
            "severity": "warning",
        },
        "explicit_kronecker_product": {
            "description": "Explicit Kronecker product construction",
            "check": "_check_kronecker",
            "fix": "Use tensor reshaping or einsum instead of np.kron",
            "severity": "info",
        },
        "missing_numerical_precision": {
            "description": "Missing float64 dtype specification",
            "check": "_check_precision",
            "fix": "Specify dtype=np.float64 explicitly for numerical stability",
            "severity": "warning",
        },
        "no_convergence_test": {
            "description": "Iterative algorithm without convergence test",
            "check": "_check_convergence",
            "fix": "Add convergence criterion with tolerance (e.g., tol=1e-6)",
            "severity": "critical",
        },
        "loose_variable_organization": {
            "description": "Function with too many local variables",
            "check": "_check_organization",
            "fix": "Use dataclass or named tuple to organize related variables",
            "severity": "info",
        },
    }
    
    def __init__(self, domain: str = "physics"):
        """Initialize physics code guard.
        
        Args:
            domain: Domain context (physics, chaos, hamiltonian, etc.)
        """
        self.domain = domain
        logger.info(f"Initialized PhysicsCodeGuard for domain: {domain}")
    
    async def check_experiment_code(
        self,
        code: str,
        domain: str | None = None,
    ) -> list[CodeQualityIssue]:
        """Scan generated code for known anti-patterns.
        
        Args:
            code: Python code to check
            domain: Domain context (overrides constructor default)
            
        Returns:
            List of identified issues
            
        Raises:
            SyntaxError: If code has syntax errors
        """
        domain = domain or self.domain
        issues = []
        
        # Parse AST
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [CodeQualityIssue(
                issue_type="syntax_error",
                severity="critical",
                line_number=e.lineno,
                description=f"Syntax error: {e.msg}",
                suggestion="Fix syntax error before proceeding",
                anti_pattern="syntax_error",
            )]
        
        # Run all checks
        for anti_pattern, config in self.ANTI_PATTERNS.items():
            check_method = getattr(self, config["check"], None)
            if check_method:
                found_issues = await check_method(tree, code, domain)
                issues.extend(found_issues)
        
        # Log summary
        if issues:
            critical = sum(1 for i in issues if i.severity == "critical")
            warnings = sum(1 for i in issues if i.severity == "warning")
            info = sum(1 for i in issues if i.severity == "info")
            
            logger.warning(
                f"Physics code guard found {len(issues)} issues: "
                f"{critical} critical, {warnings} warnings, {info} info"
            )
        else:
            logger.info(f"Physics code guard: no issues found in {domain} code")
        
        return issues
    
    async def suggest_efficient_alternative(
        self,
        code_snippet: str,
        issue: CodeQualityIssue,
    ) -> str:
        """Suggest efficient alternative for identified issue.
        
        Args:
            code_snippet: Problematic code
            issue: Identified issue
            
        Returns:
            Suggested fix with explanation
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model="claude-3-sonnet")
        
        prompt = f"""
The following code has a performance/correctness issue:

Issue: {issue.issue_type}
Description: {issue.description}
Anti-pattern: {issue.anti_pattern}

Problematic code:
```python
{code_snippet}
```

Provide an efficient, physics-aware fix using appropriate techniques:
- For sparse matrices: scipy.sparse (csr_matrix, csc_matrix)
- For vectorization: NumPy array operations, broadcasting
- For tensor operations: einsum, tensor reshaping
- For precision: dtype=np.float64
- For convergence: tolerance-based stopping criteria
- For organization: dataclasses, named tuples

Show the corrected code with detailed explanation.
"""
        
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are an expert in computational physics programming.",
        )
        
        return response.content
    
    async def suggest_fixes(
        self,
        code: str,
        issues: list[CodeQualityIssue],
    ) -> str:
        """Suggest fixes for all identified issues.
        
        Args:
            code: Original code
            issues: List of identified issues
            
        Returns:
            Code with suggested fixes
        """
        from berb.llm.client import get_llm_client
        
        if not issues:
            return code
        
        client = get_llm_client(model="claude-3-sonnet")
        
        issues_str = "\n\n".join([
            f"Issue {i+1}: {issue.issue_type}\n"
            f"Line: {issue.line_number}\n"
            f"Description: {issue.description}\n"
            f"Suggestion: {issue.suggestion}"
            for i, issue in enumerate(issues)
        ])
        
        prompt = f"""
Refactor the following code to fix all identified issues:

Original code:
```python
{code}
```

Issues to fix:
{issues_str}

Provide the complete refactored code with all fixes applied.
"""
        
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are an expert programmer refactoring physics code.",
        )
        
        # Extract code from response
        content = response.content
        if "```python" in content:
            start = content.find("```python") + len("```python")
            end = content.find("```", start)
            if end > start:
                return content[start:end].strip()
        
        return content
    
    async def _check_sparse_usage(
        self,
        tree: ast.AST,
        code: str,
        domain: str,
    ) -> list[CodeQualityIssue]:
        """Check for sparse matrix usage.
        
        Looks for large matrix creation without sparse representation.
        
        Args:
            tree: AST of code
            code: Original code string
            domain: Domain context
            
        Returns:
            List of issues
        """
        issues = []
        
        # Look for large matrix creation without sparse
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    # Check for np.zeros, np.ones, np.empty
                    if node.func.attr in ["zeros", "ones", "empty", "array"]:
                        # Check if arguments suggest large matrix
                        if self._is_large_matrix_call(node):
                            # Check if sparse is used
                            uses_sparse = self._check_sparse_import(tree)
                            
                            if not uses_sparse:
                                issues.append(CodeQualityIssue(
                                    issue_type="dense_matrix_for_sparse",
                                    severity="warning",
                                    line_number=node.lineno,
                                    description="Large dense matrix may be inefficient for sparse problems",
                                    suggestion="Consider scipy.sparse if matrix is sparse",
                                    anti_pattern="dense_matrix_for_sparse",
                                ))
        
        return issues
    
    async def _check_vectorization(
        self,
        tree: ast.AST,
        code: str,
        domain: str,
    ) -> list[CodeQualityIssue]:
        """Check for unvectorized loops.
        
        Looks for Python loops that could be vectorized.
        
        Args:
            tree: AST of code
            code: Original code string
            domain: Domain context
            
        Returns:
            List of issues
        """
        issues = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.For):
                # Check if loop body contains element-wise operations
                if self._has_elementwise_operations(node):
                    issues.append(CodeQualityIssue(
                        issue_type="unvectorized_loops",
                        severity="warning",
                        line_number=node.lineno if hasattr(node, 'lineno') else None,
                        description="Loop may be vectorizable using NumPy operations",
                        suggestion="Use NumPy array operations instead of Python loops",
                        anti_pattern="unvectorized_loops",
                    ))
        
        return issues
    
    async def _check_kronecker(
        self,
        tree: ast.AST,
        code: str,
        domain: str,
    ) -> list[CodeQualityIssue]:
        """Check for explicit Kronecker products.
        
        Looks for np.kron usage that could be replaced.
        
        Args:
            tree: AST of code
            code: Original code string
            domain: Domain context
            
        Returns:
            List of issues
        """
        issues = []
        
        # Look for np.kron usage
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "kron":
                        issues.append(CodeQualityIssue(
                            issue_type="explicit_kronecker_product",
                            severity="info",
                            line_number=node.lineno if hasattr(node, 'lineno') else None,
                            description="Explicit Kronecker product may be inefficient",
                            suggestion="Consider tensor reshaping or np.einsum",
                            anti_pattern="explicit_kronecker_product",
                        ))
        
        return issues
    
    async def _check_precision(
        self,
        tree: ast.AST,
        code: str,
        domain: str,
    ) -> list[CodeQualityIssue]:
        """Check for numerical precision.
        
        Looks for float arrays without explicit dtype.
        
        Args:
            tree: AST of code
            code: Original code string
            domain: Domain context
            
        Returns:
            List of issues
        """
        issues = []
        
        # Look for float arrays without dtype
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in ["array", "zeros", "ones", "empty", "array_like"]:
                        # Check if dtype is specified
                        has_dtype = any(
                            isinstance(kw, ast.keyword) and kw.arg == "dtype"
                            for kw in node.keywords
                        )
                        if not has_dtype:
                            issues.append(CodeQualityIssue(
                                issue_type="missing_numerical_precision",
                                severity="warning",
                                line_number=node.lineno if hasattr(node, 'lineno') else None,
                                description="Missing dtype specification may cause numerical instability",
                                suggestion="Add dtype=np.float64 for numerical stability",
                                anti_pattern="missing_numerical_precision",
                            ))
        
        return issues
    
    async def _check_convergence(
        self,
        tree: ast.AST,
        code: str,
        domain: str,
    ) -> list[CodeQualityIssue]:
        """Check for convergence tests.
        
        Looks for iterative algorithms without convergence criteria.
        
        Args:
            tree: AST of code
            code: Original code string
            domain: Domain context
            
        Returns:
            List of issues
        """
        issues = []
        
        # Look for while loops (iterative algorithms)
        has_while = any(
            isinstance(node, ast.While)
            for node in ast.walk(tree)
        )
        
        # Check for convergence indicators
        convergence_keywords = [
            "tol", "tolerance", "converge", "convergence",
            "epsilon", "eps", "atol", "rtol",
            "max_iter", "maxiter", "max_iterations",
        ]
        
        has_convergence = any(
            keyword in code.lower()
            for keyword in convergence_keywords
        )
        
        if has_while and not has_convergence:
            issues.append(CodeQualityIssue(
                issue_type="no_convergence_test",
                severity="critical",
                line_number=None,
                description="Iterative algorithm (while loop) without convergence test",
                suggestion="Add convergence criterion with tolerance (e.g., tol=1e-6)",
                anti_pattern="no_convergence_test",
            ))
        
        return issues
    
    async def _check_organization(
        self,
        tree: ast.AST,
        code: str,
        domain: str,
    ) -> list[CodeQualityIssue]:
        """Check variable organization.
        
        Looks for functions with too many local variables.
        
        Args:
            tree: AST of code
            code: Original code string
            domain: Domain context
            
        Returns:
            List of issues
        """
        issues = []
        
        # Look for functions with many local variables
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Count assignments
                assignments = sum(
                    1 for child in ast.walk(node)
                    if isinstance(child, ast.Assign)
                )
                
                # Threshold: more than 10 assignments suggests poor organization
                if assignments > 10:
                    issues.append(CodeQualityIssue(
                        issue_type="loose_variable_organization",
                        severity="info",
                        line_number=node.lineno if hasattr(node, 'lineno') else None,
                        description=f"Function has {assignments} variable assignments",
                        suggestion="Consider using dataclass or named tuple to organize variables",
                        anti_pattern="loose_variable_organization",
                    ))
        
        return issues
    
    def _is_large_matrix_call(self, node: ast.Call) -> bool:
        """Check if matrix creation call suggests large matrix.
        
        Args:
            node: AST call node
            
        Returns:
            True if matrix appears large
        """
        # Simplified check - looks for 2D shape
        if len(node.args) >= 2:
            return True
        
        # Check for tuple argument with 2+ elements
        if node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, (ast.List, ast.Tuple)):
                if len(first_arg.elts) >= 2:
                    return True
        
        return False
    
    def _has_elementwise_operations(self, node: ast.For) -> bool:
        """Check if loop body has element-wise operations.
        
        Args:
            node: For loop node
            
        Returns:
            True if element-wise operations detected
        """
        for child in ast.walk(node):
            if isinstance(child, ast.BinOp):
                # Check for indexing operations
                if isinstance(child.left, ast.Subscript) or \
                   isinstance(child.right, ast.Subscript):
                    return True
        return False
    
    def _check_sparse_import(self, tree: ast.AST) -> bool:
        """Check if scipy.sparse is imported.
        
        Args:
            tree: AST of code
            
        Returns:
            True if sparse is imported
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "sparse" in alias.name:
                        return True
            elif isinstance(node, ast.ImportFrom):
                if node.module and "sparse" in node.module:
                    return True
        return False


__all__ = [
    "PhysicsCodeGuard",
    "CodeQualityIssue",
]
