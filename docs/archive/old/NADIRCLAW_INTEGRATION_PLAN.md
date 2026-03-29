# NadirClaw Integration Plan for AutoResearchClaw

**Document Created:** 2026-03-26
**Status:** Analysis Complete | Planning Phase

---

## Executive Summary

**NadirClaw** is an open-source LLM router that automatically routes simple prompts to cheaper models and complex prompts to premium models, achieving **40-70% cost savings** on AI API costs.

**Key Capabilities:**
- **Smart routing** — ~10ms classification using sentence embeddings
- **Three-tier routing** — simple / mid / complex with configurable thresholds
- **Context Optimize** — compacts bloated context (30-70% input token savings)
- **Agentic task detection** — auto-detects tool use, multi-step loops
- **Reasoning detection** — identifies prompts needing chain-of-thought
- **Vision routing** — auto-detects images and routes to vision-capable models
- **Model aliases** — short names like `sonnet`, `flash`, `gpt4`
- **Session persistence** — pins model for multi-turn conversations
- **Fallback chains** — automatic failover on 429, 5xx, timeout
- **Prompt caching** — in-memory LRU cache for identical requests
- **Budget tracking** — real-time cost tracking with alerts
- **Live dashboard** — terminal and web UI for monitoring

**Expected Impact:**
- **-40-70%** LLM API costs
- **-30-70%** input tokens via context optimization
- **~10ms** classification overhead
- **100%** cost visibility with dashboard

---

## NadirClaw Architecture Analysis

### Core Components

| Component | File | Purpose | AutoResearchClaw Integration Point |
|-----------|------|---------|-----------------------------------|
| **Classifier** | `classifier.py` | Binary complexity classifier | Route LLM calls by complexity |
| **Router** | `routing.py` | Multi-tier routing logic | Replace/augment current router |
| **Optimizer** | `optimize.py` | Context compaction | Reduce input token usage |
| **Server** | `server.py` | OpenAI-compatible proxy | Deploy as local router |
| **Savings** | `savings.py` | Cost savings calculator | Track and report savings |
| **Cache** | `cache.py` | Prompt caching | Skip redundant LLM calls |
| **Budget** | `budget.py` | Budget tracking & alerts | Cost management |
| **Dashboard** | `web_dashboard.py` | Web UI for monitoring | Integrate with AutoResearchClaw UI |

### Key Features

| Feature | Description | AutoResearchClaw Benefit |
|---------|-------------|--------------------------|
| **Three-tier routing** | Simple → cheap, Complex → premium | 40-70% cost reduction |
| **Context Optimize** | Compact context before dispatch | 30-70% input token savings |
| **Agentic detection** | Detect tool use, multi-step tasks | Route complex agent tasks properly |
| **Reasoning detection** | Identify CoT requirements | Use reasoning models when needed |
| **Prompt caching** | LRU cache for identical requests | Skip redundant API calls |
| **Budget alerts** | Daily/monthly spend limits | Prevent budget overruns |
| **Model aliases** | Short names (sonnet, flash, gpt4) | Easier configuration |
| **Session persistence** | Pin model for conversations | Consistent multi-turn context |
| **Fallback chains** | Auto-failover on errors | Higher reliability |

### Cost Savings Data

**Typical session breakdown:**

| Prompt Type | % of Requests | Without NadirClaw | With NadirClaw | Savings |
|-------------|---------------|-------------------|----------------|---------|
| Simple (file read, short Q&A) | 60% | claude-sonnet ($0.003) | gemini-flash ($0.0002) | -93% |
| Mid (code review, debugging) | 25% | claude-sonnet ($0.03) | gpt-4o-mini ($0.015) | -50% |
| Complex (architecture, reasoning) | 15% | claude-sonnet ($0.10) | claude-sonnet ($0.10) | 0% |
| **Weighted Average** | **100%** | **$0.0345** | **$0.0167** | **-52%** |

**Context Optimize savings:**
- JSON/schema deduplication: -40% tokens
- Whitespace compaction: -15% tokens
- System prompt dedup: -25% tokens
- **Total: 30-70% input token reduction**

---

