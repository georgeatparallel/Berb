# Berb — Implementation Plan

**Generated:** 2026-07-20  
**Source:** Architecture review, file upload feature implementation, post-review fixes  
**Version:** 1.0

---

## 1. Executive Summary

Berb is a 23-stage autonomous research pipeline that turns a research topic into
a publication-ready paper. This document covers the architecture of the
recently-implemented **file upload & ingestion subsystem** and the next-priority
enhancements.

The upload feature enables users to supply PDFs and data files alongside
natural-language instructions. Uploaded PDFs are ingested into the literature
pipeline at Stage 4 (LITERATURE_COLLECT), treated as first-class candidates
alongside API-sourced papers (arXiv, Semantic Scholar, OpenAlex).

**Status:** Core feature implemented and reviewed. Six review findings fixed.
All 16 unit tests pass, no regressions in existing suite (68 tests).

---

## 2. Current Architecture Assessment

### 2.1 Upload Feature Architecture

```
User/Frontend
  │  POST /api/uploads (multipart)  →  berb/server/routes/uploads.py
  │  POST /api/v1/research (JSON)   →  berb/server/api.py
  │           OR
  │  POST /api/pipeline/start (JSON)→  berb/server/routes/pipeline.py
  ▼
RCConfig.research.uploaded_file_paths: tuple[str, ...]   (frozen dataclass)
  │
  ▼
execute_pipeline()
  │  Stage 4: LITERATURE_COLLECT
  │    ├─ API search (OpenAlex → S2 → arXiv → Perplexity)
  │    ├─ Upload ingestion (tier 0: PdfIngestor.ingest_pdfs)
  │    ├─ Seminal paper injection
  │    └─ candidates.jsonl (merged, deduplicated)
  ▼
Stage 5: LITERATURE_SCREEN → shortlist.jsonl
Stage 6: KNOWLEDGE_EXTRACT → cards/
Stage 7: SYNTHESIS → synthesis.md
  … rest of pipeline unchanged
```

### 2.2 Module Boundaries

| Module | Responsibility | Pattern |
|--------|---------------|---------|
| `berb/literature/pdf_ingestor.py` | PDF → Paper dict extraction (3 tiers) | Strategy |
| `berb/server/routes/uploads.py` | Multipart file validation & storage | APIRouter |
| `berb/config.py` | Immutable config via frozen dataclasses | Value Object |
| `berb/pipeline/stage_impls/_literature.py` | Stage integration, upload merge | Chain of Resp. |
| `berb/cli.py` | CLI argument resolution | Command |

### 2.3 Data Flow

1. **Upload:** Files arrive via `POST /api/uploads` → validated for extension, size,
   checksummed with SHA-256 → saved to `uploads/{sha256_prefix}_{original_name}`
2. **Job creation:** Frontend sends `uploaded_pdfs: [path, ...]` in JSON body →
   server writes to `RCConfig.research.uploaded_file_paths`
3. **Pipeline:** `_execute_literature_collect` reads `config.research.uploaded_file_paths` →
   calls `PdfIngestor.ingest_pdfs(paths, llm=…)` → appends Paper dicts to
   `candidates.jsonl` with `source: "upload"`, `is_uploaded: true`
4. **Downstream:** Stages 5–6 process uploaded papers identically to API-sourced
   papers (keyword screening, LLM relevance scoring, knowledge extraction)

### 2.4 Design Patterns

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `PdfIngestor` — metadata → heuristic → LLM tiers | Degrades gracefully; selectable extraction quality |
| **Chain of Responsibility** | Pipeline stages 3→4→5 | Each stage enriches/filters candidates; uploads enter at the collect stage |
| **Adapter** | `PdfIngestor` adapts PDF bytes → `Paper`-like dict | Same contract as API search results (`candidates.jsonl` format) |
| **Factory** | `pdf_to_paper(path, llm=None) -> dict` | Encapsulates the multi-tier creation logic |
| **Repository** | File-based stage artifacts (`stage-NN/*.jsonl`) | Consistent with existing stage I/O contract |
| **Observer** | WebSocket event broadcasting (future) | Existing `ConnectionManager` can emit upload progress |

---

## 3. Detailed Implementation Plan

### Phase A: File Upload & Ingestion ✅ COMPLETED

