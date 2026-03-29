# Extended Model Implementation Plan

**Integrating 11 LLM Providers with 80-97% Cost Optimization**

*Document Version: 1.0*  
*Created: March 29, 2026*  
*Based on: EXTENDED_MODEL_COMPARISON.md study*

---

## Executive Summary

This implementation plan integrates **11 LLM providers** and **100+ models** into Berb's 9 reasoning methods, achieving **97% cost savings** ($181 → $5.40 per full reasoning run) while maintaining or improving output quality.

### Implementation Goals

| Goal | Target | Success Metric |
|------|--------|----------------|
| **Cost Reduction** | 97% vs Premium | Avg cost < $6 per full run |
| **Provider Diversity** | 11 providers | No single provider >40% of calls |
| **Quality Maintenance** | Zero degradation | Benchmark scores within 5% |
| **Backward Compatibility** | 100% API compatible | Existing code works unchanged |
| **Performance** | <15ms routing overhead | P99 latency < 100ms |
| **Reliability** | 99.9% availability | Fallback success >99.5% |

### Key Discoveries Driving Implementation

| Discovery | Impact | Action |
|-----------|--------|--------|
| **MiniMax M2.5 FREE** (80.2% SWE-Bench) | 100% savings on budget phases | Primary budget model |
| **Qwen3.5-397B-A17B** (matches Opus) | 92% savings on elite tasks | Replace Claude Opus |
| **MiMo V2 Pro** (~Opus 4.6 performance) | 80% savings on premium | Replace Claude Sonnet |
| **Grok 4.20 Multi-Agent** (2M context) | Purpose-built for Jury | Jury method optimization |
| **Perplexity Sonar Pro** (built-in search) | Eliminates separate search API | Research method |
| **Kimi K2.5** (visual coding) | Unique multimodal capability | Scientific experiment design |

### Cost Impact Summary

| Configuration | Cost per Run | Monthly (1000 runs) | Annual |
|---------------|--------------|---------------------|--------|
| **Premium (baseline)** | $181.00 | $181,000 | $2,172,000 |
| **Original Value** | $39.50 | $39,500 | $474,000 |
| **NEW Optimized** | **$5.40** | **$5,400** | **$64,800** |
| **Total Savings** | **97%** | **$175,600/month** | **$2,107,200/year** |

---

## Implementation Timeline Overview

```
Week 1: Foundation & Quick Wins
├── Day 1-2: Infrastructure setup
├── Day 3-4: Provider integration (MiniMax, Qwen, GLM)
└── Day 5: Quick win deployments (FREE models)

Week 2: Core Integration
├── Day 1-2: Premium replacements (MiMo, Qwen-Max)
├── Day 3-4: Specialized providers (Kimi, Perplexity, Grok)
└── Day 5: Router enhancement complete

Week 3: Reasoner Migration
├── Day 1-2: Router-based methods (Multi-Perspective, Pre-Mortem, Bayesian)
├── Day 3-4: Direct-LLM methods (Debate, Dialectical, Research, Socratic, Scientific, Jury)
└── Day 5: Configuration finalization

Week 4: Testing & Rollout
├── Day 1-2: Comprehensive testing
├── Day 3: Staged rollout (Alpha → Beta)
├── Day 4: Canary deployment (50%)
└── Day 5: General availability (100%)
```

---

## Phase 0: Infrastructure Setup (Days 1-2)

### Task 0.1: Multi-Provider API Configuration

**Objective:** Set up API access for all 11 providers.

**Providers to Configure:**

| # | Provider | API Key Env Var | Status |
|---|----------|-----------------|--------|
| 1 | OpenRouter (aggregator) | `OPENROUTER_API_KEY` | ☐ Pending |
| 2 | MiniMax | `MINIMAX_API_KEY` | ☐ Pending |
| 3 | Qwen/Alibaba | `DASHSCOPE_API_KEY` | ☐ Pending |
| 4 | GLM/Z.ai | `ZHIPU_API_KEY` | ☐ Pending |
| 5 | MiMo/Xiaomi | `XIAOMI_API_KEY` | ☐ Pending |
| 6 | Kimi/Moonshot | `MOONSHOT_API_KEY` | ☐ Pending |
| 7 | Perplexity | `PERPLEXITY_API_KEY` | ☐ Pending |
| 8 | xAI/Grok | `XAI_API_KEY` | ☐ Pending |
| 9 | DeepSeek | `DEEPSEEK_API_KEY` | ☐ Pending |
| 10 | Google | `GOOGLE_API_KEY` | ☐ Pending |
| 11 | Anthropic | `ANTHROPIC_API_KEY` | ☐ Pending |
| 12 | OpenAI | `OPENAI_API_KEY` | ☐ Pending |

**Files Modified:**
- `.env.example` (add all provider keys)
- `config.berb.example.yaml` (add provider sections)

