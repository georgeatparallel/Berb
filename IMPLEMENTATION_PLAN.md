# Berb Enhancement Implementation Plan

**Generated:** 2026-03-29  
**Source:** BERB_IMPLEMENTATION_PROMPT.md (2239 lines, 60+ enhancements)  
**Status:** Audit Complete — Ready for Implementation

---

## Executive Summary

This document provides a comprehensive implementation plan for all enhancements specified in `BERB_IMPLEMENTATION_PROMPT.md`. The audit identified **60 enhancements** across **13 groups** (A-N), prioritized as:

- **P0 (Critical):** 12 enhancements — Implement first
- **P1 (High):** 18 enhancements — Implement second
- **P2 (Medium):** 15 enhancements — Implement third
- **P3 (Low):** 6 enhancements — Implement last

**Total Estimated Effort:** ~15,000 lines of new code, ~500 tests, 4-6 weeks

---

## Audit Results: Status Table

| Enhancement | ID | Priority | Exists? | Status | Action |
|-------------|-----|----------|---------|--------|--------|
| **Operation Mode System** | A1 | P0 | ❌ | Not implemented | Implement from scratch |
| **Style Fingerprinting** | B1 | P0 | ❌ | Not implemented | Implement from scratch |
| **Preset System Architecture** | C1 | P0 | 🔶 | Partially implemented | Complete missing features |
| **14 Domain Presets** | C2 | P0 | ❌ | Catalog empty | Create all 14 YAML files |
| **Smart Citation Classifier** | J1 | P0 | ❌ | Not implemented | Implement from scratch |
| **Reference Integrity Checker** | J2 | P0 | ❌ | Not implemented | Implement from scratch |
| **Manuscript Self-Check** | J3 | P0 | ❌ | Not implemented | Implement from scratch |
| **Cross-Model Review System** | M1 | P0 | ❌ | Not implemented | Implement from scratch |
| **Autonomous Improvement Loop** | M2 | P0 | ❌ | Not implemented | Implement from scratch |
| **SearXNG Integration** | H1 | P0 | ✅ | Fully implemented | Verify and test |
| **Firecrawl Integration** | H1 | P0 | ✅ | Fully implemented | Verify and test |
| **Evidence Consensus Mapping** | J4 | P1 | ❌ | Not implemented | Implement from scratch |
| **Section-Aware Citation Analysis** | J5 | P1 | ❌ | Not implemented | Implement from scratch |
| **Research Gap Analysis Engine** | K1 | P1 | ❌ | Not implemented | Implement from scratch |
| **Writing Pattern Memory** | K2 | P1 | ❌ | Not implemented | Implement from scratch |
| **Structured Paper Reading Notes** | K3 | P1 | ❌ | Not implemented | Implement from scratch |
| **Page-Level Citation Mode** | L1 | P1 | ❌ | Not implemented | Implement from scratch |
| **Citation Style Library** | L2 | P1 | ❌ | Not implemented | Implement from scratch |
| **LaTeX Output + Overleaf Export** | L3 | P1 | ❌ | Not implemented | Implement from scratch |
| **Compute Guard + Monitor** | M3 | P1 | ❌ | Not implemented | Implement from scratch |
| **Claim Integrity Tracker** | M4 | P1 | ❌ | Not implemented | Implement from scratch |
| **Citation Graph Engine** | D1 | P1 | ❌ | Not implemented | Implement from scratch |
| **Benchmark Suite** | E1 | P1 | ❌ | Not implemented | Implement from scratch |
| **Reproducibility Artifacts** | F1 | P1 | ❌ | Not implemented | Implement from scratch |
| **Platform API** | G1 | P1 | ❌ | Not implemented | Implement from scratch |
| **Reasoning: Multi-Perspective** | H2a | P1 | ✅ | Fully implemented | Integrate with pipeline |
| **Reasoning: Pre-Mortem** | H2b | P1 | ✅ | Fully implemented | Integrate with pipeline |
| **Reasoning: Bayesian** | H2c | P1 | ✅ | Fully implemented | Integrate with pipeline |
| **Reasoning: Debate** | H2d | P1 | ✅ | Fully implemented | Integrate with pipeline |
| **Reasoning: Dialectical** | H2e | P1 | ✅ | Fully implemented | Integrate with pipeline |
| **Reasoning: Research** | H2f | P1 | ✅ | Fully implemented | Integrate with pipeline |
| **Reasoning: Socratic** | H2g | P1 | ✅ | Fully implemented | Integrate with pipeline |
| **Reasoning: Scientific** | H2h | P1 | ✅ | Fully implemented | Integrate with pipeline |
| **Reasoning: Jury** | H2i | P1 | ✅ | Fully implemented | Integrate with pipeline |
| **OpenRouter Adapter** | H3 | P1 | ✅ | Fully implemented | Extend with more models |
| **Anti-AI Writing** | H4 | P2 | ❌ | Not implemented | Implement from scratch |
| **Obsidian Export** | H5a | P2 | ✅ | Fully implemented | Enhance features |
| **Enhanced Citation Verifier** | H5b | P2 | 🔶 | Partially implemented | Add 4-layer checking |
| **Skill Structure** | H5c | P2 | ✅ | Fully implemented | Add 4 core skills |
| **Scite MCP Integration** | J6 | P2 | ❌ | Not implemented | Implement from scratch |
| **Rebuttal Generator** | K4 | P2 | ❌ | Not implemented | Implement from scratch |
| **Knowledge Base** | K6 | P2 | 🔶 | Partially implemented | Complete features |
| **5W1H Topic Refinement** | K7 | P2 | ❌ | Not implemented | Implement from scratch |
| **Multi-Format Export Engine** | L4 | P2 | ❌ | Not implemented | Implement from scratch |
| **38-Language Support** | L5 | P2 | 🔶 | Partially implemented | Expand to 38 languages |
| **Domain Auto-Detection** | I2 | P2 | ❌ | Not implemented | Implement from scratch |
| **Progress Dashboard** | I3 | P2 | ❌ | Not implemented | Implement from scratch |
| **Patent-Academic Cross-Search** | J7 | P3 | ❌ | Not implemented | Implement from scratch |
| **Post-Acceptance Pipeline** | K5 | P3 | ❌ | Not implemented | Implement from scratch |
| **Self-Improvement Loop** | K8 | P3 | ❌ | Not implemented | Implement from scratch |