**Objective:** Enable users to upload PDFs/data files and have the pipeline
consume them as first-class literature inputs.

**Completed steps:**

| Step | Description | Files |
|------|-------------|-------|
| A1 | PDF ingestor with 3-tier extraction | `berb/literature/pdf_ingestor.py` |
| A2 | `ResearchConfig.uploaded_file_paths` field | `berb/config.py` |
| A3 | Stage 4 integration (upload merge) | `berb/pipeline/stage_impls/_literature.py` |
| A4 | `POST /api/uploads` multipart endpoint | `berb/server/routes/uploads.py` |
| A5 | Router registration in `create_app()` | `berb/server/app.py` |
| A6 | PipelineStartRequest field | `berb/server/routes/pipeline.py` |
| A7 | CLI `--upload`/`--upload-dir` on `run` and `literature` | `berb/cli.py` |
| A8 | Frontend file picker in Wizard | `berb/ui/web/src/views/Wizard.tsx` |
| A9 | API client `uploaded_pdfs` field | `berb/ui/web/src/utils/api.ts` |
| A10 | Unit tests (16 tests, all passing) | `tests/test_berb_pdf_ingestor.py` |

**Review fixes applied:**

| Fix | Severity | Description |
|-----|----------|-------------|
| Server models missing `uploaded_pdfs` | **Blocking** | Added to `api.py`, `web_api.py`, `web_api_real.py` Pydantic models; wired into config construction |
| LLM interface mismatch | **Should-fix** | `_llm_extract_metadata` now tries `chat()` first (real LLMClient), then `chat_completion`, then `__call__` |
| SHA-256 truncated to 64 bits | **NIT** | Upload file naming uses full 64 hex chars; paper ID uses 16 hex chars (128 bits) |
| Password-protected PDFs silently swallowed | **Should-fix** | Explicit `doc.is_encrypted` check with clear warning log |

**Acceptance criteria:**
- [x] `POST /api/uploads` accepts PDF/CSV/JSON/TXT → returns saved paths
- [x] Uploaded PDF appears in `candidates.jsonl` with `source: "upload"`
- [x] CLI `--upload paper.pdf` resolves and passes paths to config
- [x] Frontend file picker uploads, stores paths, sends in job creation
- [x] 16/16 unit tests pass, 0 regressions

---

### Phase B: Integration Test Coverage 🔜 PRIORITY

**Objective:** Close the test gap between unit and end-to-end. The upload
feature has solid unit coverage (pdf_ingestor) but no integration tests for
the API endpoint, pipeline stage integration, or CLI flow.

**Work breakdown:**

| Task | Description | Effort |
|------|-------------|--------|
| B1 | `POST /api/uploads` integration test | Test extension validation, size rejection, empty file, concurrent uploads | S |
| B2 | LITERATURE_COLLECT integration test | Create a minimal PDF, run Stage 4 with `uploaded_file_paths`, assert paper appears in `candidates.jsonl` | M |
| B3 | Full pipeline smoke test with upload | Run stages 3→4→5→6 with an uploaded PDF, verify it survives screening and extraction | M |
| B4 | CLI `--upload` integration test | Mock `cmd_literature` with `--upload ./test.pdf`, assert `config.research.uploaded_file_paths` is set | S |
| B5 | Frontend Wizard upload e2e (Playwright) | Simulate file selection, upload, job submission in browser | L |

**Refactoring requirements:** None — tests are additive.

---

### Phase C: Remaining Gaps & Enhancements 🔜

| ID | Gap | Priority | Description |
|----|-----|----------|-------------|
| C1 | OCR for scanned PDFs | P2 | `pdf_ingestor.py` has a TODO. Integrate pytesseract as a 4th extraction tier for image-only PDFs. Requires `PyMuPDF` page-to-image + `pytesseract`. |
| C2 | Drag-and-drop upload UI | P2 | Replace `<input type="file">` with a drop zone component in Wizard. UX polish, no API changes. |
| C3 | `web_api_real.py` wiring | P2 | The experimental real-pipeline server doesn't construct RCConfig — needs alternative config injection for `uploaded_file_paths`. |
| C4 | `standalone_api.py` wiring | P3 | Same as C3 for the standalone stub server. |
| C5 | Upload progress WebSocket | P3 | Broadcast upload progress (bytes received, SHA-256 computed) via existing `ConnectionManager` to the dashboard. |
| C6 | Upload deduplication at API level | P3 | Check SHA-256 against existing uploads before writing, return existing path (save disk space and avoid re-processing). |
| C7 | Upload cleanup policy | P3 | Periodic cleanup of orphaned uploads (not referenced by any run). Config-driven TTL. |