**Configuration Template:**
```yaml
# .env.example
# Primary aggregator (recommended - single key for all providers)
OPENROUTER_API_KEY=sk_or_xxxxx...

# Direct provider keys (optional - for higher rate limits)
MINIMAX_API_KEY=xxxxx...
DASHSCOPE_API_KEY=xxxxx...
ZHIPU_API_KEY=xxxxx...
XIAOMI_API_KEY=xxxxx...
MOONSHOT_API_KEY=xxxxx...
PERPLEXITY_API_KEY=xxxxx...
XAI_API_KEY=xxxxx...
DEEPSEEK_API_KEY=xxxxx...
GOOGLE_API_KEY=xxxxx...
ANTHROPIC_API_KEY=xxxxx...
OPENAI_API_KEY=xxxxx...
```

**Acceptance Criteria:**
- [ ] All 12 API keys configured
- [ ] Test connectivity to each provider
- [ ] Rate limit documentation created
- [ ] Fallback chain configured

---

### Task 0.2: Provider Availability Verification

**Objective:** Verify all recommended models are available and functional.

**Models to Verify (27 total):**

```python
# scripts/verify_all_models.py
MODELS_TO_VERIFY = {
    # Budget tier (FREE)
    "minimax/minimax-m2.5:free": {"provider": "MiniMax", "priority": "P0"},
    "z-ai/glm-4.5-air:free": {"provider": "GLM", "priority": "P0"},
    "qwen/qwen3-coder-480b-a35b:free": {"provider": "Qwen", "priority": "P0"},
    
    # Value tier
    "qwen/qwen3.5-flash": {"provider": "Qwen", "priority": "P0"},
    "qwen/qwen3-coder-next": {"provider": "Qwen", "priority": "P0"},
    "xiaomi/mimo-v2-flash": {"provider": "MiMo", "priority": "P1"},
    "z-ai/glm-4.7-flash": {"provider": "GLM", "priority": "P1"},
    "minimax/minimax-m2.5": {"provider": "MiniMax", "priority": "P1"},
    
    # Premium tier
    "xiaomi/mimo-v2-pro": {"provider": "MiMo", "priority": "P0"},
    "qwen/qwen3.5-397b-a17b": {"provider": "Qwen", "priority": "P0"},
    "qwen/qwen3-max-thinking": {"provider": "Qwen", "priority": "P1"},
    "moonshotai/kimi-k2.5": {"provider": "Kimi", "priority": "P1"},
    "z-ai/glm-5": {"provider": "GLM", "priority": "P2"},
    
    # Specialized
    "x-ai/grok-4.20-multi-agent-beta": {"provider": "xAI", "priority": "P0"},
    "x-ai/grok-4.20-beta": {"provider": "xAI", "priority": "P1"},
    "perplexity/sonar-pro-search": {"provider": "Perplexity", "priority": "P0"},
    "perplexity/sonar-reasoning-pro": {"provider": "Perplexity", "priority": "P1"},
    
    # Fallback (existing)
    "deepseek/deepseek-v3.2": {"provider": "DeepSeek", "priority": "P2"},
    "deepseek/deepseek-r1": {"provider": "DeepSeek", "priority": "P2"},
    "google/gemini-3.1-flash-lite-preview": {"provider": "Google", "priority": "P2"},
    "anthropic/claude-sonnet-4.6": {"provider": "Anthropic", "priority": "P3"},
    "anthropic/claude-opus-4.6": {"provider": "Anthropic", "priority": "P3"},
    "openai/gpt-5.2-codex": {"provider": "OpenAI", "priority": "P3"},
}
```

**Verification Script:**
```python
#!/usr/bin/env python3
"""Verify all recommended models are available."""

import asyncio
import httpx
import os
from typing import Dict, List

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

async def verify_model(model_id: str, priority: str) -> dict:
    """Verify single model availability."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"https://openrouter.ai/api/v1/models/{model_id}",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://github.com/georgehadji/berb",
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "model": model_id,
                    "status": "available",
                    "priority": priority,
                    "context_window": data.get("context_length", "unknown"),
                    "pricing": data.get("pricing", {}),
                }
            else:
                return {
                    "model": model_id,
                    "status": "unavailable",
                    "priority": priority,
                    "error": f"HTTP {response.status_code}",
                }
        except Exception as e:
            return {
                "model": model_id,
                "status": "error",
                "priority": priority,
                "error": str(e),
            }

async def main():
    """Verify all models."""
    tasks = [
        verify_model(model_id, info["priority"])
        for model_id, info in MODELS_TO_VERIFY.items()
    ]
    results = await asyncio.gather(*tasks)
    
    # Summary
    available = [r for r in results if r["status"] == "available"]
    unavailable = [r for r in results if r["status"] != "available"]
    
    print(f"✅ Available: {len(available)}/{len(results)}")
    print(f"❌ Unavailable: {len(unavailable)}/{len(results)}")
    
    if unavailable:
        print("\nUnavailable models:")
        for r in unavailable:
            print(f"  - {r['model']}: {r['error']}")

if __name__ == "__main__":
    asyncio.run(main())
```

**Acceptance Criteria:**
- [ ] All P0 models verified available
- [ ] Fallback models identified for any unavailable P0/P1 models
- [ ] Pricing confirmed matches research
- [ ] Rate limits documented

---

### Task 0.3: Enhanced Cost Tracking