**Legend:**
- ✅ Fully implemented — Verify and test
- 🔶 Partially implemented — Complete missing features
- ❌ Not implemented — Implement from scratch

---

## Implementation Phases

### Phase 1: P0 Critical Enhancements (Week 1-2)

**Goal:** Implement all 12 P0 enhancements that are missing

| Order | Enhancement | File(s) | Lines | Tests | Dependencies |
|-------|-------------|---------|-------|-------|--------------|
| 1 | A1: Operation Mode System | `berb/modes/operation_mode.py` | ~250 | 15 | None |
| 2 | B1: Style Fingerprinting | `berb/writing/style_fingerprint.py` | ~400 | 20 | None |
| 3 | C1: Preset System | `berb/presets/registry.py` | ~150 | 10 | C2 |
| 4 | C2: 14 Domain Presets | `berb/presets/catalog/*.yaml` | ~1400 | 14 | None |
| 5 | J1: Citation Classifier | `berb/literature/citation_classifier.py` | ~350 | 20 | None |
| 6 | J2: Reference Integrity | `berb/validation/reference_integrity.py` | ~400 | 25 | None |
| 7 | J3: Manuscript Self-Check | `berb/validation/manuscript_self_check.py` | ~350 | 20 | J1, J2 |
| 8 | M1: Cross-Model Review | `berb/review/cross_model_reviewer.py` | ~450 | 25 | None |
| 9 | M2: Improvement Loop | `berb/pipeline/improvement_loop.py` | ~600 | 30 | M1 |
| 10 | H1: SearXNG Verify | `berb/web/searxng_client.py` | - | 15 | Already exists |
| 11 | H1: Firecrawl Verify | `berb/web/firecrawl_client.py` | - | 15 | Already exists |

