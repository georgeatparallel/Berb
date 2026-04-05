# Reasoner Model Implementation Plan

**Integrating Optimized LLM Models into Berb Reasoning Methods**

*Document Version: 1.0*  
*Created: March 29, 2026*  
*Author: Senior Software Reliability Engineer*

---

## Executive Summary

This document provides a **comprehensive implementation plan** for integrating the recommended cost-optimized LLM models into Berb's 9 reasoning methods. The implementation achieves **80-85% cost savings** while maintaining or improving output quality.

### Implementation Goals

| Goal | Target | Success Metric |
|------|--------|----------------|
| **Cost Reduction** | 80-85% savings | Avg cost per reasoning execution < $5 |
| **Quality Maintenance** | Zero degradation | Benchmark scores within 5% of baseline |
| **Backward Compatibility** | 100% API compatibility | Existing code works without changes |
| **Performance** | <10ms routing overhead | P99 latency < 50ms for model selection |
| **Reliability** | 99.9% availability | Fallback success rate > 99% |

### Implementation Timeline

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| **Phase 0** | 1 day | Infrastructure setup |
| **Phase 1** | 2 days | Router enhancement |
| **Phase 2** | 3 days | Reasoner integration |
| **Phase 3** | 2 days | Testing & validation |
| **Phase 4** | 1 day | Rollout & monitoring |
| **Total** | **9 days** | Full production deployment |

---

## Current Architecture Analysis

### Existing Components

```
┌─────────────────────────────────────────────────────────────────┐
│                     Current Architecture                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Reasoner     │───▶│ NadirClaw    │───▶│ LLM Provider │      │
│  │ Methods      │    │ Router       │    │ (OpenRouter) │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                   │                                       │
│         │                   │ 3-tier routing:                       │
│         │                   │ - simple: gemini-2.5-flash           │
│         │                   │ - mid: gpt-4o-mini                   │
│         │                   │ - complex: claude-sonnet-4-5         │
│         ▼                                                           │
│  ┌──────────────┐                                                  │
│  │ llm_client   │                                                  │
│  │ (direct)     │───▶ Some methods bypass router                  │
│  └──────────────┘                                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Integration Points Identified

| Component | File | Integration Type | Complexity |
|-----------|------|------------------|------------|
| **NadirClawRouter** | `berb/llm/nadirclaw_router.py` | Enhance with role-based routing | Medium |
| **Multi-Perspective** | `berb/reasoning/multi_perspective.py` | Uses `router.get_provider_for_role()` | Low |
| **Pre-Mortem** | `berb/reasoning/pre_mortem.py` | Uses `router.get_provider_for_role()` | Low |
| **Bayesian** | `berb/reasoning/bayesian.py` | Uses `router.get_provider_for_role()` | Low |
| **Debate** | `berb/reasoning/debate.py` | Uses `llm_client.chat()` directly | Medium |
| **Dialectical** | `berb/reasoning/dialectical.py` | Uses `llm_client.chat()` directly | Medium |
| **Research** | `berb/reasoning/research.py` | Uses `llm_client.chat()` directly | Medium |
| **Socratic** | `berb/reasoning/socratic.py` | Uses `llm_client.chat()` directly | Medium |
| **Scientific** | `berb/reasoning/scientific.py` | Uses `llm_client.chat()` directly | Medium |
| **Jury** | `berb/reasoning/jury.py` | Uses `llm_client.chat()` directly | Medium |
| **Config** | `berb/config.py` | Add reasoning model config section | Low |

---

## Target Architecture

### Enhanced Router Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Target Architecture                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Reasoning Model Config (YAML)                │  │
│  │  - Per-method model routing                              │  │
│  │  - Phase-specific models                                 │  │
│  │  - Fallback chains                                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            │                                    │
│                            ▼                                    │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Reasoner     │───▶│ Enhanced     │───▶│ OpenRouter   │      │
│  │ Methods      │    │ NadirClaw    │    │ API          │      │
│  │ (9 methods)  │    │ Router       │    │              │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                            │                                    │
│                            │ Role-based routing:                │
│                            │ - constructive, destructive, etc.  │
│                            │ - 27 unique roles across methods   │
│                            ▼                                    │
│                     ┌──────────────┐                            │
│                     │ Cost Tracker │                            │
│                     │ & Metrics    │                            │
│                     └──────────────┘                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Model Routing Strategy

```python
# Example: Multi-Perspective routing
routing_config = {
    "multi_perspective": {
        "constructive": "anthropic/claude-sonnet-4.6",   # Premium
        "destructive": "anthropic/claude-opus-4.6",      # Elite
        "systemic": "openai/gpt-5.4",                    # Premium
        "minimalist": "deepseek/deepseek-v3.2",          # Budget
        "scoring": "openai/gpt-5.2-codex",               # Value
    }
}
```

---

## Phase 0: Infrastructure Setup (Day 1)

### Task 0.1: OpenRouter API Setup

**Objective:** Configure OpenRouter API access with proper authentication.

**Steps:**
1. Create OpenRouter account at https://openrouter.ai
2. Generate API key
3. Add to environment variables
4. Test connectivity

**Files Modified:**
- `.env` (create if not exists)
- `config.berb.example.yaml`

**Configuration:**
```yaml
# .env
OPENROUTER_API_KEY=sk_or_xxxxx...

