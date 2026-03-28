# Week 2 Implementation Plan

**Date:** 2026-03-28  
**Status:** Starting Week 2  
**Focus:** Reasoning Methods Integration + HyperAgent Foundation

---

## 📊 Week 1 Summary (COMPLETE ✅)

### **Completed Enhancements**
- ✅ SearXNG Integration (100+ search engines, self-hosted)
- ✅ Reasoning Methods Base (Multi-Perspective, Pre-Mortem)
- ✅ OpenRouter Adapter (15+ models, -60% cost)
- ✅ Physics Domain Phase 1 (Chaos detection tools)

### **Test Results**
- **46 tests** added
- **90% pass rate** (4 minor mock-related failures)
- **3,479 lines** added across 13 files

### **Impact**
| Metric | Improvement |
|--------|-------------|
| Search Coverage | +3300% |
| Search Cost | -100% |
| Model Diversity | +300% |
| LLM Cost | -60% |

---

## 🎯 Week 2 Objectives

### **1. Reasoning Methods Integration (P0)**
**Goal:** Integrate reasoning methods into pipeline stages

**Target Stages:**
- Stage 8 (HYPOTHESIS_GEN): Multi-Perspective, Debate
- Stage 9 (EXPERIMENT_DESIGN): Pre-Mortem
- Stage 15 (RESEARCH_DECISION): Bayesian, Multi-Perspective
- Stage 18 (PEER_REVIEW): Jury (Orchestrated)

**Expected Impact:**
- +35% hypothesis quality
- -50% design flaws
- +40% decision accuracy
- +25% review quality

### **2. HyperAgent Foundation (P0)**
**Goal:** Implement core HyperAgent architecture

**Based on:** Facebook AI Research paper (arXiv:2603.19461v1)

**Key Components:**
- Task Agent (solves research tasks)
- Meta Agent (modifies task agent + itself)
- Persistent Memory (accumulates improvements)
- Self-Improvement Loop

**Expected Impact:**
- +32% quality over time
- 10x speedup
- Continuous self-improvement
- Cross-domain transfer

### **3. Additional Reasoning Methods (P1)**
**Goal:** Complete remaining reasoning methods

**Methods to Implement:**
- Bayesian Reasoning (Stage 5, 14, 15, 20)
- Debate (Stage 8, 15)
- Dialectical (Stage 7, 8, 15)
- Research Iterative (Stage 3-6)

---

## 📋 Implementation Tasks

### **Task 1: Reasoning Methods Integration**

#### **Stage 8: HYPOTHESIS_GEN Enhancement**

**Current Implementation:**
```python
# berb/pipeline/stage_impls/_synthesis.py
def _execute_hypothesis_gen(...):
    # Multi-perspective debate (basic)
    perspectives = _multi_perspective_generate(...)
    hypotheses_md = _synthesize_perspectives(...)
```

**Enhanced Implementation:**
```python
from berb.reasoning import MultiPerspectiveMethod, DebateMethod

def _execute_hypothesis_gen(...):
    # Use formal reasoning methods
    method = MultiPerspectiveMethod(router, parallel=True, top_k=2)
    ctx = create_context(
        stage_id="HYPOTHESIS_GEN",
        stage_name="Hypothesis Generation",
        input_data={"synthesis": synthesis},
    )
    result = await method.execute(ctx)
    
    # Access structured output
    hypotheses = result.output["top_candidates"]
    scores = result.output["scores"]
```

**Files to Modify:**
- `berb/pipeline/stage_impls/_synthesis.py`
- `berb/pipeline/_helpers.py` (add reasoning method helpers)

#### **Stage 9: EXPERIMENT_DESIGN Enhancement**

**Current Implementation:**
```python
# berb/pipeline/stage_impls/_experiment_design.py
def _execute_experiment_design(...):
    # Basic design generation
    plan = _chat_with_prompt(llm, ...)
```