## Integration Approaches

### Approach 1: NadirClaw as LLM Router (Recommended)

**Architecture:**
```
AutoResearchClaw Pipeline
         │
         ▼
┌─────────────────────────┐
│  NadirClaw Router       │
│  - classify()           │
│  - route()              │
│  - optimize_context()   │
│  - cache check          │
└───────────┬─────────────┘
            │ Routes to appropriate model
            ▼
┌─────────────────────────┐
│  LLM Providers          │
│  - Simple: Gemini Flash │
│  - Mid: GPT-4o-mini     │
│  - Complex: Claude      │
└─────────────────────────┘
```

**Implementation:**
```python
# berb/llm/nadirclaw_router.py

import numpy as np
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

class NadirClawRouter:
    """LLM router with NadirClaw intelligence."""
    
    def __init__(
        self,
        simple_model: str = "gemini/gemini-2.5-flash",
        mid_model: str = "openai/gpt-4o-mini",
        complex_model: str = "anthropic/claude-sonnet-4-5-20250929",
        tier_thresholds: Tuple[float, float] = (0.3, 0.7),
        cache_enabled: bool = True,
        cache_ttl: int = 3600,
        cache_max_size: int = 1000,
    ):
        self.simple_model = simple_model
        self.mid_model = mid_model
        self.complex_model = complex_model
        self.tier_thresholds = tier_thresholds
        self.cache_enabled = cache_enabled
        self._cache = {}  # LRU cache
        self._cache_ttl = cache_ttl
        self._cache_max_size = cache_max_size
        
        # Load classifier
        from nadirclaw.classifier import BinaryComplexityClassifier
        self.classifier = BinaryComplexityClassifier()
    
    def select_model(self, prompt: str) -> Dict[str, Any]:
        """Select optimal model for a prompt.
        
        Returns:
            Dict with model, tier, confidence, reasoning
        """
        # Check cache first
        if self.cache_enabled:
            cached = self._cache_get(prompt)
            if cached:
                return cached
        
        # Classify prompt
        analysis = self.classifier.analyze(prompt)
        
        # Select model based on tier
        tier = analysis["tier"]  # simple, mid, complex
        
        if tier == "simple":
            model = self.simple_model
        elif tier == "mid":
            model = self.mid_model
        else:  # complex
            model = self.complex_model
        
        result = {
            "model": model,
            "tier": tier,
            "confidence": analysis["confidence"],
            "complexity_score": analysis["complexity_score"],
            "reasoning": analysis["reasoning"],
            "latency_ms": analysis["analyzer_latency_ms"],
        }
        
        # Cache result
        if self.cache_enabled:
            self._cache_set(prompt, result)
        
        return result
    
    def optimize_context(
        self,
        messages: list[dict],
        mode: str = "safe",
    ) -> Dict[str, Any]:
        """Optimize messages to reduce token count.
        
        Args:
            messages: List of message dicts
            mode: "off", "safe", or "aggressive"
        
        Returns:
            Dict with optimized messages and savings stats
        """
        from nadirclaw.optimize import optimize_messages
        
        result = optimize_messages(messages, mode=mode)
        
        return {
            "messages": result.messages,
            "original_tokens": result.original_tokens,
            "optimized_tokens": result.optimized_tokens,
            "tokens_saved": result.tokens_saved,
            "savings_pct": (
                result.tokens_saved / result.original_tokens * 100
                if result.original_tokens > 0 else 0
            ),
            "optimizations_applied": result.optimizations_applied,
        }
    
    def _cache_get(self, key: str) -> Optional[Dict]:
        """Get item from cache."""
        import time
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["time"] < self._cache_ttl:
                return entry["value"]
            else:
                del self._cache[key]
        return None
    
    def _cache_set(self, key: str, value: Dict):
        """Set item in cache."""
        import time
        if len(self._cache) >= self._cache_max_size:
            # Remove oldest
            oldest_key = min(self._cache, key=lambda k: self._cache[k]["time"])
            del self._cache[oldest_key]
        
        self._cache[key] = {
            "value": value,
            "time": time.time()
        }
```

---

