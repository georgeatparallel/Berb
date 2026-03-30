"""Meta Agent for HyperAgent.

The Meta Agent modifies both:
1. The Task Agent (task-solving behavior)
2. Its own modification procedure (metacognitive self-modification)

This is the key innovation of Hyperagents - the modification procedure
itself is editable, enabling metacognitive self-improvement.

Based on Facebook AI Research paper (arXiv:2603.19461v1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from berb.config import RCConfig
from berb.hyperagent.task_agent import TaskAgent, TaskAgentState

logger = logging.getLogger(__name__)

# System prompt for all LLM-based code generation requests.
_CODE_GEN_SYSTEM = (
    "You are an expert Python software engineer. "
    "When asked to improve code, return ONLY the complete improved Python source file. "
    "Do not wrap in markdown code fences. Do not add explanations outside the code. "
    "Preserve all existing function signatures unless explicitly changing them."
)


@dataclass
class ModificationResult:
    """Result of a code modification."""
    
    modification_id: str
    target: str  # "task_agent" or "meta_agent"
    code_diff: str
    description: str
    expected_benefit: str
    confidence: float  # 0-1 confidence in improvement
    rationale: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "modification_id": self.modification_id,
            "target": self.target,
            "code_diff": self.code_diff,
            "description": self.description,
            "expected_benefit": self.expected_benefit,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }


@dataclass
class MetaAgentState:
    """State of the Meta Agent."""
    
    variant_id: str = "v0"
    modification_code_version: int = 0
    total_modifications: int = 0
    successful_modifications: int = 0
    failed_modifications: int = 0
    metacognitive_improvements: int = 0  # Self-modifications of modification procedure
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @property
    def modification_success_rate(self) -> float:
        """Calculate modification success rate."""
        if self.total_modifications == 0:
            return 0.0
        return self.successful_modifications / self.total_modifications
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "variant_id": self.variant_id,
            "modification_code_version": self.modification_code_version,
            "total_modifications": self.total_modifications,
            "successful_modifications": self.successful_modifications,
            "failed_modifications": self.failed_modifications,
            "metacognitive_improvements": self.metacognitive_improvements,
            "modification_success_rate": self.modification_success_rate,
            "metadata": self.metadata,
        }


class MetaAgent:
    """Meta-modification agent with editable modification procedure.
    
    The Meta Agent:
    1. Analyzes Task Agent performance
    2. Generates code modifications to improve Task Agent
    3. Can modify ITS OWN modification procedure (metacognitive!)
    4. Learns from successful/failed modifications
    
    Key Innovation: The modification procedure is itself editable,
    enabling the agent to improve HOW it improves.
    
    Attributes:
        config: Meta agent configuration
        state: Current agent state
        modification_code: Editable code for modification procedure
    """
    
    def __init__(self, config: RCConfig):
        """
        Initialize Meta Agent.

        Args:
            config: Berb configuration
        """
        self.config = config
        self.state = MetaAgentState()
        self._llm: Any = None  # lazy-initialized on first use

        # Initialize modification procedure code
        self.modification_code = self._initialize_modification_code()

        logger.info("Meta Agent initialized (variant: %s)", self.state.variant_id)

    def _get_llm(self) -> Any:
        """Return (and cache) an LLMClient built from the current RCConfig."""
        if self._llm is None:
            from berb.llm.client import LLMClient
            self._llm = LLMClient.from_rc_config(self.config)
        return self._llm
    
    def _initialize_modification_code(self) -> str:
        """Initialize modification procedure code."""
        default_code = '''"""Default Modification Procedure.

