# Mnemo Cortex Integration Plan for AutoResearchClaw

## Executive Summary

**Mnemo Cortex** is a memory coprocessor that gives AI agents persistent memory across sessions. Integrating it with AutoResearchClaw would provide:

1. **Cross-run knowledge persistence** - Research runs remember past failures/successes
2. **Session-level checkpointing** - Every LLM call archived automatically
3. **Semantic search over past research** - Find similar experiments, hypotheses, results
4. **Preflight validation** - Catch hallucinated citations before they reach the paper
5. **Multi-agent memory isolation** - Each research project gets isolated memory

**Integration Complexity:** Low-Medium (4 endpoints, well-documented adapters)
**Expected Benefit:** +25-40% reduction in repeated mistakes, faster literature discovery

---

## Mnemo Cortex Capabilities Overview

### Core Endpoints

| Endpoint | Method | Purpose | AutoResearchClaw Use Case |
|----------|--------|---------|---------------------------|
| `/context` | POST | Retrieve relevant memories for a prompt | Inject past research lessons into stage prompts |
| `/preflight` | POST | Validate draft responses (PASS/ENRICH/WARN/BLOCK) | Catch citation hallucinations, validate experiment design |
| `/ingest` | POST | Capture prompt/response pairs | Auto-archive all 23 stage LLM calls |
| `/writeback` | POST | Curated session archiving | Archive completed research runs |
| `/health` | GET | System status | Monitor memory system health |

### Key Features

| Feature | Description | AutoResearchClaw Benefit |
|---------|-------------|--------------------------|
| **L1/L2/L3 Cache Hierarchy** | Pre-built bundles → semantic search → full scan | Fast retrieval of relevant past experiments |
| **Persona Modes** | Strict/Creative/Default bias tuning | Strict mode for citations, creative for hypothesis generation |
| **Multi-Tenant Isolation** | Per-agent memory namespaces | Isolate memory by research domain/project |
| **Circuit-Breaker Fallbacks** | Auto-failover between LLM providers | Resilient memory operations |
| **Session Watcher** | Auto-capture from session files | Zero-code automatic archiving |
| **Hot/Warm/Cold Storage** | 3 days / 30 days / archive | Cost-effective long-term memory |

---

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    AutoResearchClaw Pipeline                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  23-Stage Research Pipeline                               │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │ Stage 1-7   │  │ Stage 8-15  │  │ Stage 16-23 │       │   │
│  │  │ (Scoping)   │→ │ (Execution) │→ │ (Writing)   │       │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘       │   │
│  │         │                │                │               │   │
│  │  ┌──────┴────────────────┴────────────────┴──────┐       │   │
│  │  │         Mnemo Cortex Bridge Adapter           │       │   │
│  │  │  - /context before each stage                 │       │   │
│  │  │  - /ingest after each LLM call                │       │   │
│  │  │  - /preflight for citations & numbers         │       │   │
│  │  └──────────────────┬────────────────────────────┘       │   │
│  └─────────────────────┼─────────────────────────────────────┘   │
└────────────────────────┼─────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ⚡ Mnemo Cortex Server                        │
│                         (port 50001)                             │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────┐        │
│  │ Reasoning  │  │ Embedding  │  │ Session Watcher    │        │
│  │ + Fallback │  │ + Fallback │  │ (auto-capture)     │        │
│  └─────┬──────┘  └─────┬──────┘  └────────────────────┘        │
│        │                │                                       │
│  ┌─────┴────────────────┴──────┐                                │
│  │      Cache Hierarchy        │                                │
│  │  L1: Pre-built bundles      │  Fast (keyword)               │
│  │  L2: Semantic index         │  ↓ (vector search)            │
│  │  L3: Full memory scan       │  Slow (full scan)             │
│  └────────────┬────────────────┘                                │
│               │                                                  │
│  ┌────────────┴────────────────┐                                │
│  │   Multi-Tenant Storage      │                                │
│  │  project-1/ │ project-2/    │                                │
│  └─────────────────────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Integration Approaches (3 Options)

### Option 1: Lightweight Bridge Adapter (Recommended - Phase 1)

**Scope:** Add Mnemo Cortex as an optional memory backend alongside existing MetaClaw integration.

**Implementation:**
1. Create `berb/mnemo_bridge/` module
2. Implement 3 core functions:
   - `inject_context(stage, prompt)` → calls `/context`
   - `archive_stage(stage, result)` → calls `/ingest`
   - `validate_citations(draft)` → calls `/preflight`
3. Add config option `mnemo_bridge.enabled`
4. Start Mnemo Cortex as sidecar service

