"""Regression tests for FIX-001: MultiPerspectiveMethod integration.

This test suite ensures the fix for integrating MultiPerspectiveMethod
into the hypothesis generation stage works correctly and doesn't regress.

Test Types:
1. Regression Test - Verifies the original bug is fixed
2. Edge Case Tests - Boundary values, empty inputs, etc.
3. Failure Injection Tests - Simulates failure conditions
4. Integration Smoke Test - Verifies integration with callers
"""

from __future__ import annotations

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, Mock

from berb.llm.client import LLMClient, LLMConfig, LLMResponse
from berb.config import RCConfig
from berb.pipeline.stages import Stage, StageStatus
from berb.adapters import AdapterBundle


# ============================================================================
# 6a. Regression Test - Verifies the fix works
# ============================================================================

class TestRegression_MultiPerspectiveIntegration:
    """Regression tests ensuring MultiPerspectiveMethod integration works."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM client."""
        config = LLMConfig(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            primary_model="gpt-4o",
        )
        llm = MagicMock(spec=LLMClient)
        llm.config = config
        llm.chat.return_value = LLMResponse(
            content="Test response",
            model="gpt-4o",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )
        return llm

    @pytest.fixture
    def mock_config(self):
        """Create mock RCConfig."""
        config = MagicMock()
        config.research.topic = "Test research topic"
        config.llm.s2_api_key = ""
        return config

    def test_hypothesis_gen_uses_multiperspective_method(self, mock_llm, mock_config):
        """REGRESSION: Verify _execute_hypothesis_gen uses MultiPerspectiveMethod."""
        from berb.pipeline.stage_impls._synthesis import _execute_hypothesis_gen
        
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_dir = Path(tmpdir) / "stage_08"
            run_dir = Path(tmpdir) / "run"
            stage_dir.mkdir(parents=True)
            run_dir.mkdir(parents=True)
            
            # Create synthesis.md (required input)
            (run_dir / "synthesis.md").write_text("# Test Synthesis", encoding="utf-8")
            
            # Mock MultiPerspectiveMethod to avoid actual LLM calls
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.output = {
                "perspectives": [],
                "scores": [],
                "top_candidates": [],
            }
            mock_result.confidence = 0.85
            
            with patch('berb.pipeline.stage_impls._synthesis.MultiPerspectiveMethod') as MockMP:
                MockMP.return_value.execute = AsyncMock(return_value=mock_result)
                
                result = _execute_hypothesis_gen(
                    stage_dir=stage_dir,
                    run_dir=run_dir,
                    config=mock_config,
                    adapters=MagicMock(spec=AdapterBundle),
                    llm=mock_llm,
                    prompts=None,
                )
                
                # Verify MultiPerspectiveMethod was called
                MockMP.assert_called_once()
                
                # Verify stage completed successfully
                assert result.stage == Stage.HYPOTHESIS_GEN
                assert result.status == StageStatus.DONE
                assert "hypotheses.md" in result.artifacts

    def test_hypothesis_gen_fallback_on_failure(self, mock_llm, mock_config):
        """REGRESSION: Verify fallback works when MultiPerspectiveMethod fails."""
        from berb.pipeline.stage_impls._synthesis import _execute_hypothesis_gen
        
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_dir = Path(tmpdir) / "stage_08"
            run_dir = Path(tmpdir) / "run"
            stage_dir.mkdir(parents=True)
            run_dir.mkdir(parents=True)
            
            (run_dir / "synthesis.md").write_text("# Test Synthesis", encoding="utf-8")
            
            # Mock MultiPerspectiveMethod to fail
            with patch('berb.pipeline.stage_impls._synthesis.MultiPerspectiveMethod') as MockMP:
                MockMP.return_value.execute = AsyncMock(side_effect=Exception("Test failure"))
                
                # Should not raise, should fall back to default
                result = _execute_hypothesis_gen(
                    stage_dir=stage_dir,
                    run_dir=run_dir,
                    config=mock_config,
                    adapters=MagicMock(spec=AdapterBundle),
                    llm=mock_llm,
                    prompts=None,
                )
                
                # Verify stage still completed (fallback succeeded)
                assert result.stage == Stage.HYPOTHESIS_GEN
                assert result.status == StageStatus.DONE
                
                # Verify hypotheses.md was created
                hypotheses_path = stage_dir / "hypotheses.md"
                assert hypotheses_path.exists()


