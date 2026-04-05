# Berb — Comprehensive Enhancement Implementation Prompt

**Date:** 2026-03-29
**Version:** 7.0.0 Enhancement Specification (Complete — all sources + workflow system)
**Purpose:** Audit existing codebase, identify unimplemented features, implement all enhancements below.

---

## Instructions for Implementation Agent

You are implementing enhancements for **Berb**, an AI-powered autonomous research system that transforms a research idea into a conference-ready academic paper through a 23-stage pipeline.

### Workflow

1. **AUDIT FIRST:** Before writing any code, scan the entire `berb/` codebase. For each enhancement below, check if it exists (fully, partially, or not at all). Produce a status table:
   - ✅ Fully implemented — skip
   - 🔶 Partially implemented — identify gaps, complete
   - ❌ Not implemented — implement from scratch

2. **IMPLEMENT IN PRIORITY ORDER:** P0 → P1 → P2 → P3. Within each priority, follow the listed order.

3. **CODING STANDARDS:**
   - Python 3.12+, strict type hints everywhere
   - Pydantic v2 for data validation
   - asyncio for all I/O-bound operations
   - Mandatory error handling in every function
   - ruff for formatting
   - pytest + pytest-asyncio for tests
   - Every new module must include: docstring, type hints, error handling, at least 3 unit tests

4. **ARCHITECTURE PRINCIPLES:**
   - Hexagonal architecture: domain logic decoupled from infrastructure
   - Functional core / imperative shell separation
   - Clean layer boundaries between pipeline stages
   - Config-driven behavior (YAML/JSON, not hardcoded)
   - All new features must be toggleable via `config.berb.yaml`

5. **FILE STRUCTURE:** New modules go in their appropriate `berb/` subdirectory. Create new directories only when specified.

---

## ENHANCEMENT GROUP A: WORKFLOW & OPERATION MODE SYSTEM (P0)

### A1. Pipeline Workflow Types

**File:** `berb/modes/workflow.py`

The user selects WHAT they want, not HOW the pipeline works internally. Berb adapts its 23-stage pipeline to run only the relevant stages.

```python
class WorkflowType(str, Enum):
    # === Full Pipelines ===
    FULL_RESEARCH = "full-research"
    """End-to-end: topic → literature → hypothesis → experiments → paper.
    Runs all 23 stages. The default Berb experience."""
    
    LITERATURE_ONLY = "literature-only"
    """Literature search + synthesis only. No experiments, no paper.
    Outputs: structured bibliography, synthesis report, gap analysis, reading notes.
    Stages: 1-8 (Scoping + Literature + Synthesis + Hypothesis)"""
    
    PAPER_FROM_RESULTS = "paper-from-results"
    """User already has experiment results. Berb writes the paper.
    User uploads: data files, figures, experiment descriptions.
    Stages: 14-23 (Analysis + Writing + Finalization)"""
    
    EXPERIMENT_ONLY = "experiment-only"
    """Design and run experiments only. No paper writing.
    User provides: hypothesis + background context.
    Stages: 9-15 (Design + Execution + Analysis + Decision)"""
    
    REVIEW_ONLY = "review-only"
    """Review an existing paper/manuscript. Score + feedback + improvement suggestions.
    User uploads: manuscript PDF.
    Stages: 18 only (Peer Review) + M1 cross-model review"""
    
    REBUTTAL = "rebuttal"
    """Generate rebuttal letter from reviewer comments.
    User uploads: manuscript + reviewer comments.
    Uses: K4 Rebuttal Generator"""
    
    LITERATURE_REVIEW_PAPER = "literature-review"
    """Write a standalone literature review / survey paper.
    No experiments. Deep literature search + synthesis + paper writing.
    Stages: 1-8 + 16-23 (skip experiment stages)"""
    
    MATH_PAPER = "math-paper"
    """Paper with significant mathematical content.
    Includes: theorem/proof generation, equation typesetting, formal verification.
    All 23 stages + O2 mathematical content engine."""
    
    COMPUTATIONAL_PAPER = "computational-paper"
    """Paper with significant computational experiments.
    Emphasis on code quality, reproducibility, benchmark comparisons.
    All 23 stages + O3 pseudocode appendix + O4 code quality."""

class WorkflowConfig(BaseModel):
    workflow: WorkflowType = WorkflowType.FULL_RESEARCH
    enabled_stages: list[int] | None = None  # Auto-determined from workflow, or manual override
    
    # User-provided inputs
    uploaded_pdfs: list[Path] = []           # PDFs to include in literature (O1)
    uploaded_data: list[Path] = []           # Experiment data (for paper-from-results)
    uploaded_manuscript: Path | None = None  # For review-only / rebuttal
    uploaded_reviews: Path | None = None     # For rebuttal workflow
    
    # Component toggles (user chooses what they want)
    include_math: bool = False               # Enable mathematical content engine (O2)
    include_experiments: bool = True          # Enable experiment stages
    include_code_appendix: bool = False       # Generate pseudocode appendix (O3)
    include_supplementary: bool = True        # Generate supplementary materials (O5)
    
    # Operation mode (orthogonal to workflow)
    operation_mode: OperationMode = OperationMode.AUTONOMOUS
```

**Stage mapping per workflow:**
```python
WORKFLOW_STAGES: dict[WorkflowType, list[int]] = {
    WorkflowType.FULL_RESEARCH:          list(range(1, 24)),  # All 23
    WorkflowType.LITERATURE_ONLY:        [1, 2, 3, 4, 5, 6, 7, 8],
    WorkflowType.PAPER_FROM_RESULTS:     [14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
    WorkflowType.EXPERIMENT_ONLY:        [9, 10, 11, 12, 13, 14, 15],
    WorkflowType.REVIEW_ONLY:            [18],
    WorkflowType.REBUTTAL:               [],  # Custom pipeline, not stage-based
    WorkflowType.LITERATURE_REVIEW_PAPER: [1, 2, 3, 4, 5, 6, 7, 8, 16, 17, 18, 19, 20, 21, 22, 23],
    WorkflowType.MATH_PAPER:             list(range(1, 24)),  # All + math engine
    WorkflowType.COMPUTATIONAL_PAPER:    list(range(1, 24)),  # All + code appendix
}
```

**CLI:**
```bash
# Full research (default)
berb run --topic "..." --preset ml-conference

# Literature search only
berb literature --topic "neural architecture search" --preset ml-conference
berb literature --topic "..." --upload papers/*.pdf --min-papers 100

# Write paper from existing results
berb write --topic "..." --data results/ --figures figures/ --preset physics

# Run experiments only  
berb experiment --hypothesis "X improves Y by Z" --context background.md

# Review existing manuscript
berb review --manuscript paper.pdf --venue neurips

# Generate rebuttal
berb rebuttal --manuscript paper.pdf --reviews reviewer_comments.txt

# Literature review paper
berb survey --topic "transformer efficiency methods" --preset ml-conference

# Math-heavy paper
berb run --topic "..." --math --preset physics

# Computational paper with code appendix
berb run --topic "..." --code-appendix --preset engineering
```

### A2. Autonomous + Collaborative Mode System

**File:** `berb/modes/operation_mode.py`

The operation mode is **orthogonal** to the workflow type. Any workflow can be autonomous or collaborative.

```python
class OperationMode(str, Enum):
    AUTONOMOUS = "autonomous"      # Zero human intervention, full pipeline
    COLLABORATIVE = "collaborative" # Human-in-the-loop at decision points

class CollaborativeConfig(BaseModel):
    """Configuration for collaborative mode checkpoints."""
    pause_after_stages: list[int] = [2, 6, 8, 9, 15, 18]  # Default pause points
    approval_timeout_minutes: int = 60
    feedback_format: Literal["cli", "json", "api"] = "cli"
    allow_stage_skip: bool = False
    allow_hypothesis_edit: bool = True
    allow_experiment_override: bool = True
```

**Collaborative mode behavior:**
- After each configured stage, pipeline pauses and presents:
  - Summary of what was produced
  - Key decisions made and alternatives considered
  - Confidence scores per output
  - Explicit options: approve / edit / reject / add feedback / skip stage
- Human feedback is injected into the pipeline context for subsequent stages
- Feedback history persists in `audit_trail.json`
- Stage 8 (HYPOTHESIS_GEN): Researcher can reject/edit/add hypotheses
- Stage 9 (EXPERIMENT_DESIGN): Researcher can override experiment parameters
- Stage 15 (RESEARCH_DECISION): Researcher makes final go/no-go
- Stage 18 (PEER_REVIEW): Researcher sees reviews before revision

**Acceptance criteria:**
- Autonomous mode runs exactly as current pipeline (backward compatible)
- Collaborative mode pauses at configured stages, waits for input
- Feedback from human is injected into LLM context for subsequent stages
- `audit_trail.json` records all human decisions with timestamps

---

## ENHANCEMENT GROUP O: USER-PROVIDED SOURCES, MATH, CODE & SUPPLEMENTARY (P0-P1)

### O1. User-Uploaded PDF Integration (P0)

**File:** `berb/literature/user_sources.py`

Users can upload their own PDF collection to be included in the literature base:

```python
class UserSourceManager:
    """Integrate user-provided PDFs into the literature pipeline."""
    
    async def ingest_pdfs(
        self, pdf_paths: list[Path], 
        priority: Literal["primary", "supplementary"] = "primary"
    ) -> list[IngestedPaper]:
        """Process uploaded PDFs:
        1. Extract text (via Nemotron Parse / pymupdf / pdfplumber)
        2. Extract metadata (title, authors, year, DOI if available)
        3. Extract figures, tables, equations
        4. Generate structured reading notes (K3)
        5. Classify citation intent if citing known papers (J1)
        6. Add to literature database with priority flag
        
        Priority:
        - "primary": These papers MUST be cited in the final paper
        - "supplementary": Available for citation but not mandatory
        """
    
    async def ingest_bibtex(self, bib_path: Path) -> list[Paper]:
        """Import .bib file — metadata only, fetch PDFs if open access."""
    
    async def ingest_zotero_collection(
        self, collection_name: str
    ) -> list[IngestedPaper]:
        """Import from Zotero via MCP (if configured)."""
    
    async def ingest_mendeley_collection(
        self, collection_name: str
    ) -> list[IngestedPaper]:
        """Import from Mendeley export."""
    
    async def merge_with_search_results(
        self, user_papers: list[IngestedPaper],
        search_papers: list[Paper]
    ) -> list[Paper]:
        """Merge user uploads with search results.
        Deduplicate by DOI/title similarity.
        User papers get priority boost in relevance ranking.
        """
```

**CLI:**
```bash
# Upload specific PDFs
berb run --topic "..." --upload paper1.pdf paper2.pdf paper3.pdf

# Upload entire directory
berb run --topic "..." --upload-dir ~/research/papers/

# Upload BibTeX
berb run --topic "..." --bib references.bib

# Import from Zotero
berb run --topic "..." --zotero-collection "My Research"

# Mix: upload some + search for more
berb run --topic "..." --upload papers/ --min-papers 50
# → Berb uses uploaded papers + searches for 50 more
```

**Integration:**
- **Stage 3 (SEARCH_STRATEGY):** Account for user-provided papers in search planning
- **Stage 4 (LITERATURE_COLLECT):** User papers added first, then search fills gaps
- **Stage 5 (LITERATURE_SCREEN):** User "primary" papers auto-pass screening
- **Stage 6 (KNOWLEDGE_EXTRACT):** Full extraction from all papers (user + searched)

### O2. Mathematical Content Engine (P0)

**File:** `berb/math/math_engine.py`

For papers with significant mathematical content (proofs, theorems, derivations):

```python
class MathContentType(str, Enum):
    THEOREM = "theorem"
    LEMMA = "lemma"
    COROLLARY = "corollary"
    PROPOSITION = "proposition"
    DEFINITION = "definition"
    PROOF = "proof"
    DERIVATION = "derivation"
    EQUATION = "equation"
    ALGORITHM = "algorithm"

class MathematicalContentEngine:
    """Generate and verify mathematical content for research papers."""
    
    async def generate_theorem_proof(
        self,
        theorem_statement: str,
        context: str,  # Background mathematical framework
        proof_style: Literal["direct", "contradiction", "induction", "construction"] = "direct"
    ) -> TheoremProof:
        """Generate theorem statement + proof.
        
        Uses reasoning model (Claude Opus / GPT-4o) for mathematical reasoning.
        Output includes:
        - Formal theorem statement
        - Proof with step-by-step reasoning
        - Key lemmas required
        - LaTeX formatting
        """
    
    async def generate_derivation(
        self,
        starting_equation: str,
        target: str,  # What we're deriving
        assumptions: list[str]
    ) -> MathDerivation:
        """Generate step-by-step mathematical derivation.
        
        Each step includes:
        - Equation transformation
        - Justification (which rule/identity applied)
        - LaTeX for each step
        """
    
    async def verify_math_consistency(
        self, math_content: list[MathBlock]
    ) -> MathVerificationReport:
        """Cross-check mathematical content for:
        - Notation consistency (same symbol = same meaning throughout)
        - Dimensional analysis (units match across equations)
        - Logical flow (each step follows from previous)
        - Boundary conditions / edge cases
        - Numerical sanity checks (plug in known values)
        """
    
    async def generate_math_notation_table(
        self, math_content: list[MathBlock]
    ) -> str:
        """Generate 'Notation' table for paper:
        | Symbol | Description | First appears |
        | $\\alpha$ | Learning rate | Eq. 3 |
        """
    
    async def format_for_latex(
        self, math_content: list[MathBlock]
    ) -> str:
        """Convert all math to publication-ready LaTeX.
        Uses amsmath, amsthm environments.
        Numbered equations, theorem environments, etc.
        """

class MathBlock(BaseModel):
    content_type: MathContentType
    latex: str
    natural_language: str  # Plain English explanation
    dependencies: list[str]  # IDs of math blocks this depends on
    label: str  # For cross-referencing (e.g., "thm:convergence")
```

**Integration:**
- **Stage 9 (EXPERIMENT_DESIGN):** Mathematical formulation of the problem
- **Stage 10 (CODE_GENERATION):** Code implements the mathematical model
- **Stage 17 (PAPER_DRAFT):** Math blocks inserted with proper LaTeX formatting
- **Output:** Notation table auto-generated from used symbols