**Enhanced Implementation:**
```python
from berb.reasoning import PreMortemMethod

def _execute_experiment_design(...):
    # Generate initial design
    initial_design = _chat_with_prompt(llm, ...)
    
    # Apply Pre-Mortem analysis
    pm = PreMortemMethod(router, num_scenarios=3)
    ctx = create_context(
        stage_id="EXPERIMENT_DESIGN",
        stage_name="Experiment Design",
        input_data={"proposed_design": initial_design},
    )
    result = await pm.execute(ctx)
    
    # Use hardened design
    hardened_design = result.output["hardened_solution"]
    failure_modes = result.output["failure_narratives"]
```

**Files to Modify:**
- `berb/pipeline/stage_impls/_experiment_design.py`

#### **Stage 15: RESEARCH_DECISION Enhancement**

**Current Implementation:**
```python
# berb/pipeline/stage_impls/_analysis.py
def _execute_research_decision(...):
    # Basic decision based on analysis
    decision = _parse_decision(llm_response)
```

**Enhanced Implementation:**
```python
from berb.reasoning import BayesianMethod, MultiPerspectiveMethod

def _execute_research_decision(...):
    # Bayesian evaluation of decision options
    bayesian = BayesianMethod(router)
    ctx = create_context(
        stage_id="RESEARCH_DECISION",
        stage_name="Research Decision",
        input_data={
            "analysis": analysis,
            "options": ["PROCEED", "REFINE", "PIVOT"],
        },
    )
    result = await bayesian.execute(ctx)
    
    # Use posterior probabilities for decision
    posteriors = result.output["posteriors"]
    decision = max(posteriors, key=posteriors.get)
```

**Files to Modify:**
- `berb/pipeline/stage_impls/_analysis.py`

---

### **Task 2: HyperAgent Foundation**

#### **Core Architecture**

```
berb/hyperagent/
├── __init__.py
├── base.py                 # Hyperagent base class
├── task_agent.py           # Task-solving agent
├── meta_agent.py           # Meta-modification agent
├── memory.py               # Persistent memory
├── improvement_loop.py     # Self-improvement loop
├── evaluator.py            # Agent evaluation
└── selection.py            # Variant selection
```

#### **Implementation Steps**

**Step 1: Base Class**
```python
# berb/hyperagent/base.py
class HyperagentBase:
    """Base class for Hyperagents."""
    
    def __init__(self, config: RCConfig):
        self.config = config
        self.task_agent = None
        self.meta_agent = None
        self.memory = PersistentMemory()
        self.improvement_history = []
    
    async def run_task(self, task: str) -> Any:
        """Execute task with current agent variant."""
        pass
    
    async def self_improve(self) -> ImprovementResult:
        """Run self-improvement loop."""
        pass
```

**Step 2: Task Agent**
```python
# berb/hyperagent/task_agent.py
class TaskAgent:
    """Agent that solves research tasks."""
    
    def __init__(self, code: str, config: RCConfig):
        self.code = code  # Editable program
        self.config = config
    
    async def execute(self, task: str) -> TaskResult:
        """Execute research task."""
        pass
```

**Step 3: Meta Agent**
```python
# berb/hyperagent/meta_agent.py
class MetaAgent:
    """Agent that modifies task agent AND its own modification procedure."""
    
    def __init__(self, modification_code: str, config: RCConfig):
        self.modification_code = code  # Editable!
        self.config = config
    
    async def modify(self, task_agent: TaskAgent) -> TaskAgent:
        """Generate improved variant of task agent."""
        pass
    
    async def modify_self(self) -> MetaAgent:
        """Metacognitive: modify own modification procedure!"""
        pass
```

**Step 4: Persistent Memory**
```python
# berb/hyperagent/memory.py
class PersistentMemory:
    """Stores improvements across runs."""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.improvements = []
        self.performance_history = []
    
    def store_improvement(self, improvement: Improvement):
        """Store improvement with metadata."""
        pass
    
    def get_relevant_improvements(self, task: str) -> list[Improvement]:
        """Retrieve improvements relevant to current task."""
        pass
    
    def transfer_across_domains(self, source_domain: str, target_domain: str):
        """Transfer improvements between domains."""
        pass
```