**Objective:** Extend cost tracking to support all 11 providers.

**Files Created:**
- `berb/metrics/reasoning_cost_tracker.py` (enhanced version)

**Implementation:**
```python
"""Extended cost tracking for all 11 providers."""

from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime, timezone
from enum import Enum

class Provider(str, Enum):
    """LLM providers."""
    MINIMAX = "minimax"
    QWEN = "qwen"
    GLM = "glm"
    MIMO = "mimo"
    KIMI = "kimi"
    PERPLEXITY = "perplexity"
    XAI = "xai"
    DEEPSEEK = "deepseek"
    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"

@dataclass
class ReasoningCostRecord:
    """Single cost record for reasoning execution."""
    method: str  # e.g., "multi_perspective"
    phase: str   # e.g., "constructive"
    model: str   # e.g., "xiaomi/mimo-v2-pro"
    provider: Provider
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    timestamp: datetime
    run_id: Optional[str] = None
    quality_score: Optional[float] = None  # Post-execution quality rating

class ExtendedReasoningCostTracker:
    """Track and analyze reasoning method costs across all providers."""
    
    # Complete pricing for all 100+ models
    MODEL_PRICING: Dict[str, tuple[float, float]] = {
        # Budget tier (FREE)
        "minimax/minimax-m2.5:free": (0.00, 0.00),
        "z-ai/glm-4.5-air:free": (0.00, 0.00),
        "qwen/qwen3-coder-480b-a35b:free": (0.00, 0.00),
        
        # Value tier
        "qwen/qwen3.5-flash": (0.065, 0.26),
        "qwen/qwen3-coder-next": (0.12, 0.75),
        "xiaomi/mimo-v2-flash": (0.09, 0.29),
        "z-ai/glm-4.7-flash": (0.06, 0.40),
        "minimax/minimax-m2.5": (0.19, 1.15),
        "qwen/qwen3.5-35b-a3b": (0.1625, 1.30),
        
        # Premium tier
        "xiaomi/mimo-v2-pro": (1.00, 3.00),
        "qwen/qwen3.5-397b-a17b": (0.39, 2.34),
        "qwen/qwen3-max-thinking": (0.78, 3.90),
        "moonshotai/kimi-k2.5": (0.42, 2.20),
        "z-ai/glm-5": (0.72, 2.30),
        
        # Specialized
        "x-ai/grok-4.20-multi-agent-beta": (2.00, 6.00),
        "x-ai/grok-4.20-beta": (2.00, 6.00),
        "perplexity/sonar-pro-search": (3.00, 15.00),  # +$18/1k searches
        "perplexity/sonar-reasoning-pro": (2.00, 8.00),
        
        # Fallback (existing)
        "deepseek/deepseek-v3.2": (0.26, 0.38),
        "deepseek/deepseek-r1": (0.70, 2.50),
        "google/gemini-3.1-flash-lite-preview": (0.25, 1.50),
        "anthropic/claude-sonnet-4.6": (3.00, 15.00),
        "anthropic/claude-opus-4.6": (5.00, 25.00),
        "openai/gpt-5.2-codex": (1.75, 14.00),
    }
    
    def track(self, method: str, phase: str, model: str,
              input_tokens: int, output_tokens: int,
              duration_ms: int, run_id: Optional[str] = None) -> ReasoningCostRecord:
        """Track a reasoning execution."""
        # Determine provider from model string
        provider = self._extract_provider(model)
        
        # Calculate cost
        input_price, output_price = self.MODEL_PRICING.get(model, (0, 0))
        cost_usd = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
        
        # Handle Perplexity search costs
        if "perplexity" in model and "search" in model:
            search_cost = 0.018  # $18 per 1000 searches
            cost_usd += search_cost
        
        record = ReasoningCostRecord(
            method=method,
            phase=phase,
            model=model,
            provider=provider,
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
    
    def _extract_provider(self, model: str) -> Provider:
        """Extract provider from model string."""
        provider_map = {
            "minimax": Provider.MINIMAX,
            "qwen": Provider.QWEN,
            "z-ai": Provider.GLM,
            "xiaomi": Provider.MIMO,
            "moonshotai": Provider.KIMI,
            "perplexity": Provider.PERPLEXITY,
            "x-ai": Provider.XAI,
            "deepseek": Provider.DEEPSEEK,
            "google": Provider.GOOGLE,
            "anthropic": Provider.ANTHROPIC,
            "openai": Provider.OPENAI,
        }
        
        for prefix, provider in provider_map.items():
            if model.lower().startswith(prefix):
                return provider
        
        return Provider.OPENAI  # Default fallback
    
    def get_summary(self, days: int = 7) -> Dict:
        """Get cost summary for last N days."""
        # Query database and aggregate by:
        # - Total cost
        # - Cost per method
        # - Cost per provider
        # - Provider distribution
        # - Quality-adjusted cost (cost per quality point)
        pass
    
    def get_provider_distribution(self) -> Dict[Provider, float]:
        """Get cost distribution by provider."""
        # Returns percentage of total cost per provider
        # Target: No single provider >40%
        pass
    
    def get_alerts(self) -> List[str]:
        """Get cost-related alerts."""
        alerts = []
        summary = self.get_summary(days=1)
        
        if summary["total_cost_usd"] > 10:  # >$10 per run
            alerts.append(f"HIGH_COST: ${summary['total_cost_usd']:.2f} per run")
        
        # Check provider concentration
        distribution = self.get_provider_distribution()
        for provider, pct in distribution.items():
            if pct > 0.40:
                alerts.append(f"HIGH_CONCENTRATION: {provider.value} at {pct*100:.1f}%")
        
        return alerts
```

