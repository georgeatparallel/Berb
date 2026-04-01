# Berb Optimization Plan — Research-Backed Architectural Upgrades

**Based on:** AIRA2 (Meta FAIR), CAID (CMU), Coding Agents as Long-Context Processors, PRBench (Peking U), HorizonMath, Tao & Klowden philosophical framework, Microsoft Copilot Researcher Critique/Council, Hive evolutionary synthesis

**Date:** 2026-04-01
**Status:** Analysis complete → Ready for integration into implementation prompt v9

---

## Source Analysis Summary

### 1. AIRA2 (Meta FAIR — arXiv:2603.26499)

**What it is:** State-of-the-art AI research agent. 76.0% Percentile Rank on MLE-bench-30 at 72h. Published March 2026.

**3 architectural breakthroughs:**

**A) Asynchronous Multi-GPU Worker Pool:** Decouples decision-making from execution. 8 workers run in parallel — no synchronization barriers. Steady-state evolution: orchestrator dispatches mutations as workers become available. Result: linear throughput scaling (8 GPUs ≈ 8× experiments).

**B) Hidden Consistent Evaluation (HCE):** Splits data into D_train (80%), D_search (10%), D_val (10%). Agents NEVER see validation labels. Orchestrator evaluates in separate container. Selection decoupled from optimization. Result: eliminates the "overfitting" observed in all prior work — which was actually evaluation noise, not data memorization. +18.4 Percentile Rank points at 72h.

**C) ReAct Agents as Operators:** Replaces fixed single-turn prompts with multi-step ReAct agents that reason→act→observe iteratively. Dynamic scoping (agent decides what to do at runtime). Interactive debugging (catches errors within same trajectory). Result: +5.5 points at 3h, acts as efficiency multiplier.

**Key finding:** Parallelism WITHOUT evolution saturates at single-GPU performance. You need both parallel compute AND evolutionary selection to benefit.

**Berb relevance:** HIGH — directly applicable to experiment execution (Stage 12-13) and improvement loop (M2).

### 2. CAID — Asynchronous Multi-Agent Coordination (CMU — arXiv:2603.21489)

**What it is:** Multi-agent coordination paradigm for long-horizon software engineering tasks.

**Core pattern — Centralized Asynchronous Isolated Delegation:**
- **Centralized:** Single manager creates dependency-aware task plans
- **Asynchronous:** Subtasks run concurrently without blocking
- **Isolated:** Each agent works in its own git worktree (branch isolation)
- **Delegation:** Manager delegates, agents execute, manager integrates

**Key mechanism:** Branch-and-merge using git primitives (worktree, commit, merge) as coordination tools. Test-based verification at integration.

**Result:** +26.7% absolute accuracy on PaperBench (paper reproduction), +14.3% on Commit0 (library development).

**Finding:** Optimal parallelism = 4 agents. More than 4 introduces integration overhead. Over-fine-grained delegation hurts.

**Berb relevance:** HIGH — Berb stages 9-13 (experiment design through analysis) could use CAID pattern for parallel experiment execution with isolated workspaces.

### 3. Coding Agents as Long-Context Processors (arXiv:2603.20432)

**What it is:** Study showing coding agents outperform raw LLM attention for long-context tasks by organizing text in file systems.

**Core insight:** Externalize long-context processing from latent attention into explicit, executable interactions. Let agents organize literature in file systems and manipulate it using tools (grep, awk, python scripts).

**Result:** +17.3% over SOTA on long-context benchmarks including RAG and open-domain QA with up to 3 trillion tokens.

**Berb relevance:** MEDIUM-HIGH — Literature processing (Stages 4-6) with 100+ papers = massive context. Instead of cramming all papers into LLM context, organize them in file system and let agents search/filter/extract programmatically.

### 4. PRBench — Physics Paper Reproduction (Peking U — arXiv:2603.27646)

**What it is:** Benchmark of 30 physics paper reproduction tasks across 11 subfields.

**Key agent failure patterns identified:**
- Agents fail to translate abstract math into efficient numerical routines
- Use dense matrices instead of sparse/structured representations
- Rely on unvectorized Python loops instead of NumPy/SciPy vectorization
- Explicitly construct Kronecker products instead of tensor reshaping
- Fail to separate core algorithm from task-specific outputs
- Return loosely organized internal variables instead of clean interfaces

