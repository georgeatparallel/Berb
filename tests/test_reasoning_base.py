"""Tests for reasoning method base classes."""

from __future__ import annotations

import pytest
from datetime import datetime

from berb.reasoning.base import (
    MethodType,
    ReasoningContext,
    ReasoningResult,
    ReasoningMethod,
    create_context,
)


class TestMethodType:
    """Test MethodType enum."""
    
    def test_method_type_values(self):
        """Test all method type values are defined."""
        assert MethodType.MULTI_PERSPECTIVE.value == "multi_perspective"
        assert MethodType.PRE_MORTEM.value == "pre_mortem"
        assert MethodType.BAYESIAN.value == "bayesian"
        assert MethodType.DEBATE.value == "debate"
        assert MethodType.DIALECTICAL.value == "dialectical"
        assert MethodType.RESEARCH.value == "research"
        assert MethodType.SOCRATIC.value == "socratic"
        assert MethodType.SCIENTIFIC.value == "scientific"
        assert MethodType.JURY.value == "jury"


class TestReasoningContext:
    """Test ReasoningContext dataclass."""
    
    def test_create_context_minimal(self):
        """Test creating context with minimal parameters."""
        ctx = ReasoningContext(
            stage_id="TEST_STAGE",
            stage_name="Test Stage",
        )
        
        assert ctx.stage_id == "TEST_STAGE"
        assert ctx.stage_name == "Test Stage"
        assert ctx.input_data == {}
        assert ctx.metadata == {}
        assert isinstance(ctx.created_at, datetime)
    
    def test_create_context_full(self):
        """Test creating context with all parameters."""
        ctx = ReasoningContext(
            stage_id="HYPOTHESIS_GEN",
            stage_name="Hypothesis Generation",
            input_data={"key": "value"},
            metadata={"topic": "test topic"},
        )
        
        assert ctx.stage_id == "HYPOTHESIS_GEN"
        assert ctx.input_data == {"key": "value"}
        assert ctx.metadata == {"topic": "test topic"}
    
    def test_context_get(self):
        """Test getting values from context."""
        ctx = ReasoningContext(
            stage_id="TEST",
            stage_name="Test",
            input_data={"key1": "value1", "key2": "value2"},
        )
        
        assert ctx.get("key1") == "value1"
        assert ctx.get("key2") == "value2"
        assert ctx.get("nonexistent", "default") == "default"
    
    def test_context_set(self):
        """Test setting values in context."""
        ctx = ReasoningContext(
            stage_id="TEST",
            stage_name="Test",
        )
        
        ctx.set("new_key", "new_value")
        assert ctx.input_data["new_key"] == "new_value"
    
    def test_context_to_dict(self):
        """Test converting context to dictionary."""
        ctx = ReasoningContext(
            stage_id="TEST",
            stage_name="Test",
            input_data={"key": "value"},
        )
        
        d = ctx.to_dict()
        
        assert d["stage_id"] == "TEST"
        assert d["stage_name"] == "Test"
        assert d["input_data"]["key"] == "value"
        assert "created_at" in d
    
    def test_context_from_dict(self):
        """Test creating context from dictionary."""
        d = {
            "stage_id": "TEST",
            "stage_name": "Test",
            "input_data": {"key": "value"},
            "metadata": {},
            "created_at": "2025-01-01T00:00:00",
        }
        
        ctx = ReasoningContext.from_dict(d)
        
        assert ctx.stage_id == "TEST"
        assert ctx.input_data["key"] == "value"
        assert ctx.created_at.year == 2025


class TestReasoningResult:
    """Test ReasoningResult dataclass."""
    
    def test_create_success_result(self):
        """Test creating successful result."""
        result = ReasoningResult(
            method_type=MethodType.MULTI_PERSPECTIVE,
            success=True,
            output={"key": "value"},
            confidence=0.95,
        )
        
        assert result.method_type == MethodType.MULTI_PERSPECTIVE
        assert result.success is True
        assert result.output == {"key": "value"}
        assert result.confidence == 0.95
        assert result.error is None
    
    def test_create_error_result(self):
        """Test creating error result."""
        result = ReasoningResult(
            method_type=MethodType.PRE_MORTEM,
            success=False,
            error="Test error message",
        )
        
        assert result.success is False
        assert result.error == "Test error message"
    
    def test_success_result_classmethod(self):
        """Test success_result classmethod."""
        result = ReasoningResult.success_result(
            method_type=MethodType.BAYESIAN,
            output={"posterior": 0.85},
            confidence=0.9,
            model_used="test-model",
        )
        
        assert result.success is True
        assert result.output == {"posterior": 0.85}
        assert result.confidence == 0.9
        assert result.metadata["model_used"] == "test-model"
    
    def test_error_result_classmethod(self):
        """Test error_result classmethod."""
        result = ReasoningResult.error_result(
            method_type=MethodType.DEBATE,
            error="Connection timeout",
            retry_count=3,
        )
        
        assert result.success is False
        assert result.error == "Connection timeout"
        assert result.metadata["retry_count"] == 3
    
    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = ReasoningResult.success_result(
            method_type=MethodType.SOCRATIC,
            output={"insights": ["insight1", "insight2"]},
        )
        
        d = result.to_dict()
        
        assert d["method_type"] == "socratic"
        assert d["success"] is True
        assert "insights" in d["output"]