**Acceptance Criteria:**
- [ ] All 100+ models priced
- [ ] Provider extraction working
- [ ] Perplexity search costs handled
- [ ] Dashboard metrics available
- [ ] Alerts configured

---

## Phase 1: Router Enhancement (Days 3-5)

### Task 1.1: Extend NadirClawRouter for Multi-Provider

**Objective:** Enhance router to support all 11 providers with intelligent routing.

**Files Modified:**
- `berb/llm/nadirclaw_router.py`

**Key Enhancements:**

```python
class NadirClawRouter:
    """Enhanced router with multi-provider support and 27 role-based routes."""
    
    def __init__(
        self,
        simple_model: str = "minimax/minimax-m2.5:free",  # Changed default
        mid_model: str = "qwen/qwen3.5-flash",            # Changed default
        complex_model: str = "xiaomi/mimo-v2-pro",         # Changed default
        role_models: Optional[Dict[str, str]] = None,
        fallback_chain: Optional[List[str]] = None,
        provider_weights: Optional[Dict[Provider, float]] = None,  # NEW
        cost_budget_usd: Optional[float] = None,                   # NEW
    ):
        self.simple_model = simple_model
        self.mid_model = mid_model
        self.complex_model = complex_model
        self.role_models = role_models or {}
        self.fallback_chain = fallback_chain or [
            simple_model, mid_model, complex_model
        ]
        # NEW: Provider diversity control
        self.provider_weights = provider_weights or {
            Provider.MINIMAX: 0.25,   # 25% of calls
            Provider.QWEN: 0.25,      # 25% of calls
            Provider.MIMO: 0.15,      # 15% of calls
            Provider.GLM: 0.10,       # 10% of calls
            Provider.XAI: 0.10,       # 10% of calls
            Provider.KIMI: 0.05,      # 5% of calls
            Provider.PERPLEXITY: 0.05, # 5% of calls
            Provider.DEEPSEEK: 0.03,  # 3% of calls
            Provider.GOOGLE: 0.02,    # 2% of calls
        }
        self.cost_budget_usd = cost_budget_usd
        self._cost_tracker = ExtendedReasoningCostTracker()
    
    def get_provider_for_role(self, role: str, use_diversity: bool = True) -> Any:
        """Get LLM provider for specific role with provider diversity."""
        # Get model for role
        model = self.role_models.get(role)
        
        if model is None:
            # Fall back to complexity-based selection
            role_complexity = {
                # Multi-Perspective
                "constructive": "mid",
                "destructive": "complex",
                "systemic": "complex",
                "minimalist": "simple",
                "scoring": "mid",
                # Pre-Mortem
                "narrative": "complex",
                "root_cause": "mid",
                "early_warning": "simple",
                "hardened": "mid",
                # Bayesian
                "prior": "mid",
                "likelihood": "simple",
                "sensitivity": "simple",
                # Debate
                "pro": "complex",
                "con": "complex",
                "judge": "mid",
                # Dialectical
                "thesis": "mid",
                "antithesis": "complex",
                "synthesis": "mid",
                # Research
                "query": "mid",
                "synthesis": "mid",
                "gap": "simple",
                "final": "mid",
                # Socratic
                "clarification": "simple",
                "assumption": "simple",
                "evidence": "simple",
                "perspective": "mid",
                "meta": "mid",
                # Scientific
                "observation": "mid",
                "hypothesis": "complex",
                "prediction": "mid",
                "experiment": "mid",
                "analysis": "simple",
                # Jury
                "juror": "simple",
                "foreman": "mid",
                "verdict": "mid",
            }
            tier = role_complexity.get(role.lower(), "mid")
            model = {
                "simple": self.simple_model,
                "mid": self.mid_model,
                "complex": self.complex_model,
            }.get(tier, self.mid_model)
        
        # Apply provider diversity if enabled
        if use_diversity and self.provider_weights:
            model = self._apply_provider_diversity(model, role)
        
        # Check cost budget
        if self.cost_budget_usd:
            model = self._check_cost_budget(model)
        
        return self._create_provider(model)
    
    def _apply_provider_diversity(self, model: str, role: str) -> str:
        """Apply provider diversity routing."""
        # Get current provider distribution
        distribution = self._cost_tracker.get_provider_distribution()
        
        # Find providers under their weight target
        under_weight_providers = []
        for provider, target_weight in self.provider_weights.items():
            current_weight = distribution.get(provider, 0)
            if current_weight < target_weight:
                under_weight_providers.append(provider)
        
        # If current model's provider is over weight, try to switch
        current_provider = self._cost_tracker._extract_provider(model)
        if current_provider not in under_weight_providers and under_weight_providers:
            # Find alternative model from under-weight provider
            alternative = self._find_alternative_model(
                model, under_weight_providers, role
            )
            if alternative:
                logger.info(
                    f"Diversity routing: {model} → {alternative} "
                    f"({current_provider.value} over weight)"
                )
                return alternative
        
        return model
    
    def _find_alternative_model(self, model: str, providers: List[Provider], 
                                role: str) -> Optional[str]:
        """Find alternative model from specified providers."""
        # Model alternatives by tier and provider
        alternatives = {
            "simple": {
                Provider.MINIMAX: "minimax/minimax-m2.5:free",
                Provider.GLM: "z-ai/glm-4.5-air:free",
                Provider.QWEN: "qwen/qwen3.5-9b",
            },
            "mid": {
                Provider.QWEN: "qwen/qwen3.5-flash",
                Provider.MIMO: "xiaomi/mimo-v2-flash",
                Provider.GLM: "z-ai/glm-4.7-flash",
                Provider.KIMI: "moonshotai/kimi-k2.5",
            },
            "complex": {
                Provider.QWEN: "qwen/qwen3.5-397b-a17b",
                Provider.MIMO: "xiaomi/mimo-v2-pro",
                Provider.XAI: "x-ai/grok-4.20-beta",
            },
        }
        
        # Determine tier of current model
        tier = self._get_model_tier(model)
        
        # Find alternative from under-weight providers
        for provider in providers:
            if tier in alternatives and provider in alternatives[tier]:
                return alternatives[tier][provider]
        
        return None
```