**Config:**
```yaml
math:
  enabled: true  # or --math flag
  proof_style: "rigorous"  # "rigorous" | "sketch" | "constructive"
  verify_consistency: true
  generate_notation_table: true
  equation_numbering: "section"  # "continuous" | "section" | "none"
  theorem_style: "plain"  # LaTeX theorem style
```

### O3. Pseudocode & Algorithm Appendix (P0)

**File:** `berb/writing/code_appendix.py`

When the paper involves computational methods, auto-generate pseudocode appendix:

```python
class PseudocodeGenerator:
    """Extract and format pseudocode from experiment code."""
    
    async def extract_from_code(
        self, code_files: dict[str, str],  # filename → source code
        focus_functions: list[str] | None = None  # Specific functions to document
    ) -> list[Algorithm]:
        """Extract key algorithms from implementation code.
        
        For each algorithm:
        1. Identify the core logic (strip boilerplate, logging, error handling)
        2. Convert to clean pseudocode (language-agnostic)
        3. Add line-by-line comments explaining key steps
        4. Add complexity analysis: time O(...), space O(...)
        5. Format in LaTeX algorithmic environment
        """
    
    async def generate_algorithm_block(
        self, algorithm: Algorithm
    ) -> str:
        """Generate LaTeX algorithm block:
        
        \\begin{algorithm}[H]
        \\caption{Our proposed method for X}
        \\label{alg:method}
        \\begin{algorithmic}[1]
        \\REQUIRE Input data $D$, parameters $\\theta$
        \\ENSURE Optimized model $M^*$
        \\STATE Initialize $\\theta_0$ randomly
        \\FOR{$t = 1$ to $T$}
            \\STATE Compute gradient $g_t = \\nabla L(\\theta_t)$
            \\STATE Update $\\theta_{t+1} = \\theta_t - \\alpha g_t$
        \\ENDFOR
        \\RETURN $\\theta_T$
        \\end{algorithmic}
        \\end{algorithm}
        """
    
    async def generate_appendix(
        self, algorithms: list[Algorithm],
        include_complexity: bool = True,
        include_implementation_notes: bool = True
    ) -> str:
        """Generate complete Appendix section:
        
        Appendix A: Algorithm Details
        A.1 Main Algorithm (Algorithm 1)
        A.2 Subroutine X (Algorithm 2)
        A.3 Complexity Analysis
        A.4 Implementation Notes
        """

class Algorithm(BaseModel):
    name: str
    description: str
    pseudocode_latex: str
    time_complexity: str  # e.g., "O(n log n)"
    space_complexity: str  # e.g., "O(n)"
    inputs: list[AlgorithmParam]
    outputs: list[AlgorithmParam]
    source_file: str  # Which code file this came from
    source_lines: tuple[int, int]  # Line range in source
```

**Integration:**
- **Stage 10 (CODE_GENERATION):** Tag key functions for pseudocode extraction
- **Stage 17 (PAPER_DRAFT):** Reference algorithms in methods section ("see Algorithm 1")
- **Stage 22 (EXPORT_PUBLISH):** Appendix auto-appended to paper
- **Output:** `appendix_algorithms.tex`

### O4. Code Quality & Reproducibility Appendix (P1)

**File:** `berb/writing/code_quality_appendix.py`

Beyond pseudocode, generate a code quality report for the appendix:

```python
class CodeQualityAppendix:
    """Generate supplementary material about code quality."""
    
    async def generate_reproducibility_section(
        self, code_dir: Path, experiments: list[Experiment]
    ) -> str:
        """Generate 'Reproducibility' appendix section:
        
        B.1 Software Environment
            - Python version, key library versions
            - Hardware specifications (GPU, memory)
            - Random seeds used
        
        B.2 Training Details
            - Hyperparameter table
            - Training curves (if available)
            - Wall-clock time per experiment
        
        B.3 Statistical Significance
            - Number of runs per experiment
            - Standard deviations
            - Statistical tests applied
        
        B.4 Code Availability
            - Repository URL (if public)
            - License
            - How to reproduce: step-by-step
        """
    
    async def generate_hyperparameter_table(
        self, experiments: list[Experiment]
    ) -> str:
        """LaTeX table of all hyperparameters used:
        | Hyperparameter | Value | Search Range | Selection Method |
        """
    
    async def generate_ablation_table(
        self, ablation_results: dict
    ) -> str:
        """LaTeX table of ablation study results."""
```

### O5. Supplementary Materials Generator (P1)

**File:** `berb/writing/supplementary.py`

Auto-generate supplementary materials that accompany the main paper:

```python
class SupplementaryGenerator:
    """Generate standard supplementary material sections."""
    
    async def generate_full_supplementary(
        self, paper: GeneratedPaper, config: SupplementaryConfig
    ) -> SupplementaryMaterial:
        """Generate complete supplementary document:
        
        Appendix A: Mathematical Proofs (from O2)
            - Full proofs for theorems sketched in main paper
            - Additional lemmas
            - Derivation details
        
        Appendix B: Algorithm Details (from O3)
            - Pseudocode for all algorithms
            - Complexity analysis
            - Implementation notes
        
        Appendix C: Experimental Details (from O4)
            - Hyperparameter tables
            - Training details
            - Reproducibility instructions
        
        Appendix D: Additional Results
            - Extended result tables
            - Additional figures
            - Ablation studies not in main paper
            - Error analysis / failure cases
        
        Appendix E: Dataset Details
            - Data statistics
            - Preprocessing steps
            - Data splits
            - License / ethical considerations
        
        Appendix F: Broader Impact Statement
            - Potential positive societal impacts
            - Potential negative impacts
            - Mitigation strategies
            - Environmental cost (compute used, CO2 estimate)
        """

class SupplementaryConfig(BaseModel):
    include_proofs: bool = True
    include_algorithms: bool = True
    include_experimental_details: bool = True
    include_additional_results: bool = True
    include_dataset_details: bool = True
    include_broader_impact: bool = True
    include_environmental_cost: bool = True  # CO2 estimation from compute
    max_supplementary_pages: int = 30
```

### O6. Figure & Table Auto-Generation (P1)

**File:** `berb/writing/figure_table_gen.py`

Auto-generate publication-quality figures and tables from experiment data:

```python
class FigureTableGenerator:
    """Generate publication-ready figures and tables."""
    
    async def generate_result_table(
        self, results: dict, 
        format: Literal["comparison", "ablation", "dataset_stats"],
        highlight_best: bool = True,
        significance_markers: bool = True  # *, **, *** for p-values
    ) -> str:
        """LaTeX table with:
        - Bold best results per column
        - ± std notation
        - Significance markers
        - Proper alignment and formatting
        """
    
    async def generate_figure(
        self, data: dict,
        figure_type: Literal[
            "line_plot", "bar_chart", "scatter", "heatmap",
            "confusion_matrix", "training_curve", "ablation_plot",
            "box_plot", "violin", "architecture_diagram"
        ],
        style: Literal["neurips", "nature", "ieee", "default"] = "default"
    ) -> tuple[Path, str]:  # (figure_path, LaTeX include code)
        """Generate matplotlib/seaborn figure with venue-specific styling.
        
        Returns figure file + LaTeX \\includegraphics code.
        Venue styles: font sizes, color palettes, figure widths.
        """
    
    async def generate_architecture_diagram(
        self, description: str
    ) -> tuple[Path, str]:
        """Generate system/model architecture diagram using tikz or matplotlib."""

    async def generate_comparison_radar(
        self, methods: dict[str, dict[str, float]]
    ) -> tuple[Path, str]:
        """Radar/spider chart comparing methods across multiple metrics."""
```

### O7. Environmental Impact Statement (P2)

**File:** `berb/writing/environmental_impact.py`

Track and report the computational cost of the research:

```python
class EnvironmentalImpactTracker:
    """Track and report environmental cost of research."""
    
    async def estimate_co2(
        self, 
        gpu_hours: float,
        gpu_model: str = "A100",
        region: str = "us-east"  # Electricity grid carbon intensity
    ) -> CO2Estimate:
        """Estimate CO2 emissions from compute.
        
        Based on: Strubell et al. (2019) methodology + 
        updated grid carbon intensities from electricitymap.org
        """
    
    async def generate_impact_statement(
        self, 
        co2: CO2Estimate,
        total_api_cost: float,
        total_compute_hours: float
    ) -> str:
        """Generate broader impact / environmental statement:
        
        'This research consumed approximately X GPU-hours on [hardware],
        corresponding to an estimated Y kg CO2e (equivalent to Z km 
        driven by an average car). The total API cost was $W.'
        """
```

### O8. Related Work Auto-Positioning (P1)

**File:** `berb/writing/related_work.py`

Generate a "Related Work" section that properly positions the paper relative to existing literature:

```python
class RelatedWorkGenerator:
    """Generate structured Related Work section."""
    
    async def generate(
        self,
        paper_contribution: str,
        literature: list[Paper],
        citation_classifications: list[CitationClassification],  # From J1
        evidence_map: list[ClaimEvidence],  # From J4
        gap_analysis: list[ResearchGap]  # From K1
    ) -> str:
        """Generate Related Work with proper academic structure:
        
        1. Identify 3-5 thematic clusters in the related work
        2. For each cluster:
           - Summarize the approach of key papers
           - Identify what they don't address (→ our contribution)
           - Use citation intelligence to show support/contrast patterns
        3. Final paragraph: explicit positioning of OUR work
           - "Unlike [X] which focuses on A, our approach addresses B"
           - "Building on the work of [Y], we extend to C"
           - "In contrast to [Z], we demonstrate D"
        
        Anti-patterns to avoid:
        - "Laundry list" of papers without thematic organization
        - Citing without comparing/contrasting
        - Ignoring work that contradicts our approach
        """
```

---

## ENHANCEMENT GROUP B: WRITING STYLE MIMICRY (P0)

### B1. Style Fingerprinting Engine

**File:** `berb/writing/style_fingerprint.py`

Before paper writing (Stage 16-17), Berb must:

1. **Identify the top 3 most-cited native-language speakers** in the target domain:
   - Query Semantic Scholar / OpenAlex for top-cited authors in the domain
   - Filter for native speakers of the paper's target language (use author affiliation country + name heuristics + publication language history)
   - If target language is English: find native English speakers (US/UK/AU/CA affiliations)
   - If target language is Greek: find Greek-affiliated researchers
   - Fallback: use top 3 most-cited authors regardless of language if native speaker filter yields < 3

2. **Extract writing style fingerprint** from their top 5 most-cited papers each:
   - Sentence length distribution (mean, std, min, max)
   - Paragraph structure patterns (sentences per paragraph)
   - Vocabulary complexity (Flesch-Kincaid, academic word frequency)
   - Hedging patterns ("we suggest", "results indicate" vs "we prove", "clearly shows")
   - Section length ratios (intro:methods:results:discussion)
   - Citation density per section
   - Passive vs active voice ratio
   - Transition word patterns
   - Use of first person ("we") vs impersonal constructions
   - Discipline-specific phrasing patterns

3. **Build composite style profile:**

```python
class StyleFingerprint(BaseModel):
    """Composite writing style extracted from top authors."""
    source_authors: list[AuthorProfile]  # Who we learned from
    avg_sentence_length: float
    sentence_length_std: float
    avg_paragraph_sentences: float
    vocabulary_level: Literal["accessible", "moderate", "dense", "expert"]
    hedging_frequency: float  # 0.0 = assertive, 1.0 = heavily hedged
    passive_voice_ratio: float
    first_person_usage: Literal["never", "rare", "moderate", "frequent"]
    section_ratios: dict[str, float]  # intro: 0.15, methods: 0.30, etc.
    citation_density: float  # citations per 100 words
    transition_patterns: list[str]  # Most common transition phrases
    characteristic_phrases: list[str]  # Domain-specific patterns
    sample_paragraphs: list[str]  # 5 exemplar paragraphs for few-shot
```

4. **Inject into writing prompts:**
   - Stage 16 (PAPER_OUTLINE): Style profile determines section proportions
   - Stage 17 (PAPER_DRAFT): Each section prompt includes style constraints + 2-3 exemplar paragraphs as few-shot examples
   - Stage 19 (PAPER_REVISION): Post-revision style conformance check

**Config:**
```yaml
writing:
  style_mimicry:
    enabled: true
    num_target_authors: 3
    papers_per_author: 5
    target_language: "auto"  # auto-detect from topic or explicit
    style_weight: 0.8  # 0.0 = ignore style, 1.0 = strict mimicry
    fallback_style: "nature"  # Use Nature journal style if authors unavailable
```

**Acceptance criteria:**
- Given topic "quantum computing error correction", system identifies 3 top-cited native English speakers in QC
- Style fingerprint extracted from 15 papers total
- Generated paper exhibits measurably similar sentence length, hedging patterns, and section ratios
- Style conformance score reported in output metrics

---

## ENHANCEMENT GROUP C: DOMAIN-SPECIFIC PRESETS (P0)

### C1. Preset System Architecture

**File:** `berb/presets/base.py`, `berb/presets/registry.py`

```python
class PipelinePreset(BaseModel):
    """Complete configuration preset for a research domain."""
    name: str
    description: str
    
    # Search configuration
    primary_sources: list[str]  # ["openalex", "semantic_scholar", "pubmed", ...]
    search_engines: list[str]  # SearXNG engine overrides
    grey_sources: list[str]  # Grey literature sources
    full_text_access: list[str]  # ["arxiv", "pmc", "unpaywall", ...]
    
    # Model routing
    primary_model: str
    fallback_models: list[str]
    reasoning_model: str  # For hypothesis generation, analysis
    budget_model: str  # For formatting, simple tasks
    
    # Pipeline behavior
    enabled_stages: list[int]  # Which stages to run (default: all 23)
    stage_overrides: dict[int, dict]  # Per-stage config overrides
    
    # Experiment configuration  
    experiment_mode: Literal["simulated", "sandbox", "docker", "ssh_remote", "colab_drive"]
    experiment_frameworks: list[str]  # ["pytorch", "jax", "scipy", ...]
    validation_methods: list[str]  # ["statistical", "numerical", "qualitative", ...]
    
    # Writing configuration
    paper_format: str  # "neurips", "acl", "nature", "ieee", "apa", "custom"
    target_venue: str | None
    max_pages: int
    style_profile: str | None  # Pre-built style or "auto"
    citation_style: str  # "numeric", "author-year", "footnote"
    
    # Quality thresholds
    min_literature_papers: int
    min_quality_score: float
    min_novelty_score: float
    
    # Budget
    max_budget_usd: float
    cost_optimization: Literal["aggressive", "balanced", "quality-first"]
```