# config.berb.example.yaml
llm:
  provider: "openrouter"
  base_url: "https://openrouter.ai/api/v1"
  api_key_env: "OPENROUTER_API_KEY"
```

**Acceptance Criteria:**
- [ ] API key configured in environment
- [ ] Test connection successful
- [ ] Documentation updated

---

### Task 0.2: Model Availability Verification

**Objective:** Verify all recommended models are available on OpenRouter.

**Models to Verify:**

| Model | Provider | Status | Notes |
|-------|----------|--------|-------|
| deepseek/deepseek-v3.2 | DeepSeek | ☐ Pending | Best value |
| deepseek/deepseek-r1 | DeepSeek | ☐ Pending | Complex reasoning |
| anthropic/claude-sonnet-4.6 | Anthropic | ☐ Pending | Premium |
| anthropic/claude-opus-4.6 | Anthropic | ☐ Pending | Elite |
| anthropic/claude-haiku-4.5 | Anthropic | ☐ Pending | Fast |
| openai/gpt-5.2-codex | OpenAI | ☐ Pending | Coding |
| openai/gpt-5.4 | OpenAI | ☐ Pending | General |
| google/gemini-3-flash-preview | Google | ☐ Pending | Long-context |
| google/gemini-3.1-flash-lite-preview | Google | ☐ Pending | Budget |

**Script:**
```python
# scripts/verify_models.py
import httpx
import os

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
MODELS_TO_VERIFY = [
    "deepseek/deepseek-v3.2",
    "deepseek/deepseek-r1",
    # ... etc
]

async def verify_model(model_id: str) -> bool:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://openrouter.ai/api/v1/models/{model_id}",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
        )
        return response.status_code == 200
```

**Acceptance Criteria:**
- [ ] All 9+ models verified available
- [ ] Fallback models identified for unavailable models
- [ ] Pricing confirmed matches research

---

### Task 0.3: Cost Tracking Infrastructure

**Objective:** Set up token usage tracking for cost monitoring.

**Files Created:**
- `berb/metrics/reasoning_cost_tracker.py`

**Implementation:**
```python
"""Cost tracking for reasoning method executions."""

from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime, timezone

@dataclass
class ReasoningCostRecord:
    """Single cost record for reasoning execution."""
    method: str  # e.g., "multi_perspective"
    phase: str   # e.g., "constructive"
    model: str   # e.g., "anthropic/claude-sonnet-4.6"
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    timestamp: datetime
    run_id: Optional[str] = None

class ReasoningCostTracker:
    """Track and analyze reasoning method costs."""
    
    MODEL_PRICING = {
        # Input / Output per 1M tokens
        "deepseek/deepseek-v3.2": (0.26, 0.38),
        "deepseek/deepseek-r1": (0.70, 2.50),
        "anthropic/claude-sonnet-4.6": (3.00, 15.00),
        "anthropic/claude-opus-4.6": (5.00, 25.00),
        # ... etc
    }
    
    def track(self, method: str, phase: str, model: str, 
              input_tokens: int, output_tokens: int,
              duration_ms: int, run_id: Optional[str] = None) -> ReasoningCostRecord:
        """Track a reasoning execution."""
        input_price, output_price = self.MODEL_PRICING.get(model, (0, 0))
        cost_usd = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
        
        record = ReasoningCostRecord(
            method=method,
            phase=phase,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc),
            run_id=run_id,
        )
        # Persist to database
        self._persist(record)
        return record
    
    def get_summary(self, days: int = 7) -> Dict:
        """Get cost summary for last N days."""
        # Query database and aggregate
        pass