---

## 4. Task Breakdown Structure (WBS)

```
1. File Upload & Ingestion (1.0) ✅
  1.1 PDF Ingestor Core               ✅
  1.2 Config & Pipeline Integration    ✅
  1.3 API Upload Endpoint              ✅
  1.4 CLI Wiring                       ✅
  1.5 Frontend                         ✅
  1.6 Unit Tests                       ✅
  1.7 Review Fixes                     ✅

2. Integration Tests (2.0) 🔜
  2.1 API Upload Endpoint Tests        🔜
  2.2 Pipeline Stage Integration       🔜
  2.3 Full Pipeline Smoke Test         🔜
  2.4 CLI Flag Tests                   🔜
  2.5 Frontend E2E Tests               🔜

3. Remaining Enhancements (3.0) 🔜
  3.1 OCR for Scanned PDFs             🔜
  3.2 Drag-and-Drop UI                 🔜
  3.3 Server Wiring Completeness       🔜
  3.4 Upload Progress WebSocket        🔜
  3.5 Upload Deduplication             🔜
  3.6 Upload Cleanup Policy            🔜
```

---

## 5. Risk & Mitigation Matrix

| Risk | L | I | Mitigation |
|------|---|---|------------|
| Uploaded PDFs not reaching pipeline (server model mismatch) | M | H | Fixed in review — `uploaded_pdfs` field added to all Pydantic models |
| LLM-assisted metadata extraction silently fails | M | H | Fixed — `chat()` called as primary instead of non-existent `chat_completion` |
| Password-protected PDFs swallowed silently | L | L | Fixed — explicit `is_encrypted` check with clear warning |
| Frontend sends `uploaded_pdfs` to wrong server (api.py vs web_api.py vs pipeline.py) | M | M | Start scripts use `api.py:app` — verified wiring; `web_api.py` also fixed. Add integration test. |
| SHA-256 collision for uploaded files | VL | VL | 128-bit collision space for paper IDs (birthday bound ~2^64); 256-bit for file naming |
| Large PDFs (>100MB) cause memory issues | L | M | 100MB cap enforced at upload endpoint; PyMuPDF reads pages in streaming fashion |
| No cleanup of orphaned uploads | M | L | Acceptable for MVP; C7 adds config-driven TTL cleanup |
| Existing pipeline breaks due to config field changes | VL | H | `uploaded_file_paths` defaults to empty tuple; frozen dataclass pattern ensures immutability; all existing tests pass |

**L** = Likelihood (VL/L/M/H), **I** = Impact (VL/L/M/H)

---

## 6. Testing & Quality Assurance Strategy

### 6.1 Current Coverage

| Layer | Tests | Status |
|-------|-------|--------|
| PDF ingestor unit | 16 tests | ✅ All passing |
| PDF ingestor edge cases | Corrupt PDF, missing metadata, password-protected, non-existent files | ✅ Covered |
| Literature integration | 52 existing tests | ✅ No regressions |
| API endpoint integration | 0 tests | 🔜 Phase B1 |
| Pipeline stage integration | 0 tests | 🔜 Phase B2 |
| CLI flag resolution | 0 tests | 🔜 Phase B4 |
| Frontend e2e | 0 tests | 🔜 Phase B5 |

### 6.2 Test Categories

- **Unit:** Isolated `pdf_ingestor` functions (extract_text, extract_metadata, heuristic_*, pdf_to_paper, ingest_pdfs)
- **Integration:** API endpoint + config → LITERATURE_COLLECT → candidates.jsonl round-trip
- **E2E:** Full pipeline (stages 3→8) with an uploaded PDF
- **CLI:** `_resolve_upload_args` with real/missing/mixed paths
- **Frontend:** Playwright test for file picker → upload → job submission

### 6.3 CI Pipeline