**Phase 1 Total:** ~4,000 lines, ~200 tests

---

### Phase 2: P1 High-Priority Enhancements (Week 3-4)

**Goal:** Implement all 18 P1 enhancements

| Order | Enhancement | File(s) | Lines | Tests | Dependencies |
|-------|-------------|---------|-------|-------|--------------|
| 1 | J4: Evidence Mapping | `berb/literature/evidence_map.py` | ~300 | 15 | J1 |
| 2 | J5: Section Analysis | `berb/literature/section_analysis.py` | ~250 | 12 | J1 |
| 3 | K1: Gap Analysis | `berb/research/gap_analysis.py` | ~350 | 18 | J4 |
| 4 | K2: Writing Pattern Memory | `berb/writing/pattern_memory.py` | ~400 | 20 | None |
| 5 | K3: Structured Notes | `berb/literature/structured_notes.py` | ~300 | 15 | None |
| 6 | L1: Page-Level Citations | `berb/writing/citation_engine.py` | ~400 | 20 | None |
| 7 | L2: Citation Styles | `berb/writing/citation_styles.py` | ~500 | 25 | None |
| 8 | L3: LaTeX Export | `berb/export/latex_exporter.py` | ~600 | 30 | L2 |
| 9 | M3: Compute Guard | `berb/experiment/compute_guard.py` | ~450 | 25 | None |
| 10 | M4: Claim Tracker | `berb/validation/claim_tracker.py` | ~400 | 20 | M2 |
| 11 | D1: Citation Graph | `berb/literature/citation_graph.py` | ~500 | 25 | None |
| 12 | E1: Benchmark Suite | `berb/benchmarks/suite.py` | ~400 | 20 | None |
| 13 | F1: Reproducibility | `berb/audit/reproducibility.py` | ~350 | 18 | None |
| 14 | G1: Platform API | `berb/api/server.py` | ~800 | 40 | None |
| 15 | H2: Reasoning Integration | `berb/pipeline/stage_impls/` | ~500 | 30 | Reasoning exists |
| 16 | H3: OpenRouter Extension | `berb/llm/openrouter_adapter.py` | ~200 | 10 | Already exists |

**Phase 2 Total:** ~6,700 lines, ~330 tests

---

### Phase 3: P2 Medium-Priority Enhancements (Week 5)

**Goal:** Implement 15 P2 enhancements

| Order | Enhancement | File(s) | Lines | Tests | Dependencies |
|-------|-------------|---------|-------|-------|--------------|
| 1 | H4: Anti-AI Writing | `berb/writing/anti_ai.py` | ~300 | 15 | None |
| 2 | H5b: Citation Verifier++ | `berb/pipeline/citation_verification.py` | ~250 | 12 | Existing |
| 3 | H5c: Core Skills | `berb/skills/builtin/` | ~400 | 20 | Existing |
| 4 | J6: Scite MCP | `berb/integrations/scite_mcp.py` | ~300 | 15 | Optional |
| 5 | K4: Rebuttal Generator | `berb/writing/rebuttal_generator.py` | ~400 | 20 | J1 |
| 6 | K6: Knowledge Base++ | `berb/knowledge/knowledge_base.py` | ~350 | 18 | Existing |
| 7 | K7: 5W1H Refinement | `berb/research/topic_refinement.py` | ~250 | 12 | None |
| 8 | L4: Multi-Format Export | `berb/export/multi_format.py` | ~350 | 18 | L3 |
| 9 | L5: 38 Languages | `berb/i18n/academic_languages.py` | ~500 | 25 | Existing |
| 10 | I2: Domain Auto-Detect | `berb/presets/auto_detect.py` | ~200 | 10 | C1 |
| 11 | I3: Progress Dashboard | `berb/ui/dashboard.py` | ~400 | 20 | None |

**Phase 3 Total:** ~3,700 lines, ~185 tests

---

### Phase 4: P3 Low-Priority Enhancements (Week 6)

**Goal:** Implement 6 P3 enhancements