**Config Example:**
```yaml
mnemo_bridge:
  enabled: true
  server_url: "http://localhost:50001"
  agent_id: "autoresearch"
  persona: "strict"  # For citation validation
  auto_ingest: true  # Archive all LLM calls
  preflight_stages: [4, 18, 23]  # Literature, Peer Review, Citation Verify
```

**Pros:**
- Minimal code changes
- Works alongside MetaClaw
- Can be disabled without breaking pipeline
- Leverages existing adapter patterns

**Cons:**
- Doesn't use Session Watcher (requires manual ingest calls)
- Less automatic than OpenClaw integration

---

### Option 2: Deep Integration with Session Watcher (Phase 2)

**Scope:** Full integration using Mnemo's Session Watcher for automatic capture.

**Implementation:**
1. Modify `berb/pipeline/runner.py` to write session JSONL files
2. Run Mnemo Watcher as background daemon
3. Watcher auto-captures all LLM exchanges to `/ingest`
4. Add `/writeback` call at end of each research run

**Session File Format:**
```jsonl
{"session_id": "rc-20260326-143022-abc123", "entry": 1, "prompt": "...", "response": "..."}
{"session_id": "rc-20260326-143022-abc123", "entry": 2, "prompt": "...", "response": "..."}
```

**Pros:**
- Zero manual ingest calls
- Crash-safe (every exchange captured as written)
- Matches OpenClaw integration pattern

**Cons:**
- Requires file format changes
- Watcher must run as separate process

---

### Option 3: Mnemo as MetaClaw Replacement (Not Recommended)

**Scope:** Replace MetaClaw integration entirely with Mnemo Cortex.

**Analysis:**
- MetaClaw focuses on **skill extraction** (lessons → reusable skills)
- Mnemo focuses on **memory retrieval** (semantic search over past sessions)
- They solve different problems
- **Recommendation:** Keep both, use Mnemo for memory + MetaClaw for skills

---

## Specific Use Cases

### 1. Cross-Run Literature Discovery

**Problem:** Each run rediscoveries the same papers.

**Solution:**
```python
# Before Stage 4 (LITERATURE_COLLECT)
context = await mnemo.get_context(
    prompt=f"Search for papers on {topic}",
    agent_id=f"research-{domain}"
)
# Inject context into prompt:
# "Based on past research, these papers were relevant: {context.chunks}"
```

**Benefit:** Avoid re-collecting same papers, build on past literature reviews.

---

### 2. Citation Hallucination Prevention

**Problem:** LLMs fabricate citations that pass verification.

**Solution:**
```python
# During Stage 23 (CITATION_VERIFY)
preflight = await mnemo.preflight(
    prompt="Verify these citations are real and relevant",
    draft_response=citation_report,
    persona="strict"
)
if preflight.verdict == "WARN" or preflight.verdict == "BLOCK":
    # Trigger re-verification with LLM fallback
```

**Benefit:** Extra layer of protection beyond current 4-layer verification.

---

### 3. Experiment Design Learning

**Problem:** Same experiment design mistakes repeated across runs.

**Solution:**
```python
# Before Stage 9 (EXPERIMENT_DESIGN)
context = await mnemo.get_context(
    prompt=f"Design experiment for {hypothesis}",
    max_results=10
)
# Inject: "Past experiments with similar designs had these issues: {context.chunks}"
```

**Benefit:** LLM sees past failures (NaN errors, timeout issues, memory problems).

---

### 4. Hypothesis Generation with Memory

**Problem:** Hypotheses don't build on past research insights.

**Solution:**
```python
# During Stage 8 (HYPOTHESIS_GEN)
context = await mnemo.get_context(
    prompt=f"Generate hypotheses for {research_gap}",
    persona="creative"  # Use associative bias
)
# Inject: "Past research found these patterns: {context.chunks}"
```

**Benefit:** More grounded hypotheses, builds on accumulated knowledge.

---

### 5. Multi-Project Memory Isolation

**Problem:** Different research domains should not cross-contaminate.

**Solution:**
```yaml
mnemo_bridge:
  agent_id_template: "research-{domain}"
  # Results in:
  # - research-ml/ for machine learning projects
  # - research-bio/ for biology projects
  # - research-nlp/ for NLP projects
```

**Benefit:** ML experiments don't pollute biology memory, domain-specific learning.

---

## Implementation Plan

### Phase 1: Core Bridge (Week 1)

**Goal:** Basic Mnemo integration working alongside MetaClaw.

**Tasks:**
1. [ ] Create `berb/mnemo_bridge/` module
   - `__init__.py` - Bridge class
   - `client.py` - HTTP client for Mnemo endpoints
   - `config.py` - Config validation