This code defines how the Meta Agent generates modifications.
It can be modified by itself (metacognitive self-modification).
"""

from __future__ import annotations

def analyze_performance(task_history: list[dict]) -> dict:
    """Analyze task execution history to identify improvement opportunities.
    
    Args:
        task_history: List of task execution results
    
    Returns:
        Analysis with identified weaknesses and opportunities
    """
    # TODO: Implement performance analysis
    # This code can be modified by the Meta Agent itself
    return {
        "weaknesses": [],
        "opportunities": [],
        "patterns": [],
    }

def generate_modification(analysis: dict, current_code: str) -> str:
    """Generate code modification based on analysis.
    
    Args:
        analysis: Performance analysis
        current_code: Current task agent code
    
    Returns:
        Code diff string
    """
    # TODO: Implement modification generation
    # This code can be modified by the Meta Agent itself
    return ""
'''
        return default_code
    
    async def analyze_task_performance(
        self,
        task_result: Any,
        task_agent_state: TaskAgentState,
    ) -> dict[str, Any]:
        """
        Analyze task agent performance.
        
        Args:
            task_result: Result from task execution
            task_agent_state: Current task agent state
        
        Returns:
            Analysis with weaknesses, opportunities, and patterns
        """
        analysis = {
            "success_rate": task_agent_state.success_rate,
            "average_performance": task_agent_state.average_performance,
            "last_error": task_agent_state.last_error,
            "weaknesses": [],
            "opportunities": [],
            "patterns": [],
        }
        
        # Identify weaknesses
        if task_agent_state.success_rate < 0.8:
            analysis["weaknesses"].append("Low success rate")
        
        if task_result and hasattr(task_result, "error") and task_result.error:
            analysis["weaknesses"].append(f"Error: {task_result.error}")
        
        # Identify opportunities
        if "error" in str(task_result).lower():
            analysis["opportunities"].append("Improve error handling")
        
        # Detect patterns
        if task_agent_state.failed_tasks > 0:
            analysis["patterns"].append(f"Failed {task_agent_state.failed_tasks} tasks")
        
        logger.info(
            "Performance analysis: success_rate=%.2f, weaknesses=%d, opportunities=%d",
            analysis["success_rate"],
            len(analysis["weaknesses"]),
            len(analysis["opportunities"]),
        )
        
        return analysis
    
    async def generate_modification(
        self,
        analysis: dict[str, Any],
        task_agent: TaskAgent,
    ) -> ModificationResult:
        """
        Generate code modification for task agent.
        
        Args:
            analysis: Performance analysis
            task_agent: Current task agent
        
        Returns:
            ModificationResult with code diff
        """
        import uuid
        
        self.state.total_modifications += 1
        
        # Generate modification based on analysis
        # In production, this would use LLM to generate targeted improvements
        
        modification_id = f"mod_{uuid.uuid4().hex[:8]}"
        
        # Example modifications based on weaknesses
        code_diff = ""
        description = ""
        expected_benefit = ""
        confidence = 0.5
        
        if "Low success rate" in analysis.get("weaknesses", []):
            code_diff = self._generate_error_handling_improvement(task_agent.get_code())
            description = "Add better error handling"
            expected_benefit = "Reduce failures by 20-30%"
            confidence = 0.7
        
        elif "Improve error handling" in analysis.get("opportunities", []):
            code_diff = self._generate_error_handling_improvement(task_agent.get_code())
            description = "Enhance error handling and recovery"
            expected_benefit = "Better fault tolerance"
            confidence = 0.6
        
        else:
            # Default: optimize performance
            code_diff = self._generate_performance_optimization(task_agent.get_code())
            description = "Optimize task execution"
            expected_benefit = "Faster execution"
            confidence = 0.5
        
        result = ModificationResult(
            modification_id=modification_id,
            target="task_agent",
            code_diff=code_diff,
            description=description,
            expected_benefit=expected_benefit,
            confidence=confidence,
            rationale=f"Based on analysis: {analysis.get('weaknesses', [])}",
        )
        
        logger.info(
            "Generated modification %s: %s (confidence: %.2f)",
            result.modification_id,
            result.description,
            result.confidence,
        )
        
        return result
    
    async def modify_self(self) -> ModificationResult:
        """
        Metacognitive self-modification: modify own modification procedure!
        
        This is the key innovation of Hyperagents - the ability to improve
        HOW the agent improves.
        
        Returns:
            ModificationResult with self-modification diff
        """
        import uuid
        
        self.state.metacognitive_improvements += 1
        
        modification_id = f"meta_mod_{uuid.uuid4().hex[:8]}"
        
        # Generate self-modification
        # In production, this would analyze past modifications and improve the procedure
        
        code_diff = self._generate_meta_improvement()
        
        result = ModificationResult(
            modification_id=modification_id,
            target="meta_agent",
            code_diff=code_diff,
            description="Improve modification generation procedure",
            expected_benefit="Better quality modifications",
            confidence=0.6,
            rationale="Metacognitive self-improvement",
        )
        
        logger.info(
            "Generated metacognitive modification %s: %s",
            result.modification_id,
            result.description,
        )
        
        return result
    
    def apply_self_modification(self, code_diff: str) -> bool:
        """
        Apply self-modification to modification procedure.
        
        Args:
            code_diff: Git-style diff string
        
        Returns:
            True if modification applied successfully
        """
        try:
            # Validate new code
            if not self._validate_modification_code(code_diff):
                logger.warning("Self-modification failed validation")
                return False
            
            # Apply modification
            self.modification_code = code_diff
            self.state.modification_code_version += 1
            self.state.variant_id = f"meta_v{self.state.modification_code_version}"
            
            logger.info(
                "Self-modification applied (version: %d)",
                self.state.modification_code_version,
            )
            return True
            
        except Exception as e:
            logger.error("Failed to apply self-modification: %s", e)
            return False
    
    def _generate_error_handling_improvement(self, current_code: str) -> str:
        """Use the LLM to rewrite *current_code* with improved error handling.

        Returns the improved source code (complete file, not a patch).
        Falls back to the original code if the LLM call fails.
        """
        llm = self._get_llm()
        prompt = (
            "The following Python code is a research task agent. "
            "Rewrite it to add robust error handling:\n"
            "- Wrap every major operation in try/except with specific exception types\n"
            "- Log all errors with context using the `logging` module\n"
            "- Return structured failure results instead of raising unhandled exceptions\n"
            "- Add retry logic (up to 3 attempts) for transient failures\n\n"
            f"Current code:\n{current_code}\n\n"
            "Return ONLY the improved Python source file."
        )
        try:
            resp = llm.chat(
                [{"role": "user", "content": prompt}],
                system=_CODE_GEN_SYSTEM,
                max_tokens=4096,
            )
            improved = resp.content.strip()
            # Sanity: must parse as valid Python
            compile(improved, "<generated>", "exec")
            logger.info("MetaAgent: generated error-handling improvement (%d chars)", len(improved))
            return improved
        except Exception as exc:
            logger.warning("MetaAgent: error-handling generation failed: %s", exc)
            return current_code

    def _generate_performance_optimization(self, current_code: str) -> str:
        """Use the LLM to rewrite *current_code* with performance optimisations.

        Returns the improved source code (complete file, not a patch).
        Falls back to the original code if the LLM call fails.
        """
        llm = self._get_llm()
        prompt = (
            "The following Python code is a research task agent. "
            "Rewrite it to improve performance:\n"
            "- Cache expensive repeated computations with functools.lru_cache or instance-level dicts\n"
            "- Replace sequential loops with batch operations where possible\n"
            "- Use async/await for any I/O-bound operations\n"
            "- Minimise redundant data copies\n\n"
            f"Current code:\n{current_code}\n\n"
            "Return ONLY the improved Python source file."
        )
        try:
            resp = llm.chat(
                [{"role": "user", "content": prompt}],
                system=_CODE_GEN_SYSTEM,
                max_tokens=4096,
            )
            improved = resp.content.strip()
            compile(improved, "<generated>", "exec")
            logger.info("MetaAgent: generated performance optimisation (%d chars)", len(improved))
            return improved
        except Exception as exc:
            logger.warning("MetaAgent: performance optimisation generation failed: %s", exc)
            return current_code

    def _generate_meta_improvement(self) -> str:
        """Use the LLM to rewrite the modification procedure with metacognitive improvements.

        Returns the improved modification procedure code.
        Falls back to the current procedure if the LLM call fails.
        """
        llm = self._get_llm()
        prompt = (
            "The following Python code is the modification procedure for a MetaAgent — "
            "it defines how the agent generates improvements for a TaskAgent.\n\n"
            "Rewrite the procedure to be more effective:\n"
            "- analyse_performance() should identify concrete improvement patterns from task history\n"
            "- generate_modification() should produce targeted, high-confidence code changes\n"
            "- Add a new function: evaluate_modification(diff, task_history) that scores "
            "  a proposed modification before applying it\n\n"
            f"Current modification procedure:\n{self.modification_code}\n\n"
            "Return ONLY the improved Python source file."
        )
        try:
            resp = llm.chat(
                [{"role": "user", "content": prompt}],
                system=_CODE_GEN_SYSTEM,
                max_tokens=4096,
            )
            improved = resp.content.strip()
            compile(improved, "<generated>", "exec")
            logger.info("MetaAgent: generated metacognitive improvement (%d chars)", len(improved))
            return improved
        except Exception as exc:
            logger.warning("MetaAgent: metacognitive improvement generation failed: %s", exc)
            return self.modification_code
    
    def _validate_modification_code(self, code: str) -> bool:
        """Validate modification procedure code."""
        try:
            # Syntax check
            compile(code, "<string>", "exec")
            return True
        except SyntaxError as e:
            logger.warning("Modification code validation failed: %s", e)
            return False
    
    def get_state(self) -> MetaAgentState:
        """Get current Meta Agent state."""
        return self.state
    
    def get_modification_code(self) -> str:
        """Get current modification procedure code."""
        return self.modification_code
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "state": self.state.to_dict(),
            "modification_code": self.modification_code,
        }