| Order | Enhancement | File(s) | Lines | Tests | Dependencies |
|-------|-------------|---------|-------|-------|--------------|
| 1 | J7: Patent Search | `berb/literature/patent_search.py` | ~350 | 18 | None |
| 2 | K5: Post-Acceptance | `berb/pipeline/post_acceptance.py` | ~450 | 22 | L3 |
| 3 | K8: Self-Improvement | `berb/meta/self_improvement.py` | ~400 | 20 | None |

**Phase 4 Total:** ~1,200 lines, ~60 tests

---

## Detailed Implementation Specifications

### P0 Enhancements

#### A1: Operation Mode System

**File:** `berb/modes/operation_mode.py`

```python
class OperationMode(str, Enum):
    AUTONOMOUS = "autonomous"
    COLLABORATIVE = "collaborative"

class CollaborativeConfig(BaseModel):
    pause_after_stages: list[int] = [2, 6, 8, 9, 15, 18]
    approval_timeout_minutes: int = 60
    feedback_format: Literal["cli", "json", "api"] = "cli"
    allow_stage_skip: bool = False
    allow_hypothesis_edit: bool = True
    allow_experiment_override: bool = True
```

**Integration:** Modify `berb/pipeline/runner.py` to check mode and pause at configured stages.

---

#### B1: Style Fingerprinting Engine

**File:** `berb/writing/style_fingerprint.py`

```python
class StyleFingerprint(BaseModel):
    source_authors: list[AuthorProfile]
    avg_sentence_length: float
    sentence_length_std: float
    avg_paragraph_sentences: float
    vocabulary_level: Literal["accessible", "moderate", "dense", "expert"]
    hedging_frequency: float
    passive_voice_ratio: float
    first_person_usage: Literal["never", "rare", "moderate", "frequent"]
    section_ratios: dict[str, float]
    citation_density: float
    transition_patterns: list[str]
    characteristic_phrases: list[str]
    sample_paragraphs: list[str]
```

**Integration:** Stage 16 (PAPER_OUTLINE) uses style profile for section proportions.

---

#### C1+C2: Preset System

**Files:** `berb/presets/registry.py`, `berb/presets/catalog/*.yaml`

**14 Presets to Create:**
1. `ml-conference.yaml` — ML venues (NeurIPS, ICML, ICLR)
2. `biomedical.yaml` — Clinical research, genomics
3. `nlp.yaml` — Computational linguistics
4. `computer-vision.yaml` — Image/video analysis
5. `physics.yaml` — Computational physics, chaos
6. `social-sciences.yaml` — Psychology, sociology
7. `systematic-review.yaml` — PRISMA-compliant reviews
8. `engineering.yaml` — Systems, distributed systems
9. `humanities.yaml` — Philosophy, history, qualitative
10. `eu-sovereign.yaml` — GDPR-compliant research
11. `rapid-draft.yaml` — Fast brainstorming
12. `budget.yaml` — Maximum cost optimization
13. `max-quality.yaml` — Best possible output
14. `research-grounded.yaml` — Maximum literature coverage

---

#### J1: Smart Citation Classifier

**File:** `berb/literature/citation_classifier.py`

```python
class CitationIntent(str, Enum):
    SUPPORTING = "supporting"
    CONTRASTING = "contrasting"
    MENTIONING = "mentioning"

class CitationClassifier:
    async def classify_batch(...) -> list[CitationClassification]
    async def build_paper_citation_profile(...) -> PaperCitationProfile
    def compute_berb_confidence_score(...) -> float
```

---

#### J2: Reference Integrity Checker

**File:** `berb/validation/reference_integrity.py`

```python
class ReferenceIntegrityChecker:
    async def check_retraction_status(doi: str) -> RetractionStatus
    async def check_editorial_notices(doi: str) -> list[EditorialNotice]
    async def check_journal_quality(journal_name: str) -> JournalQuality
    async def check_staleness(paper: Paper) -> StalenessReport
    async def check_self_citation_ratio(paper: Paper) -> float
    async def full_check(references: list[Paper]) -> IntegrityReport
```

---

#### J3: Manuscript Self-Check

