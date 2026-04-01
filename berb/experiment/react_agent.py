"""ReAct Experiment Agents.

Based on AIRA2 (Meta FAIR) Section 3.3:
"ReAct Agents as Operators that reason→act→observe iteratively."

Key Features:
- Reason-Act-Observe cycles
- Dynamic scoping (agent decides what to do)
- Interactive debugging within trajectory
- Self-correction

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.experiment.react_agent import ExperimentReActAgent
    
    agent = ExperimentReActAgent()
    result = await agent.run_experiment(design)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from berb.experiment.runner import ExperimentResult
from berb.reasoning.scientific import ExperimentDesign

logger = logging.getLogger(__name__)


class ReActStep(str, Enum):
    """ReAct trajectory step."""
    REASON = "reason"
    ACT = "act"
    OBSERVE = "observe"


@dataclass
class ReActTrajectory:
    """ReAct agent trajectory.
    
    Attributes:
        steps: List of (step_type, content) tuples
        current_step: Current step index
        experiment_id: Experiment identifier
    """
    steps: list[tuple[ReActStep, str]] = field(default_factory=list)
    current_step: int = 0
    experiment_id: str = ""
    
    def add(self, step: ReActStep, content: str) -> None:
        """Add step to trajectory."""
        self.steps.append((step, content))
        self.current_step = len(self.steps)
    
    def to_dict(self) -> list[dict[str, str]]:
        """Convert to dictionary."""
        return [
            {"step": step.value, "content": content}
            for step, content in self.steps
        ]


class ExperimentReActAgent:
    """AIRA2-style ReAct agent for experiment execution.
    
    ReAct Trajectory:
    1. Reason: "I need to implement X algorithm"
    2. Act: Write code, execute
    3. Observe: Check output, training curves
    4. Reason: "Loss is diverging — learning rate too high"
    5. Act: Reduce lr, re-run
    6. Observe: Loss converging now
    7. ...
    8. Submit: Final results
    
    Key Features:
    - Dynamic scoping (agent decides what to do)
    - Interactive debugging within same trajectory
    - Self-correction based on observations
    
    Usage:
        agent = ExperimentReActAgent()
        result = await agent.run_experiment(design)
    """
    
    def __init__(
        self,
        max_iterations: int = 10,
        model: str = "claude-3-sonnet",
    ):
        """Initialize ReAct agent.
        
        Args:
            max_iterations: Maximum ReAct iterations
            model: LLM model for reasoning
        """
        self.max_iterations = max_iterations
        self.model = model
        logger.info(f"Initialized ExperimentReActAgent with {model}")
    
    async def run_experiment(
        self,
        design: ExperimentDesign,
    ) -> ExperimentResult:
        """Run experiment using ReAct trajectory.
        
        Args:
            design: Experiment design
            
        Returns:
            Experiment result
        """
        trajectory = ReActTrajectory(experiment_id=design.id)
        
        # Initial reasoning
        trajectory.add(
            ReActStep.REASON,
            f"Starting experiment: {design.description[:100]}...",
        )
        
        # ReAct loop
        code = None
        output = None
        error = None
        
        for iteration in range(self.max_iterations):
            logger.info(f"ReAct iteration {iteration + 1}/{self.max_iterations}")
            
            # Reason step
            reasoning = await self._reason(design, trajectory, output, error)
            trajectory.add(ReActStep.REASON, reasoning)
            
            # Check if ready to submit
            if "submit" in reasoning.lower() or "complete" in reasoning.lower():
                logger.info("Agent decided to submit results")
                break
            
            # Act step
            code = await self._act(reasoning, design, trajectory)
            trajectory.add(ReActStep.ACT, f"Executed code ({len(code)} chars)")
            
            # Observe step
            output, error = await self._observe(code, design)
            trajectory.add(
                ReActStep.OBSERVE,
                f"Output: {output[:200] if output else 'None'}... "
                f"Error: {error[:200] if error else 'None'}...",
            )
            
            # Check for errors
            if error:
                # Analyze error and decide next action
                error_analysis = await self._analyze_error(error, trajectory)
                trajectory.add(ReActStep.REASON, f"Error analysis: {error_analysis}")
                
                if "fatal" in error_analysis.lower():
                    logger.warning("Fatal error detected")
                    break
        
        # Create final result
        result = ExperimentResult(
            run_id=design.id,
            iteration=trajectory.current_step,
            code=code or "",
            metrics=self._extract_metrics(output),
            primary_metric=None,
            improved=True,
            kept=True,
            elapsed_sec=0,
            stdout=output or "",
            stderr=error or "",
            error=error,
        )
        
        logger.info(f"ReAct experiment complete: {design.id}")
        return result
    
    async def _reason(
        self,
        design: ExperimentDesign,
        trajectory: ReActTrajectory,
        output: str | None,
        error: str | None,
    ) -> str:
        """Reason about next action.
        
        Args:
            design: Experiment design
            trajectory: Current trajectory
            output: Last output (if any)
            error: Last error (if any)
            
        Returns:
            Reasoning text
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model=self.model)
        
        # Build context from trajectory
        context = "\n".join([
            f"[{step.value}] {content}"
            for step, content in trajectory.steps[-6:]  # Last 6 steps
        ])
        
        prompt = f"""
You are executing an experiment. Analyze the situation and decide next action.

Experiment: {design.description}

Previous trajectory:
{context}

Current output: {output[:500] if output else 'None'}...
Current error: {error[:500] if error else 'None'}...

Reason about:
1. What does the output/error tell you?
2. What needs to be fixed or improved?
3. What is your next action?

If results are satisfactory, say "SUBMIT results".
If there's a fatal error, say "FATAL ERROR: [reason]".
Otherwise, describe what code to write next.
"""
        
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are an AI researcher executing experiments. Think step by step.",
        )
        
        return response.content
    
    async def _act(
        self,
        reasoning: str,
        design: ExperimentDesign,
        trajectory: ReActTrajectory,
    ) -> str:
        """Execute action (write/run code).
        
        Args:
            reasoning: Reasoning from previous step
            design: Experiment design
            trajectory: Current trajectory
            
        Returns:
            Executed code
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model="claude-3-sonnet")
        
        prompt = f"""