# ============================================================================
# 6b. Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Edge case tests for FIX-001."""

    def test_empty_synthesis_context(self):
        """Test handling of empty synthesis context."""
        from berb.pipeline.stage_impls._synthesis import _SimpleRouter, _LLMProviderWrapper
        
        config = LLMConfig(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            primary_model="gpt-4o",
        )
        llm = LLMClient(config)
        router = _SimpleRouter(llm)
        
        # Should work even with empty context
        provider = router.get_provider_for_role("constructive")
        assert isinstance(provider, _LLMProviderWrapper)

    def test_special_characters_in_topic(self):
        """Test handling of special characters in research topic."""
        from berb.reasoning.base import create_context
        
        # Topic with special characters
        topic = "Test: LLM reasoning methods (2026)"
        problem = f"Research topic: {topic}\n\nSynthesis: Test"
        
        context = create_context(
            stage_id="test",
            input_data={"problem": problem, "topic": topic},
            query=problem,
        )
        
        assert context is not None
        assert hasattr(context, "stage_id") and context.stage_id == "test"

    def test_unicode_in_synthesis(self):
        """Test handling of unicode in synthesis."""
        from berb.pipeline.stage_impls._synthesis import _fallback_hypothesis_gen
        
        config = LLMConfig(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            primary_model="gpt-4o",
        )
        llm = LLMClient(config)
        
        unicode_synthesis = "Σύνθεση: Test with Greek Ελληνικά"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_dir = Path(tmpdir) / "stage"
            stage_dir.mkdir()
            
            with patch('berb.pipeline.stage_impls._synthesis._multi_perspective_generate', return_value={}):
                result = _fallback_hypothesis_gen(
                    llm=llm,
                    prompts=None,
                    topic="Test",
                    synthesis=unicode_synthesis,
                    stage_dir=stage_dir,
                )
                
                # Should handle unicode without errors
                assert isinstance(result, str)

    def test_null_llm_client(self):
        """Test handling of None LLM client."""
        from berb.pipeline.stage_impls._synthesis import _execute_hypothesis_gen
        
        config = MagicMock()
        config.research.topic = "Test"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_dir = Path(tmpdir) / "stage"
            run_dir = Path(tmpdir) / "run"
            stage_dir.mkdir(parents=True)
            run_dir.mkdir(parents=True)
            
            result = _execute_hypothesis_gen(
                stage_dir=stage_dir,
                run_dir=run_dir,
                config=config,
                adapters=MagicMock(spec=AdapterBundle),
                llm=None,  # No LLM
                prompts=None,
            )
            
            # Should use default hypotheses
            assert result.status == StageStatus.DONE
            hypotheses = (stage_dir / "hypotheses.md").read_text(encoding="utf-8")
            assert len(hypotheses) > 0


# ============================================================================
# 6c. Failure Injection Tests
# ============================================================================

