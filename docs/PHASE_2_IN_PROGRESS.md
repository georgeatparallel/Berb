# Phase 2 Implementation Status

**Reasoner Integration Progress**

*Date: March 29, 2026*  
*Status: 🟡 In Progress (33% Complete)*

---

## Completed Methods (3/9)

### ✅ Multi-Perspective Method
**File:** `berb/reasoning/multi_perspective.py`

**Changes:**
- Added `_run_id` for cost tracking
- Added `_track_cost()` method
- Integrated with ExtendedNadirClawRouter cost tracking

**Token Estimates:**
- Input: 2,000 tokens (4 perspectives × 500)
- Output: 1,200 tokens (4 perspectives × 300)

---

### ✅ Pre-Mortem Method
**File:** `berb/reasoning/pre_mortem.py`

**Changes:**
- Added `_run_id` for cost tracking
- Added `_track_cost()` method
- Integrated with ExtendedNadirClawRouter cost tracking

**Token Estimates:**
- Input: 800 × num_scenarios
- Output: 600 × num_scenarios

---

### ✅ Bayesian Method
**Status:** Similar pattern applied (cost tracking added)

---

## Remaining Methods (6/9)

### 🔄 Debate Method
**File:** `berb/reasoning/debate.py`

**Migration Required:**
```python
# Current (uses llm_client directly)
class DebateMethod(ReasoningMethod):
    def __init__(self, llm_client: Any = None, ...):
        self.llm_client = llm_client

# Target (uses router)
class DebateMethod(ReasoningMethod):
    def __init__(self, router: Any = None, llm_client: Any = None, ...):
        self.router = router  # NEW: Primary
        self.llm_client = llm_client  # DEPRECATED: Fallback
```

**Roles to Map:**
- `debate_pro` → Qwen3.5-397B-A17B
- `debate_con` → Qwen3-Max-Thinking
- `debate_judge` → Grok 4.20 Beta

---

### 🔄 Dialectical Method
**File:** `berb/reasoning/dialectical.py`

**Roles to Map:**
- `dialectical_thesis` → GLM 5
- `dialectical_antithesis` → Qwen3.5-397B-A17B
- `dialectical_synthesis` → Kimi K2 Thinking

---

### 🔄 Research Method
**File:** `berb/reasoning/research.py`

**Roles to Map:**
- `research_query` → Perplexity Sonar Pro Search
- `research_synthesis` → Qwen3.5-Plus
- `research_gap` → MiniMax M2.5 FREE
- `research_final` → MiMo V2 Pro

---

### 🔄 Socratic Method
**File:** `berb/reasoning/socratic.py`

**Roles to Map:**
- `socratic_clarification` → GLM 4.5 Air FREE
- `socratic_assumption` → GLM 4.7 Flash
- `socratic_evidence` → MiniMax M2.5 FREE
- `socratic_perspective` → Qwen3.5-35B-A3B
- `socratic_meta` → Kimi K2 Thinking

---

### 🔄 Scientific Method
**File:** `berb/reasoning/scientific.py`

**Roles to Map:**
- `scientific_observation` → GLM 4.7
- `scientific_hypothesis` → Qwen3-Max-Thinking
- `scientific_prediction` → Qwen3-Coder-Next
- `scientific_experiment` → Kimi K2.5
- `scientific_analysis` → MiniMax M2.5 FREE

---

### 🔄 Jury Method
**File:** `berb/reasoning/jury.py`

**Roles to Map:**
- `jury_juror` (6×) → Grok 4.20 Multi-Agent Beta
- `jury_foreman` → Qwen3.5-Plus
- `jury_verdict` → GLM 5

---

## Migration Pattern

### For Each Method

1. **Update Constructor:**
```python
def __init__(
    self,
    router: Any = None,      # NEW: Primary
    llm_client: Any = None,  # DEPRECATED: Fallback
    ...
):
    self.router = router
    self.llm_client = llm_client
    self._run_id: str | None = None
```

2. **Update Execute Method:**
```python
async def execute(self, context: ReasoningContext) -> ReasoningResult:
    import uuid
    self._run_id = f"{method_code}-{uuid.uuid4().hex[:8]}"
    
    # ... existing logic ...
    
    result = ReasoningResult.success_result(...)
    self._track_cost(elapsed)
    return result
```

3. **Add _track_cost Method:**
```python
def _track_cost(self, duration_sec: float) -> None:
    """Track cost for {method} execution."""
    if self.router is None or self._run_id is None:
        return
    
    if hasattr(self.router, 'track_cost'):
        self.router.track_cost(
            method="{method}",
            phase="all",
            model=self.router.role_models.get("{primary_role}", self.router.mid_model),
            input_tokens=estimated_input,
            output_tokens=estimated_output,
            duration_ms=int(duration_sec * 1000),
            run_id=self._run_id,
        )
```

4. **Update LLM Calls:**
```python
# Before
response = self.llm_client.chat(messages)

# After
if self.router:
    provider = self.router.get_provider_for_role("{role}")
    response = await provider.chat(messages)
else:
    response = self.llm_client.chat(messages)  # Fallback
```

---

## Token Estimates by Method

| Method | Est. Input | Est. Output | Est. Cost (Value) |
|--------|------------|-------------|-------------------|
| Multi-Perspective | 2,000 | 1,200 | $0.05 |
| Pre-Mortem | 3,200 | 2,400 | $0.08 |
| Bayesian | 1,500 | 800 | $0.03 |
| Debate | 2,500 | 1,500 | $0.06 |
| Dialectical | 2,000 | 1,200 | $0.05 |
| Research | 4,000 | 2,500 | $0.10 |
| Socratic | 3,000 | 1,800 | $0.07 |
| Scientific | 3,500 | 2,000 | $0.08 |
| Jury | 5,000 | 3,000 | $0.15 |
| **TOTAL** | **26,700** | **16,400** | **$0.67** |

---

## Next Steps

1. **Complete migrations** for remaining 6 methods
2. **Add integration tests** for all methods
3. **Update documentation** with usage examples
4. **Run full test suite** to verify backward compatibility
5. **Create Phase 2 completion report**

---

## Testing Checklist

For each migrated method:

- [ ] Constructor accepts `router` parameter
- [ ] Fallback to `llm_client` works
- [ ] Cost tracking integrated
- [ ] Unit tests pass
- [ ] Integration test created
- [ ] Backward compatibility verified

---

**Expected Completion:** Phase 2 complete after migrating remaining 6 methods.

**Total Estimated Time:** 6-8 hours for full migration.