2. [ ] Add config schema to `berb/config.py`
3. [ ] Implement `/context` injection in `berb/pipeline/runner.py`
4. [ ] Implement `/ingest` calls after each stage
5. [ ] Add `mnemo-cortex` to `pyproject.toml` dependencies (optional)
6. [ ] Write tests: `tests/test_mnemo_bridge.py`

**Files to Create:**
```
berb/mnemo_bridge/
├── __init__.py      # MnemoBridge class
├── client.py        # HTTP client
├── config.py        # Config validation
└── prompts.py       # Context injection templates
```

**Config Addition:**
```yaml
mnemo_bridge:
  enabled: false  # Opt-in
  server_url: "http://localhost:50001"
  agent_id: "autoresearch"
  persona: "default"
  auto_ingest: true
  context_injection:
    enabled: true
    max_chunks: 5
    min_relevance: 0.5
  preflight:
    enabled: true
    stages: [4, 9, 18, 23]
    persona: "strict"
```

---

### Phase 2: Session Watcher Integration (Week 2)

**Goal:** Automatic session capture without manual ingest calls.

**Tasks:**
1. [ ] Modify `runner.py` to write JSONL session files
2. [ ] Create `scripts/start_mnemo_watcher.py`
3. [ ] Add watcher config to `config.arc.yaml`
4. [ ] Implement `/writeback` at end of research run
5. [ ] Add session lifecycle management (hot/warm/cold)

**Files to Create:**
```
berb/mnemo_bridge/
├── watcher.py       # Session watcher daemon
└── session_format.py # JSONL format definition
```

---

### Phase 3: Advanced Features (Week 3)

**Goal:** Leverage Mnemo's advanced capabilities.

**Tasks:**
1. [ ] Implement persona switching per stage
   - Strict for citations (Stages 4, 18, 23)
   - Creative for hypothesis generation (Stage 8)
   - Default for others
2. [ ] Add L1 bundle pre-building for common research patterns
3. [ ] Implement semantic search UI in dashboard
4. [ ] Add metrics: memory hit rate, preflight accuracy
5. [ ] Benchmark: runs with/without Mnemo

---

### Phase 4: Production Hardening (Week 4)

**Goal:** Production-ready integration.

**Tasks:**
1. [ ] Add circuit-breaker for Mnemo server failures
2. [ ] Implement graceful degradation (pipeline continues if Mnemo down)
3. [ ] Add health check to `berb doctor`
4. [ ] Write integration guide: `docs/mnemo-integration.md`
5. [ ] Create example config: `config.mnemo.example.yaml`
6. [ ] Add to CI/CD tests

---

## Configuration Reference

### Full Mnemo Bridge Config

```yaml
mnemo_bridge:
  # === Core Settings ===
  enabled: true
  server_url: "http://localhost:50001"
  auth_token: ""  # If Mnemo has auth enabled
  timeout_sec: 30

  # === Agent Identity ===
  agent_id: "autoresearch"
  agent_id_template: "research-{domain}"  # Dynamic per domain

  # === Persona Configuration ===
  default_persona: "default"
  stage_personas:
    LITERATURE_COLLECT: "strict"
    EXPERIMENT_DESIGN: "strict"
    HYPOTHESIS_GEN: "creative"
    PEER_REVIEW: "strict"
    CITATION_VERIFY: "strict"

  # === Context Injection ===
  context_injection:
    enabled: true
    max_chunks: 5
    min_relevance: 0.5
    cache_tier_preference: "l2"  # l1 | l2 | l3
    inject_as: "system_message"  # system_message | user_message_suffix

  # === Auto-Ingest ===
  auto_ingest:
    enabled: true
    include_metadata: true
    truncate_messages: 3000  # Max chars per message

  # === Preflight Validation ===
  preflight:
    enabled: true
    stages: [4, 9, 18, 23]
    persona: "strict"
    action_on_warn: "retry_with_context"  # retry_with_context | proceed | block

  # === Session Management ===
  sessions:
    auto_start: true
    auto_end: true
    writeback_on_complete: true
    summary_template: "research_run_summary"

  # === Fallback Behavior ===
  fallback:
    on_connection_error: "proceed_without_memory"
    on_timeout: "proceed_without_memory"
    max_retries: 2
    retry_delay_sec: 1
```

---

## Code Examples

### Bridge Adapter Class