class TestReasoningMethod:
    """Test ReasoningMethod abstract base class."""
    
    def test_abstract_method(self):
        """Test that execute is abstract."""
        # Should not be able to instantiate without implementing execute
        with pytest.raises(TypeError):
            ReasoningMethod()
    
    def test_concrete_implementation(self):
        """Test creating concrete implementation."""
        class TestMethod(ReasoningMethod):
            async def execute(self, context: ReasoningContext) -> ReasoningResult:
                return ReasoningResult.success_result(
                    MethodType.RESEARCH,
                    {"result": "test"},
                )
        
        method = TestMethod(name="Test Method")
        assert method.name == "Test Method"
    
    def test_validate_context_valid(self):
        """Test context validation with valid context."""
        class TestMethod(ReasoningMethod):
            async def execute(self, context: ReasoningContext) -> ReasoningResult:
                return ReasoningResult.success_result(MethodType.RESEARCH, {})
        
        method = TestMethod()
        ctx = ReasoningContext(
            stage_id="TEST",
            stage_name="Test",
            input_data={"key": "value"},
        )
        
        assert method.validate_context(ctx) is True
    
    def test_validate_context_missing_stage_id(self, caplog):
        """Test context validation with missing stage_id."""
        class TestMethod(ReasoningMethod):
            async def execute(self, context: ReasoningContext) -> ReasoningResult:
                return ReasoningResult.success_result(MethodType.RESEARCH, {})
        
        method = TestMethod()
        ctx = ReasoningContext(
            stage_id="",  # Empty stage_id
            stage_name="Test",
            input_data={"key": "value"},
        )
        
        with caplog.at_level("WARNING"):
            result = method.validate_context(ctx)
            assert "missing stage_id" in caplog.text
        
        assert result is False
    
    def test_validate_context_missing_input_data(self, caplog):
        """Test context validation with missing input_data."""
        class TestMethod(ReasoningMethod):
            async def execute(self, context: ReasoningContext) -> ReasoningResult:
                return ReasoningResult.success_result(MethodType.RESEARCH, {})
        
        method = TestMethod()
        ctx = ReasoningContext(
            stage_id="TEST",
            stage_name="Test",
            input_data={},  # Empty input_data
        )
        
        with caplog.at_level("WARNING"):
            result = method.validate_context(ctx)
            assert "missing input_data" in caplog.text
        
        assert result is False
    
    def test_get_capabilities(self):
        """Test getting method capabilities."""
        class TestMethod(ReasoningMethod):
            async def execute(self, context: ReasoningContext) -> ReasoningResult:
                return ReasoningResult.success_result(MethodType.RESEARCH, {})
        
        method = TestMethod(
            name="Test Method",
            description="Test description",
        )
        
        caps = method.get_capabilities()
        
        assert caps["name"] == "Test Method"
        assert caps["description"] == "Test description"


class TestCreateContext:
    """Test create_context helper function."""
    
    def test_create_context_basic(self):
        """Test basic context creation."""
        ctx = create_context(
            stage_id="HYPOTHESIS_GEN",
            stage_name="Hypothesis Generation",
        )
        
        assert ctx.stage_id == "HYPOTHESIS_GEN"
        assert ctx.stage_name == "Hypothesis Generation"
        assert ctx.input_data == {}
    
    def test_create_context_with_data(self):
        """Test context creation with input data."""
        ctx = create_context(
            stage_id="EXPERIMENT_DESIGN",
            stage_name="Experiment Design",
            input_data={"hypothesis": "test hypothesis"},
            domain="biology",
            budget=1000,
        )
        
        assert ctx.input_data["hypothesis"] == "test hypothesis"
        assert ctx.metadata["domain"] == "biology"
        assert ctx.metadata["budget"] == 1000
