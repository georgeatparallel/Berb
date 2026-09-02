# Πώς Λειτουργεί το Berb: Οδηγός Λειτουργίας

**Τελευταία Ενημέρωση:** 2026-03-27  
**Έκδοση:** 1.0.0 (P4+P5 Complete)

---

## 🎯 Επισκόπηση

Το **Berb** είναι ένα αυτόνομο σύστημα έρευνας που μετατρέπει μια ερευνητική ιδέα σε ακαδημαϊκή εργασία μέσω **23 σταδίων** σε **8 φάσεις**, με **μηδενική ανθρώπινη παρέμβαση**.

**Κύρια Καινοτομία:** Πλήρης αυτοματοποίηση έρευνας με δυνατότητες από την έρευνα του 2025-2026, με κόστος 30-50x χαμηλότερο από εναλλακτικές.

---

## 📊 Αρχιτεκτονική LLM Routing

### Μοντέλα που Υποστηρίζονται

```python
# Tier 1: Budget (Οικονομικά)
- gpt-4o-mini: $0.15/1M input, $0.60/1M output
- claude-3-haiku: $0.25/1M input, $1.25/1M output

# Tier 2: Mid (Ισορροπημένα)
- gpt-4o: $2.50/1M input, $10.00/1M output
- claude-3-sonnet: $3.00/1M input, $15.00/1M output

# Tier 3: Premium (Υψηλή Ποιότητα)
- o1: $15.00/1M input, $60.00/1M output
- claude-3-opus: $15.00/1M input, $75.00/1M output
```

### Κριτήρια Επιλογής LLM

```python
# berb/llm/model_router.py
def select_model(stage: Stage, complexity: float, budget_remaining: float):
    """
    Κριτήρια επιλογής:
    1. Στάδιο pipeline (κρίσιμο vs απλό)
    2. Πολυπλοκότητα εργασίας (0.0-1.0)
    3. Υπόλοιπο budget
    4. Ιστορικό επιτυχίας ανά μοντέλο/στάδιο
    """
```

---

## 🔄 Η Ροή των 23 Σταδίων

### **Φάση A: Research Scoping (Στάδια 1-2)**

#### **Στάδιο 1: TOPIC_INIT**
```
Είσοδος: "Your research topic"
LLM: gpt-4o-mini (Budget tier)
Κριτήριο: Απλή σύνοψη θέματος, δεν απαιτείται υψηλή ποιότητα
Έξοδος: Δομημένη περιγραφή θέματος
Tokens: ~1,000 output limit
```

#### **Στάδιο 2: PROBLEM_DECOMPOSE**
```
Είσοδος: Θέμα από Στάδιο 1
LLM: gpt-4o (Mid tier)
Κριτήριο: Απαιτείται δομημένο JSON, κρίσιμο για συνέχεια
Έξοδος: Δεντρική ανάλυση υπο-εργασιών
Tokens: ~2,000 output limit
Structured Output: DecompositionOutput (Pydantic)
```

---

### **Φάση B: Literature Discovery (Στάδια 3-6)**

#### **Στάδιο 3: SEARCH_STRATEGY**
```
Είσοδος: Υπο-εργασίες από Στάδιο 2
LLM: gpt-4o-mini (Budget tier)
Κριτήριο: Δημιουργία search queries, όχι κρίσιμο
Έξοδος: Λίστα search queries ανά πηγή
Tokens: ~1,500 output limit
```

#### **Στάδιο 4: LITERATURE_COLLECT**
```
Είσοδος: Search queries
LLM: ΔΕΝ καλεί LLM
Κριτήριο: Κλήση APIs (OpenAlex, Semantic Scholar, arXiv)
Έξοδος: ~50-100 papers με metadata
```