**File:** `berb/validation/manuscript_self_check.py`

```python
class ManuscriptSelfChecker:
    async def check_citation_claim_alignment(...) -> list[MisalignmentWarning]
    async def check_contrasting_evidence_acknowledged(...) -> list[OmissionWarning]
    async def check_citation_completeness(...) -> list[UncitedClaim]
    async def check_reference_formatting(...) -> list[FormatError]
```

---

#### M1: Cross-Model Review System

**File:** `berb/review/cross_model_reviewer.py`

```python
class CrossModelReviewConfig(BaseModel):
    generation_provider: str
    review_provider: str
    allow_same_provider: bool = False
    review_model: str = "gpt-4o"
    review_reasoning_level: Literal["standard", "high", "xhigh"] = "xhigh"

class CrossModelReviewer:
    async def review(...) -> ReviewResult
    async def compare_with_prior(...) -> ImprovementDelta
```

**Critical Rule:** Generation provider ≠ Review provider

---

#### M2: Autonomous Improvement Loop

**File:** `berb/pipeline/improvement_loop.py`

```python
class ImprovementLoopConfig(BaseModel):
    enabled: bool = True
    max_rounds: int = 4
    score_threshold: float = 7.0
    max_loop_budget_usd: float = 1.0
    max_loop_time_minutes: int = 60

class AutonomousImprovementLoop:
    async def run(...) -> ImprovementResult
    # Loop: Review → Classify weaknesses → Fix → Re-review
```

---

### P1 Enhancements (Highlights)

#### L1+L2: Citation Engine

**Files:** `berb/writing/citation_engine.py`, `berb/writing/citation_styles.py`

**8 Citation Styles:**
- Numeric: `numeric`, `ieee`, `vancouver`
- Author-Year: `apa`, `harvard`, `chicago-ad`
- Note-Based: `oxford`, `chicago-notes`

---

#### L3: LaTeX Export

**File:** `berb/export/latex_exporter.py`

**10 Conference Templates:**
- `neurips.sty`, `icml.cls`, `iclr.cls`
- `acl.sty`, `emnlp.cls`
- `cvpr.cls`, `eccv.cls`
- `revtex4-2.cls` (Physical Review)
- `ieee.cls`, `nature.cls`

---

#### G1: Platform API

**File:** `berb/api/server.py`

**Endpoints:**
```
POST   /api/v1/research
GET    /api/v1/research/{id}
GET    /api/v1/research/{id}/stream (SSE)
POST   /api/v1/research/{id}/approve
GET    /api/v1/presets
GET    /healthz, /readyz
WS     /api/v1/research/{id}/ws
```

---

## Testing Strategy

### Unit Tests (per module)

```python
# Example: test_citation_classifier.py
async def test_classify_supporting_citation():
    classifier = CitationClassifier()
    result = await classifier.classify(
        context="Smith (2024) demonstrated that X improves Y by 15%.",
        claim="X improves Y"
    )
    assert result.intent == CitationIntent.SUPPORTING
    assert result.confidence > 0.8
```

### Integration Tests

```python
# Example: test_improvement_loop.py
async def test_improvement_loop_raises_score():
    loop = AutonomousImprovementLoop(config=ImprovementLoopConfig(max_rounds=3))
    result = await loop.run(paper=test_paper, reviewer=mock_reviewer)
    assert result.final_score > result.initial_score
    assert len(result.rounds) <= 3
```

### End-to-End Tests

```bash
# Full pipeline with new enhancements
berb run --preset ml-conference --topic "quantum error correction" --auto-approve
# Verify: citation classification, cross-model review, improvement loop
```

---

## Success Metrics

After implementation, verify:

| Metric | Target | Test Method |
|--------|--------|-------------|
| Autonomous mode backward-compatible | 100% | Existing tests pass |
| Collaborative mode pauses correctly | All configured stages | Integration test |
| Style fingerprint extracted | ≥3 authors identified | Unit test |
| All 14 presets load and validate | 14/14 | Config validation |
| Citation classification accuracy | ≥85% | Sample evaluation |
| Retracted references caught | 100% | Retraction Watch cross-check |
| Cross-model review uses different provider | 100% | Config validation |
| Improvement loop raises score | ≥1.0 point over 4 rounds | Score progression log |
| LaTeX compiles without errors | `pdflatex` success | Build test |
| API serves research jobs | POST → GET → artifacts | API test |