**Acceptance Criteria:**
- [ ] All 27 roles mapped
- [ ] Provider diversity working
- [ ] Cost budget enforcement
- [ ] Unit tests pass

---

### Task 1.2: Fallback Chain Enhancement

**Objective:** Implement intelligent fallback with quality preservation.

**Files Modified:**
- `berb/llm/nadirclaw_router.py`

**Implementation:**
```python
class NadirClawRouter:
    # ... existing code ...
    
    def get_provider_for_role(
        self, 
        role: str, 
        use_fallback: bool = True,
        max_fallback_depth: int = 3
    ) -> Any:
        """Get provider with intelligent fallback chain."""
        model = self.role_models.get(role)
        
        if use_fallback and self.fallback_chain:
            return self._get_with_fallback(model, role, max_fallback_depth)
        
        return self._create_provider(model)
    
    def _get_with_fallback(self, model: str, role: str, 
                           max_depth: int) -> Any:
        """Get provider with fallback, tracking quality."""
        attempted = []
        
        for depth in range(max_depth):
            # Select model based on depth
            if depth == 0:
                current_model = model
            elif depth < len(self.fallback_chain):
                current_model = self.fallback_chain[depth - 1]
            else:
                current_model = self.fallback_chain[-1]
            
            if current_model in attempted:
                continue
            
            attempted.append(current_model)
            
            try:
                provider = self._create_provider_with_health_check(current_model)
                if provider.is_healthy():
                    if depth > 0:
                        logger.warning(
                            f"Fallback used for {role}: "
                            f"{model} → {current_model} (depth={depth})"
                        )
                    return provider
            except Exception as e:
                logger.warning(
                    f"Model {current_model} unavailable: {e}. "
                    f"Attempting fallback (depth={depth+1})"
                )
                continue
        
        # All fallbacks exhausted
        raise RuntimeError(
            f"All {len(attempted)} models in fallback chain unavailable "
            f"for role '{role}': {', '.join(attempted)}"
        )
    
    def _create_provider_with_health_check(self, model: str) -> Any:
        """Create provider with comprehensive health check."""
        provider = self._create_provider(model)
        
        # Health checks
        checks = [
            self._check_model_availability(model),
            self._check_rate_limit(model),
            self._check_cost_budget(model),
        ]
        
        if not all(checks):
            raise RuntimeError(f"Health check failed for {model}")
        
        return provider
```

**Acceptance Criteria:**
- [ ] Fallback chain tested
- [ ] Health checks implemented
- [ ] Logging for fallback usage
- [ ] Max depth enforced

---

## Phase 2: Reasoner Integration (Days 6-12)

### Task 2.1: Router-Based Methods (Low Complexity)

**Objective:** Update methods already using router.

**Methods:** Multi-Perspective, Pre-Mortem, Bayesian

**Changes:** Minimal - verify role names match config

```python
# Example: multi_perspective.py
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
    
    # NEW: Log model selection with cost info
    self._logger.info(
        f"Multi-Perspective [{perspective.value}]: "
        f"using {provider.model}"
    )
    
    return provider
```

**Acceptance Criteria:**
- [ ] All 3 methods updated
- [ ] Logging enhanced
- [ ] Tests pass

---

### Task 2.2: Direct-LLM Methods Migration (Medium Complexity)

**Objective:** Migrate 6 methods from `llm_client.chat()` to router.

**Methods:** Debate, Dialectical, Research, Socratic, Scientific, Jury