#### **Στάδιο 5: LITERATURE_SCREEN 🔒**
```
Είσοδος: Papers από Στάδιο 4
LLM: claude-3-sonnet (Mid tier)
Κριτήριο: Απαιτείται ακριβής αξιολόγηση ποιότητας
Έξοδος: Φιλτραρισμένα papers (20-30)
Tokens: ~2,000 output limit
Gate: Απαιτεί human approval (εκτός --auto-approve)
```

#### **Στάδιο 6: KNOWLEDGE_EXTRACT**
```
Είσοδος: Φιλτραρισμένα papers
LLM: gpt-4o (Mid tier)
Κριτήριο: Εξαγωγή knowledge cards με δομή
Έξοδος: Knowledge cards με findings
Tokens: ~2,500 output limit
```

---

### **Φάση C: Knowledge Synthesis (Στάδια 7-8)**

#### **Στάδιο 7: SYNTHESIS**
```
Είσοδος: Knowledge cards
LLM: claude-3-sonnet (Mid tier)
Κριτήριο: Σύνθεση ευρημάτων, identification gaps
Έξοδος: Synthesis report
Tokens: ~3,000 output limit
```

#### **Στάδιο 8: HYPOTHESIS_GEN**
```
Είσοδος: Synthesis report
LLM: claude-3-opus (Premium tier)
Κριτήριο: ΚΡΙΤΙΚΟ - Δημιουργία υποθέσεων, multi-agent debate
Έξοδος: 3-5 hypotheses με justification
Tokens: ~2,000 output limit
Structured Output: HypothesisOutput
Special: 4 parallel perspectives (Novelty, Feasibility, Impact, Clarity)
```

---

### **Φάση D: Experiment Design (Στάδια 9-11)**

#### **Στάδιο 9: EXPERIMENT_DESIGN 🔒**
```
Είσοδος: Hypotheses από Στάδιο 8
LLM: claude-3-opus (Premium tier)
Κριτήριο: ΚΡΙΤΙΚΟ - Σχεδιασμός πειράματος
Έξοδος: Πλήρες experiment protocol
Tokens: ~3,000 output limit
Structured Output: ExperimentDesignOutput
Gate: Human approval required
Special: Stress testing (3 scenarios: optimal/constraint/adversarial)
```

#### **Στάδιο 10: CODE_GENERATION**
```
Είσοδος: Experiment protocol
LLM: claude-3-sonnet (Mid tier) + OpenCode Beast Mode (optional)
Κριτήριο: Δημιουργία κώδικα, TDD-first approach
Έξοδος: Python code + tests
Tokens: ~6,000 output limit
Special: 
  - Αν complexity > 0.2 → OpenCode (multi-file projects)
  - Dependency context injection
  - Hard validation με max 4 repairs
```

#### **Στάδιο 11: RESOURCE_PLANNING**
```
Είσοδος: Κώδικας από Στάδιο 10
LLM: gpt-4o-mini (Budget tier)
Κριτήριο: Εκτίμηση resources, όχι κρίσιμο
Έξοδος: Resource estimates (χρόνος, κόστος, GPU)
Tokens: ~1,500 output limit
```

---

### **Φάση E: Experiment Execution (Στάδια 12-13)**

#### **Στάδιο 12: EXPERIMENT_RUN**
```
Είσοδος: Κώδικας + resources
LLM: ΔΕΝ καλεί LLM (κατά την εκτέλεση)
Κριτήριο: Εκτέλεση σε sandbox/Docker
Έξοδος: Results + metrics
Special:
  - AST validation πριν εκτέλεση
  - NaN/Inf fast-fail detection
  - Memory/CPU limits
```

#### **Στάδιο 13: ITERATIVE_REFINE**
```
Είσοδος: Results + errors (αν υπάρχουν)
LLM: gpt-4o (Mid tier)
Κριτήριο: Self-healing, fix errors
Έξοδος: Fixed code + new results
Tokens: ~2,000 output limit per iteration
Max Iterations: 10
Special:
  - Αν failure → Experiment Repair loop (berb/pipeline/experiment_diagnosis.py + experiment_repair.py)
  - Error classification (syntax/runtime/logic/resource)
  - Pattern-based fixes από knowledge base
```