### C2. Preset Definitions

**File:** `berb/presets/catalog/` — One YAML file per preset.

#### Machine Learning Conference (`ml-conference.yaml`)
```yaml
name: ml-conference
description: "Optimized for top ML venues (NeurIPS, ICML, ICLR, AAAI)"

primary_sources: ["semantic_scholar", "openalex", "arxiv"]
search_engines: ["arxiv", "google_scholar", "dblp"]
grey_sources: ["arxiv_preprints", "openreview", "github"]
full_text_access: ["arxiv", "openreview"]

primary_model: "claude-sonnet-4.6"
fallback_models: ["gpt-4o", "deepseek-v3.2"]
reasoning_model: "claude-opus-4.6"
budget_model: "gemini-2.5-flash"

experiment_mode: "docker"
experiment_frameworks: ["pytorch", "jax", "numpy"]
validation_methods: ["statistical", "ablation", "baseline_comparison"]

paper_format: "neurips"
target_venue: null  # User specifies
max_pages: 10
style_profile: "auto"
citation_style: "numeric"

min_literature_papers: 40
min_quality_score: 8.0
min_novelty_score: 7.0

max_budget_usd: 1.50
cost_optimization: "balanced"

stage_overrides:
  8:  # HYPOTHESIS_GEN
    reasoning_method: "multi_perspective"
    num_hypotheses: 5
  9:  # EXPERIMENT_DESIGN
    require_ablation: true
    require_baselines: ["random", "simple_heuristic", "sota"]
  12: # EXPERIMENT_RUN
    max_runtime_hours: 4
    gpu_required: true
  18: # PEER_REVIEW
    review_format: "neurips"
    num_reviewers: 5
```

#### Biomedical Research (`biomedical.yaml`)
```yaml
name: biomedical
description: "Clinical research, drug discovery, genomics, epidemiology"

primary_sources: ["pubmed", "semantic_scholar", "openalex"]
search_engines: ["pubmed", "google_scholar", "clinicaltrials_gov", "who_ictrp"]
grey_sources: ["medrxiv", "biorxiv", "clinicaltrials", "who_reports"]
full_text_access: ["pmc", "unpaywall", "biorxiv"]

primary_model: "claude-sonnet-4.6"
fallback_models: ["gpt-4o", "gemini-2.5-pro"]
reasoning_model: "claude-opus-4.6"
budget_model: "gemini-2.5-flash"

experiment_mode: "simulated"  # Most biomedical is computational analysis
experiment_frameworks: ["scipy", "statsmodels", "lifelines", "scanpy"]
validation_methods: ["statistical", "cross_validation", "sensitivity_analysis", "meta_analysis"]

paper_format: "nature"
max_pages: 15
style_profile: "auto"
citation_style: "numeric"

min_literature_papers: 60
min_quality_score: 8.5
min_novelty_score: 6.5

max_budget_usd: 2.00
cost_optimization: "quality-first"

stage_overrides:
  5:  # LITERATURE_SCREEN
    require_prisma: true  # PRISMA flow diagram
    screen_criteria: ["study_type", "population", "intervention", "outcome"]
  9:  # EXPERIMENT_DESIGN
    require_power_analysis: true
    require_ethics_statement: true
  14: # RESULT_ANALYSIS
    require_effect_sizes: true
    require_confidence_intervals: true
  18: # PEER_REVIEW
    review_format: "consort"  # For clinical studies
```

#### Natural Language Processing (`nlp.yaml`)
```yaml
name: nlp
description: "Computational linguistics, LLM research, text analysis"

primary_sources: ["semantic_scholar", "acl_anthology", "arxiv"]
search_engines: ["arxiv", "acl_anthology", "google_scholar"]
grey_sources: ["arxiv_preprints", "huggingface_papers", "github"]
full_text_access: ["arxiv", "acl_anthology"]

primary_model: "claude-sonnet-4.6"
fallback_models: ["gpt-4o", "deepseek-v3.2"]
reasoning_model: "claude-opus-4.6"
budget_model: "qwen3-turbo"

experiment_mode: "docker"
experiment_frameworks: ["pytorch", "transformers", "datasets", "evaluate"]
validation_methods: ["benchmark_comparison", "human_evaluation", "statistical"]

paper_format: "acl"
max_pages: 8  # ACL long paper
style_profile: "auto"
citation_style: "author-year"

min_literature_papers: 35
min_quality_score: 7.5
min_novelty_score: 7.5

max_budget_usd: 1.50
cost_optimization: "balanced"

stage_overrides:
  8:
    require_multilingual_consideration: true
  9:
    require_baselines: ["fine_tuned_bert", "gpt_baseline", "few_shot"]
    require_multiple_datasets: true
    min_datasets: 3
  12:
    huggingface_hub_integration: true
```

#### Computer Vision (`computer-vision.yaml`)
```yaml
name: computer-vision
description: "Image/video recognition, generation, 3D vision, medical imaging"

primary_sources: ["semantic_scholar", "arxiv", "openalex"]
search_engines: ["arxiv", "google_scholar", "papers_with_code"]
grey_sources: ["arxiv_preprints", "papers_with_code", "github"]
full_text_access: ["arxiv"]

primary_model: "claude-sonnet-4.6"
fallback_models: ["gpt-4o", "gemini-2.5-pro"]
reasoning_model: "claude-opus-4.6"
budget_model: "gemini-2.5-flash"

experiment_mode: "docker"
experiment_frameworks: ["pytorch", "torchvision", "timm", "detectron2"]
validation_methods: ["benchmark_comparison", "ablation", "qualitative_visualization"]

paper_format: "cvpr"
max_pages: 8
citation_style: "numeric"

min_literature_papers: 40
min_quality_score: 8.0
min_novelty_score: 7.0

max_budget_usd: 2.50
cost_optimization: "balanced"

stage_overrides:
  9:
    require_baselines: ["resnet", "vit_base", "sota_specific"]
    require_flops_comparison: true
  12:
    gpu_required: true
    max_runtime_hours: 8
  17:
    require_qualitative_figures: true
    min_figure_count: 4
```

#### Physics / Computational Science (`physics.yaml`)
```yaml
name: physics
description: "Computational physics, chaos theory, dynamical systems, simulations"

primary_sources: ["arxiv", "openalex", "semantic_scholar"]
search_engines: ["arxiv", "inspire_hep", "google_scholar", "ads_nasa"]
grey_sources: ["arxiv_preprints", "zenodo", "cern_documents"]
full_text_access: ["arxiv"]

primary_model: "claude-sonnet-4.6"
fallback_models: ["deepseek-v3.2", "gpt-4o"]
reasoning_model: "claude-opus-4.6"
budget_model: "gemini-2.5-flash"

experiment_mode: "docker"
experiment_frameworks: ["scipy", "numpy", "sympy", "numba", "matplotlib"]
validation_methods: ["numerical_convergence", "conservation_law_check", "benchmark_systems", "analytical_comparison"]

paper_format: "revtex"  # Physical Review format
max_pages: 12
citation_style: "numeric"

min_literature_papers: 30
min_quality_score: 8.5
min_novelty_score: 7.0

max_budget_usd: 1.00
cost_optimization: "balanced"

stage_overrides:
  9:
    require_convergence_test: true
    require_error_analysis: true
    numerical_precision: "double"
  12:
    self_correcting_enabled: true  # MCP-SIM style
    physics_aware_diagnosis: true
  14:
    require_error_bars: true
    require_units_check: true
```

#### Social Sciences (`social-sciences.yaml`)
```yaml
name: social-sciences
description: "Psychology, sociology, political science, economics, education"

primary_sources: ["semantic_scholar", "openalex", "jstor"]
search_engines: ["google_scholar", "jstor", "ssrn", "eric"]
grey_sources: ["ssrn_preprints", "nber_working_papers", "world_bank_reports", "oecd_papers"]
full_text_access: ["unpaywall", "ssrn"]

primary_model: "claude-sonnet-4.6"
fallback_models: ["gpt-4o", "deepseek-v3.2"]
reasoning_model: "claude-opus-4.6"
budget_model: "gemini-2.5-flash"

experiment_mode: "sandbox"
experiment_frameworks: ["statsmodels", "scipy", "pandas", "sklearn"]
validation_methods: ["statistical", "robustness_checks", "sensitivity_analysis", "qualitative_coding"]

paper_format: "apa"
max_pages: 30  # APA tends to be longer
citation_style: "author-year"

min_literature_papers: 50
min_quality_score: 7.5
min_novelty_score: 6.0

max_budget_usd: 1.50
cost_optimization: "balanced"

stage_overrides:
  5:
    screen_criteria: ["study_design", "sample_size", "methodology", "relevance"]
  9:
    require_irb_statement: true
    require_power_analysis: true
    statistical_framework: "frequentist"  # or "bayesian"
  14:
    require_effect_sizes: true
    require_multiple_comparisons_correction: true
  17:
    require_limitations_section: true
    require_implications_section: true
```

#### Systematic Review / Meta-Analysis (`systematic-review.yaml`)
```yaml
name: systematic-review
description: "PRISMA-compliant systematic reviews and meta-analyses"

primary_sources: ["pubmed", "semantic_scholar", "openalex", "cochrane"]
search_engines: ["pubmed", "cochrane", "embase", "google_scholar", "web_of_science"]
grey_sources: ["clinicaltrials", "who_ictrp", "opengrey", "conference_proceedings"]
full_text_access: ["pmc", "unpaywall"]

primary_model: "claude-sonnet-4.6"
fallback_models: ["gpt-4o"]
reasoning_model: "claude-opus-4.6"
budget_model: "gemini-2.5-flash"

experiment_mode: "sandbox"
experiment_frameworks: ["metafor_r", "meta_python", "scipy"]
validation_methods: ["risk_of_bias", "funnel_plot", "sensitivity_analysis", "leave_one_out"]

paper_format: "prisma"
max_pages: 20
citation_style: "numeric"

min_literature_papers: 100
min_quality_score: 9.0
min_novelty_score: 5.0  # Reviews don't need high novelty

max_budget_usd: 3.00
cost_optimization: "quality-first"

enabled_stages: [1, 2, 3, 4, 5, 6, 7, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
# Skip: 8 (hypothesis), 9-11 (experiment design), 12-13 (experiment execution)

stage_overrides:
  3:  # SEARCH_STRATEGY
    require_prisma_protocol: true
    require_boolean_queries: true
    min_databases: 3
  5:  # LITERATURE_SCREEN
    dual_screening: true  # Two independent screens
    require_kappa_agreement: true
  6:  # KNOWLEDGE_EXTRACT
    structured_extraction_form: true
    risk_of_bias_tool: "rob2"  # Cochrane RoB 2
  14: # RESULT_ANALYSIS
    require_forest_plot: true
    require_heterogeneity_test: true
    require_subgroup_analysis: true
```

#### Engineering / Applied CS (`engineering.yaml`)
```yaml
name: engineering
description: "Systems engineering, distributed systems, databases, networking"

primary_sources: ["semantic_scholar", "openalex", "arxiv", "ieee"]
search_engines: ["google_scholar", "ieee_xplore", "acm_dl", "arxiv"]
grey_sources: ["arxiv_preprints", "rfc_documents", "github", "company_blogs"]
full_text_access: ["arxiv", "acm_open"]

primary_model: "claude-sonnet-4.6"
fallback_models: ["deepseek-v3.2", "gpt-4o"]
reasoning_model: "claude-opus-4.6"
budget_model: "qwen3-turbo"

experiment_mode: "docker"
experiment_frameworks: ["pytest", "locust", "docker_compose", "kubernetes"]
validation_methods: ["benchmark_comparison", "load_testing", "fault_injection", "latency_analysis"]

paper_format: "acm"
max_pages: 12
citation_style: "numeric"

min_literature_papers: 30
min_quality_score: 8.0
min_novelty_score: 7.0

max_budget_usd: 1.50
cost_optimization: "balanced"

stage_overrides:
  9:
    require_system_architecture_diagram: true
    require_failure_mode_analysis: true
  12:
    reproducible_environment: "docker-compose"
    require_benchmarks: true
  17:
    require_system_diagram: true
    require_performance_table: true
```

#### Humanities / Qualitative (`humanities.yaml`)
```yaml
name: humanities
description: "Philosophy, history, literary criticism, cultural studies, qualitative research"

primary_sources: ["openalex", "jstor", "semantic_scholar"]
search_engines: ["google_scholar", "jstor", "philpapers", "project_muse"]
grey_sources: ["ssrn_preprints", "academia_edu", "hathitrust"]
full_text_access: ["unpaywall", "jstor_open"]

primary_model: "claude-opus-4.6"  # Reasoning-heavy
fallback_models: ["gpt-4o", "claude-sonnet-4.6"]
reasoning_model: "claude-opus-4.6"
budget_model: "gemini-2.5-flash"

experiment_mode: "sandbox"
experiment_frameworks: ["nltk", "spacy", "pandas"]
validation_methods: ["thematic_analysis", "discourse_analysis", "close_reading"]

paper_format: "chicago"
max_pages: 30
citation_style: "footnote"

min_literature_papers: 30
min_quality_score: 8.0
min_novelty_score: 6.0

max_budget_usd: 2.00
cost_optimization: "quality-first"

enabled_stages: [1, 2, 3, 4, 5, 6, 7, 8, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
# Skip experiment execution stages (computational not primary here)

stage_overrides:
  7:  # SYNTHESIS
    reasoning_method: "dialectical"
    require_theoretical_framework: true
  8:  # HYPOTHESIS_GEN  
    output_type: "thesis_argument"  # Not hypothesis per se
    reasoning_method: "socratic"
  17: # PAPER_DRAFT
    writing_style: "argumentative"
    require_theoretical_grounding: true
    allow_first_person: true
```

