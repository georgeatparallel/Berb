# Automated research pipelines for computational chaos detection

**A fully automated Claude-based pipeline can now orchestrate the entire research cycle—from literature gap discovery through hybrid chaos indicator development to journal-targeted paper submission—at a cost of roughly $60–185 per complete study.** This is feasible because three converging advances have matured simultaneously: end-to-end AI research frameworks (Sakana's AI Scientist v2, FutureHouse's Kosmos), GPU-accelerated chaos indicator toolkits (Chaoticus), and multi-signal journal targeting algorithms. The practical blueprint below synthesizes the latest developments across all six domains you specified, organized as an implementable technical reference.

---

## End-to-end automated research systems have reached workshop-paper quality

The most mature framework is **Sakana AI's AI Scientist v2**, which uses agentic tree search (best-first tree search) across ideation, experimentation, paper writing, and automated peer review. It costs approximately **$15 per paper**, supports Claude Sonnet, GPT-4o, o1-preview, and DeepSeek models, and produces full LaTeX manuscripts with automated citation management via Semantic Scholar. The v2 upgrade introduced VLM-based visualization critique and multi-model pipelines (o1-preview for writeup, gpt-4o for citations, o3-mini for aggregate plots). However, independent evaluation (arXiv:2502.14297) revealed significant limitations: **nearly half of experiments failed** in independent testing, literature review quality is the weakest link, and some "novel" ideas were actually well-known techniques.

**FutureHouse's Kosmos** (November 2025) represents the next generation—processing ~1,500 papers per run, executing 42,000+ lines of code, and producing fully traceable cited reports. Its underlying engine, **PaperQA2**, achieves superhuman performance on the LitQA benchmark through a three-LLM architecture: answer generation, contextual summarization, and agent reasoning. PaperQA2's Retrieval-Augmented Generation pipeline uses max marginal relevance search over chunked/embedded papers, followed by relevance-scored contextual summaries—a pattern directly applicable to chaos detection literature synthesis.

For computational physics specifically, **MCP-SIM** (2025, published in *npj Artificial Intelligence*) provides a self-correcting multi-agent framework with plan-act-reflect-revise cycles. It solved all 12 benchmark physics tasks and reproduced published fracture simulations from single-sentence prompts. **AtomAgents** (PNAS 2025) demonstrates multimodal multi-agent AI integrating LLMs with LAMMPS molecular dynamics—a pattern transferable to chaos indicator computation with NumPy/SciPy backends.