```

**Acceptance Criteria:**
- [ ] Cost tracker implemented
- [ ] All model pricing configured
- [ ] Integration with existing TokenTracker
- [ ] Dashboard metrics available

---

## Phase 1: Router Enhancement (Days 2-3)

### Task 1.1: Extend NadirClawRouter with Role-Based Routing

**Objective:** Add `get_provider_for_role()` method to support reasoner-specific model selection.

**Files Modified:**
- `berb/llm/nadirclaw_router.py`

**Implementation:**
```python
class NadirClawRouter:
    """Enhanced router with role-based model selection."""
    
    def __init__(
        self,
        simple_model: str = "gemini/gemini-2.5-flash",
        mid_model: str = "openai/gpt-4o-mini",
        complex_model: str = "anthropic/claude-sonnet-4-5-20250929",
        role_models: Optional[Dict[str, str]] = None,  # NEW
        fallback_chain: Optional[List[str]] = None,     # NEW
    ):
        self.simple_model = simple_model
        self.mid_model = mid_model
        self.complex_model = complex_model
        # NEW: Role-specific model overrides
        self.role_models = role_models or {}
        self.fallback_chain = fallback_chain or [
            simple_model, mid_model, complex_model
        ]
    
    def get_provider_for_role(self, role: str) -> Any:
        """Get LLM provider for specific role.
        
        Args:
            role: Role name (e.g., "constructive", "destructive", "scoring")
        
        Returns:
            LLM provider instance
        
        Example:
            >>> router = NadirClawRouter(role_models={
            ...     "constructive": "anthropic/claude-sonnet-4.6",
            ...     "destructive": "anthropic/claude-opus-4.6",
            ... })
            >>> provider = router.get_provider_for_role("constructive")
        """
        # Get model for role (with fallback to complexity-based selection)
        model = self.role_models.get(role)
        
        if model is None:
            # Fall back to complexity-based selection
            # Role keywords mapped to complexity tiers
            role_complexity = {
                "constructive": "mid",
                "destructive": "complex",
                "systemic": "complex",
                "minimalist": "simple",
                "scoring": "mid",
                "narrative": "complex",
                "root_cause": "mid",
                "early_warning": "simple",
                "hardened": "mid",
                "prior": "mid",
                "likelihood": "simple",
                "sensitivity": "simple",
            }
            tier = role_complexity.get(role.lower(), "mid")
            model = {
                "simple": self.simple_model,
                "mid": self.mid_model,
                "complex": self.complex_model,
            }.get(tier, self.mid_model)
        
        # Create provider for model
        return self._create_provider(model)
    
    def _create_provider(self, model: str) -> Any:
        """Create LLM provider for specific model."""
        # Implementation depends on provider abstraction
        # Returns provider instance with .chat() method
        pass
```

**Acceptance Criteria:**
- [ ] `get_provider_for_role()` implemented
- [ ] Role-based model selection works
- [ ] Fallback to complexity-based routing
- [ ] Unit tests pass

---

### Task 1.2: Add Fallback Chain Support

**Objective:** Implement cascading fallback for model availability issues.

**Files Modified:**
- `berb/llm/nadirclaw_router.py`

**Implementation:**
```python
class NadirClawRouter:
    # ... existing code ...
    
    def get_provider_for_role(
        self, 
        role: str, 
        use_fallback: bool = True
    ) -> Any:
        """Get provider with fallback chain support."""
        model = self.role_models.get(role)
        
        if use_fallback and self.fallback_chain:
            # Try models in order until one succeeds
            for fallback_model in self.fallback_chain:
                try:
                    provider = self._create_provider_with_health_check(fallback_model)
                    if provider.is_healthy():
                        logger.info(f"Using fallback model: {fallback_model}")
                        return provider
                except Exception as e:
                    logger.warning(f"Model {fallback_model} unavailable: {e}")
                    continue
            
            # All fallbacks exhausted
            raise RuntimeError("All models in fallback chain unavailable")
        
        return self._create_provider(model)
    
    def _create_provider_with_health_check(self, model: str) -> Any:
        """Create provider with health check."""
        provider = self._create_provider(model)
        # Perform quick health check
        if not self._check_model_availability(model):
            raise RuntimeError(f"Model {model} not available")
        return provider