#### EU Sovereign / GDPR-Compliant (`eu-sovereign.yaml`)
```yaml
name: eu-sovereign
description: "Research with European data sovereignty and GDPR compliance"

primary_sources: ["openalex", "semantic_scholar"]
search_engines: ["google_scholar", "base_bielefeld", "core_ac_uk"]
grey_sources: ["zenodo", "eu_publications", "hal_archives"]
full_text_access: ["unpaywall", "core", "zenodo"]

primary_model: "mistral-large-3"  # EU-hosted
fallback_models: ["qwen3-max", "deepseek-v3.2"]
reasoning_model: "mistral-large-3"
budget_model: "qwen3-turbo"

experiment_mode: "docker"

paper_format: "custom"
max_pages: 15
citation_style: "numeric"

min_literature_papers: 40
min_quality_score: 8.0
min_novelty_score: 6.5

max_budget_usd: 1.50
cost_optimization: "balanced"

stage_overrides:
  1:
    gdpr_compliance: true
    data_processing_agreement: true
  9:
    require_privacy_impact_assessment: true
  17:
    require_data_availability_statement: true
    require_ethics_statement: true
```

#### Rapid Prototype / Quick Draft (`rapid-draft.yaml`)
```yaml
name: rapid-draft
description: "Fast, cheap first draft for brainstorming — not publication-ready"

primary_sources: ["semantic_scholar"]
search_engines: ["google_scholar"]
grey_sources: []
full_text_access: ["arxiv"]

primary_model: "deepseek-v3.2"
fallback_models: ["qwen3-turbo"]
reasoning_model: "deepseek-v3.2"
budget_model: "qwen3-turbo"

experiment_mode: "simulated"

paper_format: "markdown"
max_pages: 6
citation_style: "author-year"

min_literature_papers: 10
min_quality_score: 5.0
min_novelty_score: 3.0

max_budget_usd: 0.15
cost_optimization: "aggressive"

enabled_stages: [1, 2, 3, 4, 5, 6, 7, 8, 16, 17, 22]
# Skip: experiment execution, peer review, quality gate

stage_overrides:
  4:
    max_papers: 15
  17:
    draft_quality: "exploratory"
    skip_revision: true
```

#### Budget-Optimized (`budget.yaml`)
```yaml
name: budget
description: "Maximum quality per dollar — $0.15-0.25 per paper"

primary_sources: ["semantic_scholar", "openalex"]
search_engines: ["google_scholar", "arxiv"]
full_text_access: ["arxiv"]

primary_model: "deepseek-v3.2"
fallback_models: ["qwen3-turbo", "glm-4.5"]
reasoning_model: "deepseek-v3.2"
budget_model: "qwen3-turbo"

experiment_mode: "sandbox"

max_budget_usd: 0.25
cost_optimization: "aggressive"

min_literature_papers: 20
min_quality_score: 7.0
```

#### Maximum Quality (`max-quality.yaml`)
```yaml
name: max-quality
description: "Best possible output — cost is secondary"

primary_sources: ["semantic_scholar", "openalex", "pubmed", "arxiv"]
search_engines: ["google_scholar", "arxiv", "pubmed", "dblp"]
grey_sources: ["arxiv_preprints", "openreview", "ssrn", "github"]

primary_model: "claude-opus-4.6"
fallback_models: ["gpt-4o", "claude-sonnet-4.6"]
reasoning_model: "claude-opus-4.6"
budget_model: "claude-sonnet-4.6"

experiment_mode: "docker"

max_budget_usd: 5.00
cost_optimization: "quality-first"

min_literature_papers: 80
min_quality_score: 9.0
min_novelty_score: 8.0

stage_overrides:
  8:
    reasoning_method: "multi_perspective"
    num_hypotheses: 8
  12:
    max_iterations: 10
    self_correcting_enabled: true
  18:
    num_reviewers: 7
    review_rounds: 2
```

#### Research-Grounded / Search-Heavy (`research-grounded.yaml`)
```yaml
name: research-grounded
description: "Maximum literature coverage with search-augmented reasoning"

primary_sources: ["semantic_scholar", "openalex", "pubmed", "arxiv"]
search_engines: ["google_scholar", "arxiv", "pubmed", "base_bielefeld", "core_ac_uk"]
grey_sources: ["arxiv_preprints", "openreview", "ssrn", "zenodo", "conference_proceedings"]

primary_model: "sonar-pro"  # Perplexity — search-native
fallback_models: ["claude-sonnet-4.6", "gpt-4o"]
reasoning_model: "claude-opus-4.6"
budget_model: "gemini-2.5-flash"

min_literature_papers: 200
max_budget_usd: 3.00

stage_overrides:
  4:
    search_depth: "exhaustive"
    citation_traversal: true
    max_papers: 400
  6:
    extract_figures: true
    extract_tables: true
```

**CLI integration:**
```bash
berb run --preset ml-conference --topic "..."
berb run --preset biomedical --mode collaborative --topic "..."
berb run --preset rapid-draft --topic "..."
berb presets list
berb presets show ml-conference
berb presets create my-custom --base ml-conference  # Fork and customize
```

---

## ENHANCEMENT GROUP D: CITATION GRAPH INTELLIGENCE (P1)

### D1. Citation Graph Engine

**File:** `berb/literature/citation_graph.py`

```python
class CitationGraphEngine:
    """Navigate and analyze citation networks for deeper literature understanding."""
    
    async def traverse_forward(self, paper_id: str, depth: int = 2) -> list[Paper]:
        """Find papers that cite this paper (forward citation)."""
        
    async def traverse_backward(self, paper_id: str, depth: int = 2) -> list[Paper]:
        """Find papers cited by this paper (backward citation)."""
    
    async def find_citation_clusters(self, seed_papers: list[str]) -> list[Cluster]:
        """Identify thematic clusters in citation network."""
        
    async def detect_contradictions(self, papers: list[Paper]) -> list[Contradiction]:
        """Find papers that report conflicting results."""
    
    async def journal_quality_check(self, paper: Paper) -> JournalQuality:
        """Check journal impact factor, H-index, predatory status, retraction status."""
        
    async def author_authority_score(self, author_id: str, domain: str) -> float:
        """Score author's authority in a specific domain based on citations and publications."""
```

**Integration points:**
- Stage 4 (LITERATURE_COLLECT): Use citation traversal to expand paper set
- Stage 5 (LITERATURE_SCREEN): Use journal quality to filter predatory sources
- Stage 6 (KNOWLEDGE_EXTRACT): Weight knowledge by author authority
- Stage 23 (CITATION_VERIFY): Verify citation graph consistency

---

## ENHANCEMENT GROUP E: EXTERNAL VALIDATION & BENCHMARKING (P1)

### E1. Benchmark Suite

**File:** `berb/benchmarks/`

```python
class BerbBenchmarkSuite:
    """Run Berb against established benchmarks for credibility."""
    
    async def run_ai_scientist_reviewer(self, paper_path: str) -> ReviewScore:
        """Submit paper to AI Scientist's Automated Reviewer (open-source)."""
        
    async def run_reproduction_benchmark(self, 
        known_papers: list[str],  # DOIs of papers to reproduce
        domain: str
    ) -> ReproductionReport:
        """Run Berb on known topics and compare to published results."""
        
    async def run_quality_benchmark(self,
        topics: list[str],
        preset: str,
        n_runs: int = 5
    ) -> QualityReport:
        """Statistical quality assessment across multiple runs."""
```

**Benchmark sets to include:**
- 5 well-known ML papers (reproducible results)
- 5 biomedical papers (with known conclusions)
- 5 physics papers (with analytical solutions)
- Quality comparison: Berb output vs AI Scientist V2 output on same topics

---

## ENHANCEMENT GROUP F: REPRODUCIBILITY ARTIFACTS (P1)

### F1. Audit Trail & Reproducibility Package

**File:** `berb/audit/reproducibility.py`

Every Berb run must produce:

```
output/
├── paper.pdf                    # Final paper
├── paper.tex                    # LaTeX source
├── reproducibility_package/
│   ├── environment.yml          # Conda/pip environment
│   ├── Dockerfile               # Exact environment reproduction
│   ├── data/                    # All data used (or download scripts)
│   ├── code/                    # All experiment code
│   ├── figures/                 # All generated figures
│   └── run_all.sh               # One-command reproduction
├── audit_trail.json             # Every LLM call: input, output, model, cost, latency
├── decision_log.md              # Human-readable research decisions
├── style_report.json            # Writing style conformance metrics
├── cost_report.json             # Detailed cost breakdown
├── trace.jsonl                  # Span-level tracing for debugging
└── metadata.json                # Run config, preset, models used, timestamps
```

---

## ENHANCEMENT GROUP G: PLATFORM API (P1)

### G1. FastAPI REST Layer

**File:** `berb/api/server.py`

```python
# Minimal API endpoints
POST   /api/v1/research              # Submit research job
GET    /api/v1/research/{id}         # Get status + results  
GET    /api/v1/research/{id}/stream  # SSE stream of progress
POST   /api/v1/research/{id}/approve # Approve stage (collaborative mode)
POST   /api/v1/research/{id}/feedback # Submit feedback (collaborative mode)
GET    /api/v1/research/{id}/artifacts # Download output artifacts
DELETE /api/v1/research/{id}         # Cancel running job

GET    /api/v1/presets               # List available presets
GET    /api/v1/presets/{name}        # Get preset details

GET    /healthz                      # Liveness probe (already exists)
GET    /readyz                       # Readiness probe
```

**WebSocket for real-time updates:**
```
WS /api/v1/research/{id}/ws
  → { "stage": 8, "status": "running", "progress": 0.6, "message": "Generating hypotheses..." }
  → { "stage": 8, "status": "pending_approval", "data": { "hypotheses": [...] } }
```

---

## ENHANCEMENT GROUP H: REMAINING PLANNED FEATURES (P1-P2)

### H1. SearXNG + Firecrawl Integration (P0 — already planned, prioritize)

Audit `berb/web/` for existing implementation. If not present, implement as specified in `docs/SEARXNG_FIRECRAWL_INTEGRATION.md`. This is the HIGHEST PRIORITY planned feature.

### H2. Reasoning Methods (P1 — implement top 3 only first)

Audit `berb/reasoning/` for existing implementation. Implement only:
1. Multi-Perspective (P0)
2. Pre-Mortem Analysis (P0)  
3. Bayesian Reasoning (P0)

After implementing these 3, create a benchmark comparing pipeline quality with and without reasoning methods. Only proceed to remaining 6 methods if benchmark shows ≥15% quality improvement.

### H3. OpenRouter Model Integration (P1)

Audit `berb/llm/` for OpenRouter support. Implement adapter and add:
- Phase 1 (critical): DeepSeek V3.2, Qwen3-Max, Qwen3-Turbo, GLM-4.5
- Phase 2 (premium): Claude Sonnet 4.6, Gemini 2.5 Flash, Sonar Pro
- Phase 3 (specialized): Mistral Large 3, DeepSeek R1

### H4. Anti-AI Writing Enhancement (P2)

**File:** `berb/writing/anti_ai.py`

Detect and replace AI-typical phrasing:
- "In conclusion" → domain-appropriate alternatives
- "It is worth noting that" → remove or rephrase
- "This paper presents" → vary construction
- "Delve into" → eliminate
- Overuse of "Furthermore", "Moreover", "Additionally" → vary transitions
- Excessive hedging patterns → match target style fingerprint

Bilingual support: English + target language of paper.

### H5. Claude Scholar Enhancements (P2 — subset)

From the planned 19 enhancements, prioritize only:
1. Obsidian Export (knowledge persistence)
2. Enhanced Citation Verifier (4-layer checking)
3. Skill Structure (4 skills for literature, experiments, writing, citations)

Skip: Zotero integration, command system, hook system — these can come later.

---

## ENHANCEMENT GROUP I: QUALITY-OF-LIFE IMPROVEMENTS (P2)

### I1. Multi-Language Paper Generation

Expand from 13 to 20+ languages. For each language:
- Verify academic writing conventions differ (e.g., Greek academic style ≠ English)
- Load language-specific style norms
- Validate grammar with language-specific tools where available

### I2. Domain Auto-Detection

**File:** `berb/presets/auto_detect.py`

Given only a research topic, automatically suggest the best preset:
```python
async def detect_domain(topic: str) -> str:
    """Classify topic into preset domain using LLM + keyword heuristics."""
    # "quantum error correction" → physics or ml-conference (ambiguous)
    # "CRISPR gene therapy for sickle cell" → biomedical
    # "transformer attention mechanisms" → nlp or ml-conference
    # Return top 2 suggestions with confidence scores
```

### I3. Progress Dashboard (Terminal UI)

**File:** `berb/ui/dashboard.py`

Rich terminal UI showing:
- Current stage + progress bar
- Cost running total
- Papers found / screened / included
- Model usage breakdown
- ETA
- Quality metrics (live-updating)

Use `rich` library (already a dependency).

### I4. Interactive Configuration Wizard (P2) — inspired by Writeless AI

**File:** `berb/cli/wizard.py`

Step-by-step CLI wizard for users who don't want to write YAML:

```python
class ConfigWizard:
    """Interactive guided setup for new research runs."""
    
    async def run(self) -> BerbConfig:
        """Step-by-step configuration:
        1. "What is your research topic?" → free text
        2. Auto-detect domain → suggest preset (I2)
        3. "Confirm preset or customize?" → show preset summary
        4. "Target word count / page count?" → with page estimation
        5. "Citation style?" → show options for preset domain
        6. "Minimum citation year?" → default: current_year - 10
        7. "Budget limit?" → show estimated cost range
        8. "Operation mode?" → autonomous / collaborative
        9. "Output formats?" → PDF / LaTeX / Word / Overleaf
        10. Summary → confirm → run
        """
```

**CLI:**
```bash
berb wizard                    # Interactive setup
berb run --topic "..." --preset ml-conference  # Direct (existing)
```

### I5. Citation Recency Filter (P2) — inspired by Writeless AI

**File:** Add to `berb/literature/search.py` and preset configs