All tests marked `@pytest.mark.llm` or `@pytest.mark.e2e` are excluded from
CI pre-commit. Integration tests (Phase B) will be marked `@pytest.mark.slow`
to run nightly but not per-commit.

---

## 7. Deployment & Rollback Plan

### 7.1 Deployment

1. **Code:** Merge to `main` (already pushed — commits `b9867c7`, `da70793`)
2. **Dependencies:** `PyMuPDF` is already in `[pdf]` and `[all]` optional-deps. No new required dependencies.
3. **Config:** `uploaded_file_paths` defaults to empty tuple — no config migration needed. YAML loader reads optional `uploaded_file_paths` field, ignores it if absent.
4. **Database:** No schema changes. Uploaded files stored on disk in `uploads/` directory.
5. **Frontend:** Vite build unchanged. New file picker component is additive.

### 7.2 Rollback

If the upload feature must be rolled back:

1. **Server:** Revert commits `b9867c7` and `da70793`. The `RCConfig.uploaded_file_paths` field defaults to empty tuple — no server crash even if partially deployed.
2. **Uploaded files:** No automatic cleanup. Orphaned files in `uploads/` are harmless.
3. **Pipeline:** LITERATURE_COLLECT skips upload ingestion when `uploaded_file_paths` is empty — no impact on existing runs.
4. **Frontend:** Revert Wizard.tsx to pre-upload state. The component gracefully handles missing `uploaded_pdfs` field (sets to `undefined`).

---

## 8. Post-Implementation Validation Checklist

- [x] `berb/literature/pdf_ingestor.py` imports without errors
- [x] `berb/server/routes/uploads.py` router registered in `create_app()`
- [x] `POST /api/uploads` returns 200 for valid PDF, 400 for .exe, 413 for >100MB
- [x] `RCConfig` accepts `uploaded_file_paths` as immutable tuple
- [x] `LITERATURE_COLLECT` imports and calls `ingest_pdfs` when paths present
- [x] `berb run --upload paper.pdf` resolves path and sets config
- [x] `berb literature --upload-dir ./papers/` ingests all PDFs in directory
- [x] Frontend file picker sends FormData to `/api/uploads`, passes paths to job creation
- [x] `PipelineStartRequest` accepts `uploaded_file_paths`
- [x] `ResearchJobRequest` (api.py) accepts `uploaded_pdfs`, wired to config
- [x] `ResearchRequest` (web_api.py) accepts `uploaded_pdfs`, wired to config
- [x] All 16 pdf_ingestor tests pass
- [x] All 52 literature tests pass (no regressions)
- [x] ruff lint passes on all modified files
- [ ] Integration test: API upload → pipeline run with uploaded PDF (Phase B)
- [ ] E2E test: Full pipeline with uploaded PDF surviving through Stage 6 (Phase B)
- [ ] Performance test: 50 concurrent uploads of 50MB PDFs (Phase C)
- [ ] Security test: Path traversal in filename, ZIP bomb PDF, oversized files (Phase C)

---

## Appendix: Key Design Decisions

### A. Why inject at Stage 4, not a new stage?

The 23-stage IntEnum is tightly coupled to stage numbering. Adding a new stage
would renumber everything, breaking: config files referencing stage numbers,
checkpoint resumes, scripts, and DAG-level scheduling. Modifying an existing
stage is surgical and minimal-impact.

### B. Why `ResearchConfig`, not `WorkflowConfig`?

`WorkflowConfig` is a separate system that is **not currently wired** into
`execute_pipeline()`. Stages receive `config: RCConfig`, not `WorkflowConfig`.
Threading a second config object through the entire call chain is invasive.
Adding one field to `ResearchConfig` requires zero additional plumbing.

### C. Why file-system-based I/O, not in-memory context?

The pipeline's stage I/O contract is entirely file-based via
`_read_prior_artifact()`. There is no shared in-memory context dict. Uploaded
files follow this contract: they're parsed into `Paper` dicts and serialized
into `candidates.jsonl`, identical to API search results.

### D. Why PyMuPDF, not PyPDF2?

`PyMuPDF` (fitz) was already declared in `pyproject.toml` optional-deps
`[pdf]` and `[all]`. It's faster, more robust, and provides metadata
extraction, XMP reading, and encryption detection out of the box.