```

**Acceptance Criteria:**
- [ ] Fallback chain implemented
- [ ] Health check before provider creation
- [ ] Logging for fallback usage
- [ ] Tests for fallback scenarios

---

### Task 1.3: Configuration Integration

**Objective:** Load role-based model config from YAML.

**Files Modified:**
- `berb/config.py`
- `berb/llm/nadirclaw_router.py`

**Configuration Schema:**
```yaml
# config.berb.yaml

reasoning:
  # Global defaults
  default_model: "deepseek/deepseek-v3.2"
  fallback_models:
    - "google/gemini-3.1-flash-lite-preview"
    - "openai/gpt-5.2-codex"
  
  # Per-method overrides
  methods:
    multi_perspective:
      constructive: "anthropic/claude-sonnet-4.6"
      destructive: "anthropic/claude-opus-4.6"
      systemic: "openai/gpt-5.4"
      minimalist: "deepseek/deepseek-v3.2"
      scoring: "openai/gpt-5.2-codex"
    
    pre_mortem:
      narrative: "deepseek/deepseek-r1"
      root_cause: "openai/gpt-5.2-codex"
      early_warning: "deepseek/deepseek-v3.2"
      hardened: "anthropic/claude-sonnet-4.6"
    
    # ... etc for all 9 methods
```

**Config Class:**
```python
@dataclass(frozen=True)
class ReasoningConfig:
    """Reasoning method configuration."""
    default_model: str = "deepseek/deepseek-v3.2"
    fallback_models: tuple[str, ...] = (
        "google/gemini-3.1-flash-lite-preview",
        "openai/gpt-5.2-codex",
    )
    method_models: dict[str, dict[str, str]] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReasoningConfig:
        """Parse from config dict."""
        return cls(
            default_model=data.get("default_model", "deepseek/deepseek-v3.2"),
            fallback_models=tuple(data.get("fallback_models", [])),
            method_models=data.get("methods", {}),
        )
```

**Router Integration:**
```python
def create_router_from_config(config: ReasoningConfig) -> NadirClawRouter:
    """Create router from reasoning config."""
    # Flatten method-specific models
    role_models = {}
    for method, roles in config.method_models.items():
        for role, model in roles.items():
            role_models[role] = model
    
    return NadirClawRouter(
        simple_model=config.default_model,
        mid_model=config.default_model,  # Override per role
        complex_model=config.default_model,
        role_models=role_models,
        fallback_chain=list(config.fallback_models),
    )
```

**Acceptance Criteria:**
- [ ] Config schema defined
- [ ] YAML parsing implemented
- [ ] Router creation from config
- [ ] Documentation updated

---

## Phase 2: Reasoner Integration (Days 4-6)

### Task 2.1: Update Router-Based Methods (Low Complexity)

**Objective:** Update methods already using router to use new role-based routing.

**Methods:**
- Multi-Perspective (`berb/reasoning/multi_perspective.py`)
- Pre-Mortem (`berb/reasoning/pre_mortem.py`)
- Bayesian (`berb/reasoning/bayesian.py`)

**Changes Required:**
- Minimal - these methods already use `router.get_provider_for_role()`
- Verify role names match config
- Add logging for model selection

**Example Change:**
```python
# multi_perspective.py - Add logging
def _get_provider_for_perspective(self, perspective: PerspectiveType) -> Any:
    """Get LLM provider for perspective."""
    if self.router is None:
        self._logger.warning("No router configured, using fallback")
        return _FallbackProvider()
    
    role_map = {
        PerspectiveType.CONSTRUCTIVE: "constructive",
        PerspectiveType.DESTRUCTIVE: "destructive",
        PerspectiveType.SYSTEMIC: "systemic",
        PerspectiveType.MINIMALIST: "minimalist",
    }
    
    role = role_map[perspective]
    provider = self.router.get_provider_for_role(role)
    
    # NEW: Log model selection
    self._logger.info(
        f"Multi-Perspective: {perspective.value} → "
        f"using model from router"
    )
    
    return provider