```python
class CitationRecencyFilter(BaseModel):
    """Control the age of cited sources."""
    min_year: int | None = None          # Only cite papers from this year forward
    max_age_years: int | None = 10       # Alternative: max age relative to current year
    exceptions: list[str] = []           # DOIs exempt from filter (seminal papers)
    weight_by_recency: bool = True       # More recent = higher relevance score
    
    # Domain defaults (configurable per preset):
    # ml-conference: max_age=5 (fast-moving)
    # physics: max_age=15 (slower-moving, classics matter)
    # humanities: max_age=None (no filter — older works are primary sources)
    # systematic-review: max_age=None (must include all relevant literature)
```

**Integration:**
- **Stage 4 (LITERATURE_COLLECT):** Apply filter during search
- **Stage 5 (LITERATURE_SCREEN):** Weight newer papers higher
- **Per-preset defaults:** ML=5yr, NLP=5yr, Biomedical=10yr, Physics=15yr, Humanities=None

---

## ENHANCEMENT GROUP J: CITATION INTELLIGENCE — inspired by scite.ai (P0-P1)

Scite.ai has indexed 1.6B+ citation statements across 280M+ sources and classifies each as supporting, contrasting, or mentioning. Berb currently treats all citations equally. These enhancements bring citation intelligence into the pipeline.

### J1. Smart Citation Classification Engine (P0)

**File:** `berb/literature/citation_classifier.py`

For every paper Berb uses, classify how it cites other work and how it IS cited:

```python
class CitationIntent(str, Enum):
    SUPPORTING = "supporting"    # Provides evidence FOR the cited claim
    CONTRASTING = "contrasting"  # Provides evidence AGAINST the cited claim
    MENTIONING = "mentioning"    # References without evaluative stance

class CitationClassification(BaseModel):
    citing_paper_id: str
    cited_paper_id: str
    intent: CitationIntent
    confidence: float  # 0.0–1.0
    context_snippet: str  # The sentence(s) surrounding the citation
    section: str  # intro/methods/results/discussion

class CitationClassifier:
    """LLM-based citation intent classification."""
    
    async def classify_batch(
        self,
        paper_citations: list[tuple[str, str]],  # (context_text, cited_claim)
        model: str = "gemini-2.5-flash"  # Budget model for throughput
    ) -> list[CitationClassification]:
        """Classify citation intent using LLM.
        
        Prompt template:
        "Given this citation context from a research paper:
        Context: '{context}'
        The cited paper's main finding: '{claim}'
        
        Classify: Does this citation SUPPORT, CONTRAST, or merely MENTION 
        the cited finding? Respond with JSON: 
        {intent, confidence, reasoning}"
        """
    
    async def build_paper_citation_profile(
        self, paper_id: str
    ) -> PaperCitationProfile:
        """Aggregate: how many supporting/contrasting/mentioning citations."""
    
    def compute_berb_confidence_score(
        self, profile: PaperCitationProfile
    ) -> float:
        """(supporting - contrasting) / total, weighted by recency."""
```

**Integration points:**
- **Stage 5 (LITERATURE_SCREEN):** Rank papers by support/contrast ratio as quality signal. Papers with high contrasting citations = debated findings (valuable context, not rejection criteria).
- **Stage 7 (SYNTHESIS):** Generate structured evidence landscape: "Finding X is supported by [N] studies, but challenged by [M] studies regarding [specific aspect]"
- **Stage 8 (HYPOTHESIS_GEN):** Contrasting citations = research gaps = hypothesis opportunities. Feed contradictions directly into hypothesis generation prompt.
- **Stage 17 (PAPER_DRAFT):** Auto-calibrate hedging language. Claims backed by strong consensus → assertive writing. Claims with mixed evidence → hedged writing ("recent evidence suggests..." vs "it has been well established that...")
- **Stage 23 (CITATION_VERIFY):** Verify that contrasting evidence is acknowledged, not ignored.

**Cost estimate:** ~$0.001 per classification (budget model). 100 papers × 5 citations = $0.50 per run.

**Config:**
```yaml
citation_intelligence:
  enabled: true
  classifier_model: "gemini-2.5-flash"  # Budget model
  min_confidence: 0.7
  classify_top_n_papers: 50  # Only classify most relevant papers
  inject_into_writing: true
```

### J2. Reference Integrity Check (P0)

**File:** `berb/validation/reference_integrity.py`

Automated pre-output quality gate. Every reference Berb cites must pass:

```python
class ReferenceIntegrityChecker:
    """Validates all references before paper output."""
    
    async def check_retraction_status(self, doi: str) -> RetractionStatus:
        """Check Retraction Watch database + CrossRef for retraction notices."""
        
    async def check_editorial_notices(self, doi: str) -> list[EditorialNotice]:
        """Check for corrections, expressions of concern, errata."""
        
    async def check_journal_quality(self, journal_name: str) -> JournalQuality:
        """Check against Beall's List (predatory), impact metrics."""
        
    async def check_staleness(
        self, paper: Paper, current_year: int = 2026
    ) -> StalenessReport:
        """Flag papers > 10 years old with no recent supporting citations."""
        
    async def check_self_citation_ratio(self, paper: Paper) -> float:
        """Detect papers with abnormally high self-citation."""
    
    async def full_check(self, references: list[Paper]) -> IntegrityReport:
        """Run all checks. Return pass/fail per reference + overall score."""
```

**Integration:**
- **Stage 20 (QUALITY_GATE):** Auto-fail if ≥1 retracted reference without acknowledgment
- **Stage 23 (CITATION_VERIFY):** Enhanced report with per-reference health status
- **Auto-fix:** If retracted paper found → remove from references, find replacement, re-run affected sections
- **Output artifact:** `reference_integrity_report.json`

### J3. Manuscript Self-Check (P0)

**File:** `berb/validation/manuscript_self_check.py`

New sub-stage between Stage 20 and Stage 21. After the paper is "done" but before output:

```python
class ManuscriptSelfChecker:
    """Self-audit of generated paper before delivery."""
    
    async def check_citation_claim_alignment(
        self, paper_text: str, references: list[Paper]
    ) -> list[MisalignmentWarning]:
        """Verify paper doesn't say 'X supports Y' when X actually contrasts Y."""
        
    async def check_contrasting_evidence_acknowledged(
        self, paper_text: str, evidence_map: EvidenceMap
    ) -> list[OmissionWarning]:
        """Verify paper acknowledges known contradictions."""
        
    async def check_citation_completeness(
        self, paper_text: str
    ) -> list[UncitedClaim]:
        """Find empirical claims in paper that lack citations."""
    
    async def check_reference_formatting(
        self, references: list[Paper], style: str
    ) -> list[FormatError]:
        """Verify citation format consistency (APA, numeric, etc.)."""
```

### J4. Evidence Consensus Mapping (P1)

**File:** `berb/literature/evidence_map.py`

For each key claim the paper makes, build a structured evidence landscape:

```python
class ClaimEvidence(BaseModel):
    claim: str
    consensus: Literal["strong_support", "moderate_support", "mixed", "emerging_debate", "contested"]
    supporting_count: int
    contrasting_count: int
    key_supporters: list[PaperSummary]  # Top 3 by citation count
    key_challengers: list[PaperSummary]  # Top 3
    trend: Literal["stable", "growing_support", "declining", "emerging_debate"]
    berb_confidence: float  # 0.0–1.0
    recommended_hedging: Literal["assertive", "moderate", "cautious", "highly_hedged"]

class EvidenceMapper:
    async def build_evidence_map(
        self, claims: list[str], classified_citations: list[CitationClassification]
    ) -> list[ClaimEvidence]:
        """Build evidence map for each claim."""
```

**Integration:**
- **Stage 7 (SYNTHESIS):** Evidence map structures the synthesis
- **Stage 17 (PAPER_DRAFT):** Per-claim hedging guidance
- **Output artifact:** `evidence_map.json` — researcher sees which claims are solid vs contested

### J5. Section-Aware Citation Analysis (P1)

**File:** `berb/literature/section_analysis.py`

Track where papers are cited (Introduction/Methods/Results/Discussion) for smarter citation placement:

```python
class SectionCitationAnalyzer:
    async def analyze_citation_sections(
        self, paper_id: str, citations: list[CitationClassification]
    ) -> dict[str, list[CitationClassification]]:
        """Group citations by section they appear in."""
    
    def recommend_placement(
        self, paper: Paper, target_section: str
    ) -> CitationRecommendation:
        """Recommend whether/how to cite a paper in a specific section.
        
        Rules:
        - Paper cited mainly in Methods → cite in Methods, not Discussion
        - Paper cited mainly as contrast in Discussion → cite as limitation
        - Paper cited in Introduction → cite as background
        """
```

### J6. Scite MCP Integration (P2 — Optional Premium)

**File:** `berb/integrations/scite_mcp.py`

Optional integration with scite.ai's MCP for users who have scite subscriptions:

```python
class SciteMCPClient:
    """Optional: use scite.ai for pre-classified citation intelligence.
    
    Provides 1.6B+ pre-classified citations vs our LLM-based approach.
    Requires scite subscription ($10-20/month).
    """
    async def search_with_smart_citations(self, query: str) -> list[SmartCitationResult]
    async def get_paper_citation_profile(self, doi: str) -> CitationProfile
    async def reference_check(self, manuscript_pdf: Path) -> ReferenceCheckReport
    async def get_scite_index(self, doi: str) -> float
```

**Config:**
```yaml
integrations:
  scite:
    enabled: false  # Off by default — requires subscription
    mcp_url: "https://scite.ai/mcp"
    api_key_env: "SCITE_API_KEY"
    prefer_over_llm_classifier: true  # Use scite instead of J1 when available
```

### J7. Patent-Academic Cross-Search (P3)

**File:** `berb/literature/patent_search.py`

```python
class PatentSearchEngine:
    """Search patents alongside academic papers for engineering/biomedical research."""
    async def search_google_patents(self, query: str) -> list[Patent]
    async def cross_reference(self, paper: Paper) -> list[Patent]  # Find patents citing this paper
    async def patent_landscape(self, topic: str) -> PatentLandscape  # Prior art analysis
```

Integration: Especially valuable for `engineering`, `biomedical`, and `physics` presets.

---

## ENHANCEMENT GROUP K: RESEARCH WORKFLOW PATTERNS — inspired by Claude Scholar (P1-P2)

Claude Scholar (2.1k stars) provides a battle-tested semi-automated research workflow with skills, agents, hooks, and commands. These patterns can be adapted for Berb's pipeline.

### K1. Research Gap Analysis Engine (P1)

**File:** `berb/research/gap_analysis.py`

Claude Scholar identifies 5 types of research gaps. Berb should do this systematically in Stage 7-8:

```python
class ResearchGapType(str, Enum):
    LITERATURE = "literature"           # Topic understudied
    METHODOLOGY = "methodology"         # Existing methods have limitations
    APPLICATION = "application"         # Not applied to domain X yet
    INTERDISCIPLINARY = "interdisciplinary"  # Gap between fields
    TEMPORAL = "temporal"               # Outdated studies need updating

class ResearchGapAnalyzer:
    async def identify_gaps(
        self,
        synthesis: str,  # Output from Stage 7
        evidence_map: list[ClaimEvidence],  # From J4
        classified_citations: list[CitationClassification]  # From J1
    ) -> list[ResearchGap]:
        """Systematic gap identification using LLM + citation evidence.
        
        For each gap:
        - Type classification
        - Evidence strength (how clear is the gap?)
        - Feasibility assessment (can Berb address this?)
        - Novelty potential (has anyone started filling this?)
        - Priority score
        """
    
    async def rank_gaps_for_hypothesis(
        self, gaps: list[ResearchGap]
    ) -> list[ResearchGap]:
        """Rank by: novelty × feasibility × impact."""
```

**Integration:**
- **Stage 7 (SYNTHESIS):** Gap analysis runs automatically after synthesis
- **Stage 8 (HYPOTHESIS_GEN):** Hypotheses generated from ranked gaps, not just topic brainstorming
- **Output artifact:** `research_gaps.json`

### K2. Writing Pattern Mining & Memory (P1)

**File:** `berb/writing/pattern_memory.py`

Claude Scholar maintains a global "writing memory" that learns patterns from mined papers. Berb should build this:

```python
class WritingPatternMemory:
    """Persistent memory of writing patterns learned across runs.
    
    Stores: transition phrases, section templates, argument structures,
    domain-specific vocabulary, hedging patterns per confidence level.
    """
    
    async def mine_patterns_from_papers(
        self, papers: list[Paper], domain: str
    ) -> WritingPatterns:
        """Extract reusable writing patterns from top-cited papers.
        
        Patterns include:
        - Introduction structures (funnel, problem-solution, narrative)
        - Methods description templates
        - Results presentation patterns (finding → evidence → implication)
        - Discussion argument flows
        - Transition vocabulary per section boundary
        """
    
    def save(self, path: Path) -> None:
        """Persist patterns for cross-run reuse."""
    
    def load(self, path: Path) -> WritingPatterns:
        """Load patterns from previous runs."""
    
    def merge(self, new_patterns: WritingPatterns) -> None:
        """Merge new patterns with existing memory. Deduplicate."""
```

**Integration:**
- **Stage 6 (KNOWLEDGE_EXTRACT):** Mine patterns from literature
- **Stage 16-17 (PAPER_OUTLINE/DRAFT):** Inject patterns into writing prompts
- **Persistence:** `.berb/writing_memory/` — improves over time across runs
- **Synergy with B1 (Style Fingerprinting):** Writing memory provides structural patterns; style fingerprint provides surface-level mimicry. Together = comprehensive style matching.

### K3. Structured Paper Reading Notes (P1)

**File:** `berb/literature/structured_notes.py`

Claude Scholar creates structured reading notes per paper. Berb should generate these for traceability:

```python
class PaperReadingNote(BaseModel):
    paper_id: str
    doi: str
    title: str
    # Structured extraction
    research_question: str
    methodology: str
    key_findings: list[str]
    limitations: list[str]
    claims: list[ClaimWithEvidence]  # Reusable claims with citation context
    relevance_to_topic: str
    quality_assessment: float  # 0-10
    # Citation intelligence (from J1)
    citation_profile: PaperCitationProfile
    # Berb-specific
    used_in_stages: list[int]  # Which pipeline stages referenced this paper
    contribution_type: Literal["background", "methodology", "comparison", "supporting", "contrasting"]
```