```python
# berb/mnemo_bridge/__init__.py

import httpx
from typing import Optional
from berb.config import RCConfig

class MnemoBridge:
    def __init__(self, config: RCConfig):
        self.config = config.mnemo_bridge
        self.base_url = self.config.server_url
        self.agent_id = self.config.agent_id
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.config.timeout_sec
        )

    async def get_context(
        self,
        prompt: str,
        persona: Optional[str] = None,
        max_results: int = 5
    ) -> dict:
        """Retrieve relevant memories for a prompt."""
        response = await self.client.post(
            "/context",
            json={
                "prompt": prompt,
                "agent_id": self.agent_id,
                "persona": persona or self.config.default_persona,
                "max_results": max_results
            }
        )
        response.raise_for_status()
        return response.json()

    async def ingest(
        self,
        prompt: str,
        response: str,
        metadata: Optional[dict] = None
    ) -> dict:
        """Archive a prompt/response pair."""
        response = await self.client.post(
            "/ingest",
            json={
                "prompt": prompt,
                "response": response,
                "agent_id": self.agent_id,
                "metadata": metadata
            }
        )
        response.raise_for_status()
        return response.json()

    async def preflight(
        self,
        prompt: str,
        draft_response: str,
        persona: Optional[str] = None
    ) -> dict:
        """Validate a draft response."""
        response = await self.client.post(
            "/preflight",
            json={
                "prompt": prompt,
                "draft_response": draft_response,
                "agent_id": self.agent_id,
                "persona": persona or self.config.default_persona
            }
        )
        response.raise_for_status()
        return response.json()

    async def writeback(
        self,
        session_id: str,
        summary: str,
        key_facts: list[str],
        decisions: list[str]
    ) -> dict:
        """Archive completed research run."""
        response = await self.client.post(
            "/writeback",
            json={
                "session_id": session_id,
                "summary": summary,
                "key_facts": key_facts,
                "decisions_made": decisions,
                "agent_id": self.agent_id
            }
        )
        response.raise_for_status()
        return response.json()

    async def health_check(self) -> dict:
        """Check Mnemo server health."""
        response = await self.client.get("/health")
        response.raise_for_status()
        return response.json()
```

### Usage in Pipeline Runner

```python
# berb/pipeline/runner.py

from berb.mnemo_bridge import MnemoBridge

class Runner:
    def __init__(self, config: RCConfig):
        self.config = config
        self.mnemo = None
        if config.mnemo_bridge.enabled:
            self.mnemo = MnemoBridge(config)

    async def execute_stage(self, stage: Stage, **kwargs):
        # 1. Get context before stage
        if self.mnemo and self.mnemo.config.context_injection.enabled:
            context = await self.mnemo.get_context(
                prompt=kwargs.get("prompt", ""),
                persona=self._get_stage_persona(stage)
            )
            kwargs["mnemo_context"] = self._format_context(context)

        # 2. Execute stage
        result = await super().execute_stage(stage, **kwargs)

        # 3. Ingest result after stage
        if self.mnemo and self.mnemo.config.auto_ingest.enabled:
            await self.mnemo.ingest(
                prompt=kwargs.get("prompt", ""),
                response=result.output,
                metadata={"stage": int(stage), "status": result.status}
            )

        # 4. Preflight validation for critical stages
        if self.mnemo and stage in self.mnemo.config.preflight.stages:
            preflight = await self.mnemo.preflight(
                prompt=kwargs.get("prompt", ""),
                draft_response=result.output,
                persona=self.mnemo.config.preflight.persona
            )
            if preflight["verdict"] in ("WARN", "BLOCK"):
                # Retry with enriched context
                result = await self._retry_with_enrichment(stage, preflight, kwargs)

        return result
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_mnemo_bridge.py

import pytest
from berb.mnemo_bridge import MnemoBridge

@pytest.fixture
def mnemo_bridge(config):
    config.mnemo_bridge.enabled = True
    config.mnemo_bridge.server_url = "http://localhost:50001"
    return MnemoBridge(config)

@pytest.mark.asyncio
async def test_get_context(mnemo_bridge, mock_mnemo_server):
    context = await mnemo_bridge.get_context("test prompt")
    assert "chunks" in context
    assert len(context["chunks"]) > 0

@pytest.mark.asyncio
async def test_preflight_strict_persona(mnemo_bridge, mock_mnemo_server):
    result = await mnemo_bridge.preflight(
        prompt="Verify citations",
        draft_response="Smith et al. (2023) found...",
        persona="strict"
    )
    assert result["verdict"] in ("PASS", "ENRICH", "WARN", "BLOCK")

@pytest.mark.asyncio
async def test_fallback_on_connection_error(mnemo_bridge):
    # Mnemo server down - pipeline should continue
    mnemo_bridge.config.fallback.on_connection_error = "proceed_without_memory"
    result = await mnemo_bridge.get_context("test")
    assert result == {"chunks": [], "fallback_used": True}
```