```

**Acceptance Criteria:**
- [ ] All 3 methods updated
- [ ] Logging added
- [ ] Tests pass
- [ ] No breaking changes

---

### Task 2.2: Migrate Direct-LLM Methods to Router (Medium Complexity)

**Objective:** Migrate methods using `llm_client.chat()` directly to use router.

**Methods:**
- Debate (`berb/reasoning/debate.py`)
- Dialectical (`berb/reasoning/dialectical.py`)
- Research (`berb/reasoning/research.py`)
- Socratic (`berb/reasoning/socratic.py`)
- Scientific (`berb/reasoning/scientific.py`)
- Jury (`berb/reasoning/jury.py`)

**Migration Strategy:**

**Before:**
```python
class DebateMethod(ReasoningMethod):
    def __init__(self, llm_client: Any = None, ...):
        self.llm_client = llm_client
    
    async def _generate_pro_arguments(self, topic: str) -> list:
        response = self.llm_client.chat([...])
        return parse_arguments(response.content)
```

**After:**
```python
class DebateMethod(ReasoningMethod):
    def __init__(
        self, 
        router: Any = None,  # Changed from llm_client
        llm_client: Any = None,  # Kept for backward compatibility
        ...
    ):
        self.router = router
        self.llm_client = llm_client  # Fallback
    
    async def _generate_pro_arguments(self, topic: str) -> list:
        # Use router if available
        if self.router:
            provider = self.router.get_provider_for_role("debate_pro")
            response = await provider.chat([...])
        else:
            # Fallback to direct llm_client
            response = self.llm_client.chat([...])
        return parse_arguments(response.content)
```

**Role Mapping:**

| Method | Phase | Role Name |
|--------|-------|-----------|
| Debate | Pro arguments | `debate_pro` |
| Debate | Con arguments | `debate_con` |
| Debate | Judge | `debate_judge` |
| Dialectical | Thesis | `dialectical_thesis` |
| Dialectical | Antithesis | `dialectical_antithesis` |
| Dialectical | Synthesis | `dialectical_synthesis` |
| Research | Query | `research_query` |
| Research | Synthesis | `research_synthesis` |
| Research | Gap | `research_gap` |
| Research | Final | `research_final` |
| Socratic | Clarification | `socratic_clarification` |
| Socratic | Assumption | `socratic_assumption` |
| Socratic | Evidence | `socratic_evidence` |
| Socratic | Perspective | `socratic_perspective` |
| Socratic | Meta | `socratic_meta` |
| Scientific | Observation | `scientific_observation` |
| Scientific | Hypothesis | `scientific_hypothesis` |
| Scientific | Prediction | `scientific_prediction` |
| Scientific | Experiment | `scientific_experiment` |
| Scientific | Analysis | `scientific_analysis` |
| Jury | Juror | `jury_juror` |
| Jury | Foreman | `jury_foreman` |
| Jury | Verdict | `jury_verdict` |

**Acceptance Criteria:**
- [ ] All 6 methods migrated
- [ ] Backward compatibility maintained
- [ ] Router used when available
- [ ] Fallback to llm_client works
- [ ] Tests pass for both modes

---

### Task 2.3: Update Method Constructors

**Objective:** Update all reasoner constructors to accept router parameter.

**Pattern:**
```python
class ReasoningMethod(ReasoningMethod):
    def __init__(
        self,
        router: Any = None,      # NEW: Primary interface
        llm_client: Any = None,  # DEPRECATED: Fallback only
        **kwargs
    ):
        super().__init__(...)
        self.router = router
        self.llm_client = llm_client  # For backward compatibility
        
        if router is None and llm_client is None:
            self._logger.warning(
                "No router or llm_client provided. "
                "Method will use default fallback."
            )
```

**Factory Function Updates:**
```python
# In berb/reasoning/__init__.py

def get_reasoner(
    method_type: str | MethodType,
    router: Any = None,      # NEW
    llm_client: Any = None,  # DEPRECATED
    **kwargs
) -> ReasoningMethod:
    """Get reasoner with router support."""
    # Auto-create router from config if not provided
    if router is None:
        from berb.config import load_config
        config = load_config()
        router = create_router_from_config(config.reasoning)
    
    # Create reasoner with router
    return ReasonerRegistry.create(
        method_type,
        router=router,
        llm_client=llm_client,
        **kwargs
    )