**Integration:**
- **Stage 6 (KNOWLEDGE_EXTRACT):** Generate structured note per paper
- **Output artifact:** `reading_notes/` directory — one JSON per paper
- **Audit trail:** Reviewers can trace exactly how each paper contributed

### K4. Rebuttal/Response Generation (P2)

**File:** `berb/writing/rebuttal_generator.py`

Claude Scholar has a dedicated review-response skill with classification and strategies. Berb should offer this as post-pipeline feature:

```python
class ReviewCommentType(str, Enum):
    MAJOR = "major"             # Requires new experiments or analysis
    MINOR = "minor"             # Clarification or small change
    TYPO = "typo"               # Surface-level fix
    MISUNDERSTANDING = "misunderstanding"  # Reviewer didn't understand

class ResponseStrategy(str, Enum):
    ACCEPT = "accept"           # Agree and implement change
    DEFEND = "defend"           # Provide evidence for current approach
    CLARIFY = "clarify"         # Explain more clearly
    EXPERIMENT = "experiment"   # Run additional experiment

class RebuttalGenerator:
    async def classify_reviews(
        self, reviews: list[str]
    ) -> list[ClassifiedComment]:
        """Classify each review comment by type."""
    
    async def generate_response(
        self, comment: ClassifiedComment, paper: str, evidence_map: list[ClaimEvidence]
    ) -> RebuttalResponse:
        """Generate evidence-based response with strategy selection."""
    
    async def generate_rebuttal_letter(
        self, responses: list[RebuttalResponse]
    ) -> str:
        """Assemble complete rebuttal letter with proper formatting."""
```

**CLI:**
```bash
berb rebuttal --paper output/paper.pdf --reviews reviews.txt
```

### K5. Post-Acceptance Pipeline (P3)

**File:** `berb/pipeline/post_acceptance.py`

Claude Scholar has a dedicated post-acceptance skill. Berb should automate:

```python
class PostAcceptancePipeline:
    async def generate_camera_ready(self, paper: str, reviewer_comments: list[str]) -> str:
        """Apply accepted changes, format for camera-ready submission."""
    
    async def generate_slides(self, paper: str, format: str = "beamer") -> str:
        """Generate conference presentation slides from paper."""
    
    async def generate_poster(self, paper: str) -> str:
        """Generate conference poster layout."""
    
    async def generate_abstract_variants(self, paper: str) -> dict[str, str]:
        """Generate: 1-sentence, 3-sentence, full abstract, tweet-length."""
    
    async def generate_blog_post(self, paper: str) -> str:
        """Generate accessible blog post from technical paper."""
```

### K6. Experiment Tracking & Obsidian Knowledge Base (P2)

**File:** `berb/knowledge/knowledge_base.py`

Claude Scholar routes durable knowledge into Obsidian-style directories. Berb should maintain a structured knowledge base:

```python
class KnowledgeBase:
    """Filesystem-first research knowledge base."""
    
    base_dirs = {
        "Papers": "Literature notes and reading summaries",
        "Knowledge": "Extracted domain knowledge and key concepts",
        "Experiments": "Experiment designs, configs, and tracking",
        "Results": "Analysis results, figures, and statistical reports",
        "Results/Reports": "Per-round experiment reports",
        "Writing": "Draft sections, outlines, and writing artifacts",
    }
    
    async def export_stage_output(
        self, stage: int, output: Any, project_dir: Path
    ) -> Path:
        """Route stage output to appropriate knowledge base directory."""
    
    async def generate_experiment_report(
        self, experiment_id: str, results: dict
    ) -> str:
        """Markdown report with stats, figures, next actions."""
    
    async def export_to_obsidian(
        self, vault_path: Path
    ) -> None:
        """Export knowledge base to Obsidian vault with wikilinks."""
```

**Config:**
```yaml
knowledge_base:
  enabled: true
  format: "markdown"  # or "obsidian" for wikilinks
  obsidian_vault_path: null  # Optional
  auto_export_stages: [6, 12, 13, 14, 17, 21]
```

### K7. 5W1H Brainstorming for Topic Refinement (P2)

**File:** `berb/research/topic_refinement.py`

Claude Scholar uses 5W1H (What/Why/Who/When/Where/How) to turn vague topics into structured research questions. Adapt for Stage 1-2:

```python
class TopicRefiner:
    async def apply_5w1h(self, vague_topic: str) -> StructuredTopic:
        """Transform vague topic into structured research questions.
        
        Returns:
        - What: Core phenomenon/mechanism
        - Why: Motivation and significance
        - Who: Target population/domain
        - When: Temporal scope
        - Where: Application context
        - How: Methodology direction
        - Refined research question(s)
        - Scope boundaries (in-scope / out-of-scope)
        """
```

### K8. Self-Improvement Loop for Pipeline Skills (P3)

**File:** `berb/meta/self_improvement.py`

Claude Scholar has a skill review + improvement loop. Berb should track which pipeline configurations produce better results:

```python
class PipelineMetaLearner:
    """Track what works across runs and adapt."""
    
    async def record_run_metrics(
        self, run_id: str, preset: str, config: dict,
        quality_scores: dict, cost: float, time_seconds: float
    ) -> None:
        """Record metrics for meta-learning."""
    
    async def analyze_what_works(
        self, domain: str, min_runs: int = 10
    ) -> PipelineRecommendations:
        """After N runs, identify: best model per stage, optimal 
        literature count, most effective reasoning methods, etc."""
    
    async def suggest_config_improvements(
        self, current_config: dict
    ) -> list[ConfigSuggestion]:
        """Suggest specific config changes based on historical data."""
```

---

## ENHANCEMENT GROUP L: OUTPUT FORMAT & CITATION ENGINE — inspired by ThesisAI (P1)

ThesisAI's strengths are in output formatting: native LaTeX, Overleaf export, page-level citations, 8 citation styles. Its weaknesses (fabricated citations, shallow content, AI detection) are areas where Berb already excels. These enhancements bring ThesisAI's UX advantages into Berb.

### L1. Page-Level Citation Mode (P1)

**File:** `berb/writing/citation_engine.py`

Currently Berb cites at paper level ("Smith 2024"). Add page-level citation for precision:

```python
class CitationLevel(str, Enum):
    PAPER = "paper"   # Smith (2024) — standard for STEM
    PAGE = "page"     # Smith (2024, p. 47) — required for humanities, lit reviews

class CitationEngine:
    """Unified citation generation with paper-level and page-level support."""
    
    def __init__(self, level: CitationLevel, style: CitationStyle):
        self.level = level
        self.style = style
    
    async def generate_citation(
        self, 
        paper: Paper,
        claim: str,
        page_number: int | None = None,
        section: str | None = None
    ) -> FormattedCitation:
        """Generate citation with optional page reference.
        
        Page-level mode:
        - Extracts page number from PDF where claim appears
        - Generates separate BibTeX entry per page reference
        - Formats: Smith (2024, p. 47) or [12, p. 47]
        """
    
    async def extract_page_from_pdf(
        self, paper: Paper, claim_text: str
    ) -> int | None:
        """Find the exact page number where a cited claim appears.
        Uses text search in PDF, with fuzzy matching for paraphrased claims."""
    
    def format_bibliography_entry(
        self, paper: Paper, page: int | None = None
    ) -> str:
        """Generate BibTeX/bibliography entry."""
```

**Integration:**
- **Config:** `citation.level: "paper"` or `"page"` in preset YAML
- **Default per preset:**
  - `ml-conference`, `physics`, `engineering` → paper-level (standard)
  - `humanities`, `social-sciences`, `systematic-review` → page-level (required)
- **Stage 17 (PAPER_DRAFT):** Citation engine injects correct format
- **Output:** Separate BibTeX file with page-level entries when applicable

### L2. Comprehensive Citation Style Library (P1)

**File:** `berb/writing/citation_styles.py`

Unified citation style engine supporting all major academic formats:

```python
class CitationStyle(str, Enum):
    # Numeric styles
    NUMERIC = "numeric"           # [1], [2], [3]
    ALPHABETIC = "alphabetic"     # [Smi24], [Jon23]
    IEEE = "ieee"                 # [1] with IEEE formatting rules
    
    # Author-year styles
    APA = "apa"                   # (Smith, 2024)
    HARVARD = "harvard"           # (Smith 2024)
    CHICAGO_AUTHOR_DATE = "chicago-ad"  # (Smith 2024)
    
    # Note-based styles
    OXFORD = "oxford"             # Footnote: ¹ Smith, ...
    CHICAGO_NOTES = "chicago-notes"  # Footnote: ¹ Smith, ...
    
    # Field-specific
    VANCOUVER = "vancouver"       # Biomedical: superscript numbers
    ACS = "acs"                   # Chemistry
    AMS = "ams"                   # Mathematics
    MLA = "mla"                   # Humanities: (Smith 47)
    NATURE = "nature"             # Nature journal style
    
    # Custom
    CUSTOM = "custom"             # User-provided CSL file

class CitationStyleConfig(BaseModel):
    style: CitationStyle
    csl_file: Path | None = None  # For custom styles (Citation Style Language)
    bibliography_sort: Literal["alphabetical", "order_of_appearance", "year"]
    include_doi: bool = True
    include_url: bool = False
    max_authors_before_etal: int = 3

class CitationFormatter:
    """Format citations and bibliography in any academic style."""
    
    def format_inline(self, paper: Paper, style: CitationStyle) -> str:
        """Generate inline citation text."""
    
    def format_bibliography(
        self, papers: list[Paper], style: CitationStyle
    ) -> str:
        """Generate complete bibliography/reference list."""
    
    def to_bibtex(self, papers: list[Paper]) -> str:
        """Export all references as BibTeX."""
    
    def to_csl_json(self, papers: list[Paper]) -> str:
        """Export as CSL-JSON for compatibility with reference managers."""
```

**Default per preset:**
```yaml
# In each preset YAML:
ml-conference:    citation_style: "numeric"
biomedical:       citation_style: "vancouver"
nlp:              citation_style: "apa"  # ACL uses author-year
physics:          citation_style: "numeric"
social-sciences:  citation_style: "apa"
humanities:       citation_style: "chicago-notes"
systematic-review: citation_style: "numeric"
engineering:      citation_style: "ieee"
```

### L3. Native LaTeX Output + Overleaf Export (P1)

**File:** `berb/export/latex_exporter.py`

Currently Berb outputs PDF. Add editable LaTeX source:

```python
class LaTeXExporter:
    """Generate publication-ready LaTeX source files."""
    
    async def export_latex_project(
        self, paper: GeneratedPaper, output_dir: Path,
        template: str = "article"  # article, neurips, acl, revtex, etc.
    ) -> LaTeXProject:
        """Generate complete LaTeX project:
        
        output/latex/
        ├── main.tex          # Main document
        ├── references.bib    # BibTeX bibliography
        ├── figures/           # All generated figures
        ├── sections/          # One .tex file per section (for modularity)
        │   ├── introduction.tex
        │   ├── methods.tex
        │   ├── results.tex
        │   └── discussion.tex
        ├── style.sty          # Custom style definitions
        └── Makefile           # pdflatex + bibtex build commands
        """
    
    async def export_overleaf_zip(
        self, latex_project: LaTeXProject
    ) -> Path:
        """Package as .zip ready for Overleaf import.
        
        Includes:
        - All .tex files
        - .bib file
        - Figures
        - Conference template if applicable (neurips.sty, acl.sty, etc.)
        """
    
    def get_template(self, format_name: str) -> str:
        """Load LaTeX template for target venue.
        
        Built-in templates:
        - article (generic)
        - neurips, icml, iclr (ML conferences)
        - acl, emnlp (NLP conferences)  
        - cvpr, eccv (CV conferences)
        - revtex (physics - Physical Review)
        - ieee (IEEE transactions)
        - nature, science (top journals)
        - apa7 (APA 7th edition)
        - springer (Springer journals)
        - elsevier (Elsevier journals)
        """
```

**Conference template library:**
```
berb/export/templates/
├── article.tex        # Generic article
├── neurips.sty        # NeurIPS 2026
├── acl.sty            # ACL format
├── ieee.cls           # IEEE Transactions
├── revtex4-2.cls      # Physical Review
├── nature.cls         # Nature
├── springer.cls       # Springer LNCS
├── elsevier.cls       # Elsevier
├── apa7.cls           # APA 7th
└── beamer.cls         # Presentations (for K5 post-acceptance)
```

**CLI:**
```bash
berb run --topic "..." --preset ml-conference --output-format latex
berb export --run-id abc123 --format overleaf-zip
berb export --run-id abc123 --format latex --template neurips
```

**Output artifacts:**
```
output/
├── paper.pdf              # Compiled PDF
├── paper.tex              # LaTeX source (main)
├── references.bib         # BibTeX
├── latex/                 # Complete LaTeX project
│   ├── main.tex
│   ├── sections/
│   ├── figures/
│   └── Makefile
├── overleaf_export.zip    # Ready for Overleaf upload
└── ... (other existing artifacts)
```

### L4. Multi-Format Export Engine (P2)

**File:** `berb/export/multi_format.py`

Unified export supporting all output formats:

```python
class ExportFormat(str, Enum):
    PDF = "pdf"
    LATEX = "latex"
    WORD = "word"           # .docx via python-docx
    MARKDOWN = "markdown"    # For rapid-draft preset
    HTML = "html"           # Web-readable version
    BIBTEX = "bibtex"       # References only
    CSL_JSON = "csl-json"   # For reference managers
    OVERLEAF_ZIP = "overleaf-zip"

class MultiFormatExporter:
    async def export(
        self, paper: GeneratedPaper, 
        formats: list[ExportFormat],
        output_dir: Path
    ) -> dict[ExportFormat, Path]:
        """Export paper in multiple formats simultaneously."""
```

### L5. 38-Language Academic Writing Support (P2)

**File:** `berb/i18n/academic_languages.py`

ThesisAI supports 38 languages. Berb has 13. Expand and add language-specific academic conventions:

```python
class AcademicLanguageProfile(BaseModel):
    language_code: str  # ISO 639-1
    language_name: str
    writing_direction: Literal["ltr", "rtl"]
    # Academic conventions that vary by language
    passive_voice_convention: Literal["preferred", "neutral", "discouraged"]
    first_person_convention: Literal["we", "I", "impersonal", "varies"]
    typical_sentence_length: tuple[int, int]  # (min, max) words
    citation_placement: Literal["inline", "footnote", "endnote"]
    abstract_conventions: str  # Language-specific abstract structure
    # Formatting
    date_format: str  # "DD/MM/YYYY" or "MM/DD/YYYY" etc.
    number_format: str  # "1.000,50" vs "1,000.50"
    bibliography_sort_locale: str  # Locale for alphabetical sorting
```

**Languages to add (beyond current 13):**
Afrikaans, Albanian, Arabic, Bulgarian, Czech, Danish, Dutch, Finnish, Hebrew, Hungarian, Icelandic, Indonesian, Korean, Malay, Norwegian, Persian, Romanian, Serbian, Slovak, Swedish, Turkish, Ukrainian, Xhosa, Zulu.

---

## ENHANCEMENT GROUP M: CROSS-MODEL REVIEW & ITERATIVE IMPROVEMENT — inspired by Auto-claude-code-research-in-sleep (P0-P1)

This small project (33 stars) contains the single most impactful pattern Berb is missing: **separation of generation and evaluation across different model families**. Currently Berb's peer review (Stage 18) and quality gate (Stage 20) use models from the same family that generated the paper — this creates self-grading bias. The fix is architecturally simple but transformative.

### M1. Cross-Model Review System (P0)

**File:** `berb/review/cross_model_reviewer.py`

**Core principle:** The model that writes the paper must NEVER be the model that evaluates it.

```python
class CrossModelReviewConfig(BaseModel):
    """Configuration for cross-model review."""
    # Model separation rules
    generation_provider: str       # e.g., "anthropic" — writes the paper
    review_provider: str           # e.g., "openai" — reviews the paper  
    # MUST be different provider families
    allow_same_provider: bool = False  # Safety: default False
    
    # Review parameters
    review_model: str = "gpt-4o"   # Specific model for reviews
    review_reasoning_level: Literal["standard", "high", "xhigh"] = "xhigh"
    review_temperature: float = 0.3  # Lower = more consistent scoring
    
    # Anti-gaming
    hide_generation_model: bool = True  # Don't tell reviewer which model wrote it
    hide_intermediate_reasoning: bool = True  # Reviewer sees output only, not chain-of-thought

class CrossModelReviewer:
    """External model reviews paper without seeing generation process."""
    
    async def review(
        self, 
        paper_text: str,
        review_criteria: list[str],
        prior_review: ReviewResult | None = None  # For iterative reviews
    ) -> ReviewResult:
        """Single-round deep review from external model.
        
        Review prompt structure:
        1. Role: "You are a senior reviewer for [venue]. Be ruthlessly honest."
        2. Paper: Full text (no metadata about generation)
        3. Criteria: Venue-specific (e.g., NeurIPS: novelty, significance, clarity)
        4. Output: Structured JSON with:
           - overall_score: float (1-10)
           - strengths: list[str]
           - weaknesses: list[WeaknessWithSeverity]
           - missing_experiments: list[str]
           - writing_issues: list[str]
           - verdict: "accept" | "weak_accept" | "borderline" | "reject"
           - actionable_improvements: list[ActionableImprovement]
        
        Anti-gaming rule injected into prompt:
        "Do NOT hide weaknesses to produce a positive score. 
         Be as critical as a real reviewer would be."
        """
    
    async def compare_with_prior(
        self, current_review: ReviewResult, prior_review: ReviewResult
    ) -> ImprovementDelta:
        """Track what improved and what regressed between rounds."""
```

**Model pairing rules:**
```yaml
cross_model_review:
  # Default pairings (generation → review)
  pairings:
    anthropic: "openai"      # Claude writes → GPT reviews
    openai: "anthropic"      # GPT writes → Claude reviews
    deepseek: "anthropic"    # DeepSeek writes → Claude reviews
    google: "openai"         # Gemini writes → GPT reviews
  
  # Fallback if preferred reviewer unavailable
  fallback_reviewer: "deepseek-v3.2"
  
  # Budget allocation for reviews
  max_review_cost_pct: 0.15  # Max 15% of total budget on reviews
```

**Integration:**
- **Stage 18 (PEER_REVIEW):** Replace self-review with cross-model review
- **Stage 20 (QUALITY_GATE):** Final score from external model determines pass/fail

### M2. Autonomous Iterative Improvement Loop (P0)

**File:** `berb/pipeline/improvement_loop.py`

After Stage 18 review, if score < threshold: auto-fix and re-review.

```python
class ImprovementLoopConfig(BaseModel):
    enabled: bool = True
    max_rounds: int = 4            # Safety: prevent infinite loops
    score_threshold: float = 7.0   # Stop when score ≥ threshold
    max_loop_budget_usd: float = 1.0  # Budget cap for improvement loop
    max_loop_time_minutes: int = 60
    
    # Fix prioritization
    prefer_reframing: bool = True  # Prefer narrative rewrite over new experiments
    max_new_experiment_hours: float = 4.0  # Skip experiments > 4 hours
    skip_expensive_fixes: bool = True
    
    # Anti-gaming
    no_hiding_weaknesses: bool = True  # Explicit rule
    require_fix_before_resubmit: bool = True  # Must implement, not promise

class AutonomousImprovementLoop:
    """Review → Fix → Re-review until publication-ready or budget exhausted."""
    
    async def run(
        self,
        paper: GeneratedPaper,
        reviewer: CrossModelReviewer,
        config: ImprovementLoopConfig
    ) -> ImprovementResult:
        """
        Loop:
        1. External review → score + weaknesses
        2. Classify weaknesses by severity and fix cost
        3. Prioritize: cheap fixes first, reframing over experiments
        4. Implement fixes (rewrite sections, add analysis, fix claims)
        5. If weakness requires new experiment AND experiment < 4hrs → run it
        6. If weakness requires new experiment AND experiment > 4hrs → flag for human
        7. Re-review with prior review context (reviewer sees improvement delta)
        8. Repeat until score ≥ threshold OR max_rounds reached OR budget exhausted
        
        Returns: final paper + all review rounds + improvement log
        """
    
    async def classify_weakness(
        self, weakness: Weakness
    ) -> ClassifiedWeakness:
        """Classify each weakness by:
        - severity: critical/major/minor/cosmetic
        - fix_type: reframe/add_analysis/new_experiment/rewrite/acknowledge
        - estimated_cost: compute hours + API cost
        - priority: severity × (1/cost)  # Fix cheap severe issues first
        """
    
    async def implement_fix(
        self, weakness: ClassifiedWeakness, paper: GeneratedPaper
    ) -> FixResult:
        """Implement a single fix. Types:
        - reframe: Rewrite affected sections with new narrative
        - add_analysis: Run statistical analysis on existing data
        - new_experiment: Design + run + analyze (if within budget)
        - rewrite: Improve clarity/structure without changing claims
        - acknowledge: Add limitation discussion (honest, not hiding)
        """
    
    async def kill_unsupported_claims(
        self, paper: GeneratedPaper, review: ReviewResult
    ) -> GeneratedPaper:
        """If reviewer identifies claims that don't hold up:
        1. Check if claim is actually supported by evidence
        2. If not → remove claim, reframe narrative
        3. Log: "Claim X killed in round Y because [reason]"
        
        This is critical for scientific integrity.
        """
```

**Integration:**
- New loop inserted between Stage 18 (PEER_REVIEW) and Stage 20 (QUALITY_GATE)
- Configurable via presets:
  - `rapid-draft`: loop disabled (too expensive)
  - `budget`: max 1 round
  - `ml-conference`: max 3 rounds, threshold 7.0
  - `max-quality`: max 4 rounds, threshold 8.0

**Score progression tracking:**
```python
class ScoreProgression(BaseModel):
    """Track improvement across rounds."""
    rounds: list[RoundResult]
    initial_score: float
    final_score: float
    total_improvements: int
    claims_killed: int  # Claims removed for not holding up
    experiments_run: int
    narrative_rewrites: int
    total_cost_usd: float
    total_time_minutes: float
```

**Output artifact:** `improvement_log.json` + `score_progression.png` (chart showing score over rounds)

### M3. Experiment Monitor & Compute Guards (P1)

**File:** `berb/experiment/compute_guard.py`

Prevent runaway experiments during improvement loop:

```python
class ComputeGuard:
    """Prevent expensive experiments from blowing the budget."""
    
    async def estimate_experiment_cost(
        self, experiment_design: dict
    ) -> ExperimentCostEstimate:
        """Estimate: GPU hours, API cost, wall-clock time.
        
        Heuristics:
        - Dataset size × model parameters → GPU hours
        - Number of configurations × epochs → total compute
        - Historical data from prior runs (if available)
        """
    
    async def should_run(
        self, estimate: ExperimentCostEstimate, 
        budget_remaining: float,
        time_remaining_minutes: float
    ) -> tuple[bool, str]:
        """Decide: run, skip, or suggest cheaper alternative.
        
        Returns (should_run, reason):
        - (True, "Within budget: $0.30, 45 min")
        - (False, "Estimated 6 GPU-hours exceeds 4hr limit. Flagged for human.")
        - (False, "Budget would drop below 10% safety margin. Suggesting: run on smaller dataset.")
        """
    
    async def suggest_cheaper_alternative(
        self, experiment: dict
    ) -> dict | None:
        """Suggest: smaller dataset, fewer epochs, simpler model, subsample.
        Returns modified experiment config or None if no cheaper option."""

class ExperimentMonitor:
    """Monitor running experiments in real-time."""
    
    async def check_progress(
        self, experiment_id: str
    ) -> ExperimentProgress:
        """Check: running/completed/failed, progress %, ETA, current metrics."""
    
    async def detect_failure_early(
        self, experiment_id: str, metrics: list[float]
    ) -> bool:
        """Detect: loss diverging, NaN, no improvement after N epochs.
        Kill early to save compute."""
    
    async def collect_results(
        self, experiment_id: str
    ) -> ExperimentResults:
        """Collect: metrics, figures, logs, artifacts."""
```

**Integration:**
- **Stage 12 (EXPERIMENT_RUN):** ComputeGuard checks before launching
- **Stage 13 (ITERATIVE_REFINE):** Monitor detects failures early
- **M2 improvement loop:** ComputeGuard prevents expensive fix-experiments

### M4. Claim Integrity Tracker (P1)

**File:** `berb/validation/claim_tracker.py`

Track every empirical claim through the pipeline. If a claim fails reproduction in the improvement loop, it gets killed — not hidden.

```python
class ClaimTracker:
    """Track lifecycle of every empirical claim in the paper."""
    
    claims: dict[str, ClaimRecord]
    
    async def register_claim(
        self, claim: str, source_stage: int, evidence: list[str]
    ) -> str:
        """Register a new claim with its supporting evidence."""
    
    async def challenge_claim(
        self, claim_id: str, round: int, reason: str
    ) -> None:
        """Mark claim as challenged by reviewer."""
    
    async def verify_claim(
        self, claim_id: str, experiment_results: dict
    ) -> ClaimVerdict:
        """Attempt to verify claim with new evidence.
        Returns: supported / weakened / refuted / inconclusive"""
    
    async def kill_claim(
        self, claim_id: str, reason: str
    ) -> None:
        """Remove claim from paper. Log reason. Reframe narrative."""
    
    def generate_claim_report(self) -> ClaimIntegrityReport:
        """Summary: N claims registered, M verified, K killed, J weakened.
        This is the scientific integrity audit trail."""

class ClaimRecord(BaseModel):
    id: str
    text: str
    source_stage: int
    registered_round: int
    evidence: list[str]
    status: Literal["active", "challenged", "verified", "killed", "weakened"]
    challenge_history: list[ChallengeEvent]
    kill_reason: str | None = None
```

**Output artifact:** `claim_integrity_report.json` — shows exactly which claims survived peer review and which were killed. This is uniquely valuable for scientific credibility.

---

## ENHANCEMENT GROUP N: CLAIM VERIFICATION & WRITING INTELLIGENCE — inspired by Jenni AI (P0-P1)

Jenni AI (5M+ users, 15M+ papers written) has a unique "Reviews" feature that performs claim-level verification — checking each claim against sources. This is complementary to scite's citation-level analysis (Group J): scite classifies HOW papers cite each other; Jenni classifies whether YOUR claims are actually supported by your sources. Both are needed.

### N1. Claim Confidence Analysis (P0)

**File:** `berb/validation/claim_confidence.py`

Before outputting the paper, analyze every empirical claim and classify its support level:

```python
class ClaimConfidenceLevel(str, Enum):
    WELL_SUPPORTED = "well_supported"     # Multiple strong sources confirm
    WEAKLY_SUPPORTED = "weakly_supported" # Only 1 source or indirect support
    UNSUPPORTED = "unsupported"           # No citation backs this claim
    OVERSTATED = "overstated"             # Evidence exists but claim is too strong
    CONTRADICTED = "contradicted"         # Sources actually say the opposite
    MISREPRESENTED = "misrepresented"     # Source exists but doesn't say what paper claims
    UNVERIFIABLE = "unverifiable"         # Claim can't be checked against literature

class ClaimConfidenceAnalyzer:
    """Analyze every claim in generated paper against source evidence."""
    
    async def extract_claims(self, paper_text: str) -> list[ExtractedClaim]:
        """Extract all empirical/factual claims from paper text.
        
        A claim is: any sentence that asserts something about the world
        that should be backed by evidence. Excludes: definitions, 
        methodological descriptions, mathematical derivations.
        """
    
    async def verify_claim_against_sources(
        self, 
        claim: ExtractedClaim,
        cited_sources: list[Paper],
        all_sources: list[Paper]  # Including uncited but relevant
    ) -> ClaimConfidenceResult:
        """For each claim:
        1. Find which source(s) the paper cites for this claim
        2. Read the actual source text at the cited location
        3. Determine: does the source actually support this claim?
        4. Check for misrepresentation (source says X, paper claims Y)
        5. Check for overstatement ("suggests" → "proves")
        6. Check uncited sources for contradicting evidence
        
        Returns: confidence level + explanation + fix suggestion
        """
    
    async def full_analysis(
        self, paper_text: str, sources: list[Paper]
    ) -> ClaimConfidenceReport:
        """Complete claim confidence report.
        
        Output:
        {
            "total_claims": 47,
            "well_supported": 31,
            "weakly_supported": 8,
            "unsupported": 4,
            "overstated": 2,
            "contradicted": 1,
            "misrepresented": 1,
            "unverifiable": 0,
            "overall_confidence": 0.82,
            "claims": [...]  // Per-claim detail
        }
        """
```