### Approach 2: NadirClaw Server as Proxy

**Deploy NadirClaw server and route all LLM calls through it:**

```yaml
# docker-compose.nadirclaw.yaml

version: '3.8'

services:
  nadirclaw:
    image: doramirdor/nadirclaw:latest
    container_name: nadirclaw
    ports:
      - "8856:8856"
    environment:
      - NADIRCLAW_SIMPLE_MODEL=gemini/gemini-2.5-flash
      - NADIRCLAW_MID_MODEL=openai/gpt-4o-mini
      - NADIRCLAW_COMPLEX_MODEL=anthropic/claude-sonnet-4-5-20250929
      - NADIRCLAW_TIER_THRESHOLDS=0.3,0.7
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - nadirclaw-data:/root/.nadirclaw
    restart: unless-stopped

volumes:
  nadirclaw-data:
```

**Usage in AutoResearchClaw:**
```python
# berb/llm/nadirclaw_proxy.py

import httpx

class NadirClawProxy:
    """LLM provider via NadirClaw proxy server."""
    
    def __init__(self, base_url: str = "http://localhost:8856"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)
    
    async def chat_completion(
        self,
        messages: list[dict],
        model: str = "auto",  # Let NadirClaw decide
        **kwargs
    ) -> dict:
        """Request chat completion via NadirClaw."""
        
        response = await self.client.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": model,  # "auto" for auto-routing
                "messages": messages,
                **kwargs
            }
        )
        response.raise_for_status()
        
        result = response.json()
        
        # Extract routing info from headers
        routed_model = response.headers.get("X-Routed-Model")
        routed_tier = response.headers.get("X-Routed-Tier")
        complexity_score = response.headers.get("X-Complexity-Score")
        
        return {
            "response": result,
            "routed_model": routed_model,
            "routed_tier": routed_tier,
            "complexity_score": complexity_score,
        }
```

---

### Approach 3: Context Optimization Integration

**Use NadirClaw's context optimization to reduce input tokens:**

```python
# berb/llm/context_optimizer.py

from nadirclaw.optimize import (
    optimize_messages,
    OptimizeResult,
)

class AutoResearchClawContextOptimizer:
    """Optimize LLM context for AutoResearchClaw stages."""
    
    def __init__(self, mode: str = "safe"):
        self.mode = mode
    
    def optimize_for_stage(
        self,
        stage_name: str,
        messages: list[dict],
        context: dict,
    ) -> dict:
        """Optimize context for a specific pipeline stage.
        
        Args:
            stage_name: Pipeline stage (e.g., "HYPOTHESIS_GEN")
            messages: LLM messages
            context: Additional context dict
        
        Returns:
            Optimized messages and stats
        """
        # Apply stage-specific optimizations
        if stage_name in ["LITERATURE_COLLECT", "SYNTHESIS"]:
            # Heavy context stages → aggressive optimization
            opt_mode = "aggressive"
        elif stage_name in ["EXPERIMENT_DESIGN", "CODE_GENERATION"]:
            # Code stages → safe optimization only
            opt_mode = "safe"
        else:
            opt_mode = self.mode
        
        # Optimize messages
        result = optimize_messages(messages, mode=opt_mode)
        
        # Optimize context dict
        optimized_context = self._optimize_context_dict(context)
        
        return {
            "messages": result.messages,
            "context": optimized_context,
            "original_tokens": result.original_tokens,
            "optimized_tokens": result.optimized_tokens,
            "tokens_saved": result.tokens_saved,
            "savings_pct": result.tokens_saved / result.original_tokens * 100,
        }
    
    def _optimize_context_dict(self, context: dict) -> dict:
        """Optimize context dictionary."""
        import json
        
        # Remove empty fields
        optimized = {k: v for k, v in context.items() if v}
        
        # Compact JSON representation
        for key, value in optimized.items():
            if isinstance(value, (dict, list)):
                # Remove whitespace from JSON
                optimized[key] = json.dumps(value, separators=(',', ':'))
        
        return optimized
```

---

## Implementation Roadmap

### Phase 1: Basic Router Integration (Week 1) - P0

**Goal:** NadirClaw routing working for LLM calls