```

**Acceptance Criteria:**
- [ ] All constructors updated
- [ ] Factory function updated
- [ ] Deprecation warnings added
- [ ] Documentation updated

---

## Phase 3: Testing & Validation (Days 7-8)

### Task 3.1: Unit Tests

**Objective:** Create comprehensive unit tests for router and reasoners.

**Files Created:**
- `tests/test_reasoning_router.py`
- `tests/test_reasoning_models.py`

**Test Cases:**

```python
class TestNadirClawRouterRoleBased:
    """Test role-based routing."""
    
    def test_get_provider_for_role(self):
        """Router returns correct provider for role."""
        router = NadirClawRouter(role_models={
            "constructive": "anthropic/claude-sonnet-4.6",
            "destructive": "anthropic/claude-opus-4.6",
        })
        
        provider = router.get_provider_for_role("constructive")
        assert provider.model == "anthropic/claude-sonnet-4.6"
    
    def test_fallback_chain(self):
        """Router uses fallback chain when primary unavailable."""
        router = NadirClawRouter(
            role_models={"test": "unavailable/model"},
            fallback_chain=["deepseek/deepseek-v3.2"]
        )
        
        provider = router.get_provider_for_role("test", use_fallback=True)
        assert provider.model == "deepseek/deepseek-v3.2"
    
    def test_config_loading(self):
        """Router loads from config correctly."""
        config = ReasoningConfig.from_dict({
            "default_model": "deepseek/deepseek-v3.2",
            "methods": {
                "multi_perspective": {
                    "constructive": "anthropic/claude-sonnet-4.6"
                }
            }
        })
        router = create_router_from_config(config)
        
        provider = router.get_provider_for_role("constructive")
        assert provider.model == "anthropic/claude-sonnet-4.6"


class TestReasonerIntegration:
    """Test reasoner integration with router."""
    
    @pytest.mark.asyncio
    async def test_multi_perspective_with_router(self):
        """Multi-perspective uses router correctly."""
        router = create_test_router()
        method = get_reasoner("multi_perspective", router=router)
        
        result = await method.execute(test_context)
        
        assert result.success
        assert len(result.output["perspectives"]) == 4
    
    @pytest.mark.asyncio
    async def test_debate_migration(self):
        """Debate method works with router."""
        router = create_test_router()
        method = get_reasoner("debate", router=router)
        
        result = await method.execute(test_context)
        
        assert result.success
        assert "winner" in result.output
```

**Acceptance Criteria:**
- [ ] 20+ unit tests created
- [ ] All tests pass
- [ ] Code coverage > 80%
- [ ] CI integration working

---

### Task 3.2: Integration Tests

**Objective:** Test full reasoning pipeline with new models.

**Files Created:**
- `tests/test_reasoning_integration.py`

**Test Scenarios:**

```python
class TestReasoningIntegration:
    """Integration tests for reasoning methods with optimized models."""
    
    @pytest.mark.asyncio
    async def test_all_methods_with_value_config(self):
        """Test all 9 methods with value-tier models."""
        config = load_value_config()  # Value-tier model config
        router = create_router_from_config(config)
        
        methods = [
            "multi_perspective",
            "pre_mortem",
            "bayesian",
            "debate",
            "dialectical",
            "research",
            "socratic",
            "scientific",
            "jury",
        ]
        
        for method_name in methods:
            method = get_reasoner(method_name, router=router)
            result = await method.execute(test_context)
            
            assert result.success, f"{method_name} failed"
            assert result.confidence > 0.5, f"{method_name} low confidence"
    
    @pytest.mark.asyncio
    async def test_cost_tracking(self):
        """Verify cost tracking works correctly."""
        tracker = ReasoningCostTracker()
        router = create_test_router(cost_tracker=tracker)
        
        method = get_reasoner("multi_perspective", router=router)
        result = await method.execute(test_context)
        
        # Verify cost was tracked
        summary = tracker.get_summary(days=1)
        assert summary["total_cost_usd"] > 0
        assert summary["total_executions"] == 1
    
    @pytest.mark.asyncio
    async def test_fallback_behavior(self):
        """Test fallback chain activates correctly."""
        # Configure with unavailable primary model
        config = {
            "methods": {
                "multi_perspective": {
                    "constructive": "unavailable/model"
                }
            },
            "fallback_models": ["deepseek/deepseek-v3.2"]
        }
        router = create_router_from_config(ReasoningConfig.from_dict(config))
        
        method = get_reasoner("multi_perspective", router=router)
        result = await method.execute(test_context)
        
        # Should succeed using fallback
        assert result.success