**Berb relevance:** HIGH — directly informs the Math Engine (O2) and experiment code quality (O4). These are known failure modes Berb must avoid.

### 5. HorizonMath — Mathematical Discovery Benchmark (arXiv:2603.15617)

**What it is:** 100+ predominantly unsolved problems across 8 domains in computational/applied math, paired with automated verification framework.

**Key insight:** "Discovery is hard (requires mathematical insight), but verification is computationally efficient." Most SOTA models score near 0%.

**Design principle:** Problems where verification is easy but discovery is hard are immune to data contamination.

**Berb relevance:** MEDIUM — for the `math-paper` workflow (O2), Berb should adopt the same principle: generate mathematical claims, then verify computationally. Separate the "insight" step from the "verification" step.

### 6. Tao & Klowden — Mathematical Methods and Human Thought in the Age of AI

**Key philosophical arguments:**
- AI tools should be viewed through BOTH technical lens (micro: what problems they solve) AND humanitarian lens (macro: how society benefits)
- Technology should augment human understanding, not just produce outputs
- Prior technological advances (calculators, computers) changed what mathematicians DO, not whether they're needed
- Questions about what knowledge IS vs what knowledge is USEFUL will define AI's role

**Berb relevance:** HIGH-LEVEL — Berb should produce research that advances understanding, not just generates text. The collaborative mode is philosophically aligned. The claim confidence system (N1) ensures claims represent real knowledge.

### 7. Microsoft Copilot Researcher — Critique & Council

**What it is:** Microsoft's multi-model research system (launched March 30, 2026).

**Critique pattern:** GPT drafts research → Claude reviews for accuracy/completeness/citation quality → refined output. Separation of generation from evaluation. Result: +13.88% over best single-model system on DRACO benchmark.

**Council pattern:** Multiple models generate independent reports on same query → judge model evaluates, identifies agreement/divergence/unique insights → cover letter synthesizes.

**Key quote:** "GPT drafts, Claude critiques" — this is exactly the cross-model review pattern from M1 in our implementation prompt, but now validated by Microsoft at enterprise scale.

**Berb relevance:** CRITICAL — validates M1 (cross-model review) as the correct architectural direction. Also introduces the "Council" pattern which Berb doesn't yet have.

### 8. Hive — Evolutionary LLM Program Synthesis (arXiv:2603.26359)

**What it is:** AI platform using LLMs to drive distributed evolutionary process for algorithm discovery. Applied to quantum chemistry.

**Architecture:** Highly distributed evolutionary search over program space. LLMs propose mutations, environment evaluates, fitness drives selection. Multi-level optimization with interpretable outputs.

**Key pattern:** Separate the search (evolutionary) from the evaluation (execution environment) from the interpretation (post-hoc analysis of what the discovered algorithm does).

**Berb relevance:** MEDIUM — the evolutionary search pattern parallels AIRA2's approach and could inform Berb's improvement loop (M2).

---

## Berb Optimization Plan — 12 Concrete Upgrades

### UPGRADE 1: Asynchronous Parallel Experiment Execution (P0)
**Source:** AIRA2 + CAID
**File:** `berb/experiment/async_executor.py`

Replace sequential experiment execution (Stage 12) with asynchronous worker pool:

```python
class AsyncExperimentPool:
    """AIRA2-inspired asynchronous experiment execution."""
    
    def __init__(self, max_workers: int = 4):
        self.workers: list[ExperimentWorker] = []
        self.result_db: dict[str, ExperimentResult] = {}
    
    async def execute_parallel(
        self,
        experiments: list[ExperimentDesign],
        isolation: Literal["docker", "worktree", "sandbox"] = "docker"
    ) -> list[ExperimentResult]:
        """Run experiments in parallel isolated environments.
        
        CAID-inspired isolation:
        - Each experiment runs in its own Docker container or git worktree
        - No shared state between experiments
        - Results collected asynchronously
        - Failed experiments don't affect others
        
        AIRA2-inspired scheduling:
        - Steady-state: dispatch new experiment as worker frees
        - No synchronization barriers
        - Linear throughput scaling with workers
        """
```