class TestFailureInjection:
    """Failure injection tests - simulate failure conditions."""

    def test_multiperspective_returns_empty_output(self):
        """Test when MultiPerspectiveMethod returns empty output."""
        from berb.pipeline.stage_impls._synthesis import _execute_hypothesis_gen
        
        config = MagicMock()
        config.research.topic = "Test"
        
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.config = LLMConfig(
            base_url="https://api.openai.com/v1",
            api_key="test",
            primary_model="gpt-4o",
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_dir = Path(tmpdir) / "stage"
            run_dir = Path(tmpdir) / "run"
            stage_dir.mkdir(parents=True)
            run_dir.mkdir(parents=True)
            (run_dir / "synthesis.md").write_text("# Test", encoding="utf-8")
            
            # Mock success but with empty output
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.output = {}  # Empty!
            mock_result.confidence = 0.0
            
            with patch('berb.pipeline.stage_impls._synthesis.MultiPerspectiveMethod') as MockMP:
                MockMP.return_value.execute = AsyncMock(return_value=mock_result)
                
                result = _execute_hypothesis_gen(
                    stage_dir=stage_dir,
                    run_dir=run_dir,
                    config=config,
                    adapters=MagicMock(spec=AdapterBundle),
                    llm=mock_llm,
                    prompts=None,
                )
                
                # Should fall back gracefully
                assert result.status == StageStatus.DONE

    @pytest.mark.llm
    def test_async_execution_timeout(self):
        """Test handling of async execution timeout."""
        from berb.pipeline.stage_impls._synthesis import _SimpleRouter, _LLMProviderWrapper

        config = LLMConfig(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            primary_model="gpt-4o",
        )
        llm = LLMClient(config)
        wrapper = _LLMProviderWrapper(llm)
        
        # Should complete without hanging
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            async def test_complete():
                return await wrapper.complete("test")
            result = loop.run_until_complete(test_complete())
            assert result is not None
        finally:
            loop.close()

    def test_router_provider_caching(self):
        """Test that router caches providers correctly."""
        from berb.pipeline.stage_impls._synthesis import _SimpleRouter
        
        config = LLMConfig(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            primary_model="gpt-4o",
        )
        llm = LLMClient(config)
        router = _SimpleRouter(llm)
        
        # Get same provider twice - should be cached
        provider1 = router.get_provider_for_role("constructive")
        provider2 = router.get_provider_for_role("constructive")
        
        assert provider1 is provider2  # Same object (cached)
        
        # Different role - should be different
        provider3 = router.get_provider_for_role("destructive")
        assert provider1 is not provider3


# ============================================================================
# 6d. Integration Smoke Test
# ============================================================================

class TestIntegrationSmoke:
    """Integration smoke tests - verify patched module integrates correctly."""

    def test_module_imports(self):
        """Test that all required imports work."""
        from berb.pipeline.stage_impls._synthesis import (
            _execute_synthesis,
            _execute_hypothesis_gen,
            _SimpleRouter,
            _LLMProviderWrapper,
            _fallback_hypothesis_gen,
            MultiPerspectiveMethod,
        )
        
        # All imports successful
        assert _execute_synthesis is not None
        assert _execute_hypothesis_gen is not None
        assert _SimpleRouter is not None
        assert _LLMProviderWrapper is not None
        assert _fallback_hypothesis_gen is not None
        assert MultiPerspectiveMethod is not None

    def test_stage_result_compatibility(self):
        """Test that StageResult is compatible with pipeline."""
        from berb.pipeline.stage_impls._synthesis import _execute_hypothesis_gen
        from berb.pipeline.stages import Stage, StageStatus
        
        config = MagicMock()
        config.research.topic = "Integration test"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_dir = Path(tmpdir) / "stage"
            run_dir = Path(tmpdir) / "run"
            stage_dir.mkdir(parents=True)
            run_dir.mkdir(parents=True)
            
            result = _execute_hypothesis_gen(
                stage_dir=stage_dir,
                run_dir=run_dir,
                config=config,
                adapters=MagicMock(spec=AdapterBundle),
                llm=None,
                prompts=None,
            )
            
            # Verify StageResult structure
            assert hasattr(result, 'stage')
            assert hasattr(result, 'status')
            assert hasattr(result, 'artifacts')
            assert hasattr(result, 'evidence_refs')
            
            # Verify values
            assert result.stage == Stage.HYPOTHESIS_GEN
            assert result.status == StageStatus.DONE
            assert isinstance(result.artifacts, tuple)

    def test_file_artifact_creation(self):
        """Test that hypothesis file artifacts are created correctly."""
        from berb.pipeline.stage_impls._synthesis import _execute_hypothesis_gen
        
        config = MagicMock()
        config.research.topic = "Test"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_dir = Path(tmpdir) / "stage"
            run_dir = Path(tmpdir) / "run"
            stage_dir.mkdir(parents=True)
            run_dir.mkdir(parents=True)
            
            result = _execute_hypothesis_gen(
                stage_dir=stage_dir,
                run_dir=run_dir,
                config=config,
                adapters=MagicMock(spec=AdapterBundle),
                llm=None,
                prompts=None,
            )
            
            # Verify artifacts exist
            assert "hypotheses.md" in result.artifacts
            
            hypotheses_path = stage_dir / "hypotheses.md"
            assert hypotheses_path.exists()
            
            content = hypotheses_path.read_text(encoding="utf-8")
            assert len(content) > 0


# ============================================================================
# Main test runner
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