```

**Acceptance Criteria:**
- [ ] All 9 methods tested
- [ ] Cost tracking verified
- [ ] Fallback behavior tested
- [ ] Performance benchmarks met

---

### Task 3.3: Quality Validation

**Objective:** Validate output quality matches or exceeds baseline.

**Methodology:**

1. **Generate baseline outputs** with premium models
2. **Generate test outputs** with value models
3. **Compare outputs** using:
   - LLM-as-judge evaluation
   - Human expert review (sample)
   - Benchmark task performance

**Evaluation Script:**
```python
class QualityValidator:
    """Validate reasoning output quality."""
    
    def compare_outputs(
        self,
        baseline_output: dict,
        test_output: dict,
        method: str
    ) -> QualityComparison:
        """Compare baseline vs test output quality."""
        # Use LLM-as-judge
        judge_prompt = f"""
        Compare two reasoning outputs for {method}:
        
        Output A (Baseline - Premium Models):
        {json.dumps(baseline_output, indent=2)}
        
        Output B (Test - Value Models):
        {json.dumps(test_output, indent=2)}
        
        Rate each on:
        - Logical consistency (1-10)
        - Completeness (1-10)
        - Actionability (1-10)
        - Overall quality (1-10)
        
        Which is better? A, B, or Tie?
        """
        
        judge_response = self._call_judge(judge_prompt)
        return QualityComparison.from_judge_response(judge_response)
    
    def run_benchmark_tasks(self, method: str) -> BenchmarkResults:
        """Run standardized benchmark tasks."""
        # Method-specific benchmarks
        benchmarks = {
            "multi_perspective": self._benchmark_multi_perspective,
            "pre_mortem": self._benchmark_pre_mortem,
            # ... etc
        }
        return benchmarks[method]()
```

**Acceptance Criteria:**
- [ ] Quality within 5% of baseline
- [ ] No critical quality regressions
- [ ] Benchmark scores documented
- [ ] Human review completed (sample)

---

## Phase 4: Rollout & Monitoring (Day 9)

### Task 4.1: Staged Rollout

**Objective:** Gradual rollout to minimize risk.

**Rollout Plan:**

| Stage | Duration | Scope | Success Criteria |
|-------|----------|-------|------------------|
| **Alpha** | 4 hours | Internal testing | No critical bugs |
| **Beta** | 24 hours | 10% of runs | Cost savings confirmed |
| **Canary** | 48 hours | 50% of runs | Quality maintained |
| **General** | Ongoing | 100% of runs | All metrics green |

**Rollback Triggers:**
- Error rate > 5%
- Cost increase > 10%
- Quality score drop > 10%
- User complaints > 3

---

### Task 4.2: Monitoring Dashboard

**Objective:** Real-time visibility into model performance and costs.

**Metrics to Track:**

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Cost per execution | < $5 | > $10 |
| P99 latency | < 500ms | > 1000ms |
| Error rate | < 1% | > 5% |
| Fallback usage | < 10% | > 25% |
| Quality score | > 8/10 | < 7/10 |

**Dashboard Implementation:**
```python
# berb/metrics/reasoning_dashboard.py

class ReasoningDashboard:
    """Real-time reasoning metrics dashboard."""
    
    def get_current_metrics(self) -> dict:
        """Get current metrics for dashboard."""
        return {
            "cost_per_execution": self._calc_avg_cost(),
            "p99_latency": self._calc_p99_latency(),
            "error_rate": self._calc_error_rate(),
            "fallback_rate": self._calc_fallback_rate(),
            "quality_score": self._get_quality_score(),
            "model_distribution": self._get_model_distribution(),
        }
    
    def get_alerts(self) -> list:
        """Get active alerts."""
        alerts = []
        metrics = self.get_current_metrics()
        
        if metrics["cost_per_execution"] > 10:
            alerts.append("HIGH_COST: Cost per execution > $10")
        if metrics["error_rate"] > 0.05:
            alerts.append("HIGH_ERROR_RATE: Error rate > 5%")
        # ... etc
        
        return alerts