**Tasks:**
- [ ] **P0** Create `berb/llm/nadirclaw_router.py`
  - [ ] NadirClawRouter class
  - [ ] `select_model()` method
  - [ ] `optimize_context()` method
  - [ ] LRU cache implementation
  - [ ] Tier-based model selection

- [ ] **P0** Integrate with LLM providers
  - [ ] Wrap `berb/llm/base.py`
  - [ ] Add model selection before each call
  - [ ] Track routing decisions
  - [ ] Log cost savings

- [ ] **P0** Deploy NadirClaw server (optional)
  - [ ] Docker Compose setup
  - [ ] Configure models and thresholds
  - [ ] Test connectivity
  - [ ] Write setup guide

- [ ] **P0** Add to config schema
  - [ ] `nadirclaw.enabled` option
  - [ ] `nadirclaw.simple_model`
  - [ ] `nadirclaw.mid_model`
  - [ ] `nadirclaw.complex_model`
  - [ ] `nadirclaw.tier_thresholds`
  - [ ] `nadirclaw.cache_enabled`

- [ ] **P0** Write unit tests
  - [ ] `tests/test_nadirclaw_router.py`
  - [ ] Test model selection
  - [ ] Test context optimization
  - [ ] Test caching
  - [ ] Test cost tracking

---

### Phase 2: Context Optimization (Week 2) - P1

**Goal:** Reduce input token consumption

**Tasks:**
- [ ] **P1** Create `berb/llm/context_optimizer.py`
  - [ ] Stage-specific optimization
  - [ ] System prompt deduplication
  - [ ] JSON/schema compaction
  - [ ] Whitespace optimization

- [ ] **P1** Integrate with pipeline stages
  - [ ] Apply to Stage 3-4 (Literature)
  - [ ] Apply to Stage 8 (Hypothesis)
  - [ ] Apply to Stage 16-18 (Writing)
  - [ ] Track token savings per stage

- [ ] **P1** Add agentic task detection
  - [ ] Detect multi-step tasks
  - [ ] Detect tool use requirements
  - [ ] Force complex model for agentic tasks
  - [ ] Write tests: `test_agentic_detection()`

- [ ] **P1** Add reasoning detection
  - [ ] Identify CoT requirements
  - [ ] Route to reasoning models
  - [ ] Track reasoning usage
  - [ ] Write tests: `test_reasoning_detection()`

- [ ] **P1** Write integration tests
  - [ ] Test end-to-end routing
  - [ ] Test context optimization savings
  - [ ] Test cost reduction
  - [ ] Benchmark performance

---

### Phase 3: Cost Tracking & Dashboard (Week 3) - P2

**Goal:** Comprehensive cost visibility

**Tasks:**
- [ ] **P2** Create cost tracking system
  - [ ] Track per-request costs
  - [ ] Calculate savings vs baseline
  - [ ] Generate savings reports
  - [ ] Export to CSV/JSON

- [ ] **P2** Add budget management
  - [ ] Set daily/monthly budgets
  - [ ] Alert at thresholds
  - [ ] Auto-pause on budget exceeded
  - [ ] Budget forecasting

- [ ] **P2** Integrate NadirClaw dashboard
  - [ ] Embed web dashboard
  - [ ] Terminal dashboard widget
  - [ ] Real-time cost tracking
  - [ ] Model usage breakdown

- [ ] **P2** Add Prometheus metrics
  - [ ] Request counts
  - [ ] Latency histograms
  - [ ] Token/cost totals
  - [ ] Cache hit rates

- [ ] **P2** Create savings reports
  - [ ] Daily/weekly/monthly
  - [ ] Per-project breakdown
  - [ ] Per-stage breakdown
  - [ ] ROI analysis

---

### Phase 4: Advanced Features (Week 4) - P2

**Goal:** Intelligent optimization

**Tasks:**
- [ ] **P2** Implement session persistence
  - [ ] Pin model for conversations
  - [ ] Track session context
  - [ ] Avoid model switching mid-thread
  - [ ] Write tests: `test_session_persistence()`