---

### **Φάση F: Analysis & Decision (Στάδια 14-15)**

#### **Στάδιο 14: RESULT_ANALYSIS**
```
Είσοδος: Results από Στάδιο 12/13
LLM: claude-3-sonnet (Mid tier)
Κριτήριο: Multi-agent analysis
Έξοδος: Analysis report
Tokens: ~2,500 output limit
Special: Statistical significance testing
```

#### **Στάδιο 15: RESEARCH_DECISION**
```
Είσοδος: Analysis report
LLM: claude-3-opus (Premium tier)
Κριτήριο: ΚΡΙΤΙΚΟ - Απόφαση PROCEED/REFINE/PIVOT
Έξοδος: Decision με rationale
Tokens: ~1,000 output limit
Structured Output: ResearchDecisionOutput
Special: Structured critique scoring (6 dimensions)
```

---

### **Φάση G: Paper Writing (Στάδια 16-19)**

#### **Στάδιο 16: PAPER_OUTLINE**
```
Είσοδος: Decision + results
LLM: gpt-4o (Mid tier)
Κριτήριο: Δομή εργασίας
Έξοδος: Section outline
Tokens: ~2,000 output limit
```

#### **Στάδιο 17: PAPER_DRAFT**
```
Είσοδος: Outline + results
LLM: claude-3-opus (Premium tier)
Κριτήριο: ΚΡΙΤΙΚΟ - Full paper generation
Έξοδος: Full draft (5,000-6,500 words)
Tokens: ~8,000 output limit
Special:
  - Section-by-section generation
  - Citation injection από literature
  - LaTeX math support
```

#### **Στάδιο 18: PEER_REVIEW**
```
Είσοδος: Paper draft
LLM: 5x claude-3-sonnet (Mid tier) + 1x claude-3-opus (Area Chair)
Κριτήριο: 5-reviewer ensemble (NEW P4 feature)
Έξοδος: Reviews + meta-review
Tokens: ~800 output per reviewer
Special:
  - Reviewer 1: Novelty & Significance
  - Reviewer 2: Technical Correctness
  - Reviewer 3: Experimental Rigor
  - Reviewer 4: Clarity & Presentation
  - Reviewer 5: Reproducibility
  - Area Chair: Aggregation + acceptance recommendation
```

#### **Στάδιο 19: PAPER_REVISION**
```
Είσοδος: Paper + reviews
LLM: claude-3-sonnet (Mid tier)
Κριτήριο: Revision based on reviews
Έξοδος: Revised draft
Tokens: ~6,000 output limit
Special: Diff-based revisions (60-80% token reduction)
```

---

### **Φάση H: Finalization (Στάδια 20-23)**

#### **Στάδιο 20: QUALITY_GATE 🔒**
```
Είσοδος: Revised paper
LLM: claude-3-opus (Premium tier)
Κριτήριο: ΚΡΙΤΙΚΟ - Final quality check
Έξοδος: Pass/Fail + notes
Tokens: ~500 output limit
Gate: Human approval required
Special: 4-layer citation verification
```

#### **Στάδιο 21: KNOWLEDGE_ARCHIVE**
```
Είσοδος: Final paper
LLM: gpt-4o-mini (Budget tier)
Κριτήριο: Αρχειοθέτηση, όχι κρίσιμο
Έξοδος: Archive summary
Tokens: ~1,500 output limit
```

#### **Στάδιο 22: EXPORT_PUBLISH**
```
Είσοδος: Final paper
LLM: ΔΕΝ καλεί LLM
Κριτήριο: Export σε LaTeX/PDF
Έξοδος: paper.tex, references.bib
Templates: NeurIPS/ICML/ICLR
```