**Impact:** 2-4× speedup on experiment-heavy runs. Enables evolutionary exploration of experiment variants.

### UPGRADE 2: Hidden Consistent Evaluation Protocol (P0)
**Source:** AIRA2
**File:** `berb/validation/hidden_eval.py`

Apply HCE principle to Berb's quality assessment:

```python
class HiddenConsistentEvaluation:
    """Prevent self-grading bias and evaluation noise.
    
    AIRA2 showed that "overfitting" in research agents is actually
    evaluation noise — not data memorization. Fix: decouple
    optimization signal from selection signal.
    """
    
    def __init__(self):
        # Three-way split of evaluation criteria
        self.search_criteria: EvalCriteria   # Used during improvement loop
        self.selection_criteria: EvalCriteria # Used for final paper selection
        self.test_criteria: EvalCriteria      # Never seen by any agent
    
    async def evaluate_for_search(
        self, paper: GeneratedPaper
    ) -> float:
        """Score used by improvement loop (M2) to guide optimization.
        Agent sees this score but NOT the underlying criteria details."""
    
    async def evaluate_for_selection(
        self, papers: list[GeneratedPaper]
    ) -> GeneratedPaper:
        """Select final paper from candidates using HIDDEN criteria.
        Never used during search — prevents hill-climbing on selection metric."""
```

**Impact:** Eliminates score gaming. Enables sustained improvement over extended runs (AIRA2 gained +4.2 points between 24h and 72h thanks to HCE).

### UPGRADE 3: Council Mode — Multi-Model Parallel Reports (P1)
**Source:** Microsoft Copilot Council
**File:** `berb/review/council_mode.py`

Beyond M1 (cross-model review), add Council mode where multiple models generate independent research outputs:

```python
class CouncilMode:
    """Microsoft Council-inspired: multiple models generate independent
    reports, then judge model evaluates agreement/divergence."""
    
    async def run_council(
        self,
        task: str,
        models: list[str],  # e.g., ["claude-opus", "gpt-4o", "gemini-pro"]
        judge_model: str = "claude-sonnet"
    ) -> CouncilResult:
        """
        1. Each model generates independent synthesis/analysis
        2. Judge model creates cover letter:
           - Where models agree (high confidence)
           - Where models diverge (requires investigation)
           - Unique insights from each model
        3. Researcher (or autonomous system) uses this to make decisions
        """
```

**Use in Berb pipeline:**
- **Stage 7 (SYNTHESIS):** Council on literature synthesis — catch blind spots
- **Stage 8 (HYPOTHESIS_GEN):** Council on hypothesis generation — more diverse ideas
- **Stage 15 (RESEARCH_DECISION):** Council on go/no-go — critical decision with multiple perspectives

### UPGRADE 4: File-System-Based Literature Processing (P1)
**Source:** Coding Agents as Long-Context Processors
**File:** `berb/literature/fs_processor.py`

Instead of cramming 100+ papers into LLM context, organize them in file system:

```python
class FileSystemLiteratureProcessor:
    """Process large literature collections via file system operations
    instead of attention-based context windows.
    
    Insight from arXiv:2603.20432: coding agents outperform raw LLM
    attention for long-context tasks by +17.3% when they organize
    text in file systems and manipulate it using tools.
    """
    
    async def organize_literature(
        self, papers: list[Paper], workspace: Path
    ) -> LiteratureWorkspace:
        """Create structured file system:
        workspace/
        ├── by_topic/           # Clustered by theme
        ├── by_year/            # Chronological
        ├── by_relevance/       # Ranked by relevance score
        ├── summaries/          # One-paragraph per paper
        ├── claims/             # Extracted claims with citations
        ├── contradictions/     # Identified contradictions
        ├── methods/            # Method descriptions
        └── index.json          # Searchable metadata index
        """
    
    async def query_literature(
        self, query: str, workspace: LiteratureWorkspace
    ) -> list[RelevantExcerpt]:
        """Use grep/search tools instead of LLM attention to find
        relevant content. Then pass only relevant excerpts to LLM."""
```