- [ ] **P2** Add fallback chains
  - [ ] Configure fallback models
  - [ ] Handle 429, 5xx, timeout
  - [ ] Auto-cascade through chain
  - [ ] Track fallback usage

- [ ] **P2** Implement routing profiles
  - [ ] auto, eco, premium, free, reasoning
  - [ ] Per-request profile selection
  - [ ] Profile-specific routing
  - [ ] Write tests: `test_routing_profiles()`

- [ ] **P2** Add model aliases
  - [ ] Short names (sonnet, flash, gpt4)
  - [ ] Custom alias configuration
  - [ ] Alias resolution
  - [ ] Documentation

- [ ] **P2** Documentation
  - [ ] Router configuration guide
  - [ ] Cost optimization tips
  - [ ] Dashboard user guide
  - [ ] API reference

---

## Configuration Reference

### AutoResearchClaw Config with NadirClaw

```yaml
# config.arc.yaml

# NadirClaw LLM routing
nadirclaw:
  enabled: true
  
  # Model configuration
  simple_model: "gemini/gemini-2.5-flash"     # ~$0.0002/1K tokens
  mid_model: "openai/gpt-4o-mini"             # ~$0.015/1K tokens
  complex_model: "anthropic/claude-sonnet-4-5-20250929"  # ~$0.03/1K tokens
  
  # Tier thresholds (0-1)
  tier_thresholds: [0.3, 0.7]  # simple < 0.3 < mid < 0.7 < complex
  
  # Context optimization
  context_optimize:
    enabled: true
    mode: "safe"  # off | safe | aggressive
    stages:  # Apply to specific stages
      - "LITERATURE_COLLECT"
      - "SYNTHESIS"
      - "PAPER_DRAFT"
  
  # Caching
  cache:
    enabled: true
    ttl_seconds: 3600  # 1 hour
    max_size: 1000  # entries
  
  # Budget management
  budget:
    daily_limit_usd: 10.0
    monthly_limit_usd: 200.0
    alert_thresholds: [50, 80, 100]  # percentage
    auto_pause: false
  
  # Fallback configuration
  fallback:
    enabled: true
    max_retries: 3
    retry_delay_sec: 5
    models:
      - "openai/gpt-4o"
      - "anthropic/claude-haiku-4-5-20251001"
  
  # Routing profiles
  default_profile: "auto"  # auto | eco | premium | free | reasoning
  
  # Cost tracking
  tracking:
    enabled: true
    baseline_model: "anthropic/claude-sonnet-4-5-20250929"
    report_format: "json"  # json | csv
    export_path: "./cost_reports/"
```

---

## Code Examples

### Example 1: Route LLM Call with NadirClaw

```python
# berb/llm/base.py

from berb.llm.nadirclaw_router import NadirClawRouter

class BaseLLMProvider:
    def __init__(self, config: RCConfig):
        self.config = config
        
        # Initialize NadirClaw router
        if config.nadirclaw.enabled:
            self.router = NadirClawRouter(
                simple_model=config.nadirclaw.simple_model,
                mid_model=config.nadirclaw.mid_model,
                complex_model=config.nadirclaw.complex_model,
                tier_thresholds=config.nadirclaw.tier_thresholds,
                cache_enabled=config.nadirclaw.cache.enabled,
            )
        else:
            self.router = None
    
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        # Select optimal model via NadirClaw
        if self.router:
            # Optimize context first
            opt_result = self.router.optimize_context(
                messages,
                mode="safe"
            )
            messages = opt_result["messages"]
            
            # Select model
            selection = self.router.select_model(user_prompt)
            model = selection["model"]
            
            logger.info(
                f"NadirClaw routing: {selection['tier']} tier → {model} "
                f"(saved {opt_result['tokens_saved']} tokens, "
                f"{opt_result['savings_pct']:.1f}%)"
            )
        else:
            model = self.config.llm.primary_model
        
        # Execute LLM call
        response = await self._call_llm(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )
        
        return response
```

---

### Example 2: Cost Tracking Dashboard