**Migration Pattern:**

```python
# Before (debate.py)
class DebateMethod(ReasoningMethod):
    def __init__(self, llm_client: Any = None, ...):
        self.llm_client = llm_client
    
    async def _generate_pro_arguments(self, topic: str) -> list:
        response = self.llm_client.chat([...])
        return parse_arguments(response.content)

# After (debate.py)
class DebateMethod(ReasoningMethod):
    def __init__(
        self, 
        router: Any = None,      # NEW: Primary
        llm_client: Any = None,  # DEPRECATED: Fallback
        ...
    ):
        self.router = router
        self.llm_client = llm_client
    
    async def _generate_pro_arguments(self, topic: str) -> list:
        if self.router:
            provider = self.router.get_provider_for_role("debate_pro")
            response = await provider.chat([...])
        else:
            # Fallback for backward compatibility
            response = self.llm_client.chat([...])
        return parse_arguments(response.content)
```

**Role Mapping Table:**

| Method | Phase | Role Name | Recommended Model |
|--------|-------|-----------|-------------------|
| Debate | Pro | `debate_pro` | Qwen3.5-397B-A17B |
| Debate | Con | `debate_con` | Qwen3-Max-Thinking |
| Debate | Judge | `debate_judge` | Grok 4.20 Beta |
| Dialectical | Thesis | `dialectical_thesis` | GLM 5 |
| Dialectical | Antithesis | `dialectical_antithesis` | Qwen3.5-397B-A17B |
| Dialectical | Synthesis | `dialectical_synthesis` | Kimi K2 Thinking |
| Research | Query | `research_query` | Perplexity Sonar Pro Search |
| Research | Synthesis | `research_synthesis` | Qwen3.5-Plus |
| Research | Gap | `research_gap` | MiniMax M2.5 FREE |
| Research | Final | `research_final` | MiMo V2 Pro |
| Socratic | Clarification | `socratic_clarification` | GLM 4.5 Air FREE |
| Socratic | Assumption | `socratic_assumption` | GLM 4.7 Flash |
| Socratic | Evidence | `socratic_evidence` | MiniMax M2.5 FREE |
| Socratic | Perspective | `socratic_perspective` | Qwen3.5-35B-A3B |
| Socratic | Meta | `socratic_meta` | Kimi K2 Thinking |
| Scientific | Observation | `scientific_observation` | GLM 4.7 |
| Scientific | Hypothesis | `scientific_hypothesis` | Qwen3-Max-Thinking |
| Scientific | Prediction | `scientific_prediction` | Qwen3-Coder-Next |
| Scientific | Experiment | `scientific_experiment` | Kimi K2.5 |
| Scientific | Analysis | `scientific_analysis` | MiniMax M2.5 FREE |
| Jury | Juror (6×) | `jury_juror` | Grok 4.20 Multi-Agent |
| Jury | Foreman | `jury_foreman` | Qwen3.5-Plus |
| Jury | Verdict | `jury_verdict` | GLM 5 |

**Acceptance Criteria:**
- [ ] All 6 methods migrated
- [ ] Backward compatibility maintained
- [ ] All 27 roles mapped
- [ ] Tests pass

---

## Phase 3: Testing & Validation (Days 13-16)

### Task 3.1: Unit Tests

**Objective:** Comprehensive unit tests for router and all reasoners.

**Files Created:**
- `tests/test_extended_router.py`
- `tests/test_all_reasoners_models.py`

**Test Coverage:**
- 50+ unit tests
- All 27 roles tested
- All 11 providers tested
- Fallback scenarios
- Provider diversity
- Cost budget enforcement

---

### Task 3.2: Integration Tests

**Objective:** Test full reasoning pipeline with optimized models.

**Test Scenarios:**

```python
class TestAllReasonersWithOptimizedModels:
    """Integration tests for all 9 methods with optimized models."""
    
    @pytest.mark.asyncio
    async def test_all_methods_value_config(self):
        """Test all 9 methods with value-tier models."""
        config = load_optimized_config()  # NEW optimized config
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
        
        results = {}
        for method_name in methods:
            method = get_reasoner(method_name, router=router)
            result = await method.execute(test_context)
            results[method_name] = result
            
            assert result.success, f"{method_name} failed"
            assert result.confidence > 0.5, f"{method_name} low confidence"
        
        # Verify total cost
        total_cost = sum(r.metadata.get("cost_usd", 0) for r in results.values())
        assert total_cost < 6.00, f"Total cost ${total_cost:.2f} exceeds $6 target"
    
    @pytest.mark.asyncio
    async def test_provider_diversity(self):
        """Verify provider diversity is maintained."""
        router = create_test_router(use_diversity=True)
        
        # Execute 100 reasoning calls
        for _ in range(100):
            method = get_reasoner("multi_perspective", router=router)
            await method.execute(test_context)
        
        # Check distribution
        distribution = router._cost_tracker.get_provider_distribution()
        
        # No provider should exceed 40%
        for provider, pct in distribution.items():
            assert pct < 0.40, f"{provider.value} at {pct*100:.1f}% (max 40%)"
```

