# Berb — File Upload & Ingestion Implementation Plan

Generated: 2026-07-20 | Source: Architecture gap analysis

**Goal:** Enable users to upload arbitrary files (PDFs, data files) alongside
natural-language instructions, and have the pipeline consume them as
first-class research inputs.

---

## Current State (Verified)

| Capability | Status | Detail |
|---|---|---|
| Prompts / directions | ✅ Yes | `berb run --topic "..."` works end-to-end |
| Local file paths | ✅ Partial | `--manuscript`, `--reviews` flags work for review/rebuttal workflows; not for literature/experiment |
| Browser drag-and-drop upload | ❌ No | No multipart endpoint; frontend has no file input |
| Upload + NL instructions | ❌ No | Upload and prompt can't be combined in one request |
| `--upload` CLI flag | ❌ Dead | Parsed at `berb/cli.py:1302` but never read in `cmd_literature()` (line 890) |
| `uploaded_pdfs` in API model | ❌ Unwired | `ResearchJobCreate` (server.py:38) has the field as `list[str]` but no stage consumes it |
| `WorkflowConfig.uploaded_pdfs` | ❌ Unwired | Modeled at `workflow.py:113` but never reaches `execute_pipeline()` |

---

## Architecture Constraints

These are **non-negotiable** — the plan must work with them, not against them:

1. **File-based stage I/O**: Pipeline stages communicate exclusively through
   files on disk under `artifacts/{run_id}/stage-NN/`. There is no in-memory
   shared context. Stages read prior artifacts via `_read_prior_artifact()`.

2. **Immutable config**: `RCConfig` is a `@dataclass(frozen=True)` that flows
   from CLI → runner → executor → stage impl. Stages receive the full config
   object.

3. **Stage contracts**: Every stage declares `input_files` / `output_files`
   via `StageContract` in `berb/pipeline/contracts.py`. Adding or changing
   stages requires updating the contract registry.

4. **23-stage numbering is fixed**: `Stage(IntEnum)` — renumbering would break
   configs, scripts, tests, and checkpoint resumes. New logic must fit
   **within** existing stages.

5. **Production server**: `create_app()` in `berb/server/app.py` is the
   canonical FastAPI factory. New routes go in `berb/server/routes/` and are
   registered via `app.include_router()`.

6. **Adapter pattern**: External integrations go through `AdapterBundle`
   (`berb/adapters.py`). The LLM adapter is injected into stages via
   `adapters.llm`.

---

## Design Decisions

### D1: Inject at LITERATURE_COLLECT (Stage 4), not a new stage

**Chosen:** Modify `_execute_literature_collect()` to accept uploaded PDFs as
an **auxiliary source** alongside API search results. Uploaded papers are
parsed into `Paper` objects and merged into `candidates.jsonl` with
`"source": "upload"`.

**Rationale:**
- Adding a new stage to the `IntEnum` renumbers stages 1–23, breaking
  every config file, checkpoint, and script that references stage numbers.
- Modifying one existing stage is a **surgical, minimal-impact change**
  that respects the existing file-based I/O contract.
- `_read_prior_artifact(run_dir, "uploaded_candidates.jsonl")` would work
  if we wrote to a new stage, but the contract system and DAG would need
  updating — more surface area for bugs.
- LITERATURE_COLLECT already has three fallback tiers (OpenAlex → Semantic
  Scholar → arXiv → Perplexity → LLM-generated). Uploaded files become
  **tier 0**: always included before any API search.

### D2: Config via `ResearchConfig`, not `WorkflowConfig`

**Chosen:** Add `uploaded_file_paths: tuple[str, ...] = ()` to
`ResearchConfig` (frozen dataclass at `berb/config.py:134`).

**Rationale:**
- `WorkflowConfig` is a separate system that is **not currently wired**
  into `execute_pipeline()`. Stages receive `config: RCConfig`, not
  `WorkflowConfig`. Threading a second config object through the entire
  call chain is invasive and breaks the single-config-source pattern.
- `ResearchConfig` is already received by every stage implementation.
  Adding a field here is a one-line change with zero plumbing.

### D3: PDF parsing as a standalone utility module

**Chosen:** New module `berb/literature/pdf_ingestor.py` with no pipeline
dependency.

**Rationale:**
- Separation of concerns: PDF I/O is orthogonal to pipeline execution.
- Testable in isolation without spinning up the pipeline.
- Reusable by the API server (for preview/validation before job creation)
  and by the CLI.

### D4: Multipart endpoint following the voice.py pattern

**Chosen:** New route file `berb/server/routes/uploads.py` with
`POST /api/uploads`, using `fastapi.UploadFile`.