```python
# berb/dashboard/widgets.py

from berb.llm.nadirclaw_router import NadirClawRouter
from nadirclaw.savings import generate_savings_report

def render_cost_widget(router: NadirClawRouter) -> str:
    """Render cost tracking widget."""
    
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    
    console = Console()
    
    # Generate savings report
    report = generate_savings_report(
        log_path=Path("./logs/nadirclaw.jsonl"),
        since="7d",
    )
    
    # Create summary table
    table = Table(title="Cost Savings (Last 7 Days)")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row(
        "Total Requests",
        str(report.get("total_requests", 0))
    )
    table.add_row(
        "Actual Cost",
        f"${report.get('actual_cost', 0):.4f}"
    )
    table.add_row(
        "Baseline Cost",
        f"${report.get('baseline_cost', 0):.4f}"
    )
    table.add_row(
        "Total Saved",
        f"${report.get('total_saved', 0):.4f} "
        f"({report.get('savings_pct', 0):.1f}%)"
    )
    table.add_row(
        "Projected Monthly",
        f"${report.get('monthly_projection', 0):.2f}"
    )
    
    # Render
    console.print(Panel(table))
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_nadirclaw_router.py

import pytest
from berb.llm.nadirclaw_router import NadirClawRouter

@pytest.fixture
def router():
    return NadirClawRouter(
        simple_model="gemini/gemini-2.5-flash",
        mid_model="openai/gpt-4o-mini",
        complex_model="anthropic/claude-sonnet-4-5-20250929",
    )

def test_select_model_simple(router):
    result = router.select_model("What is 2+2?")
    
    assert result["tier"] == "simple"
    assert "flash" in result["model"].lower()
    assert result["confidence"] > 0

def test_select_model_complex(router):
    result = router.select_model(
        "Design a distributed system for handling 1M requests/sec"
    )
    
    assert result["tier"] == "complex"
    assert "claude" in result["model"].lower() or "sonnet" in result["model"].lower()

def test_optimize_context(router):
    messages = [
        {"role": "system", "content": "You are helpful" * 100},
        {"role": "user", "content": "Hello"},
    ]
    
    result = router.optimize_context(messages, mode="safe")
    
    assert result["tokens_saved"] > 0
    assert result["savings_pct"] > 0
    assert len(result["messages"]) == len(messages)

def test_cache(router):
    prompt = "Test prompt"
    
    # First call
    result1 = router.select_model(prompt)
    
    # Second call (should be cached)
    result2 = router.select_model(prompt)
    
    assert result1["model"] == result2["model"]
    # Second call should be faster (cached)
```

---

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| **LLM cost reduction** | 100% | 40-60% | Cost tracking |
| **Input token reduction** | 100% | 30-70% | Context optimization |
| **Routing accuracy** | N/A | >85% | Manual audit |
| **Cache hit rate** | 0% | 20-40% | Cache metrics |
| **Cost visibility** | None | 100% | Dashboard |
| **Budget adherence** | N/A | <10% over | Budget tracking |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Misclassification** | Wrong model selected | Bias toward complex, manual feedback loop |
| **Cache staleness** | Outdated responses | TTL-based expiration, max size |
| **Overhead** | Added latency | ~10ms classification, benchmark |
| **NadirClaw dependency** | External project | Fallback to direct routing |
| **Privacy concerns** | Prompt logging | Local-only storage, opt-in |

---

## Next Steps

1. **Decision:** Approve Phase 1 implementation
2. **Setup:** Install NadirClaw locally
3. **Development:** Create router integration
4. **Integration:** Add to LLM providers
5. **Testing:** Write comprehensive tests
6. **Documentation:** Write user guide

---

## References

- **NadirClaw Repo:** `E:\Documents\Vibe-Coding\Github Projects\Token Consumption\NadirClaw-main\NadirClaw-main`
- **NadirClaw GitHub:** https://github.com/doramirdor/NadirClaw
- **NadirClaw Website:** https://getnadir.com
- **Install Guide:** https://github.com/doramirdor/NadirClaw#quick-start
- **Comparisons:** https://github.com/doramirdor/NadirClaw/docs/comparison.md

---

**Last Updated:** 2026-03-26
**Next Review:** After Phase 1 completion
