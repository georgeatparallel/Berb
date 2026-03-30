"""Base classes and interfaces for reasoning methods.

This module defines the common interface that all reasoning methods must implement,
along with shared data structures and utilities.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MethodType(str, Enum):
    """Type of reasoning method."""
    
    MULTI_PERSPECTIVE = "multi_perspective"
    PRE_MORTEM = "pre_mortem"
    BAYESIAN = "bayesian"
    DEBATE = "debate"
    DIALECTICAL = "dialectical"
    RESEARCH = "research"
    SOCRATIC = "socratic"
    SCIENTIFIC = "scientific"
    JURY = "jury"


@dataclass
class ReasoningContext:
    """Context for reasoning execution.
    
    Attributes:
        stage_id: ID of the pipeline stage (e.g., "HYPOTHESIS_GEN")
        stage_name: Human-readable stage name
        input_data: Input data for reasoning
        metadata: Additional metadata
        created_at: Timestamp when context was created
    """
    
    stage_id: str
    """ID of the pipeline stage (e.g., 'HYPOTHESIS_GEN', 'EXPERIMENT_DESIGN')"""
    
    stage_name: str
    """Human-readable stage name"""
    
    input_data: dict[str, Any] = field(default_factory=dict)
    """Input data for reasoning"""
    
    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional metadata (topic, domain, constraints, etc.)"""
    
    created_at: datetime = field(default_factory=datetime.now)
    """Timestamp when context was created"""
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from input_data."""
        return self.input_data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set value in input_data."""
        self.input_data[key] = value
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "stage_id": self.stage_id,
            "stage_name": self.stage_name,
            "input_data": self.input_data,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReasoningContext:
        """Create from dictionary."""
        return cls(
            stage_id=data.get("stage_id", "UNKNOWN"),
            stage_name=data.get("stage_name", "Unknown Stage"),
            input_data=data.get("input_data", {}),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
        )


@dataclass
class ReasoningResult:
    """Result from reasoning method execution.
    
    Attributes:
        method_type: Type of reasoning method used
        success: Whether execution was successful
        output: Output data from reasoning
        confidence: Confidence score (0-1)
        metadata: Additional metadata
        error: Error message if failed
        duration_sec: Execution duration in seconds
    """
    
    method_type: MethodType
    """Type of reasoning method used"""
    
    success: bool = True
    """Whether execution was successful"""
    
    output: dict[str, Any] = field(default_factory=dict)
    """Output data from reasoning"""
    
    confidence: float = 1.0
    """Confidence score (0-1)"""
    
    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional metadata (model_used, tokens, cost, etc.)"""
    
    error: str | None = None
    """Error message if failed"""
    
    duration_sec: float = 0.0
    """Execution duration in seconds"""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "method_type": self.method_type.value,
            "success": self.success,
            "output": self.output,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "error": self.error,
            "duration_sec": self.duration_sec,
        }
    
    @classmethod
    def success_result(
        cls,
        method_type: MethodType,
        output: dict[str, Any],
        confidence: float = 1.0,
        **metadata: Any,
    ) -> ReasoningResult:
        """Create a successful result."""
        return cls(
            method_type=method_type,
            success=True,
            output=output,
            confidence=confidence,
            metadata=metadata,
        )
    
    @classmethod
    def error_result(
        cls,
        method_type: MethodType,
        error: str,
        **metadata: Any,
    ) -> ReasoningResult:
        """Create an error result."""
        return cls(
            method_type=method_type,
            success=False,
            error=error,
            metadata=metadata,
        )


class ReasoningMethod(ABC):
    """Abstract base class for all reasoning methods.
    
    All reasoning methods must implement this interface.
    
    Attributes:
        method_type: Type of reasoning method
        name: Human-readable name
        description: Description of the method
    """
    
    method_type: MethodType
    """Type of reasoning method (class attribute)"""
    
    def __init__(
        self,
        name: str | None = None,
        description: str | None = None,
    ):
        """
        Initialize reasoning method.
        
        Args:
            name: Human-readable name (default: from class)
            description: Description of the method
        """
        self.name = name or self.__class__.__name__
        self.description = description or self.__doc__ or ""
        self._logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    async def execute(self, context: ReasoningContext) -> ReasoningResult:
        """
        Execute reasoning method.
        
        Args:
            context: Reasoning context with input data
        
        Returns:
            ReasoningResult with output and metadata
        
        Raises:
            Exception: If reasoning fails
        """
        pass
    
    async def __aenter__(self) -> ReasoningMethod:
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        pass
    
    def validate_context(self, context: ReasoningContext) -> bool:
        """
        Validate reasoning context.
        
        Override in subclasses to add specific validation.
        
        Args:
            context: Context to validate
        
        Returns:
            True if valid, False otherwise
        """
        if not context.stage_id:
            self._logger.warning("Context missing stage_id")
            return False
        
        if not context.input_data:
            self._logger.warning("Context missing input_data")
            return False
        
        return True
    
    def get_capabilities(self) -> dict[str, Any]:
        """
        Get method capabilities.
        
        Override in subclasses to provide specific capabilities.
        
        Returns:
            Dictionary of capabilities
        """
        return {
            "name": self.name,
            "type": self.method_type.value if hasattr(self, "method_type") else "unknown",
            "description": self.description,
        }


def create_context(
    stage_id: str,
    stage_name: str = "",
    input_data: dict[str, Any] | None = None,
    **metadata: Any,
) -> ReasoningContext:
    """
    Create reasoning context helper function.
    
    Args:
        stage_id: ID of the pipeline stage
        stage_name: Human-readable stage name
        input_data: Input data for reasoning
        **metadata: Additional metadata
    
    Returns:
        ReasoningContext instance
    
    Examples:
        >>> ctx = create_context(
        ...     stage_id="HYPOTHESIS_GEN",
        ...     stage_name="Hypothesis Generation",
        ...     input_data={"synthesis": synthesis_report},
        ...     topic="CRISPR gene editing",
        ... )
    """
    return ReasoningContext(
        stage_id=stage_id,
        stage_name=stage_name,
        input_data=input_data or {},
        metadata=metadata,
    )