**Acceptance Criteria:**
- [ ] All 9 methods tested
- [ ] Cost target met (<$6 per run)
- [ ] Provider diversity maintained
- [ ] Quality benchmarks passed

---

### Task 3.3: Quality Validation

**Objective:** Validate output quality matches or exceeds baseline.

**Methodology:**

1. **Generate baseline** with premium models (Claude Opus, GPT-5.4)
2. **Generate test output** with optimized models (Qwen, MiMo, MiniMax)
3. **Compare** using LLM-as-judge + human review

**Quality Metrics:**

| Metric | Target | Measurement |
|--------|--------|-------------|
| Logical consistency | >8/10 | LLM judge score |
| Completeness | >8/10 | LLM judge score |
| Actionability | >8/10 | LLM judge score |
| Overall quality | >8/10 | LLM judge score |
| Human preference | >50% | Blind A/B test |

**Acceptance Criteria:**
- [ ] Quality within 5% of baseline
- [ ] No critical regressions
- [ ] Human review completed (sample of 50)

---

## Phase 4: Rollout & Monitoring (Days 17-20)

### Task 4.1: Staged Rollout

**Rollout Plan:**

| Stage | Duration | Traffic | Success Criteria | Rollback Trigger |
|-------|----------|---------|------------------|------------------|
| **Alpha** | 4 hours | Internal (1%) | No critical bugs | Any P0 bug |
| **Beta** | 24 hours | 10% | Cost < $7/run | Cost > $10/run |
| **Canary** | 48 hours | 50% | Quality > 7.5/10 | Quality < 7/10 |
| **General** | Ongoing | 100% | All metrics green | Any metric red |

---

### Task 4.2: Monitoring Dashboard

**Metrics to Track:**

| Metric | Target | Alert | Critical |
|--------|--------|-------|----------|
| Cost per run | < $6 | > $8 | > $10 |
| P99 latency | < 100ms | > 200ms | > 500ms |
| Error rate | < 1% | > 3% | > 5% |
| Fallback rate | < 10% | > 20% | > 30% |
| Provider concentration | < 40% | > 50% | > 60% |
| Quality score | > 8/10 | < 7.5/10 | < 7/10 |

**Dashboard Implementation:**
```python
class ExtendedReasoningDashboard:
    """Real-time dashboard for optimized model routing."""
    
    def get_current_metrics(self) -> dict:
        return {
            "cost_per_run": self._calc_avg_cost(),
            "p99_latency": self._calc_p99_latency(),
            "error_rate": self._calc_error_rate(),
            "fallback_rate": self._calc_fallback_rate(),
            "quality_score": self._get_quality_score(),
            "provider_distribution": self._get_provider_distribution(),
            "model_usage": self._get_model_usage(),
            "cost_by_method": self._get_cost_by_method(),
            "cost_by_provider": self._get_cost_by_provider(),
        }
    
    def get_alerts(self) -> list:
        alerts = []
        metrics = self.get_current_metrics()
        
        if metrics["cost_per_run"] > 10:
            alerts.append("🔴 CRITICAL: Cost per run > $10")
        elif metrics["cost_per_run"] > 8:
            alerts.append("🟡 WARNING: Cost per run > $8")
        
        if metrics["provider_distribution"]["max"] > 0.60:
            alerts.append("🔴 CRITICAL: Provider concentration > 60%")
        
        # ... etc
        
        return alerts
```

---

## Resource Requirements

### Team

| Role | FTE | Duration | Responsibilities |
|------|-----|----------|------------------|
| Backend Engineer | 1.0 | 4 weeks | Router enhancement, reasoner migration |
| ML Engineer | 0.5 | 2 weeks | Model verification, quality validation |
| QA Engineer | 0.5 | 2 weeks | Testing, benchmark validation |
| DevOps Engineer | 0.25 | 1 week | Monitoring, rollout |
| Tech Lead | 0.25 | 4 weeks | Architecture, review |

### Infrastructure

| Resource | Cost/Month | Notes |
|----------|------------|-------|
| OpenRouter API | $5,400 | 1000 runs/month @ $5.40/run |
| Monitoring (Datadog) | $500 | Custom dashboards |
| Testing infrastructure | $200 | CI/CD, benchmark runs |
| **Total** | **$6,100** | vs $181,000 baseline |

---

## Risk Mitigation

### Identified Risks

| Risk | Probability | Impact | Mitigation | Owner |
|------|-------------|--------|------------|-------|
| Model unavailable | Medium | High | 3-tier fallback chain | Backend |
| Quality regression | Low | High | Quality gates, staged rollout | QA |
| Cost overrun | Low | Medium | Cost budget enforcement | Backend |
| Provider rate limits | Medium | Medium | Multi-provider diversity | DevOps |
| Breaking changes | Low | Medium | Backward compatibility layer | Backend |
| Data privacy (China providers) | Low | High | US provider fallback for sensitive data | Tech Lead |

### Contingency Plans

**If model unavailable:**
1. Activate fallback chain (automatic)
2. Switch to alternative provider
3. Use cached responses (if available)