```

**Acceptance Criteria:**
- [ ] Dashboard implemented
- [ ] All metrics tracked
- [ ] Alerts configured
- [ ] Documentation complete

---

### Task 4.3: Documentation Updates

**Objective:** Complete documentation for users and developers.

**Documents to Update:**

1. **User Guide** (`docs/REASONER_MODEL_RECOMMENDATIONS.md`)
   - Already created ✓

2. **Developer Guide** (`docs/REASONER_IMPLEMENTATION.md`)
   - Architecture diagrams
   - API reference
   - Extension guide

3. **Configuration Reference** (`docs/CONFIGURATION.md`)
   - YAML schema
   - Examples
   - Troubleshooting

4. **Migration Guide** (`docs/MIGRATION_GUIDE.md`)
   - Upgrade steps
   - Breaking changes
   - Rollback procedures

**Acceptance Criteria:**
- [ ] All documents updated
- [ ] Examples tested
- [ ] Screenshots included
- [ ] Version control tagged

---

## Risk Mitigation

### Identified Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Model unavailable | Medium | High | Fallback chain, multi-provider |
| Quality regression | Low | High | Quality validation, staged rollout |
| Cost overrun | Low | Medium | Cost tracking, alerts |
| Breaking changes | Low | Medium | Backward compatibility, deprecation warnings |
| Performance regression | Low | Low | Performance testing, monitoring |

### Contingency Plans

**If models unavailable:**
1. Activate fallback chain
2. Switch to alternative provider
3. Use cached responses (if available)

**If quality regression detected:**
1. Rollback to previous config
2. Investigate root cause
3. Adjust model selection

**If cost overrun:**
1. Review model selection
2. Adjust routing thresholds
3. Implement stricter budgets

---

## Success Metrics

### Cost Metrics

| Metric | Baseline | Target | Actual |
|--------|----------|--------|--------|
| Avg cost per reasoning execution | $20 | $4 | ☐ |
| Monthly reasoning cost | $1000 | $200 | ☐ |
| Cost savings | - | 80% | ☐ |

### Quality Metrics

| Metric | Baseline | Target | Actual |
|--------|----------|--------|--------|
| Output quality score | 8.5/10 | 8.0/10 | ☐ |
| User satisfaction | 90% | 85% | ☐ |
| Benchmark performance | 100% | 95% | ☐ |

### Performance Metrics

| Metric | Baseline | Target | Actual |
|--------|----------|--------|--------|
| P99 latency | 400ms | 500ms | ☐ |
| Error rate | 0.5% | 1% | ☐ |
| Fallback rate | N/A | <10% | ☐ |

---

## Appendix A: Complete Role Mapping

### All 27 Roles Across 9 Methods

```yaml
roles:
  multi_perspective:
    - constructive
    - destructive
    - systemic
    - minimalist
    - scoring
  
  pre_mortem:
    - narrative
    - root_cause
    - early_warning
    - hardened
  
  bayesian:
    - prior
    - likelihood
    - sensitivity
  
  debate:
    - pro
    - con
    - judge
  
  dialectical:
    - thesis
    - antithesis
    - synthesis
  
  research:
    - query
    - synthesis
    - gap
    - final
  
  socratic:
    - clarification
    - assumption
    - evidence
    - perspective
    - meta
  
  scientific:
    - observation
    - hypothesis
    - prediction
    - experiment
    - analysis
  
  jury:
    - juror
    - foreman
    - verdict
```

---

## Appendix B: Model Pricing Reference

```yaml
model_pricing:
  # Budget tier
  deepseek/deepseek-v3.2:
    input: 0.26
    output: 0.38
    context: 164000
  
  deepseek/deepseek-r1:
    input: 0.70
    output: 2.50
    context: 64000
  
  # Value tier
  openai/gpt-5.2-codex:
    input: 1.75
    output: 14.00
    context: 400000
  
  google/gemini-3.1-flash-lite:
    input: 0.25
    output: 1.50
    context: 1050000
  
  # Premium tier
  anthropic/claude-sonnet-4.6:
    input: 3.00
    output: 15.00
    context: 1000000
  
  openai/gpt-5.4:
    input: 2.50
    output: 15.00
    context: 1050000
  
  # Elite tier
  anthropic/claude-opus-4.6:
    input: 5.00
    output: 25.00
    context: 1000000
```

---

**Document End**

*For questions or issues, contact the Berb development team.*