The recommended architecture for a computational physics pipeline combines these components: PaperQA2 for literature RAG (replacing AI Scientist's weak keyword-based search), AI Scientist v2's tree-search experimentation framework adapted with physics-specific code templates, and MCP-SIM's self-correcting execution loop for numerical simulation reliability.

---

## Chaos detection indicators: the state of the art favors Birkhoff-weighted and Lagrangian methods

The classical indicators—**SALI, FLI, GALI, MEGNO, FMA**—remain foundational but have been substantially improved. The most impactful recent advance is the **Fast Lyapunov Indicator with Birkhoff Weights (FLI^WB)**, introduced by Bazzani, Giovannozzi, Montanari, and Turchetti (2023, *Physical Review E* 107). The Birkhoff weight function w(t) = exp(−1/(t(1−t))) provides **superconvergence for quasiperiodic time series**, meaning regular orbits are classified dramatically faster than with standard FLI. This was validated on realistic 6D symplectic maps of the HL-LHC accelerator lattice (Montanari et al., 2025).

**Lagrangian Descriptor (LD) indicators** represent the most significant new family of chaos detection tools. Hillebrand, Zimper, and collaborators (2023, *Chaos* 33) introduced D_L (difference) and R_L (ratio) indicators achieving **>90% agreement with SALI** while requiring no variational equations. Daquin et al. (2024, *Physica D*) then showed that computing LD derivatives via differential algebra (automatic differentiation) achieves machine-precision accuracy, reducing misclassification from ~20% (finite differences) to near zero for thin resonant webs.

The **Multi-Particle Method (MPM)** by Many Manda and Skokos (2025, *Communications in Nonlinear Science and Numerical Simulation*) eliminates the need to derive variational equations for SALI/GALI computation entirely. Instead of evolving tangent vectors, MPM uses differences between nearby orbits with optimal parameters d₀ ≈ ε^(1/2) ≈ 10⁻⁸ for double precision and renormalization times τ ≲ 1. This opens chaos detection to systems where variational equations are difficult or impossible to derive.

**Shannon entropy indicators** (Cincotta, Giordano et al., 2021, *Physica D* 417) provide qualitatively different information—direct measurement of diffusion rates rather than binary regular/chaotic classification. The time derivative S' estimates the diffusion coefficient without variational equations, proving especially valuable for understanding chaotic transport in multidimensional systems.

The **Reversibility Error Method (REM)** deserves special mention for its implementation simplicity: it requires only forward-then-backward integration with a symmetric symplectic integrator, exploiting round-off error to distinguish chaotic (REM ~ exp(λt)) from regular (REM ~ t^α) motion. Computational cost is exactly 2× orbit computation with zero additional complexity.

---

## Machine learning is transforming chaos classification from binary to multi-class

Three distinct ML paradigms have emerged for chaos detection. **Convolutional Neural Networks** trained on time series data achieve high accuracy and, crucially, demonstrate transfer learning: Boullé et al. (2020, *Physica D* 403) trained on the logistic map and successfully classified Lorenz system and Kuramoto-Sivashinsky equation trajectories. Barrio et al. (2023, *Chaos* 33) showed CNNs can rapidly classify biparametric and triparametric chaos regions at far lower computational cost than traditional Lyapunov methods.

The most promising recent advance is **multimodal deep neural networks**. Giuseppi, Menegatti, and Pietrabissa (2024, *Machine Learning: Science and Technology*) built the first multi-class classifier combining time series, recurrence plots, and spectrograms—validated across 15 dynamical systems with robustness to white, pink, and brown noise. A 2025 follow-up (arXiv:2510.21318) extended classification beyond binary regular/chaotic to include **weakly chaotic, strongly chaotic, resonant, and non-resonant** orbits in the generalized kicked rotator.

For a hybrid chaos indicator pipeline, the optimal ML integration point is **threshold optimization on multi-indicator feature vectors**. Rather than using fixed thresholds for individual indicators, train a classifier (XGBoost or lightweight CNN) on combined features: [FLI^WB, SALI, LD_difference, REM, Shannon_entropy] → classification label. This leverages the complementary information each indicator provides while handling the difficult "sticky orbit" cases that defeat single-indicator approaches.

---

## Bibliographic search integration requires a four-API architecture

The most robust literature discovery system combines four complementary APIs:

- **arXiv API** via the `arxiv` Python package (v2.4.0): supports query fields `ti:`, `au:`, `abs:`, `cat:` with Boolean operators, pagination up to 30,000 results, and automated PDF download. Rate limit is 3-second delay between requests. Use category filter `nlin.CD` (Nonlinear Sciences - Chaotic Dynamics) and `math-ph` for chaos detection papers.

- **Semantic Scholar API** via the `semanticscholar` package (v0.11.0): provides SPECTER2 embeddings, TLDR summaries, citation intent classification, and recommendation endpoints. The AI Scientist uses this during ideation to verify novelty—search for the proposed idea and check if highly similar papers exist.

- **OpenAlex API** via `pyalex`: 250M+ works with CC0 license, rich citation network data, and concept tagging. As of February 2026, requires a free API key (100,000 credits/day). Ideal for citation network analysis and identifying bridging papers.

- **Google Scholar** access via `scholarly` library (free, rate-limited) or SerpAPI ($75–275/month for structured JSON). Essential for capturing grey literature and conference proceedings missed by other APIs.

For **automated gap analysis**, the pipeline should: (1) collect papers using keyword queries across all four APIs, (2) generate SPECTER2 embeddings for each paper, (3) cluster papers using HDBSCAN to identify research communities, (4) identify sparse regions in embedding space as potential gaps, (5) use PaperQA2's agentic RAG to validate whether identified gaps are genuine by querying the collected corpus with targeted questions like "Has anyone combined FLI with Lagrangian descriptors using Birkhoff weights?" Tools like **litstudy** (Python) provide topic modeling, co-citation analysis, and bibliometric visualizations directly from Semantic Scholar, CrossRef, and arXiv data sources.

---

## AI model selection should follow a tiered cost-performance strategy

The optimal model assignment for each research phase reflects a clear pattern: **Opus for reasoning-heavy tasks, Sonnet for coding and structured analysis, Haiku for high-volume execution**.

| Phase | Primary model | Rationale | Estimated cost |
|-------|--------------|-----------|----------------|
| Literature review & gap analysis | Claude Opus 4.6 (1M context beta) | Deep synthesis across dozens of papers requires maximum reasoning depth | $15–50 |
| Hypothesis & method design | Claude Opus 4.6 with extended thinking | Creative scientific reasoning benefits from explicit chain-of-thought | $5–15 |
| Simulation code generation | Claude Sonnet 4.5 (generation) + Opus (review) | Sonnet achieves 77–82% SWE-bench at $3/$15 per MTok; Opus catches subtle numerical bugs | $10–30 |
| Execution & statistical analysis | Sonnet 4.5 + DeepSeek-R1 (verification) | Statistical precision needs moderate intelligence; DeepSeek-R1 provides independent mathematical verification at ~$0.27/$1.10 per MTok | $3–10 |
| Results interpretation & visualization | Sonnet 4.5 (analysis) + Haiku 4.5 (plot code) | Haiku generates matplotlib/plotly boilerplate at $1/$5 per MTok; Sonnet interprets | $5–15 |
| Paper writing | Claude Opus 4.6 (64K output) | Highest writing quality with nuanced scientific prose; supports full paper length | $20–60 |
| Journal selection | Sonnet 4.5 with structured JSON output | Systematic evaluation doesn't require maximum reasoning; benefits from reliable structured output | $2–5 |

**Critical cost optimizations**: Prompt caching (5-minute writes at 1.25×, cache reads at 0.1× base price) reduces repeated system prompt costs by 90%. The Batch API provides 50% discount for non-urgent phases (literature review, paper writing). Combined, these reduce total pipeline cost to **$35–100 per complete study**. For mathematical verification, **DeepSeek-R1** (MIT license, self-hostable) provides near-zero marginal cost with 87.5% AIME 2025 accuracy. **Gemini 3 Pro** serves as an alternative for Phase 1 with its native 1M+ token context and 91.9% GPQA Diamond score.

---

## Journal targeting uses multi-signal fusion across content, citations, and metrics

The recommended three-stage architecture combines embedding-based semantic matching with citation pattern analysis and LLM-powered evaluation:

**Stage 1** extracts manuscript features: KeyBERT for keyword extraction (keyphrase_ngram_range=(1,3)), sentence-transformers `all-mpnet-base-v2` for manuscript embedding (best accuracy at 0.71±0.04 similarity), and Claude Sonnet for domain classification (computational vs. theoretical, methodology type, application domain).

**Stage 2** fuses four matching signals with empirically-derived weights: **semantic similarity** (0.40 weight) via cosine similarity between manuscript and pre-computed journal scope embeddings; **citation pattern analysis** (0.25) identifying which journals publish papers citing the same references; **topic model overlap** (0.15) using LDA on manuscript vs. journal topic distributions; and **reference distribution** (0.10) analyzing where the manuscript's own bibliography was published, plus **journal metrics normalization** (0.10) incorporating impact factor, CiteScore, and review speed.

**Stage 3** uses Claude Sonnet 4.5 with structured JSON output to evaluate the top-10 candidates on scope alignment, methodology fit, impact factor appropriateness, and strategic positioning, returning ranked recommendations with justifications.

For chaos detection and dynamical systems manuscripts specifically, the journal landscape sorts into clear tiers. **Tier 1** (high impact, competitive): *Physical Review Letters* (IF ~8.6), *Nonlinear Dynamics* (IF ~5.6), *Chaos, Solitons & Fractals* (IF ~5.3, faster review at 6–12 weeks). **Tier 2** (solid, field-specific): *Chaos* (AIP, IF ~3.6, favors interdisciplinary approaches), *Physica D* (IF ~3.06, emphasizes mathematical rigor, receptive to ML + dynamical systems convergence), *Communications in Nonlinear Science and Numerical Simulation* (IF ~3.9, fast 4–8 week review). **Tier 3** (accessible): *Physical Review E* (IF ~2.4, requires clear physics contribution), *International Journal of Bifurcation and Chaos* (IF ~2.2). A novel hybrid chaos indicator paper combining LD methods with ML classification would likely find optimal fit at *Chaos* (AIP) or *Physica D*, given their explicit scope coverage and receptivity to methodological innovation.

---

## The optimal hybrid chaos indicator pipeline for 2–3D systems

Synthesizing across all findings, the most promising approach for developing novel hybrid chaos indicators follows a three-tier architecture validated by recent literature:

**For 2D Hamiltonian systems**: LD-based screening (ΔL indicator, no variational equations, GPU-parallelizable via Chaoticus) → FLI^WB classification (Birkhoff-weighted superconvergence for regular orbits) → REM validation (independent method, trivially simple implementation). This combination exploits the analytical FLI↔MEGNO relation (Mestre et al., 2011) while adding the variational-equation-free LD and REM methods as independent checks.

**For 3D+ Hamiltonian systems**: GALI_k via MPM (provides unique torus dimensionality information—if motion is on an s-dimensional torus, GALI_k for k > s decays as t^(2(s−k))) + FLI^WB (proven in 6D HL-LHC lattice models) + Shannon entropy S' (measures diffusion rate, qualitatively different from binary classification).

**The ML fusion layer** trains a classifier on the concatenated feature vector [FLI^WB, SALI, LD_diff, REM, Shannon_S'] to handle the hardest classification cases: "sticky" orbits near regular islands that can appear regular for 10⁶ iterations before transitioning to chaos. The Chaoticus GPU package (Jiménez-López et al., 2025, arXiv:2507.00622) provides orders-of-magnitude speedup for simultaneous computation of SALI, GALI, LD indicators, and Lyapunov spectra using QR factorization, making the multi-indicator approach computationally tractable for large parameter space surveys.

## Conclusion

Three implementation priorities emerge from this research. First, **build on PaperQA2 rather than AI Scientist for literature review**—PaperQA2's superhuman RAG performance directly addresses the weakest link in current automated research pipelines. Second, **the Birkhoff weight function w(t) = exp(−1/(t(1−t))) should be applied universally** across all time-averaged chaos indicators, as it provides superconvergence at zero additional computational cost. Third, the most publishable novel contribution would be a **multi-indicator ML fusion classifier** combining LD-based features (no variational equations) with FLI^WB and Shannon entropy, benchmarked on standard systems (Hénon-Heiles, 4D coupled standard map) and accelerated via Chaoticus—this fills a genuine gap where no existing paper has combined all three methodological advances (Birkhoff weights, Lagrangian descriptors, ML classification) into a unified framework.