**Rationale:**
- `berb/server/routes/voice.py:16-17` already demonstrates the exact
  FastAPI multipart pattern (`File(...)`, `UploadFile`). Following this
  ensures consistency and avoids inventing a new pattern.
- Separating upload from job creation allows: progress indication during
  large uploads, preview/validation before committing, and reuse across
  different workflow types.

### D5: UI as a minimal file-picker, not drag-and-drop

**Chosen:** `<input type="file" multiple>` in the Wizard view, with
`FormData` upload via the existing API client.

**Rationale:**
- Drag-and-drop is a UX polish feature that adds React state management
  complexity (drop zones, file previews, progress bars) without changing
  the data flow.
- A simple file input validates the end-to-end pipeline first. DnD can
  be layered on later without API changes.

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `PdfIngestor` — pluggable extraction backends (PyPDF2 text, pdfplumber tables, LLM metadata) | Different PDFs need different parsing strategies; strategy pattern lets us select/extend without modifying callers |
| **Chain of Responsibility** | Pipeline stages 3→4→5 — search, collect (with upload merge), screen | Each stage processes and passes candidates down the chain; uploaded files enter at the collect stage naturally |
| **Adapter** | `PdfIngestor` adapts raw PDF bytes → `Paper` domain model | Converts external format (PDF binary) into internal representation, matching the existing `LiteratureSource` adapter pattern in `AdapterBundle` |
| **Factory** | `Paper.from_uploaded_pdf(path, llm=None) -> Paper` classmethod | Encapsulates the creation logic; keeps the `Paper` dataclass as the single source of truth for paper representation |
| **Repository** | File-based artifact store (`stage-NN/*.jsonl`) already acts as a repository | No change needed — uploaded papers are serialized into the same JSONL format and become part of the existing repository |
| **Observer** | WebSocket events emitted on upload completion | Existing `ConnectionManager` (`berb/server/websocket/manager.py`) can broadcast upload progress; follows the event-driven pattern already used for pipeline stage events |

---

## Implementation Steps

### Phase 1: PDF Ingestion Core

#### Step 1.1 — Create `berb/literature/pdf_ingestor.py`

New module with three tiers of PDF extraction:

```
extract_text_from_pdf(path: Path) -> str
    → PyPDF2.PdfReader — extracts plain text from all pages

extract_metadata(path: Path) -> dict[str, str]
    → Reads PDF document-info dictionary (title, author, subject)
    → Reads XMP metadata for DOI if present

pdf_to_paper(path: Path, llm: LLMClient | None = None) -> Paper
    → Tier 1: Use embedded PDF metadata for title/authors
    → Tier 2: Regex-heuristic extraction from first 2000 chars of text
    → Tier 3: LLM-assisted extraction (if llm provided) — prompt the LLM
      to extract structured metadata from text
    → Returns a Paper with source="upload", source_id=sha256(path)

ingest_pdfs(paths: list[Path], llm: LLMClient | None = None) -> list[Paper]
    → Batch version; parallelizes where possible; logs per-file results
```

**Dependencies:** `PyPDF2` (lightweight, pure Python) — add to
`pyproject.toml` optional-deps `[all]` and `[literature]`.

**Error handling:** Malformed/corrupt PDFs log a warning and are skipped;
password-protected PDFs log an error. Individual file failures never block
the batch.

#### Step 1.2 — Unit tests for `pdf_ingestor`

File: `tests/test_berb_pdf_ingestor.py`

- `test_extract_text_from_valid_pdf` — uses a minimal PDF generated in-test
- `test_extract_text_from_corrupt_pdf` — returns empty string, logs warning
- `test_extract_metadata_with_doi` — reads XMP metadata
- `test_pdf_to_paper_without_llm` — heuristic extraction only
- `test_pdf_to_paper_with_llm` — mocked LLM returns structured response
- `test_ingest_pdfs_batch` — multiple files, one corrupt, verify skip behavior

---

### Phase 2: Config & Pipeline Integration

#### Step 2.1 — Add `uploaded_file_paths` to `ResearchConfig`

File: `berb/config.py`, line 134–140

```diff
 @dataclass(frozen=True)
 class ResearchConfig:
     topic: str
     domains: tuple[str, ...] = ()
     daily_paper_count: int = 0
     quality_threshold: float = 0.0
     graceful_degradation: bool = True
+    uploaded_file_paths: tuple[str, ...] = ()
+    """Absolute paths to user-uploaded PDFs/data files for ingestion."""
```

Frozen dataclass — callers must use `dataclasses.replace()` to set it.
Follows the existing pattern for `topic` override in `cmd_run()` (cli.py:233).

#### Step 2.2 — Modify `_execute_literature_collect` to ingest uploads