#### **Στάδιο 23: CITATION_VERIFY**
```
Είσοδος: References
LLM: gpt-4o (Mid tier) + APIs
Κριτήριο: 4-layer verification (NEW P4 feature)
Έξοδος: Verification report
Tokens: ~2,000 output limit
Layers:
  1. arXiv ID check
  2. CrossRef/DataCite DOI
  3. Semantic Scholar title match
  4. LLM relevance scoring
Special: Hallucination detection (berb/pipeline/hallucination_detector.py)
```

---

## 🧠 LLM Routing Logic

### Model Router (`berb/llm/model_router.py`)

```python
def route_llm_request(stage: Stage, context: dict) -> str:
    """
    Επιλογή μοντέλου βάσει:
    1. Stage criticality
    2. Task complexity score (0.0-1.0)
    3. Budget remaining
    4. Historical success rate per model/stage
    """
    
    # Critical stages → Premium
    CRITICAL_STAGES = {8, 9, 15, 17, 20}  # Hypothesis, Design, Decision, Draft, Gate
    
    if stage in CRITICAL_STAGES:
        return "claude-3-opus"
    
    # High complexity → Mid
    if context.get("complexity_score", 0) > 0.6:
        return "claude-3-sonnet"
    
    # Default → Budget
    return "gpt-4o-mini"
```

### Cost Optimization Strategies

```python
# 1. Output Token Limits (berb/llm/output_limits.py)
OUTPUT_TOKEN_LIMITS = {
    Stage.HYPOTHESIS_GEN: 2000,
    Stage.PAPER_DRAFT: 8000,
    Stage.PEER_REVIEW: 800,  # Concise reviews!
}

# 2. Model Cascading (berb/llm/model_cascade.py)
# Try cheap → expensive only if needed
cascade = ["gpt-4o-mini", "gpt-4o", "claude-3-opus"]

# 3. Prompt Caching (berb/llm/prompt_cache.py)
# Cache system prompts across parallel calls
cache_control = {"type": "ephemeral"}

# 4. Batch API (berb/llm/batch_api.py)
# Non-critical stages → batch API (50% cheaper)
NON_CRITICAL_STAGES = {5, 18, 20, 23}
```

---

## 💰 Κόστος Ανά Στάδιο (Παράδειγμα)

| Στάδιο | LLM | Input Tokens | Output Tokens | Cost |
|--------|-----|--------------|---------------|------|
| 1. TOPIC_INIT | gpt-4o-mini | 500 | 1,000 | $0.001 |
| 2. PROBLEM_DECOMPOSE | gpt-4o | 2,000 | 2,000 | $0.025 |
| 8. HYPOTHESIS_GEN | claude-3-opus | 5,000 | 2,000 | $0.225 |
| 9. EXPERIMENT_DESIGN | claude-3-opus | 8,000 | 3,000 | $0.345 |
| 17. PAPER_DRAFT | claude-3-opus | 15,000 | 8,000 | $0.825 |
| 18. PEER_REVIEW | 5x sonnet + 1x opus | 20,000 | 4,000 | $0.450 |
| **ΣΥΝΟΛΟ** | **Mixed** | **~50,000** | **~20,000** | **$0.40-0.70** |

---

## 🔑 Κρίσιμα Σημεία Απόφασης

### 1. **Gate Stages (🔒)**
- **Στάδιο 5:** Literature screening
- **Στάδιο 9:** Experiment design
- **Στάδιο 20:** Quality gate

Απαιτούν human approval (εκτός `--auto-approve`)

### 2. **Decision Points**
- **Στάδιο 15:** PROCEED / REFINE / PIVOT
  - PROCEED: Συνέχεια στο writing phase
  - REFINE: Πίσω στο Stage 13 (iterative refinement)
  - PIVOT: Πίσω στο Stage 8 (new hypotheses)

### 3. **Self-Healing**
- **Στάδιο 13:** Max 10 iterations
- **Στάδιο 10:** Max 4 repair cycles
- Αν αποτυχία → Automated Debugger

---

## 📊 Παράδειγμα Ροής