**Integration:**
- **Stage 20 (QUALITY_GATE):** Auto-fail if any claims are contradicted or misrepresented
- **Stage 19 (PAPER_REVISION):** Auto-fix overstated claims (add hedging), add citations to unsupported claims
- **M2 (Improvement Loop):** Feed claim confidence into improvement prioritization
- **Output artifact:** `claim_confidence_report.json`

**Difference from M4 (Claim Integrity Tracker):** M4 tracks claims across improvement rounds (lifecycle). N1 verifies claims against sources (accuracy). They work together: N1 detects the problem, M4 tracks whether it gets fixed.

### N2. Academic Prose Polisher (P1)

**File:** `berb/writing/academic_polisher.py`

Fine-grained academic writing quality checks beyond anti-AI (H4):

```python
class AcademicPolishCategory(str, Enum):
    WORD_CHOICE = "word_choice"           # "utilize" → "use", precision
    FORMALITY = "formality"               # Informal language in formal context
    GRAMMAR = "grammar"                   # Academic grammar conventions
    TRANSITIONS = "transitions"           # "Also" → "In addition", "Furthermore"
    OVERGENERALIZED = "overgeneralized"   # "All" → "The majority of"
    HEDGING = "hedging"                   # "proves" → "suggests", "indicates"
    TENSE_CONSISTENCY = "tense"           # Methods=past, Results=past, Discussion=present
    PASSIVE_ACTIVE = "voice"              # Match domain conventions
    CITATION_INTEGRATION = "citation"     # "Smith (2024) says" → "Smith (2024) demonstrated"

class AcademicProsePolisher:
    """Polish academic writing to match scholarly conventions."""
    
    async def polish(
        self, text: str, 
        target_style: StyleFingerprint | None = None,
        domain: str = "general"
    ) -> PolishReport:
        """Scan text and suggest improvements per category.
        
        Returns categorized suggestions with:
        - Original text span
        - Suggested replacement
        - Category
        - Severity (error/warning/suggestion)
        - Explanation
        
        Domain-aware: physics uses more passive voice than CS.
        Style-aware: if target_style provided, calibrate to match.
        """
    
    async def auto_apply(
        self, text: str, 
        categories: list[AcademicPolishCategory],
        confidence_threshold: float = 0.9
    ) -> str:
        """Auto-apply suggestions above confidence threshold.
        Only for high-confidence fixes (grammar, obvious word choice).
        Leave hedging/tone changes for human/collaborative review.
        """
```

**Integration:**
- **Stage 17 (PAPER_DRAFT):** Auto-apply high-confidence fixes (grammar, tense)
- **Stage 19 (PAPER_REVISION):** Full polish report for all categories
- **Collaborative mode:** Present suggestions for human approval
- **Synergy with B1 (Style Fingerprinting):** Polisher calibrates to target style

### N3. Source-Traceable Citation Links (P1)

**File:** `berb/writing/traceable_citations.py`

Every citation in the output paper must link to the exact page + paragraph in the source PDF:

```python
class TraceableCitation(BaseModel):
    """Citation with full source traceability."""
    paper: Paper
    page_number: int
    paragraph_index: int  # Which paragraph on that page
    source_text_snippet: str  # The actual text being referenced (max 200 chars)
    claim_in_paper: str  # What our paper says about this source
    alignment_score: float  # How well our claim matches the source (0-1)

class CitationTracer:
    async def trace_all_citations(
        self, paper_text: str, source_pdfs: dict[str, Path]
    ) -> list[TraceableCitation]:
        """For each citation in the paper, find exact source location."""
    
    async def generate_verification_links(
        self, citations: list[TraceableCitation]
    ) -> str:
        """Generate HTML/PDF with clickable links to source locations.
        
        Output: verification_links.html — researcher can click any
        citation and see the exact source text.
        """
```

**Output artifact:** `verification_links.html` — interactive citation verification page

### N4. Smart Source-Based Generation (P2)

**File:** `berb/writing/source_writer.py`

When writing sections, anchor generation in specific source material (not just general knowledge):

```python
class SourceBasedWriter:
    """Generate text anchored in specific source documents."""
    
    async def write_section_from_sources(
        self,
        section_outline: str,
        relevant_sources: list[Paper],
        reading_notes: list[PaperReadingNote],  # From K3
        style: StyleFingerprint,  # From B1
        citation_engine: CitationEngine  # From L1/L2
    ) -> GeneratedSection:
        """Write a section where every claim traces to a specific source.
        
        Process:
        1. For each outline point, find matching evidence in reading notes
        2. Construct argument flow: claim → evidence → interpretation
        3. Generate text with inline citations at point-of-claim
        4. Verify each citation-claim pair (N1 claim confidence)
        5. Apply style constraints from fingerprint
        
        Returns section text + per-sentence source mapping
        """
```

This ensures the paper is grounded in actual sources, not hallucinated content.

---

## Implementation Checklist

Before starting, produce this table:

| Enhancement | ID | Priority | Exists? | Status | Action |
|-------------|-----|----------|---------|--------|--------|
| Workflow Type System | A1 | P0 | ? | ? | ? |
| Operation Mode System | A2 | P0 | ? | ? | ? |
| **User-Uploaded PDF Integration** | **O1** | **P0** | ? | ? | ? |
| **Mathematical Content Engine** | **O2** | **P0** | ? | ? | ? |
| **Pseudocode & Algorithm Appendix** | **O3** | **P0** | ? | ? | ? |
| Style Fingerprinting | B1 | P0 | ? | ? | ? |
| Preset System | C1 | P0 | ? | ? | ? |
| ML Conference Preset | C2a | P0 | ? | ? | ? |
| Biomedical Preset | C2b | P0 | ? | ? | ? |
| NLP Preset | C2c | P0 | ? | ? | ? |
| CV Preset | C2d | P0 | ? | ? | ? |
| Physics Preset | C2e | P0 | ? | ? | ? |
| Social Sciences Preset | C2f | P0 | ? | ? | ? |
| Systematic Review Preset | C2g | P0 | ? | ? | ? |
| Engineering Preset | C2h | P0 | ? | ? | ? |
| Humanities Preset | C2i | P0 | ? | ? | ? |
| EU Sovereign Preset | C2j | P0 | ? | ? | ? |
| Rapid Draft Preset | C2k | P0 | ? | ? | ? |
| Budget Preset | C2l | P0 | ? | ? | ? |
| Max Quality Preset | C2m | P0 | ? | ? | ? |
| Research Grounded Preset | C2n | P0 | ? | ? | ? |
| **Smart Citation Classifier** | **J1** | **P0** | ? | ? | ? |
| **Reference Integrity Check** | **J2** | **P0** | ? | ? | ? |
| **Manuscript Self-Check** | **J3** | **P0** | ? | ? | ? |
| **Claim Confidence Analysis** | **N1** | **P0** | ? | ? | ? |
| **Cross-Model Review System** | **M1** | **P0** | ? | ? | ? |
| **Autonomous Improvement Loop** | **M2** | **P0** | ? | ? | ? |
| **Compute Guard + Experiment Monitor** | **M3** | **P1** | ? | ? | ? |
| **Claim Integrity Tracker** | **M4** | **P1** | ? | ? | ? |
| Citation Graph Engine | D1 | P1 | ? | ? | ? |
| **Evidence Consensus Mapping** | **J4** | **P1** | ? | ? | ? |
| **Section-Aware Citation Analysis** | **J5** | **P1** | ? | ? | ? |
| **Research Gap Analysis Engine** | **K1** | **P1** | ? | ? | ? |
| **Writing Pattern Memory** | **K2** | **P1** | ? | ? | ? |
| **Structured Paper Reading Notes** | **K3** | **P1** | ? | ? | ? |
| Benchmark Suite | E1 | P1 | ? | ? | ? |
| Reproducibility Artifacts | F1 | P1 | ? | ? | ? |
| Platform API | G1 | P1 | ? | ? | ? |
| SearXNG Integration | H1 | P0 | ? | ? | ? |
| Firecrawl Integration | H1 | P0 | ? | ? | ? |
| Reasoning: Multi-Perspective | H2a | P1 | ? | ? | ? |
| Reasoning: Pre-Mortem | H2b | P1 | ? | ? | ? |
| Reasoning: Bayesian | H2c | P1 | ? | ? | ? |
| OpenRouter Adapter | H3 | P1 | ? | ? | ? |
| Anti-AI Writing | H4 | P2 | ? | ? | ? |
| Obsidian Export | H5a | P2 | ? | ? | ? |
| Enhanced Citation Verifier | H5b | P2 | ? | ? | ? |
| Skill Structure | H5c | P2 | ? | ? | ? |
| **Scite MCP Integration** | **J6** | **P2** | ? | ? | ? |
| **Rebuttal Generator** | **K4** | **P2** | ? | ? | ? |
| **Knowledge Base / Obsidian** | **K6** | **P2** | ? | ? | ? |
| **5W1H Topic Refinement** | **K7** | **P2** | ? | ? | ? |
| **Code Quality & Reproducibility Appendix** | **O4** | **P1** | ? | ? | ? |
| **Supplementary Materials Generator** | **O5** | **P1** | ? | ? | ? |
| **Figure & Table Auto-Generation** | **O6** | **P1** | ? | ? | ? |
| **Related Work Auto-Positioning** | **O8** | **P1** | ? | ? | ? |
| **Academic Prose Polisher** | **N2** | **P1** | ? | ? | ? |
| **Source-Traceable Citation Links** | **N3** | **P1** | ? | ? | ? |
| **Page-Level Citation Mode** | **L1** | **P1** | ? | ? | ? |
| **Citation Style Library** | **L2** | **P1** | ? | ? | ? |
| **LaTeX Output + Overleaf Export** | **L3** | **P1** | ? | ? | ? |
| **Environmental Impact Statement** | **O7** | **P2** | ? | ? | ? |
| **Source-Based Generation** | **N4** | **P2** | ? | ? | ? |
| **Multi-Format Export Engine** | **L4** | **P2** | ? | ? | ? |
| **38-Language Support** | **L5** | **P2** | ? | ? | ? |
| Domain Auto-Detection | I2 | P2 | ? | ? | ? |
| Progress Dashboard | I3 | P2 | ? | ? | ? |
| **Interactive Config Wizard** | **I4** | **P2** | ? | ? | ? |
| **Citation Recency Filter** | **I5** | **P2** | ? | ? | ? |
| **Patent-Academic Cross-Search** | **J7** | **P3** | ? | ? | ? |
| **Post-Acceptance Pipeline** | **K5** | **P3** | ? | ? | ? |
| **Self-Improvement Loop** | **K8** | **P3** | ? | ? | ? |

Fill `Exists?` with ✅/🔶/❌ after codebase audit.
Fill `Status` with description of what exists.
Fill `Action` with: skip / complete / implement.

Then implement in order: all P0 → all P1 → all P2.

---

## Critical Success Metrics

After implementation, verify:

| Metric | Target | Measurement |
|--------|--------|-------------|
| Autonomous mode backward-compatible | 100% | Existing tests pass |
| Collaborative mode pauses correctly | All configured stages | Integration test |
| Style fingerprint extracted | ≥3 authors identified | Unit test per domain |
| Generated paper style similarity | ≥70% on key metrics | Style score |
| All presets load and validate | 14/14 | Config validation test |
| Preset selection via CLI works | `--preset X` | CLI test |
| Citation classification accuracy | ≥85% agreement with manual | Sample evaluation |
| Retracted references caught | 100% | Retraction Watch cross-check |
| Manuscript self-check passes | 0 unacknowledged contradictions | Output validation |
| Evidence map generated | Per key claim | JSON output check |
| Research gaps identified | ≥3 typed gaps per run | Gap analysis output |
| Writing patterns mined | ≥10 patterns per domain | Pattern memory check |
| Citation graph traversal | 2-hop forward/backward | Integration test |
| API serves research jobs | POST → GET → artifacts | API test |
| Reproducibility package complete | All artifacts present | Output validation |
| SearXNG returns results | ≥100 engines available | Docker test |
| Anti-AI score | ≥80% human-like | Detector test |
| Cost per paper (budget preset) | ≤$0.25 | End-to-end test |
| Cost per paper (max-quality preset) | ≤$5.00 | End-to-end test |
| Rebuttal generation | Classified + response per comment | Unit test |
| Knowledge base export | All 6 directories populated | Output check |
| Page-level citations accurate | Page numbers match PDF source | Sample verification |
| Citation styles render correctly | 8+ styles supported | Format validation |
| LaTeX compiles without errors | `pdflatex` + `bibtex` success | Build test |
| Overleaf zip imports clean | Manual Overleaf test | Manual check |
| Conference templates render | neurips, acl, ieee, revtex | Build test per template |
| Cross-model review uses different provider | Generation ≠ Review provider | Config validation |
| Improvement loop raises score | ≥1.0 point improvement over 4 rounds | Score progression log |
| Claims killed when unsupported | ≥1 claim killed in test run | Claim integrity report |
| Compute guard blocks expensive experiments | >4hr experiments flagged | Unit test |
| Claim confidence: 0 contradicted/misrepresented | No false claims in output | Claim confidence report |
| Source-traceable citations | Every citation has page+paragraph | Verification links check |
| Academic polish categories | 6+ categories checked | Polish report output |
| All 9 workflow types selectable | CLI commands work | Integration test |
| User PDF upload ingested | Metadata + text extracted | Upload test |
| Math content generates valid LaTeX | Compiles without errors | LaTeX build test |
| Pseudocode appendix generated | ≥1 algorithm per code-heavy paper | Output check |
| Supplementary material generated | All configured sections present | Output check |
| Related Work properly positions paper | Thematic clusters + positioning | Manual review |
| Figure/table quality | Venue-specific styling applied | Visual check |

---

**END OF IMPLEMENTATION PROMPT**
