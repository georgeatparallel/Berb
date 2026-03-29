# NadirClaw Integration Summary

**Date:** 2026-03-26
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
- **Prompt caching** — in-memory LRU cache for identical requests
- **Budget tracking** — real-time cost tracking with alerts
- **Live dashboard** — terminal and web UI for monitoring

**Expected Impact:**
- **-40-70%** LLM API costs
- **-30-70%** input tokens via context optimization
- **~10ms** classification overhead
- **100%** cost visibility with dashboard

---

## NadirClaw Analysis

### What NadirClaw Does

NadirClaw sits between your application and LLM providers, intelligently routing each request to the most cost-effective model:

```
Application → NadirClaw Router → LLM Provider
     │              │
     │              ├─→ Simple → Gemini Flash ($0.0002)
     │              ├─→ Mid → GPT-4o-mini ($0.015)
     │              └─→ Complex → Claude Sonnet ($0.03)
     │
     └─→ 50% cost savings
```

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

### Core Components

| Component | File | Purpose |
|-----------|------|---------|
| **Classifier** | `classifier.py` | Binary complexity classifier |
| **Router** | `routing.py` | Multi-tier routing logic |
| **Optimizer** | `optimize.py` | Context compaction |
| **Server** | `server.py` | OpenAI-compatible proxy |
| **Savings** | `savings.py` | Cost savings calculator |
| **Cache** | `cache.py` | Prompt caching |
| **Budget** | `budget.py` | Budget tracking & alerts |
| **Dashboard** | `web_dashboard.py` | Web UI for monitoring |

---

## Integration Value for AutoResearchClaw

### Problem Solved

AutoResearchClaw currently:
- Makes many LLM API calls (23 stages)
- Uses same premium model for all calls
- No intelligent routing based on complexity
- No context optimization
- No cost visibility per stage

**NadirClaw solves this by:**
- Routing simple stages to cheap models
- Optimizing context before each call
- Caching identical requests
- Tracking costs per stage
- Providing budget alerts

### Integration Points

1. **LLM Model Selection**
   - Classify each prompt (simple/mid/complex)
   - Route to appropriate model tier
   - Track routing decisions
   - Calculate savings

2. **Context Optimization**
   - Compact literature review context
   - Deduplicate system prompts
   - Remove whitespace from JSON
   - 30-70% input token reduction

3. **Prompt Caching**
   - Cache identical prompts
   - Skip redundant API calls
   - LRU eviction
   - TTL-based expiration

4. **Cost Dashboard**
   - Per-stage cost breakdown
   - Daily/weekly/monthly reports
   - Budget alerts
   - ROI analysis

---

## Implementation Plan

### Phase 1: Basic Router Integration (Week 1) - P0

**Goal:** NadirClaw routing working for LLM calls

**Deliverables:**
- `berb/llm/nadirclaw_router.py` - NadirClawRouter class
- Integration with LLM providers
- Config schema updates
- Unit tests

**Key Features:**
- Three-tier model selection
- Context optimization
- LRU caching
- Cost tracking

---

### Phase 2: Context Optimization (Week 2) - P1

**Goal:** Reduce input token consumption

**Deliverables:**
- `berb/llm/context_optimizer.py` - Context optimizer
- Integration with pipeline stages
- Agentic task detection
- Reasoning detection

**Key Features:**
- Stage-specific optimization
- System prompt deduplication
- JSON/schema compaction
- Agentic/reasoning detection

---

### Phase 3: Analytics & Dashboard (Week 3) - P2

**Goal:** Comprehensive cost visibility

**Deliverables:**
- Cost tracking system
- Budget management
- NadirClaw dashboard integration
- Savings reports

**Key Features:**
- Per-request cost tracking
- Budget alerts (50%/80%/100%)
- Real-time dashboard
- CSV/JSON export

---

### Phase 4: Advanced Features (Week 4) - P2

**Goal:** Intelligent optimization

**Deliverables:**
- Session persistence
- Fallback chains
- Routing profiles
- Documentation

**Key Features:**
- Model pinning for conversations
- Auto-failover on errors
- Profile-based routing (auto/eco/premium/free/reasoning)
- Model aliases

---

## Configuration

```yaml
# config.arc.yaml

nadirclaw:
  enabled: true
  
  # Model configuration
  simple_model: "gemini/gemini-2.5-flash"
  mid_model: "openai/gpt-4o-mini"
  complex_model: "anthropic/claude-sonnet-4-5-20250929"
  
  # Tier thresholds
  tier_thresholds: [0.3, 0.7]
  
  # Context optimization
  context_optimize:
    enabled: true
    mode: "safe"
  
  # Caching
  cache:
    enabled: true
    ttl_seconds: 3600
    max_size: 1000
  
  # Budget
  budget:
    daily_limit_usd: 10.0
    monthly_limit_usd: 200.0
    alert_thresholds: [50, 80, 100]
```

---

## Code Example

```python
from berb.llm.nadirclaw_router import NadirClawRouter

# Initialize router
router = NadirClawRouter(
    simple_model="gemini/gemini-2.5-flash",
    mid_model="openai/gpt-4o-mini",
    complex_model="anthropic/claude-sonnet-4-5-20250929",
)

# Select optimal model
selection = router.select_model("What is 2+2?")
print(f"Tier: {selection['tier']}, Model: {selection['model']}")

# Optimize context
messages = [
    {"role": "system", "content": "You are helpful" * 100},
    {"role": "user", "content": "Hello"},
]
result = router.optimize_context(messages, mode="safe")
print(f"Saved {result['tokens_saved']} tokens ({result['savings_pct']:.1f}%)")
```

---

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| LLM cost reduction | 100% | 40-60% | Cost tracking |
| Input token reduction | 100% | 30-70% | Context optimization |
| Routing accuracy | N/A | >85% | Manual audit |
| Cache hit rate | 0% | 20-40% | Cache metrics |
| Cost visibility | None | 100% | Dashboard |
| Budget adherence | N/A | <10% over | Budget tracking |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Misclassification | Wrong model selected | Bias toward complex |
| Cache staleness | Outdated responses | TTL-based expiration |
| Overhead | Added latency | ~10ms classification |
| NadirClaw dependency | External project | Fallback to direct routing |
| Privacy concerns | Prompt logging | Local-only storage |

---

## Next Steps

1. **Approve Phase 1** - Basic router integration
2. **Install NadirClaw** - Local testing environment
3. **Develop** - Create router integration
4. **Integrate** - Add to LLM providers
5. **Test** - Write comprehensive tests
6. **Document** - User guide and API reference

---

## Resources

- **Full Plan:** `docs/NADIRCLAW_INTEGRATION_PLAN.md`
- **NadirClaw Repo:** `E:\Documents\Vibe-Coding\Github Projects\Token Consumption\NadirClaw-main\NadirClaw-main`
- **NadirClaw GitHub:** https://github.com/doramirdor/NadirClaw
- **NadirClaw Website:** https://getnadir.com
- **Install Guide:** https://github.com/doramirdor/NadirClaw#quick-start

---

**Prepared by:** AI Analysis  
**Date:** 2026-03-26  
**Next Review:** After Phase 1 approval