### Integration Tests

```python
# tests/test_mnemo_integration.py

@pytest.mark.integration
class TestMnemoIntegration:
    async def test_full_pipeline_with_mnemo(self):
        config = load_test_config()
        config.mnemo_bridge.enabled = True
        config.mnemo_bridge.auto_ingest.enabled = True

        runner = Runner(config)
        results = await runner.run(topic="Test topic")

        # Verify all stages ingested
        sessions = await get_mnemo_sessions("autoresearch")
        assert len(sessions) >= 23  # One per stage
```

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Mnemo server downtime | Memory operations fail | Circuit-breaker + graceful degradation |
| Slow context retrieval | Pipeline slowdown | L1 cache priority, timeout limits |
| Memory contamination | Wrong context injected | Multi-tenant isolation, domain-specific agent IDs |
| API breaking changes | Integration breaks | Version pinning, adapter abstraction |
| Increased complexity | Harder to debug | Comprehensive logging, health checks |

---

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Repeated mistakes | 15% per run | <5% per run | Error pattern analysis |
| Citation hallucination rate | 2-3% | <0.5% | Post-verification audit |
| Literature discovery time | 45 min | 30 min | Stage 3-4 timing |
| Pipeline completion rate | 85% | 92% | Run success tracking |
| User satisfaction | N/A | >4/5 | Post-run surveys |

---

## Comparison: Mnemo Cortex vs MetaClaw

| Feature | Mnemo Cortex | MetaClaw | Use Both? |
|---------|--------------|----------|-----------|
| **Primary Focus** | Memory retrieval | Skill extraction | ✅ Yes |
| **Storage Format** | Raw sessions + embeddings | Structured skills (SKILL.md) | ✅ Complementary |
| **Retrieval** | Semantic search (L1/L2/L3) | Skill injection into prompts | ✅ Both useful |
| **Learning Mechanism** | Passive (auto-ingest) | Active (lesson→skill conversion) | ✅ Different approaches |
| **Persona Support** | Yes (strict/creative/default) | No | ✅ Mnemo advantage |
| **Session Watcher** | Yes (auto-capture) | No | ✅ Mnemo advantage |
| **Multi-Tenant** | Yes (isolated dirs) | Yes (skills_dir per project) | ✅ Both support |
| **Integration Effort** | Low (4 endpoints) | Medium (skill conversion) | ✅ Mnemo easier |

**Recommendation:** Use **both** - Mnemo for memory retrieval + MetaClaw for skill extraction.

---

## Next Steps

1. **Decision:** Approve Phase 1 implementation (core bridge)
2. **Setup:** Install Mnemo Cortex locally for testing
3. **Development:** Create `berb/mnemo_bridge/` module
4. **Testing:** Write unit tests + integration tests
5. **Documentation:** Write `docs/mnemo-integration.md`
6. **Rollout:** Enable for beta testers, gather feedback

---

## Appendix: Quick Start Commands

### Install Mnemo Cortex

```bash
# Option 1: pip install
pip install mnemo-cortex

# Option 2: From source
git clone https://github.com/GuyMannDude/mnemo-cortex.git
cd mnemo-cortex
pip install -e .

# Initialize
mnemo-cortex init  # Interactive setup

# Start server
mnemo-cortex start

# Start watcher (for OpenClaw-style auto-capture)
mnemo-cortex watch --backfill

# Check status
mnemo-cortex status
```

### Test Endpoints

```bash
# Health check
curl http://localhost:50001/health

# Get context
curl -X POST http://localhost:50001/context \
  -H "Content-Type: application/json" \
  -d '{"prompt": "n-body symplectic integrators", "agent_id": "autoresearch"}'

# Ingest
curl -X POST http://localhost:50001/ingest \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test", "response": "test response", "agent_id": "autoresearch"}'

# Preflight
curl -X POST http://localhost:50001/preflight \
  -H "Content-Type: application/json" \
  -d '{"prompt": "verify", "draft_response": "Smith et al. 2023 found...", "agent_id": "autoresearch"}'
```

---

## References

- **Mnemix Repo:** `E:\Documents\Vibe-Coding\Github Projects\Research\AutoResearchClaw-main\AutoResearchClaw-main\mnemix`
- **Mnemo Cortex GitHub:** https://github.com/GuyMannDude/mnemo-cortex
- **AutoResearchClaw MetaClaw Integration:** `berb/metaclaw_bridge/`
- **OpenClaw Adapter Example:** `mnemix/adapters/openclaw/`