File: `berb/pipeline/stage_impls/_literature.py`, function
`_execute_literature_collect` (starts ~line 374)

Insert **after** API search results are collected and **before** deduplication:

```python
# --- Ingest uploaded PDFs (tier 0) ---
uploaded_paths = config.research.uploaded_file_paths
if uploaded_paths:
    from berb.literature.pdf_ingestor import ingest_pdfs
    logger.info("Ingesting %d uploaded PDF(s)...", len(uploaded_paths))
    uploaded_papers = ingest_pdfs(
        [Path(p) for p in uploaded_paths],
        llm=adapters.llm,  # LLM-assisted metadata extraction
    )
    # Tag with source for traceability
    for paper in uploaded_papers:
        paper_dict = _paper_to_dict(paper)
        paper_dict["source"] = "upload"
        all_candidates.append(paper_dict)
    logger.info("Ingested %d papers from uploads.", len(uploaded_papers))
```

The `all_candidates` list then proceeds through deduplication and writing to
`candidates.jsonl` as normal. Uploaded papers participate in Stage 5 screening
and Stage 6 knowledge extraction on equal footing with API results.

**Contract impact:** None. `input_files` and `output_files` for
LITERATURE_COLLECT remain `("search_plan.yaml",)` → `("candidates.jsonl",)`.
Uploaded files are an optional auxiliary input, not a contract requirement.

#### Step 2.3 — Ensure `_paper_to_dict` helper exists

Check if `_execute_literature_collect` already has a paper→dict serializer.
If not, add a small helper that converts `Paper` fields to the JSONL dict
format matching what API search results produce. The `Paper` dataclass is at
`berb/literature/models.py`.

---

### Phase 3: API Upload Endpoint

#### Step 3.1 — Create `berb/server/routes/uploads.py`

Following the pattern of `berb/server/routes/voice.py`:

```python
"""File upload API routes for Berb Web UI."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["uploads"])

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB
ALLOWED_EXTENSIONS = {".pdf", ".csv", ".json", ".jsonl", ".txt", ".md"}


@router.post("/uploads")
async def upload_files(
    files: list[UploadFile] = File(...),
    run_id: str | None = None,
) -> dict:
    """Upload one or more files for a research run.

    Saves files to uploads/{run_id}/ (or a temp dir if no run_id).
    Returns a list of saved file paths for use in job creation.
    """
    ...
```

**Key behaviors:**
- Validates file extension against `ALLOWED_EXTENSIONS`
- Rejects files > `MAX_UPLOAD_SIZE` with 413
- Computes SHA-256 of file content for deduplication
- Saves to `uploads/{run_id or 'pending'}/{sha256_prefix}_{original_name}`
- Returns `{"files": [{"path": "...", "size": N, "sha256": "..."}]}`

#### Step 3.2 — Register the uploads router in `create_app()`

File: `berb/server/app.py`, after existing router includes (~line 98):

```python
from berb.server.routes.uploads import router as uploads_router
app.include_router(uploads_router)
```

#### Step 3.3 — Add multipart support to job creation (optional enhancement)

The existing `POST /api/v1/research` (in `berb/api/server.py:145`) accepts
JSON only. For a combined upload+create flow, either:

- **Option A (simpler):** Client uploads first via `POST /api/uploads`,
  receives paths, then includes them in the JSON body of `POST /api/v1/research`
  as `uploaded_pdfs: ["/path/to/file.pdf"]`.

- **Option B (all-in-one):** Add a new `POST /api/v1/research/form` endpoint
  that accepts `multipart/form-data` with both file uploads and JSON metadata.
  This is a convenience wrapper around the two-step flow.

**Recommendation:** Start with Option A (two-step). It's simpler, debuggable,
and the separation of upload from execution allows the user to review what
was uploaded before committing budget.

---

### Phase 4: CLI Wiring

#### Step 4.1 — Wire `--upload`/`--upload-dir` in `cmd_literature()`

File: `berb/cli.py`, function `cmd_literature` (line 890)

After config load and topic override (~line 909), add:

```python
# Resolve uploaded files
uploaded: list[str] = []
if getattr(args, "upload", None):
    uploaded.extend(args.upload)
if getattr(args, "upload_dir", None):
    upload_dir = Path(args.upload_dir)
    if upload_dir.is_dir():
        uploaded.extend(str(p.resolve()) for p in upload_dir.glob("*.pdf"))
    else:
        print(f"Warning: --upload-dir not found: {args.upload_dir}", file=sys.stderr)

if uploaded:
    # Resolve all paths to absolute
    resolved = [str(Path(p).resolve()) for p in uploaded]
    missing = [p for p in resolved if not Path(p).exists()]
    if missing:
        print(f"Warning: {len(missing)} file(s) not found: {missing}", file=sys.stderr)
    existing = [p for p in resolved if Path(p).exists()]
    if existing:
        config = dataclasses.replace(
            config,
            research=dataclasses.replace(
                config.research,
                uploaded_file_paths=tuple(existing),
            ),
        )
        print(f"Including {len(existing)} uploaded file(s) in literature search.")
```