**Step 5: Self-Improvement Loop**
```python
# berb/hyperagent/improvement_loop.py
class ImprovementLoop:
    """Runs the Hyperagent self-improvement loop."""
    
    async def run(self, hyperagent: HyperagentBase, n_iterations: int):
        for iteration in range(n_iterations):
            # 1. Execute task
            result = await hyperagent.run_task(current_task)
            
            # 2. Track performance
            hyperagent.memory.store_performance(result)
            
            # 3. Analyze for improvements
            analysis = await hyperagent.meta_agent.analyze(result)
            
            # 4. Generate modifications
            modifications = await hyperagent.meta_agent.generate_mods(analysis)
            
            # 5. Evaluate variants
            scores = await self.evaluate_variants(modifications)
            
            # 6. Select best variant
            best = self.select_best(scores)
            
            # 7. Store improvement
            hyperagent.memory.store_improvement(best)
```

---

### **Task 3: Additional Reasoning Methods**

#### **Bayesian Reasoning**
```python
# berb/reasoning/bayesian.py
class BayesianMethod(ReasoningMethod):
    """Bayesian reasoning for evidence-grounded belief updates."""
    
    async def execute(self, context: ReasoningContext) -> ReasoningResult:
        # Phase 1: Prior elicitation
        priors = await self._elicit_priors(context)
        
        # Phase 2: Likelihood assessment
        likelihoods = await self._assess_likelihoods(context)
        
        # Phase 3: Posterior update
        posteriors = await self._update_posteriors(priors, likelihoods)
        
        # Phase 4: Sensitivity analysis
        sensitivity = await self._analyze_sensitivity(posteriors)
```

#### **Debate Method**
```python
# berb/reasoning/debate.py
class DebateMethod(ReasoningMethod):
    """Debate with Pro/Con arguments and judge evaluation."""
    
    async def execute(self, context: ReasoningContext) -> ReasoningResult:
        # Round 0: Opening statements
        pro_opening = await self._debate_argument("pro", ...)
        con_opening = await self._debate_argument("con", ...)
        
        # Round 1-2: Rebuttals
        for round_num in range(1, 3):
            pro_rebuttal = await self._debate_rebuttal("pro", ...)
            con_rebuttal = await self._debate_rebuttal("con", ...)
        
        # Judge decision
        judge_decision = await self._debate_judge(...)
```

---

## 📅 Week 2 Timeline

| Day | Focus | Deliverables |
|-----|-------|--------------|
| **Mon** | Reasoning Integration | Stage 8, 9 enhanced |
| **Tue** | Reasoning Integration | Stage 15 enhanced |
| **Wed** | HyperAgent Base | base.py, task_agent.py |
| **Thu** | HyperAgent Base | meta_agent.py, memory.py |
| **Fri** | HyperAgent Loop | improvement_loop.py |
| **Sat** | Additional Methods | Bayesian, Debate |
| **Sun** | Testing & Docs | Tests, documentation |

---

## 🧪 Testing Strategy

### **Unit Tests**
- `tests/test_reasoning_integration.py` - Pipeline integration tests
- `tests/test_hyperagent_base.py` - HyperAgent base tests
- `tests/test_hyperagent_loop.py` - Improvement loop tests

### **Integration Tests**
- Run 10 research projects with reasoning methods
- Run 5 projects with HyperAgent
- Compare quality metrics vs baseline

### **Benchmarks**
- Hypothesis quality (Stage 8)
- Design flaw detection (Stage 9)
- Decision accuracy (Stage 15)
- Self-improvement rate (HyperAgent)

---

## 📈 Success Metrics

| Metric | Baseline | Week 2 Target | Improvement |
|--------|----------|---------------|-------------|
| **Hypothesis Quality** | 8.5/10 | 11.5/10 | +35% |
| **Design Flaws** | ~10 | ~5 | -50% |
| **Decision Accuracy** | ~80% | ~95% | +19% |
| **Review Quality** | 7.5/10 | 9.5/10 | +27% |
| **Self-Improvement** | 0% | +10%/run | New capability |

---

## 🔗 Related Documentation

- `docs/HYPERAGENTS_PAPER_ANALYSIS.md` - HyperAgents paper analysis
- `docs/REASONING_METHODS_FOR_BERB.md` - Reasoning methods analysis
- `docs/REASONER_IMPLEMENTATION_PLAN.md` - Reasoner integration plan
- `TODO.md` - Implementation tracking

---

**Status:** Ready to implement!