**Impact:** Handles 200-400 papers without context window pressure. Better retrieval accuracy than attention-only approaches.

### UPGRADE 5: Physics-Aware Code Quality Guards (P1)
**Source:** PRBench failure analysis
**File:** `berb/experiment/physics_guards.py`

PRBench identified specific failure patterns. Berb must avoid them:

```python
class PhysicsCodeGuard:
    """Prevent common computational physics coding failures
    identified by PRBench (arXiv:2603.27646)."""
    
    ANTI_PATTERNS = [
        "dense_matrix_for_sparse",     # Use scipy.sparse instead
        "unvectorized_loops",          # Use NumPy vectorization
        "explicit_kronecker_product",  # Use tensor reshaping
        "missing_numerical_precision", # Check dtypes (float64)
        "no_convergence_test",         # Must verify convergence
        "loose_variable_organization", # Clean interfaces required
    ]
    
    async def check_experiment_code(
        self, code: str, domain: str
    ) -> list[CodeQualityIssue]:
        """Scan generated code for known anti-patterns.
        Auto-fix where possible, flag for human review otherwise."""
    
    async def suggest_efficient_alternative(
        self, code_snippet: str, issue: str
    ) -> str:
        """Suggest: scipy.sparse, numpy vectorization, einsum, etc."""
```

### UPGRADE 6: Verification-First Mathematical Content (P1)
**Source:** HorizonMath + PRBench
**File:** Update to `berb/math/math_engine.py` (O2)

Mathematical claims must be computationally verifiable:

```python
class VerifiableMathContent:
    """HorizonMath principle: discovery is hard, verification is easy.
    Generate math claims, then verify computationally."""
    
    async def generate_and_verify_theorem(
        self, statement: str, context: str
    ) -> VerifiedTheorem:
        """
        1. Generate theorem + proof (reasoning model)
        2. Translate key claims to computational tests
        3. Run numerical verification (plug in known values)
        4. Check boundary conditions automatically
        5. If verification fails → regenerate or flag
        """
    
    async def verify_equation_numerically(
        self, equation: str, test_values: dict
    ) -> bool:
        """Plug numbers into both sides of equation.
        If they don't match → equation is wrong."""
    
    async def verify_convergence_claim(
        self, algorithm: str, test_cases: list
    ) -> ConvergenceReport:
        """Run algorithm on known inputs, verify convergence rate matches claim."""
```

### UPGRADE 7: Evolutionary Experiment Search (P2)
**Source:** AIRA2 + Hive
**File:** `berb/experiment/evolutionary_search.py`

Apply evolutionary search over experiment variants:

```python
class EvolutionaryExperimentSearch:
    """AIRA2/Hive-inspired: maintain population of experiment variants,
    evolve toward better results."""
    
    async def search(
        self,
        base_experiment: ExperimentDesign,
        population_size: int = 8,
        max_generations: int = 4,
        mutation_rate: float = 0.3
    ) -> ExperimentResult:
        """
        1. Create initial population of experiment variants
           (different hyperparams, architectures, data splits)
        2. Run all in parallel (Upgrade 1)
        3. Evaluate with HCE (Upgrade 2)
        4. Select best, mutate, crossover
        5. Repeat until convergence or budget exhausted
        
        Temperature-scaled rank selection (AIRA2 Eq. 1):
        p(i) = (N - r_i + 1)^(1/T) / Σ(N - r_j + 1)^(1/T)
        """
```

### UPGRADE 8: Humanitarian Research Lens (P2)
**Source:** Tao & Klowden
**File:** `berb/writing/impact_assessment.py`

Every paper should address: does this advance understanding or just produce output?

```python
class HumanitarianImpactAssessment:
    """Tao/Klowden: AI tools should be viewed through BOTH technical
    and humanitarian lenses. Research should advance understanding."""
    
    async def assess_contribution_type(
        self, paper: GeneratedPaper
    ) -> ContributionAssessment:
        """Classify: does this paper...
        - Advance fundamental understanding? (highest value)
        - Provide useful tools/methods? (high value)
        - Confirm known results? (moderate value)
        - Generate text without insight? (low value — flag)
        """
    
    async def generate_broader_impact(
        self, paper: GeneratedPaper
    ) -> str:
        """Generate honest broader impact statement:
        - Who benefits from this research?
        - What are the risks?
        - How does this change what we UNDERSTAND?
        - Is this genuinely novel or incremental?
        """
```