Same pattern for `cmd_write()` (`--data` flag already exists, line 1309).

#### Step 4.2 — Add `--upload`/`--upload-dir` to `berb run`

File: `berb/cli.py`, run subparser definition (lines 1161–1183)

```python
_ = run_p.add_argument("--upload", nargs="+", help="Upload PDFs for literature inclusion")
_ = run_p.add_argument("--upload-dir", help="Upload directory of PDFs")
```

Wire in `cmd_run()` with the same resolution logic as step 4.1.

---

### Phase 5: Frontend

#### Step 5.1 — Add file upload to Wizard view

File: `berb/ui/web/src/views/Wizard.tsx`

Add a file input section to the research creation form:

```tsx
const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
const [uploadedPaths, setUploadedPaths] = useState<string[]>([]);

async function handleUpload() {
  const formData = new FormData();
  uploadedFiles.forEach(f => formData.append("files", f));
  const res = await fetch("/api/uploads", { method: "POST", body: formData });
  const data = await res.json();
  setUploadedPaths(data.files.map((f: any) => f.path));
}
```

#### Step 5.2 — Update `CreateResearchRequest` type and API client

File: `berb/ui/web/src/utils/api.ts`

Add `uploaded_pdfs?: string[]` to `CreateResearchRequest` interface and
include it in the JSON body.

File: `berb/ui/web/types/index.ts`

Already has `uploaded_pdfs?: string[]` at line 28 — no change needed.

---

### Phase 6: Testing & Validation

#### Step 6.1 — Integration test: upload → pipeline

File: `tests/e2e/test_upload_pipeline.py` (new, marked `@pytest.mark.e2e`)

- Creates a synthetic 2-page PDF with known title/abstract
- Calls `POST /api/uploads` to upload it
- Creates a research job with `uploaded_pdfs` referencing the path
- Asserts the PDF appears in `candidates.jsonl` with `source: "upload"`
- Asserts the paper survives screening (Stage 5) and extraction (Stage 6)

#### Step 6.2 — Unit test: CLI flag wiring

File: `tests/test_berb_cli.py` (add to existing)

- `test_literature_upload_flag_resolves_paths` — mocks `cmd_literature`,
  asserts `config.research.uploaded_file_paths` is set

#### Step 6.3 — Manual smoke test checklist

- [ ] `berb literature --topic "graph neural networks" --upload ./paper.pdf`
  produces `candidates.jsonl` containing the uploaded paper
- [ ] `curl -F "files=@paper.pdf" http://localhost:8000/api/uploads` returns
  saved path
- [ ] Web UI: select files via file picker, see upload confirmation, create
  job with those files

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| `PyPDF2` fails on complex PDFs (scanned, multi-column) | Medium | Three-tier extraction (metadata → heuristic → LLM) degrades gracefully |
| Uploaded PDFs confuse LLM screening (low-quality metadata) | Medium | Mark uploaded papers with `source: "upload"` so the LLM can see provenance; uploaded papers with empty abstracts still get keyword-matched |
| Large PDFs (>100 MB) exhaust memory | Low | `MAX_UPLOAD_SIZE` cap; PyPDF2 streams pages, doesn't load entire file into memory |
| Stage numbering conflict | Avoided | D1 keeps changes within existing Stage 4; no new stage added |
| Breaking existing `WorkflowConfig` serialization | Avoided | D2 uses `ResearchConfig`, not `WorkflowConfig`; no serialization format change |

---

## Summary

```
User uploads PDF ──→ POST /api/uploads ──→ saved to uploads/{run_id}/
                           │
                           ▼
              ResearchJobCreate.uploaded_pdfs: [path, ...]
                           │
                           ▼
              config.research.uploaded_file_paths
                           │
                           ▼
              execute_pipeline() ──→ Stage 4: LITERATURE_COLLECT
                           │               │
                           │   ┌───────────┘
                           │   ▼
                           │   PdfIngestor.ingest_pdfs() → Paper[]
                           │   merged into candidates.jsonl
                           │   with source="upload"
                           │
                           ▼
              Stage 5: LITERATURE_SCREEN (screens all candidates)
                           ▼
              Stage 6: KNOWLEDGE_EXTRACT (extracts cards)
                           ▼
              ... rest of pipeline unchanged ...
```
