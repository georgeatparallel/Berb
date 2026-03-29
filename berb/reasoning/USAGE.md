# Reasoning Methods Usage Guide

## Overview

Berb provides **9 advanced reasoning methods** for enhanced decision-making throughout the 23-stage research pipeline. Each method is implemented **once** in its dedicated file and can be reused via the **registry pattern**.

## Architecture

```
berb/reasoning/
├── __init__.py           # Public API exports
├── base.py               # Base classes (ReasoningMethod, ReasoningContext, ReasoningResult)
├── registry.py           # Central registry (singleton pattern)
├── multi_perspective.py  # 4-perspective analysis (constructive, destructive, systemic, minimalist)
├── pre_mortem.py         # Failure identification via prospective hindsight
├── bayesian.py           # Probability-based belief updates
├── debate.py             # Pro/Con arguments with judge evaluation
├── dialectical.py        # Hegelian triad (thesis → antithesis → synthesis)
├── research.py           # Iterative search and synthesis
├── socratic.py           # Question-driven understanding
├── scientific.py         # Hypothesis generation and testing
└── jury.py               # Orchestrated multi-agent evaluation
```

## Usage Patterns

### Pattern 1: Registry Singleton (Recommended)

```python
from berb.reasoning.registry import get_reasoner

# Get singleton instance (same instance returned on subsequent calls)
method = get_reasoner("multi_perspective", llm_client)
result = await method.execute(context)

# Second call returns the SAME instance
method2 = get_reasoner("multi_perspective", llm_client)
assert method is method2  # True
```

**Benefits:**
- ✅ Single instance across your application
- ✅ Consistent configuration
- ✅ Reduced memory footprint
- ✅ Thread-safe initialization

### Pattern 2: Factory Creation (Fresh Instance)

```python
from berb.reasoning.registry import create_reasoner

# Always creates a NEW instance
method1 = create_reasoner("debate", llm_client, num_arguments=3)
method2 = create_reasoner("debate", llm_client, num_arguments=5)

assert method1 is not method2  # True - different instances
```

**Benefits:**
- ✅ Independent configuration per instance
- ✅ Useful for parallel execution with different parameters
- ✅ Test isolation

### Pattern 3: Direct Import (One-off Usage)

```python
from berb.reasoning import MultiPerspectiveMethod

method = MultiPerspectiveMethod(llm_client)
result = await method.execute(context)
```

**Benefits:**
- ✅ Explicit and clear
- ✅ No registry dependency
- ✅ Traditional Python pattern

## Available Methods

### 1. Multi-Perspective Method

**File:** `berb/reasoning/multi_perspective.py`

**Purpose:** Analyze problems from 4 distinct perspectives.