### UPGRADE 9: CAID Branch-and-Merge for Paper Sections (P2)
**Source:** CAID
**File:** `berb/writing/parallel_writer.py`

Write paper sections in parallel using git-like isolation:

```python
class ParallelSectionWriter:
    """CAID-inspired: write paper sections in parallel with
    isolated workspaces and merge with verification."""
    
    async def write_sections_parallel(
        self, outline: PaperOutline
    ) -> GeneratedPaper:
        """
        1. Manager creates dependency-aware section plan
        2. Independent sections written in parallel
           (e.g., Methods + Related Work can be parallel)
        3. Dependent sections wait (Results depends on Methods)
        4. Integration: merge sections with coherence check
        5. Test: cross-reference verification (do Methods and Results match?)
        """
```

### UPGRADE 10: ReAct-Style Experiment Agents (P1)
**Source:** AIRA2
**File:** `berb/experiment/react_agent.py`

Replace fixed experiment scripts with ReAct agents that reason-act-observe:

```python
class ExperimentReActAgent:
    """AIRA2-style: experiment agent that iteratively reasons,
    executes code, observes output, and adapts."""
    
    async def run_experiment(
        self, design: ExperimentDesign
    ) -> ExperimentResult:
        """ReAct trajectory:
        Reason: "I need to implement X algorithm"
        Act: Write code, execute
        Observe: Check output, training curves
        Reason: "Loss is diverging — learning rate too high"
        Act: Reduce lr, re-run
        Observe: Loss converging now
        Reason: "Training time = 15min of 9hr budget, likely underfitting"
        Act: Scale up model, extend training
        ...
        Submit: Final results
        
        Key: dynamic scoping + interactive debugging
        within single experiment trajectory.
        """
```

### UPGRADE 11: Critique + Council Integration Points (P1)
**Source:** Microsoft Copilot Researcher
**File:** Update to existing M1 (cross-model review)

Add specific Critique and Council modes at pipeline decision points:

```yaml
# Config for where to use each pattern
multi_model:
  critique:  # Generation → Evaluation (different models)
    enabled: true
    stages: [17, 19]  # Paper draft + revision
    generator: "claude-sonnet"
    evaluator: "gpt-4o"
  
  council:  # Multiple independent analyses → synthesis
    enabled: true
    stages: [7, 8, 15]  # Synthesis, hypothesis, decision
    models: ["claude-opus", "gpt-4o", "deepseek-v3.2"]
    judge: "claude-sonnet"
```

### UPGRADE 12: Benchmark-Ready Evaluation Framework (P1)
**Source:** PRBench + HorizonMath + AIRA2
**File:** `berb/benchmarks/evaluation_framework.py`

Build Berb's evaluation against established benchmarks:

```python
class BerbBenchmarkFramework:
    """Evaluate Berb outputs against established research benchmarks."""
    
    async def evaluate_on_prbench(
        self, physics_tasks: list[str]
    ) -> PRBenchScore:
        """Run Berb on PRBench physics reproduction tasks.
        Compare output code + results against ground truth."""
    
    async def evaluate_paper_quality(
        self, papers: list[GeneratedPaper]
    ) -> DRACOScore:
        """Evaluate using DRACO framework:
        - Factual accuracy
        - Breadth and depth of analysis
        - Presentation quality
        - Citation quality
        """
    
    async def evaluate_mathematical_content(
        self, math_papers: list[GeneratedPaper]
    ) -> MathScore:
        """HorizonMath-inspired: verify mathematical claims
        computationally. Score = % of claims that verify."""
```

---

## Implementation Priority Matrix