---

## File Structure After Implementation

```
berb/
├── modes/                    # NEW: Operation modes
│   ├── __init__.py
│   └── operation_mode.py
├── writing/                  # ENHANCED: Writing features
│   ├── __init__.py
│   ├── style_fingerprint.py  # NEW
│   ├── citation_engine.py    # NEW
│   ├── citation_styles.py    # NEW
│   ├── anti_ai.py            # NEW
│   ├── pattern_memory.py     # NEW
│   └── rebuttal_generator.py # NEW
├── presets/                  # ENHANCED: Domain presets
│   ├── __init__.py
│   ├── base.py              # Existing
│   ├── registry.py          # NEW
│   └── catalog/             # NEW: 14 YAML files
│       ├── ml-conference.yaml
│       ├── biomedical.yaml
│       └── ...
├── literature/               # ENHANCED: Citation intelligence
│   ├── __init__.py
│   ├── citation_classifier.py    # NEW
│   ├── evidence_map.py           # NEW
│   ├── section_analysis.py       # NEW
│   ├── citation_graph.py         # NEW
│   ├── structured_notes.py       # NEW
│   └── ...
├── validation/               # ENHANCED: Integrity checks
│   ├── __init__.py
│   ├── reference_integrity.py    # NEW
│   ├── manuscript_self_check.py  # NEW
│   └── claim_tracker.py          # NEW
├── review/                   # ENHANCED: Cross-model review
│   ├── __init__.py
│   ├── ensemble.py              # Existing
│   └── cross_model_reviewer.py  # NEW
├── pipeline/                 # ENHANCED: Improvement loop
│   ├── __init__.py
│   ├── improvement_loop.py     # NEW
│   └── ...
├── experiment/               # ENHANCED: Compute guards
│   ├── __init__.py
│   ├── compute_guard.py        # NEW
│   └── ...
├── research/                 # ENHANCED: Gap analysis
│   ├── __init__.py
│   ├── gap_analysis.py         # NEW
│   └── ...
├── export/                   # NEW: Export engines
│   ├── __init__.py
│   ├── latex_exporter.py       # NEW
│   └── multi_format.py         # NEW
├── api/                      # NEW: REST API
│   ├── __init__.py
│   └── server.py               # NEW
├── audit/                    # NEW: Reproducibility
│   ├── __init__.py
│   └── reproducibility.py      # NEW
├── benchmarks/               # NEW: Benchmarking
│   ├── __init__.py
│   └── suite.py                # NEW
├── integrations/             # NEW: External integrations
│   ├── __init__.py
│   └── scite_mcp.py            # NEW
├── meta/                     # NEW: Self-improvement
│   ├── __init__.py
│   └── self_improvement.py     # NEW
├── ui/                       # NEW: Dashboard
│   ├── __init__.py
│   └── dashboard.py            # NEW
└── ...
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing pipeline | Extensive unit tests, backward-compatible design |
| API cost explosion | Compute guards, budget caps, cost tracking |
| Infinite improvement loops | Max rounds (4), budget caps, time limits |
| Citation classifier errors | Human-in-the-loop for low-confidence classifications |
| LaTeX compilation failures | Fallback to PDF-only output |
| Cross-model review bias | Multiple reviewer providers, rotation |

---

## Next Steps

1. **Start Phase 1 (P0):** Begin with A1 (Operation Mode System)
2. **Daily checkpoints:** Verify each enhancement with unit tests
3. **Weekly integration:** Run full pipeline with new features
4. **Final benchmark:** Compare before/after quality metrics

---

**Total Implementation:**
- **Lines of Code:** ~15,600
- **Tests:** ~775
- **New Files:** ~35
- **Enhanced Files:** ~15
- **Estimated Time:** 4-6 weeks