**If quality regression:**
1. Rollback to previous config (automatic if quality < 7/10)
2. Investigate root cause
3. Adjust model selection

**If cost overrun:**
1. Review model selection
2. Tighten cost budget
3. Implement stricter fallback thresholds

**If provider rate limited:**
1. Shift traffic to under-weight providers (automatic)
2. Enable additional fallback providers
3. Request rate limit increase

---

## Success Metrics

### Cost Metrics

| Metric | Baseline (Premium) | Target | Actual | Status |
|--------|-------------------|--------|--------|--------|
| Avg cost per run | $181.00 | < $6.00 | ☐ | ☐ |
| Monthly cost (1000 runs) | $181,000 | < $6,000 | ☐ | ☐ |
| Cost savings | - | > 95% | ☐ | ☐ |

### Quality Metrics

| Metric | Baseline | Target | Actual | Status |
|--------|----------|--------|--------|--------|
| Output quality score | 8.5/10 | > 8.0/10 | ☐ | ☐ |
| User satisfaction | 90% | > 85% | ☐ | ☐ |
| Benchmark performance | 100% | > 95% | ☐ | ☐ |

### Performance Metrics

| Metric | Baseline | Target | Actual | Status |
|--------|----------|--------|--------|--------|
| P99 latency | 400ms | < 100ms | ☐ | ☐ |
| Error rate | 0.5% | < 1% | ☐ | ☐ |
| Fallback rate | N/A | < 10% | ☐ | ☐ |
| Provider diversity | N/A | All < 40% | ☐ | ☐ |

---

## Appendix A: Complete Configuration Template

```yaml
# config.berb.yaml - OPTIMIZED for 11 providers

llm:
  provider: "openrouter"
  base_url: "https://openrouter.ai/api/v1"
  api_key_env: "OPENROUTER_API_KEY"
  
  # Default fallback chain (3 tiers)
  primary_model: "qwen/qwen3.5-flash"
  fallback_models:
    - "minimax/minimax-m2.5:free"
    - "z-ai/glm-4.5-air:free"
    - "qwen/qwen3-coder-480b-a35b:free"

reasoning:
  # Global defaults
  default_model: "minimax/minimax-m2.5:free"
  fallback_models:
    - "qwen/qwen3.5-flash"
    - "z-ai/glm-4.7-flash"
  
  # Provider diversity targets
  provider_weights:
    minimax: 0.25
    qwen: 0.25
    mimo: 0.15
    glm: 0.10
    xai: 0.10
    kimi: 0.05
    perplexity: 0.05
    deepseek: 0.03
    google: 0.02
  
  # Cost budget
  cost_budget_usd: 6.00  # Max $6 per full reasoning run
  
  # Per-method optimized routing
  methods:
    multi_perspective:
      constructive: "xiaomi/mimo-v2-pro"
      destructive: "qwen/qwen3.5-397b-a17b"
      systemic: "z-ai/glm-5"
      minimalist: "minimax/minimax-m2.5:free"
      scoring: "qwen/qwen3-coder-next"
    
    pre_mortem:
      narrative: "qwen/qwen3-max-thinking"
      root_cause: "qwen/qwen3-coder-next"
      early_warning: "minimax/minimax-m2.5:free"
      hardened: "xiaomi/mimo-v2-pro"
    
    bayesian:
      prior: "z-ai/glm-4.5"
      likelihood: "minimax/minimax-m2.5:free"
      sensitivity: "qwen/qwen3.5-flash"
    
    debate:
      pro: "qwen/qwen3.5-397b-a17b"
      con: "qwen/qwen3-max-thinking"
      judge: "x-ai/grok-4.20-beta"
    
    dialectical:
      thesis: "z-ai/glm-5"
      antithesis: "qwen/qwen3.5-397b-a17b"
      synthesis: "moonshotai/kimi-k2-thinking"
    
    research:
      query: "perplexity/sonar-pro-search"
      synthesis: "qwen/qwen3.5-plus"
      gap: "minimax/minimax-m2.5:free"
      final: "xiaomi/mimo-v2-pro"
    
    socratic:
      clarification: "z-ai/glm-4.5-air:free"
      assumption: "z-ai/glm-4.7-flash"
      evidence: "minimax/minimax-m2.5:free"
      perspective: "qwen/qwen3.5-35b-a3b"
      meta: "moonshotai/kimi-k2-thinking"
    
    scientific:
      observation: "z-ai/glm-4.7"
      hypothesis: "qwen/qwen3-max-thinking"
      prediction: "qwen/qwen3-coder-next"
      experiment: "moonshotai/kimi-k2.5"
      analysis: "minimax/minimax-m2.5:free"
    
    jury:
      juror: "x-ai/grok-4.20-multi-agent-beta"
      foreman: "qwen/qwen3.5-plus"
      verdict: "z-ai/glm-5"
```

---

**Document End**

*For questions or issues, contact the Berb development team.*

**Next Steps:**
1. Review and approve implementation plan
2. Set up API keys for all 11 providers
3. Begin Phase 0 (Infrastructure Setup)
4. Schedule daily standups during implementation weeks