**Perspectives:**
- **Constructive:** Build the strongest solution
- **Destructive:** Find every flaw
- **Systemic:** Identify second/third-order effects
- **Minimalist:** Find simplest 80% solution (Occam's Razor)

**Usage:**
```python
from berb.reasoning.registry import get_reasoner, create_context

method = get_reasoner("multi_perspective", llm_client)
context = create_context(
    stage_id="HYPOTHESIS_GEN",
    stage_name="Hypothesis Generation",
    input_data={"synthesis": synthesis_report},
    topic="CRISPR gene editing",
)
result = await method.execute(context)

# Access results
perspectives = result.output["perspectives"]
scores = result.output["scores"]
top_candidates = result.output["top_candidates"]
```

---

### 2. Pre-Mortem Method

**File:** `berb/reasoning/pre_mortem.py`

**Purpose:** Identify failures via prospective hindsight (Gary Klein's research).

**Process:**
1. Assume failure has already occurred
2. Reconstruct the failure narrative
3. Identify root causes
4. Generate early warning signals
5. Create hardened redesign

**Usage:**
```python
from berb.reasoning.registry import get_reasoner

method = get_reasoner("pre_mortem")
context = create_context(
    stage_id="EXPERIMENT_DESIGN",
    stage_name="Experiment Design",
    input_data={"design": experiment_plan},
)
result = await method.execute(context)

# Access results
failure_narratives = result.output["failure_narratives"]
root_causes = result.output["root_causes"]
early_signals = result.output["early_signals"]
hardened_solution = result.output["hardened_solution"]
```

---

### 3. Bayesian Method

**File:** `berb/reasoning/bayesian.py`

**Purpose:** Evidence-grounded belief updates using Bayes' rule.

**Formula:** `P(H|E) = P(E|H) × P(H) / P(E)`

**Usage:**
```python
from berb.reasoning.registry import get_reasoner

method = get_reasoner("bayesian", llm_client)
context = create_context(
    stage_id="LITERATURE_SCREEN",
    stage_name="Literature Screening",
    input_data={
        "hypotheses": ["H1", "H2"],
        "evidence": [paper_findings],
    },
)
result = await method.execute(context)

# Access results
posteriors = result.output["posteriors"]
sensitivity = result.output["sensitivity"]
```

---

### 4. Debate Method

**File:** `berb/reasoning/debate.py`

**Purpose:** Structured debate with Pro/Con arguments and Judge evaluation.

**Process:**
1. Generate Pro arguments supporting a position
2. Generate Con arguments opposing the position
3. Judge evaluates arguments and declares winner
4. Balanced conclusion based on debate

**Usage:**
```python
from berb.reasoning.registry import get_reasoner

method = get_reasoner("debate", llm_client, num_arguments=5)
context = create_context(
    stage_id="RESEARCH_DECISION",
    stage_name="Research Decision",
    input_data={"position": "Continue with approach A"},
)
result = await method.execute(context)

# Access results
winner = result.output["winner"]  # "pro", "con", or "undecided"
conclusion = result.output["conclusion"]
```

---

### 5. Dialectical Method

**File:** `berb/reasoning/dialectical.py`

**Purpose:** Hegelian dialectic: Thesis → Antithesis → Aufhebung (Synthesis).

**Process:**
1. Establish thesis (initial position)
2. Generate antithesis (opposing position)
3. Resolve contradictions through aufhebung
4. Produce higher-level understanding

**Usage:**
```python
from berb.reasoning.registry import get_reasoner

method = get_reasoner("dialectical", llm_client)
context = create_context(
    stage_id="SYNTHESIS",
    stage_name="Literature Synthesis",
    input_data={"thesis": initial_theory},
)
result = await method.execute(context)

# Access results
thesis = result.output["thesis"]
antithesis = result.output["antithesis"]
synthesis = result.output["synthesis"]
```

---

### 6. Research Method

**File:** `berb/reasoning/research.py`

**Purpose:** Iterative search-synthesis-gap identification loop.

**Process:**
1. Initial search/query formulation
2. Information gathering
3. Analysis and synthesis
4. Gap identification
5. Refined search (iterate)
6. Final synthesis

**Usage:**
```python
from berb.reasoning.registry import get_reasoner

method = get_reasoner("research", llm_client, search_client=search_client)
context = create_context(
    stage_id="LITERATURE_COLLECT",
    stage_name="Literature Collection",
    input_data={"topic": "quantum computing"},
)
result = await method.execute(context)

# Access results
findings = result.output["key_findings"]
gaps = result.output["remaining_gaps"]
synthesis = result.output["final_synthesis"]
```

---

### 7. Socratic Method

**File:** `berb/reasoning/socratic.py`

**Purpose:** Deep understanding through systematic questioning.

**Question Categories:**
1. Clarification
2. Assumptions
3. Evidence
4. Perspectives
5. Implications
6. Meta-questioning

**Usage:**
```python
from berb.reasoning.registry import get_reasoner

method = get_reasoner("socratic", llm_client)
context = create_context(
    stage_id="PROBLEM_DECOMPOSE",
    stage_name="Problem Decomposition",
    input_data={"question": "What causes X?"},
)
result = await method.execute(context)

# Access results
insights = result.output["key_insights"]
understanding = result.output["final_understanding"]
remaining = result.output["remaining_questions"]
```

---

### 8. Scientific Method

**File:** `berb/reasoning/scientific.py`

**Purpose:** Hypothesis-driven inquiry following the scientific method.

**Process:**
1. Observation/Question
2. Hypothesis formulation
3. Prediction derivation
4. Experiment design
5. Data collection
6. Analysis and conclusion
7. Iteration (refine hypothesis)

**Usage:**
```python
from berb.reasoning.registry import get_reasoner

method = get_reasoner("scientific", llm_client)
context = create_context(
    stage_id="HYPOTHESIS_GEN",
    stage_name="Hypothesis Generation",
    input_data={"observation": "Phenomenon X occurs under condition Y"},
)
result = await method.execute(context)

# Access results
hypothesis = result.output["hypothesis"]
experiment = result.output["experiment_design"]
conclusion = result.output["conclusion"]
```

---

### 9. Jury Method

**File:** `berb/reasoning/jury.py`

**Purpose:** Orchestrated multi-agent evaluation with jury deliberation.

**Juror Roles:**
- Optimist, Skeptic, Practitioner, Ethicist, Innovator, Economist

**Process:**
1. Select diverse jurors
2. Present evidence to all jurors
3. Each juror deliberates independently
4. Foreman synthesizes verdict
5. Unanimous/majority decision

**Usage:**
```python
from berb.reasoning.registry import get_reasoner

method = get_reasoner("jury", llm_client, jury_size=6)
context = create_context(
    stage_id="PEER_REVIEW",
    stage_name="Peer Review",
    input_data={"paper": draft_paper},
)
result = await method.execute(context)

# Access results
verdict = result.output["verdict"]  # "unanimous_approve", "majority_approve", etc.
vote_count = result.output["vote_count"]
synthesis = result.output["foreman_synthesis"]
```

---

## Registry API Reference

### `get_reasoner(method_type, llm_client=None, **kwargs)`

Get a reasoning method instance (singleton pattern).

**Parameters:**
- `method_type` (str | MethodType): Type of reasoner
- `llm_client`: LLM client for the reasoner
- `**kwargs`: Additional initialization arguments

**Returns:** `ReasoningMethod` instance

**Example:**
```python
method = get_reasoner("bayesian", llm_client)
```

---

### `create_reasoner(method_type, llm_client=None, **kwargs)`

Create a new reasoning method instance (always fresh).

**Parameters:** Same as `get_reasoner`

**Returns:** New `ReasoningMethod` instance

**Example:**
```python
method1 = create_reasoner("debate", llm_client, num_arguments=3)
method2 = create_reasoner("debate", llm_client, num_arguments=5)
```

---

### `list_reasoners()`

List all available reasoning methods.

**Returns:** `list[str]` of method type names

**Example:**
```python
from berb.reasoning.registry import list_reasoners
print(list_reasoners())
# ['multi_perspective', 'pre_mortem', 'bayesian', 'debate', ...]
```

---

### `ReasonerRegistry` Class

Direct access to the registry (advanced usage).

**Methods:**
- `register(method_type, reasoner_class, factory_func=None)` - Register a method
- `get(method_type, llm_client=None, **kwargs)` - Get singleton instance
- `create(method_type, llm_client=None, **kwargs)` - Create new instance
- `clear_singletons()` - Clear all singleton instances
- `list_available()` - List registered methods
- `is_registered(method_type)` - Check if registered

---

## Best Practices

### 1. Use Registry for Reuse

```python
# ✅ Recommended: Singleton pattern
from berb.reasoning.registry import get_reasoner

reasoner = get_reasoner("multi_perspective", llm_client)
# Use in multiple stages
result1 = await reasoner.execute(context1)
result2 = await reasoner.execute(context2)
```

### 2. Clear Singletons When Needed

```python
from berb.reasoning.registry import ReasonerRegistry

# Clear when LLM client needs refresh
ReasonerRegistry.clear_singletons()
```

### 3. Use create_reasoner for Parallel Execution

```python
from berb.reasoning.registry import create_reasoner
import asyncio

# Create independent instances for parallel execution
tasks = [
    create_reasoner("perspective", llm_client).execute(ctx)
    for ctx in contexts
]
results = await asyncio.gather(*tasks)
```

### 4. Type-Safe Method Types

```python
from berb.reasoning import MethodType, get_reasoner

# Use enum for type safety
method = get_reasoner(MethodType.BAYESIAN, llm_client)
```

---

## Testing

```python
import pytest
from berb.reasoning.registry import get_reasoner, ReasonerRegistry
from berb.reasoning.base import create_context

@pytest.mark.asyncio
async def test_multi_perspective():
    # Clear singletons for test isolation
    ReasonerRegistry.clear_singletons()
    
    # Get reasoner
    method = get_reasoner("multi_perspective", mock_llm)
    context = create_context(
        stage_id="TEST",
        stage_name="Test Stage",
        input_data={"problem": "test problem"},
    )
    
    # Execute
    result = await method.execute(context)
    
    # Assert
    assert result.success
    assert "perspectives" in result.output
```

---

## Migration Guide

### From Direct Imports to Registry

**Before:**
```python
from berb.reasoning.multi_perspective import MultiPerspectiveMethod

method = MultiPerspectiveMethod(llm_client)
result = await method.execute(context)
```

**After:**
```python
from berb.reasoning.registry import get_reasoner

method = get_reasoner("multi_perspective", llm_client)
result = await method.execute(context)
```

### Benefits of Migration

1. **Consistency:** Single pattern across all methods
2. **Flexibility:** Easy to swap implementations
3. **Testability:** Mock registry in tests
4. **Performance:** Singleton reduces instantiation overhead

---

## Troubleshooting

### "Unknown reasoning method" Error

```python
# Check available methods
from berb.reasoning.registry import list_reasoners
print(list_reasoners())

# Ensure method type is correct
from berb.reasoning import MethodType
method = get_reasoner(MethodType.BAYESIAN, llm_client)  # ✅
method = get_reasoner("bayesian", llm_client)  # ✅
method = get_reasoner("unknown", llm_client)  # ❌ ValueError
```

### Singleton Not Working

```python
# Clear singletons if needed
from berb.reasoning.registry import ReasonerRegistry
ReasonerRegistry.clear_singletons()

# Verify same instance
m1 = get_reasoner("bayesian", llm_client)
m2 = get_reasoner("bayesian", llm_client)
assert m1 is m2  # Should be True
```

### LLM Client Not Passed

```python
# Some methods require llm_client
method = get_reasoner("bayesian", llm_client)  # ✅
method = get_reasoner("bayesian")  # May fail if llm_client required

# Check method requirements
from berb.reasoning.registry import ReasonerRegistry
print(ReasonerRegistry.list_available())
```

---

## Author

Georgios-Chrysovalantis Chatzivantsidis

## License

MIT