| Upgrade | Source | Priority | Effort | Impact | Dependencies |
|---------|--------|----------|--------|--------|-------------|
| 1. Async Parallel Experiments | AIRA2+CAID | P0 | 3-4 days | 2-4× speedup | Docker |
| 2. Hidden Consistent Evaluation | AIRA2 | P0 | 2 days | Eliminates score gaming | M2 improvement loop |
| 3. Council Mode | MS Copilot | P1 | 2 days | Multi-perspective decisions | M1 cross-model |
| 4. FS-Based Literature | Long-Context | P1 | 2-3 days | 200-400 paper handling | SearXNG |
| 5. Physics Code Guards | PRBench | P1 | 1-2 days | -50% code failures | O2, O3 |
| 6. Verification-First Math | HorizonMath | P1 | 2-3 days | Verifiable theorems | O2 |
| 7. Evolutionary Experiment Search | AIRA2+Hive | P2 | 3-4 days | Better experiment results | Upgrade 1 |
| 8. Humanitarian Impact Lens | Tao/Klowden | P2 | 1 day | Research integrity | O7 |
| 9. Parallel Section Writing | CAID | P2 | 2 days | Faster paper generation | L3 |
| 10. ReAct Experiment Agents | AIRA2 | P1 | 3-4 days | Interactive debugging | Upgrade 1 |
| 11. Critique+Council Config | MS Copilot | P1 | 1 day | Better at decision points | M1 |
| 12. Benchmark Framework | PRBench+DRACO | P1 | 2-3 days | External validation | E1 |

---

## Key Architectural Insights

### From AIRA2: "No single component is a silver bullet, but each is critical"
Each of AIRA2's 3 components alone is insufficient. It's the INTERPLAY that works:
- Parallel compute without evolution = saturates at single-GPU performance
- Evolution without HCE = overfits (evaluation noise)
- HCE without ReAct agents = limited operator capability

**Berb implication:** Don't implement upgrades in isolation. The combination of async execution (1) + HCE (2) + ReAct agents (10) + cross-model review (M1) creates the same synergistic effect.

### From CAID: "Optimal parallelism is NOT maximum parallelism"
4 agents > 8 agents on most tasks. Over-delegation introduces integration overhead.

**Berb implication:** Default max_workers=4, not unlimited. Test empirically.

### From Microsoft: "Generation ≠ Evaluation" — now validated at enterprise scale
The Critique pattern (GPT generates, Claude evaluates) is the exact pattern in Berb's M1. Microsoft's DRACO results (+13.88%) provide independent validation.

**Berb implication:** M1 is correctly architected. Implement with confidence. Also add Council for synthesis/hypothesis stages.

### From Tao: "AI should advance understanding, not just produce output"
Research is not text generation. Berb must produce papers that contain genuine insight.

**Berb implication:** Every paper output should include a self-assessment of contribution type. The claim confidence system (N1) + claim integrity tracker (M4) + evidence consensus map (J4) together ensure Berb doesn't just produce text — it produces verified knowledge.

---

## Integration with Existing Implementation Prompt

These 12 upgrades map to existing groups as follows:

| Upgrade | Maps to Group | Action |
|---------|---------------|--------|
| 1 (Async Parallel) | M3 (Compute Guard) | Extend M3 with full async pool |
| 2 (HCE) | M2 (Improvement Loop) | Add HCE as sub-component |
| 3 (Council) | M1 (Cross-Model Review) | Add Council alongside Critique |
| 4 (FS Literature) | D1 (Citation Graph) | Add FS processing layer |
| 5 (Physics Guards) | O2 (Math Engine) | Add code quality guards |
| 6 (Verify Math) | O2 (Math Engine) | Add verification step |
| 7 (Evolutionary Search) | M2 (Improvement Loop) | Add evolutionary variant |
| 8 (Humanitarian Lens) | O7 (Environmental Impact) | Extend to broader impact |
| 9 (Parallel Sections) | O3/L3 (Writing/LaTeX) | Add parallel writing |
| 10 (ReAct Agents) | Stage 12 (EXPERIMENT_RUN) | Replace fixed scripts |
| 11 (Critique+Council Config) | M1 (Cross-Model Review) | Add config options |
| 12 (Benchmark Framework) | E1 (Benchmark Suite) | Add DRACO + PRBench |

---

**RECOMMENDATION:** Add these 12 upgrades as Group Q in the implementation prompt v9. They represent the latest research (March 2026) and are architecturally proven at scale (AIRA2, Microsoft, CAID).

**END OF OPTIMIZATION PLAN**
