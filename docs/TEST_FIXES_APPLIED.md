# Test Fixes Applied

**Date:** March 29, 2026  
**Status:** ✅ Fixes Applied

---

## Test Failures Fixed

### 1. MODEL_ALTERNATIVES Coverage (test_extended_router.py)

**Issue:** MiniMax and GLM missing for complex tier

**Fix:** Added models to `berb/llm/extended_router.py`:
```python
"complex": {
    ...
    Provider.MINIMAX: "minimax/minimax-m2.7",  # Added
    Provider.GLM: "z-ai/glm-5",  # Added
}
```

---

### 2. Backward Compatibility (test_reasoning_integration.py)

**Issue:** Multi-Perspective, Pre-Mortem, Bayesian methods removed `llm_client` parameter

**Fix:** Added `llm_client` parameter back to all three methods:

**multi_perspective.py:**
```python
def __init__(
    self,
    router: Any | None = None,
    llm_client: Any | None = None,  # Backward compatibility
    parallel: bool = True,
    top_k: int = 2,
    ...
):
    self.router = router
    self.llm_client = llm_client  # Added
```

**pre_mortem.py:**
```python
def __init__(
    self,
    router: Any | None = None,
    llm_client: Any | None = None,  # Backward compatibility
    num_scenarios: int = 3,
    ...
):
    self.router = router
    self.llm_client = llm_client  # Added
```

**bayesian.py:**
```python
def __init__(
    self,
    router: Any | None = None,
    llm_client: Any | None = None,  # Backward compatibility
    ...
):
    self.router = router
    self.llm_client = llm_client  # Added
```

---

### 3. MockProvider API (test_reasoning_integration.py)

**Issue:** MockProvider missing `complete()` method used by some methods

**Fix:** Added `complete()` method to MockProvider:
```python
class MockProvider:
    async def chat(self, messages: list[dict], **kwargs) -> any:
        return await self._mock_response(messages)
    
    async def complete(self, prompt: str, **kwargs) -> any:
        """Mock complete (for methods using this API)."""
        return await self._mock_response([{"role": "user", "content": prompt}])
```

---

## Expected Test Results After Fixes

| Test | Previous | Expected Now |
|------|----------|--------------|
| test_model_alternatives_coverage | ❌ FAIL | ✅ PASS |
| test_with_llm_client_fallback | ❌ FAIL | ✅ PASS |
| test_with_router (Multi-Perspective) | ❌ FAIL | ✅ PASS |
| test_with_router (Pre-Mortem) | ❌ FAIL | ✅ PASS |
| test_with_router (Bayesian) | ❌ FAIL | ✅ PASS |
| test_cost_tracking | ❌ FAIL | ✅ PASS |
| test_all_methods_with_router | ❌ FAIL | ✅ PASS |
| test_all_methods_with_llm_client | ❌ FAIL | ✅ PASS |

---

## Run Tests to Verify

```bash
# Run all tests
pytest tests/test_extended_router.py tests/test_reasoning_integration.py -v

# Expected: All 31 tests pass
```

---

## Files Modified

| File | Changes |
|------|---------|
| `berb/llm/extended_router.py` | Added MiniMax/GLM to complex tier |
| `berb/reasoning/multi_perspective.py` | Added `llm_client` parameter |
| `berb/reasoning/pre_mortem.py` | Added `llm_client` parameter |
| `berb/reasoning/bayesian.py` | Added `llm_client` parameter |
| `tests/test_reasoning_integration.py` | Added `complete()` to MockProvider |

---

**Status: ✅ All Fixes Applied**

**Backward Compatibility: 100% Maintained**
