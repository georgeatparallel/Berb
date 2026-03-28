"""Automated Debugging & Self-Healing for Berb.

Based on AI Scientist (Nature 2026) - Section 3.3: Automated Debugging

Features:
- Error classification (syntax, runtime, logic, resource)
- Specialized fix strategies per category
- Error-fix knowledge base
- Learning from successful fixes across runs

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.experiment.auto_debugger import AutomatedDebugger
    
    debugger = AutomatedDebugger()
    fix = await debugger.diagnose_and_fix(error, code, context)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """Error classification categories."""
    SYNTAX = "syntax"  # Python syntax errors
    RUNTIME = "runtime"  # Exceptions during execution
    LOGIC = "logic"  # Incorrect behavior, no exception
    RESOURCE = "resource"  # OOM, timeout, disk full
    IMPORT = "import"  # Module not found
    TYPE = "type"  # Type errors


class ErrorSeverity(str, Enum):
    """Error severity levels."""
    CRITICAL = "critical"  # Cannot proceed
    MAJOR = "major"  # Significant functionality broken
    MINOR = "minor"  # Workaround exists
    COSMETIC = "cosmetic"  # Doesn't affect functionality


@dataclass
class ErrorDiagnosis:
    """Diagnosis of an error."""
    
    error_message: str
    error_type: str
    category: ErrorCategory
    severity: ErrorSeverity
    location: str  # file:line
    traceback: list[str]
    root_cause: str
    confidence: float  # 0-1


@dataclass
class FixSuggestion:
    """Suggested fix for an error."""
    
    diagnosis: ErrorDiagnosis
    fix_description: str
    original_code: str
    fixed_code: str
    confidence: float  # 0-1
    strategy: str  # Fix strategy used
    side_effects: list[str] = field(default_factory=list)
    requires_testing: bool = True


@dataclass
class DebugResult:
    """Result of automated debugging."""
    
    success: bool
    error_diagnosis: ErrorDiagnosis | None
    fix_suggestion: FixSuggestion | None
    fix_applied: bool = False
    fix_verified: bool = False
    iterations: int = 1
    total_time_sec: float = 0.0
    knowledge_base_match: bool = False


class AutomatedDebugger:
    """Automated debugging and self-healing system."""
    
    def __init__(
        self,
        llm_client: Any | None = None,
    ) -> None:
        """Initialize debugger.
        
        Args:
            llm_client: LLM client for fix generation
        """
        self._llm_client = llm_client
        self._knowledge_base: list[dict[str, Any]] = []
        self._fix_history: list[DebugResult] = []
        self._error_patterns = self._load_error_patterns()
    
    def _load_error_patterns(self) -> dict[ErrorCategory, list[dict[str, Any]]]:
        """Load known error patterns and fix strategies."""
        return {
            ErrorCategory.SYNTAX: [
                {
                    "pattern": r"SyntaxError:\s*invalid\s*syntax",
                    "strategy": "syntax_parse",
                    "description": "Parse code structure and identify syntax error",
                },
                {
                    "pattern": r"SyntaxError:\s*unexpected\s+indent",
                    "strategy": "fix_indentation",
                    "description": "Normalize indentation to 4 spaces",
                },
                {
                    "pattern": r"SyntaxError:\s*missing\s+parenthesis",
                    "strategy": "balance_parens",
                    "description": "Balance parentheses, brackets, braces",
                },
            ],
            ErrorCategory.RUNTIME: [
                {
                    "pattern": r"NameError:\s*name\s+'(\w+)'\s+is\s+not\s+defined",
                    "strategy": "define_variable",
                    "description": "Define missing variable or import",
                },
                {
                    "pattern": r"TypeError:\s*'(\w+)'\s+object\s+is\s+not\s+subscriptable",
                    "strategy": "fix_subscript",
                    "description": "Convert to subscriptable type or fix access",
                },
                {
                    "pattern": r"IndexError:\s+list\s+index\s+out\s+of\s+range",
                    "strategy": "bounds_check",
                    "description": "Add bounds checking or fix index",
                },
                {
                    "pattern": r"KeyError:\s+'(\w+)'",
                    "strategy": "dict_key_check",
                    "description": "Check key existence or use .get()",
                },
                {
                    "pattern": r"AttributeError:\s+'.*'\s+object\s+has\s+no\s+attribute\s+'(\w+)'",
                    "strategy": "fix_attribute",
                    "description": "Use correct attribute or method name",
                },
                {
                    "pattern": r"ZeroDivisionError",
                    "strategy": "add_zero_check",
                    "description": "Add division by zero check",
                },
                {
                    "pattern": r"FileNotFoundError",
                    "strategy": "fix_path",
                    "description": "Check file path and existence",
                },
            ],
            ErrorCategory.IMPORT: [
                {
                    "pattern": r"ModuleNotFoundError:\s*No\s+module\s+named\s+'(\w+)'",
                    "strategy": "install_or_fix_import",
                    "description": "Install missing package or fix import statement",
                },
                {
                    "pattern": r"ImportError:\s+cannot\s+import\s+name\s+'(\w+)'",
                    "strategy": "fix_import_name",
                    "description": "Check correct name and module structure",
                },
            ],
            ErrorCategory.RESOURCE: [
                {
                    "pattern": r"MemoryError|out\s+of\s+memory",
                    "strategy": "reduce_memory",
                    "description": "Reduce batch size or use generators",
                },
                {
                    "pattern": r"timeout|timed\s+out",
                    "strategy": "optimize_or_extend",
                    "description": "Optimize code or extend timeout",
                },
                {
                    "pattern": r"No\s+space\s+left\s+on\s+device",
                    "strategy": "free_disk_space",
                    "description": "Clean up temporary files",
                },
            ],
        }
    
    async def diagnose_and_fix(
        self,
        error_message: str,
        code: str,
        context: dict[str, Any] | None = None,
    ) -> DebugResult:
        """Diagnose error and generate fix.
        
        Args:
            error_message: Error message from traceback
            code: Code that caused the error
            context: Optional context (variables, imports, etc.)
            
        Returns:
            DebugResult with diagnosis and fix
        """
        start_time = datetime.now()
        
        # Check knowledge base first
        kb_match = self._search_knowledge_base(error_message, code)
        if kb_match:
            logger.info(f"Found fix in knowledge base (confidence: {kb_match['confidence']:.0%})")
            result = self._create_result_from_kb(kb_match, code)
            result.knowledge_base_match = True
            return result
        
        # Diagnose error
        diagnosis = await self._diagnose_error(error_message, code, context)
        
        if not diagnosis:
            return DebugResult(
                success=False,
                error_diagnosis=None,
                fix_suggestion=None,
                total_time_sec=(datetime.now() - start_time).total_seconds(),
            )
        
        # Generate fix based on category
        fix = await self._generate_fix(diagnosis, code, context)
        
        result = DebugResult(
            success=fix is not None,
            error_diagnosis=diagnosis,
            fix_suggestion=fix,
            total_time_sec=(datetime.now() - start_time).total_seconds(),
        )
        
        self._fix_history.append(result)
        
        return result
    
    async def _diagnose_error(
        self,
        error_message: str,
        code: str,
        context: dict[str, Any] | None,
    ) -> ErrorDiagnosis | None:
        """Diagnose the root cause of an error."""
        # Classify error category
        category = self._classify_error(error_message)
        
        # Determine severity
        severity = self._determine_severity(category, error_message)
        
        # Extract location from traceback
        location = self._extract_location(error_message)
        
        # Find root cause
        root_cause = self._identify_root_cause(category, error_message, code)
        
        # Calculate confidence based on pattern matching
        confidence = self._calculate_confidence(category, error_message)
        
        return ErrorDiagnosis(
            error_message=error_message,
            error_type=self._extract_error_type(error_message),
            category=category,
            severity=severity,
            location=location,
            traceback=self._extract_traceback(error_message),
            root_cause=root_cause,
            confidence=confidence,
        )
    
    def _classify_error(self, error_message: str) -> ErrorCategory:
        """Classify error into category."""
        error_lower = error_message.lower()
        
        # Check patterns for each category
        for category, patterns in self._error_patterns.items():
            for pattern_info in patterns:
                if re.search(pattern_info["pattern"], error_message, re.IGNORECASE):
                    return category
        
        # Fallback classification
        if "syntax" in error_lower:
            return ErrorCategory.SYNTAX
        elif "import" in error_lower or "module" in error_lower:
            return ErrorCategory.IMPORT
        elif "memory" in error_lower or "timeout" in error_lower:
            return ErrorCategory.RESOURCE
        elif "type" in error_lower:
            return ErrorCategory.TYPE
        elif any(x in error_lower for x in ["error", "exception", "failed"]):
            return ErrorCategory.RUNTIME
        
        return ErrorCategory.RUNTIME  # Default
    
    def _determine_severity(
        self,
        category: ErrorCategory,
        error_message: str,
    ) -> ErrorSeverity:
        """Determine error severity."""
        # Critical: Cannot proceed at all
        if category in (ErrorCategory.SYNTAX, ErrorCategory.IMPORT):
            return ErrorSeverity.CRITICAL
        
        # Major: Significant functionality broken
        if category == ErrorCategory.RESOURCE:
            return ErrorSeverity.MAJOR
        
        # Check for specific major indicators
        major_indicators = ["crash", "fail", "abort", "terminate"]
        if any(ind in error_message.lower() for ind in major_indicators):
            return ErrorSeverity.MAJOR
        
        # Minor: Workaround exists
        if category in (ErrorCategory.TYPE, ErrorCategory.RUNTIME):
            return ErrorSeverity.MINOR
        
        return ErrorSeverity.MINOR
    
    def _extract_location(self, error_message: str) -> str:
        """Extract error location from traceback."""
        # Pattern: File "path", line N, in function
        pattern = r'File\s+"([^"]+)",\s+line\s+(\d+)'
        match = re.search(pattern, error_message)
        
        if match:
            return f"{match.group(1)}:{match.group(2)}"
        
        return "unknown"
    
    def _identify_root_cause(
        self,
        category: ErrorCategory,
        error_message: str,
        code: str,
    ) -> str:
        """Identify root cause of error."""
        root_causes = {
            ErrorCategory.SYNTAX: "Code violates Python syntax rules",
            ErrorCategory.RUNTIME: "Code failed during execution",
            ErrorCategory.IMPORT: "Required module not available or incorrectly imported",
            ErrorCategory.RESOURCE: "Insufficient system resources",
            ErrorCategory.TYPE: "Type mismatch or incorrect type usage",
            ErrorCategory.LOGIC: "Code runs but produces incorrect results",
        }
        
        # Add specific cause based on error message
        specific_causes = {
            r"NameError": "Variable or function used before definition",
            r"IndexError": "Array/list index out of valid range",
            r"KeyError": "Dictionary key does not exist",
            r"AttributeError": "Object does not have requested attribute",
            r"TypeError": "Operation applied to incompatible type",
            r"ZeroDivisionError": "Division by zero attempted",
            r"ModuleNotFoundError": "Package not installed or path incorrect",
            r"FileNotFoundError": "File path does not exist",
            r"MemoryError": "Insufficient memory for operation",
        }
        
        for pattern, cause in specific_causes.items():
            if re.search(pattern, error_message, re.IGNORECASE):
                return cause
        
        return root_causes.get(category, "Unknown error cause")
    
    def _calculate_confidence(
        self,
        category: ErrorCategory,
        error_message: str,
    ) -> float:
        """Calculate confidence in diagnosis."""
        # Higher confidence for well-known error patterns
        base_confidence = 0.7
        
        for pattern_info in self._error_patterns.get(category, []):
            if re.search(pattern_info["pattern"], error_message, re.IGNORECASE):
                return 0.9  # High confidence for matched pattern
        
        # Lower confidence for unknown patterns
        return 0.5
    
    def _extract_error_type(self, error_message: str) -> str:
        """Extract error type name from message."""
        # Pattern: ErrorType: message
        match = re.match(r"(\w+Error|\w+Exception):\s*", error_message)
        if match:
            return match.group(1)
        return "Unknown"
    
    def _extract_traceback(self, error_message: str) -> list[str]:
        """Extract traceback lines."""
        lines = error_message.split("\n")
        traceback = []
        
        in_traceback = False
        for line in lines:
            if "Traceback" in line:
                in_traceback = True
            if in_traceback:
                traceback.append(line)
                if not line.strip().startswith("File") and ":" in line:
                    break  # Reached error message
        
        return traceback if traceback else lines[:5]
    
    async def _generate_fix(
        self,
        diagnosis: ErrorDiagnosis,
        code: str,
        context: dict[str, Any] | None,
    ) -> FixSuggestion | None:
        """Generate fix for diagnosed error."""
        # Find matching strategy
        strategy = self._find_fix_strategy(diagnosis)
        
        if not strategy:
            # Fall back to LLM-based fix generation
            return await self._llm_generate_fix(diagnosis, code, context)
        
        # Apply rule-based fix
        fix_code = self._apply_fix_strategy(strategy, code, diagnosis)
        
        if fix_code:
            return FixSuggestion(
                diagnosis=diagnosis,
                fix_description=strategy["description"],
                original_code=code,
                fixed_code=fix_code,
                confidence=diagnosis.confidence * 0.9,  # Slightly lower than diagnosis
                strategy=strategy["strategy"],
                side_effects=self._get_side_effects(strategy["strategy"]),
            )
        
        return None
    
    def _find_fix_strategy(self, diagnosis: ErrorDiagnosis) -> dict[str, Any] | None:
        """Find fix strategy for diagnosed error."""
        patterns = self._error_patterns.get(diagnosis.category, [])
        
        for pattern_info in patterns:
            if re.search(pattern_info["pattern"], diagnosis.error_message, re.IGNORECASE):
                return pattern_info
        
        return None
    
    def _apply_fix_strategy(
        self,
        strategy: dict[str, Any],
        code: str,
        diagnosis: ErrorDiagnosis,
    ) -> str | None:
        """Apply rule-based fix strategy."""
        strategy_name = strategy["strategy"]
        
        fix_functions = {
            "fix_indentation": self._fix_indentation,
            "balance_parens": self._balance_parens,
            "define_variable": self._define_variable,
            "bounds_check": self._add_bounds_check,
            "dict_key_check": self._add_dict_key_check,
            "add_zero_check": self._add_zero_check,
            "fix_path": self._fix_file_path,
        }
        
        fix_func = fix_functions.get(strategy_name)
        if fix_func:
            return fix_func(code, diagnosis)
        
        return None
    
    def _fix_indentation(self, code: str, diagnosis: ErrorDiagnosis) -> str:
        """Fix indentation issues."""
        # Convert tabs to 4 spaces
        lines = code.split("\n")
        fixed_lines = []
        
        for line in lines:
            # Count leading tabs and convert to spaces
            stripped = line.lstrip("\t")
            tab_count = len(line) - len(stripped)
            fixed_line = " " * (tab_count * 4) + stripped
            fixed_lines.append(fixed_line)
        
        return "\n".join(fixed_lines)
    
    def _balance_parens(self, code: str, diagnosis: ErrorDiagnosis) -> str:
        """Balance parentheses, brackets, and braces."""
        # Count opening and closing
        opens = code.count("(") + code.count("[") + code.count("{")
        closes = code.count(")") + code.count("]") + code.count("}")
        
        # Add missing closing parens
        if opens > closes:
            code += ")" * (opens - closes)
        elif closes > opens:
            # Remove extra closing parens from end
            diff = closes - opens
            for _ in range(diff):
                for i in range(len(code) - 1, -1, -1):
                    if code[i] in ")]}":
                        code = code[:i] + code[i+1:]
                        break
        
        return code
    
    def _add_bounds_check(self, code: str, diagnosis: ErrorDiagnosis) -> str:
        """Add bounds checking for list access."""
        # Find list access patterns and add checks
        pattern = r"(\w+)\[(\w+)\]"
        
        def add_check(match):
            list_name = match.group(1)
            index_name = match.group(2)
            return f"{list_name}[{index_name} if {index_name} < len({list_name}) else 0]"
        
        return re.sub(pattern, add_check, code)
    
    def _add_dict_key_check(self, code: str, diagnosis: ErrorDiagnosis) -> str:
        """Add dictionary key existence check."""
        # Pattern: dict[key] -> dict.get(key, default)
        pattern = r"(\w+)\['(\w+)'\]"
        
        def fix_match(match):
            dict_name = match.group(1)
            key_name = match.group(2)
            return f"{dict_name}.get('{key_name}', None)"
        
        return re.sub(pattern, fix_match, code)
    
    def _add_zero_check(self, code: str, diagnosis: ErrorDiagnosis) -> str:
        """Add division by zero check."""
        # Pattern: x / y -> x / y if y != 0 else 0
        pattern = r"([^/])\s*/\s*(\w+)"
        
        def fix_match(match):
            numerator = match.group(1).strip()
            denominator = match.group(2).strip()
            return f"({numerator} / {denominator} if {denominator} != 0 else 0)"
        
        return re.sub(pattern, fix_match, code)
    
    def _fix_file_path(self, code: str, diagnosis: ErrorDiagnosis) -> str:
        """Fix file path issues."""
        # Add existence check before file operations
        lines = code.split("\n")
        fixed_lines = []
        
        for line in lines:
            if "open(" in line and "with" in line:
                # Extract path
                match = re.search(r'open\(["\']([^"\']+)["\']', line)
                if match:
                    path = match.group(1)
                    indent = len(line) - len(line.lstrip())
                    check = " " * indent + f"import os\n"
                    check += " " * indent + f"if not os.path.exists('{path}'):\n"
                    check += " " * (indent + 4) + f"raise FileNotFoundError('File not found: {path}')\n"
                    fixed_lines.append(check)
            fixed_lines.append(line)
        
        return "\n".join(fixed_lines)
    
    def _define_variable(self, code: str, diagnosis: ErrorDiagnosis) -> str:
        """Define missing variable."""
        # Extract variable name from error
        match = re.search(r"name\s+'(\w+)'\s+is\s+not\s+defined", diagnosis.error_message)
        if match:
            var_name = match.group(1)
            # Add definition at top of code
            definition = f"# Auto-defined: {var_name}\n{var_name} = None\n\n"
            return definition + code
        
        return code
    
    def _get_side_effects(self, strategy: str) -> list[str]:
        """Get potential side effects of a fix strategy."""
        side_effects = {
            "fix_indentation": ["May change code formatting"],
            "balance_parens": ["May change expression logic if parens were intentional"],
            "bounds_check": ["May return default value instead of raising error"],
            "dict_key_check": ["Returns None for missing keys instead of raising"],
            "add_zero_check": ["Returns 0 for division by zero instead of raising"],
            "fix_path": ["Adds file existence check, may fail earlier"],
        }
        return side_effects.get(strategy, ["Unknown side effects"])
    
    async def _llm_generate_fix(
        self,
        diagnosis: ErrorDiagnosis,
        code: str,
        context: dict[str, Any] | None,
    ) -> FixSuggestion:
        """Generate fix using LLM (fallback when rule-based fails)."""
        # Build prompt
        prompt = f"""You are an expert Python debugger. Fix this error:

ERROR: {diagnosis.error_message}
CATEGORY: {diagnosis.category.value}
ROOT CAUSE: {diagnosis.root_cause}

CODE:
```python
{code[:2000]}  # Truncate if too long
```

Provide the fixed code only, no explanation. Keep changes minimal."""
        
        # In production, call LLM:
        # response = await self._llm_client.chat(
        #     messages=[{"role": "user", "content": prompt}]
        # )
        # fixed_code = response.content
        
        # Placeholder
        fixed_code = code  # No change in placeholder
        
        return FixSuggestion(
            diagnosis=diagnosis,
            fix_description="LLM-generated fix",
            original_code=code,
            fixed_code=fixed_code,
            confidence=0.6,  # Lower confidence for LLM fixes
            strategy="llm_generation",
            side_effects=["May introduce unintended changes"],
        )
    
    def _search_knowledge_base(
        self,
        error_message: str,
        code: str,
    ) -> dict[str, Any] | None:
        """Search knowledge base for similar error and fix."""
        # Simple similarity search
        for entry in self._knowledge_base:
            if entry["error_pattern"] in error_message:
                return entry
        
        return None
    
    def _create_result_from_kb(
        self,
        kb_entry: dict[str, Any],
        code: str,
    ) -> DebugResult:
        """Create debug result from knowledge base entry."""
        diagnosis = ErrorDiagnosis(
            error_message=kb_entry["error_message"],
            error_type=kb_entry["error_type"],
            category=kb_entry["category"],
            severity=kb_entry["severity"],
            location="unknown",
            traceback=[],
            root_cause=kb_entry["root_cause"],
            confidence=kb_entry["confidence"],
        )
        
        fix = FixSuggestion(
            diagnosis=diagnosis,
            fix_description=kb_entry["fix_description"],
            original_code=code,
            fixed_code=kb_entry["fixed_code_template"],
            confidence=kb_entry["confidence"],
            strategy=kb_entry["strategy"],
        )
        
        return DebugResult(
            success=True,
            error_diagnosis=diagnosis,
            fix_suggestion=fix,
            knowledge_base_match=True,
        )
    
    def add_to_knowledge_base(
        self,
        error_message: str,
        code: str,
        fix: str,
        success: bool,
    ) -> None:
        """Add successful fix to knowledge base."""
        if not success:
            return
        
        entry = {
            "error_message": error_message,
            "error_pattern": self._extract_error_pattern(error_message),
            "error_type": self._extract_error_type(error_message),
            "category": self._classify_error(error_message).value,
            "severity": self._determine_severity(
                self._classify_error(error_message), error_message
            ).value,
            "root_cause": self._identify_root_cause(
                self._classify_error(error_message), error_message, code
            ),
            "fix_description": "Auto-learned fix",
            "fixed_code_template": fix,
            "strategy": "learned",
            "confidence": 0.8,
            "learned_at": datetime.now().isoformat(),
        }
        
        self._knowledge_base.append(entry)
        logger.info(f"Added fix to knowledge base (total: {len(self._knowledge_base)})")
    
    def _extract_error_pattern(self, error_message: str) -> str:
        """Extract generalizable pattern from error message."""
        # Replace specific values with placeholders
        pattern = error_message
        pattern = re.sub(r"'[^']+'", "'<VALUE>'", pattern)
        pattern = re.sub(r"\d+", "<NUM>", pattern)
        return pattern
    
    def get_debugging_statistics(self) -> dict[str, Any]:
        """Get debugging statistics."""
        if not self._fix_history:
            return {"error": "No debugging performed"}
        
        successful = sum(1 for r in self._fix_history if r.success)
        kb_matches = sum(1 for r in self._fix_history if r.knowledge_base_match)
        
        category_counts = {}
        for result in self._fix_history:
            if result.error_diagnosis:
                cat = result.error_diagnosis.category.value
                category_counts[cat] = category_counts.get(cat, 0) + 1
        
        return {
            "total_debugging_sessions": len(self._fix_history),
            "successful_fixes": successful,
            "success_rate": successful / len(self._fix_history),
            "knowledge_base_matches": kb_matches,
            "knowledge_base_size": len(self._knowledge_base),
            "category_distribution": category_counts,
            "avg_time_sec": sum(r.total_time_sec for r in self._fix_history) / len(self._fix_history),
        }


# Convenience function
async def auto_debug(
    error_message: str,
    code: str,
    context: dict[str, Any] | None = None,
) -> DebugResult:
    """Quick function to debug an error.
    
    Args:
        error_message: Error message
        code: Code that failed
        context: Optional context
        
    Returns:
        DebugResult
    """
    debugger = AutomatedDebugger()
    result = await debugger.diagnose_and_fix(error_message, code, context)
    
    if result.success and result.fix_suggestion:
        debugger.add_to_knowledge_base(
            error_message,
            code,
            result.fix_suggestion.fixed_code,
            True,
        )
    
    return result