```
User Input: "CRISPR gene editing for rare diseases"
    ↓
Stage 1 (gpt-4o-mini): Topic summary
    ↓
Stage 2 (gpt-4o): Problem decomposition → 5 sub-tasks
    ↓
Stage 3 (gpt-4o-mini): Search queries
    ↓
Stage 4 (APIs): Collect 80 papers
    ↓
Stage 5 (claude-3-sonnet): Screen → 25 papers 🔒
    ↓
Stage 6 (gpt-4o): Extract knowledge cards
    ↓
Stage 7 (claude-3-sonnet): Synthesis report
    ↓
Stage 8 (claude-3-opus): 4 hypotheses ⭐
    ↓
Stage 9 (claude-3-opus): Experiment design 🔒
    ↓
Stage 10 (claude-3-sonnet + OpenCode): Code generation
    ↓
Stage 11 (gpt-4o-mini): Resource estimates
    ↓
Stage 12 (Sandbox): Execute experiment
    ↓
Stage 13 (gpt-4o): Fix errors (2 iterations)
    ↓
Stage 14 (claude-3-sonnet): Result analysis
    ↓
Stage 15 (claude-3-opus): Decision → PROCEED ⭐
    ↓
Stage 16 (gpt-4o): Paper outline
    ↓
Stage 17 (claude-3-opus): Full draft (6,000 words)
    ↓
Stage 18 (5x sonnet + 1x opus): Reviews
    ↓
Stage 19 (claude-3-sonnet): Revision
    ↓
Stage 20 (claude-3-opus): Quality gate 🔒
    ↓
Stage 21 (gpt-4o-mini): Archive
    ↓
Stage 22 (No LLM): Export LaTeX
    ↓
Stage 23 (gpt-4o + APIs): Citation verification
    ↓
OUTPUT: paper.tex + references.bib + verification_report.json
```

---

## 🎯 Συμπέρασμα

Το Berb χρησιμοποιεί **έξυπνο LLM routing** για βελτιστοποίηση κόστους-ποιότητας:

1. **Budget tier** (gpt-4o-mini): Απλές εργασίες (~40% σταδίων)
2. **Mid tier** (gpt-4o/claude-3-sonnet): Μέτριας πολυπλοκότητας (~40% σταδίων)
3. **Premium tier** (claude-3-opus): Κρίσιμες εργασίες (~20% σταδίων)

**Συνολικό κόστος:** $0.40-0.70 ανά εργασία (30-50x φθηνότερο από alternatives)

---

## 📚 Δομή Αρχείων

```
berb/
├── llm/
│   ├── model_router.py         # LLM routing logic
│   ├── output_limits.py        # Token limits per stage
│   ├── model_cascade.py        # Cheap→expensive cascading
│   ├── prompt_cache.py         # Provider prompt caching
│   └── batch_api.py            # Batch API for non-critical
├── pipeline/
│   ├── runner.py               # Main pipeline runner
│   ├── stages.py               # 23-stage state machine
│   ├── executor.py             # Stage execution engine
│   └── hallucination_detector.py # Citation verification
├── experiment/
│   ├── sandbox.py              # Local sandbox execution
│   ├── self_correcting.py      # MCP-SIM inspired self-healing
└── review/
    └── ensemble.py             # 5-reviewer + Area Chair
```

---

## 🔗 Σχετική Τεκμηρίωση

- **[README](../README.md)** — Κύρια επισκόπηση
- **[QWEN.md](../QWEN.md)** — Τεχνικό context
- **[docs/INDEX.md](../docs/INDEX.md)** — Ευρετήριο τεκμηρίωσης
- **[docs/P4_OPTIMIZATION_PLAN.md](../docs/P4_OPTIMIZATION_PLAN.md)** — Βελτιστοποιήσεις κόστους
- **[docs/P5_ENHANCEMENT_PLAN.md](../docs/P5_ENHANCEMENT_PLAN.md)** — Τελευταίες έρευνες

---

**Berb — Research, Refined.** 🧪✨