Based on this reasoning, write the Python code to execute:

{reasoning}

Experiment context: {design.description}

Write complete, executable Python code that:
1. Implements the required functionality
2. Prints results clearly
3. Handles errors gracefully

Provide only the code, no explanations.
"""
        
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are a programmer writing experiment code.",
        )
        
        # Extract code from response
        code = response.content
        if "```python" in code:
            start = code.find("```python") + len("```python")
            end = code.find("```", start)
            if end > start:
                code = code[start:end].strip()
        
        return code
    
    async def _observe(
        self,
        code: str,
        design: ExperimentDesign,
    ) -> tuple[str | None, str | None]:
        """Observe execution results.
        
        Args:
            code: Code to execute
            design: Experiment design
            
        Returns:
            (output, error) tuple
        """
        from berb.experiment.sandbox import LocalSandbox
        
        sandbox = LocalSandbox()
        
        try:
            result = await sandbox.execute(code, timeout=300)
            return result.stdout, result.stderr
        except Exception as e:
            return None, str(e)
    
    async def _analyze_error(
        self,
        error: str,
        trajectory: ReActTrajectory,
    ) -> str:
        """Analyze error and suggest fix.
        
        Args:
            error: Error message
            trajectory: Current trajectory
            
        Returns:
            Error analysis
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model=self.model)
        
        prompt = f"""
Analyze this error and determine if it's fixable or fatal:

Error: {error}

Previous trajectory:
{trajectory.to_dict()}

Classify the error:
1. Syntax error (fixable)
2. Runtime error (may be fixable)
3. Logic error (fixable)
4. Resource error (may need different approach)
5. Fatal (cannot continue)

Provide analysis and recommended next action.
"""
        
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are debugging an experiment.",
        )
        
        return response.content
    
    def _extract_metrics(self, output: str | None) -> dict[str, Any]:
        """Extract metrics from output.
        
        Args:
            output: Execution output
            
        Returns:
            Metrics dictionary
        """
        import re
        
        if not output:
            return {}
        
        metrics = {}
        
        # Look for numeric patterns
        number_pattern = r'(\w+):\s*([\d.]+)'
        matches = re.findall(number_pattern, output)
        
        for name, value in matches:
            try:
                metrics[name.lower()] = float(value)
            except ValueError:
                pass
        
        return metrics


__all__ = [
    "ExperimentReActAgent",
    "ReActTrajectory",
    "ReActStep",
]
