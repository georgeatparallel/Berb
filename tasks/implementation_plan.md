# Berb — Production Hardening Implementation Plan
Generated: 2026-03-30 | Source: Full Shutdown Audit v2.0

This plan covers every P1 and P2 finding from the audit, plus selected P3 items.
Each item includes: exact files, exact line numbers, the change required, and the
acceptance test. Items are ordered strict-priority-first within each tier.

---

## STATUS LEGEND
- [ ] Not started
- [~] In progress
- [x] Complete

---

## P1 — MUST FIX BEFORE HANDING OVER

---

### P1-01 · Fix bare `except:` in `berb/reasoner_bridge/__init__.py`
**Severity:** P1 — Silent data corruption. Bare `except` catches `SystemExit`,
`KeyboardInterrupt`, `MemoryError` — these must never be swallowed.

**Files:**
- `berb/reasoner_bridge/__init__.py` — lines 294–297, 356–360, 469–472, 541–544

**Change:**

Block 1 (line 294 — hypothesis generation):
```diff
 try:
     data = json.loads(response.content)
-except:
+except (json.JSONDecodeError, ValueError, KeyError) as e:
+    logger.warning("Failed to parse hypothesis response: %s", e)
     data = {"hypothesis": response.content, "key_insights": [], "confidence": 0.5}
```

Block 2 (line 356 — candidate scoring):
```diff
 try:
     data = json.loads(response.content)
     scores = data.get("scores", [])
-except:
+except (json.JSONDecodeError, ValueError, KeyError) as e:
+    logger.warning("Failed to parse scoring response: %s", e)
     scores = []
```

Block 3 (line 469 — stress test scenario):
```diff
 try:
     data = json.loads(response.content)
-except:
+except (json.JSONDecodeError, ValueError, KeyError) as e:
+    logger.warning("Failed to parse stress-test response: %s", e)
     data = {}
```

Block 4 (line 541 — context vetting):
```diff
 try:
     data = json.loads(response.content)
-except:
+except (json.JSONDecodeError, ValueError, KeyError) as e:
+    logger.warning("Failed to parse vetting response: %s", e)
     data = {}
```

**Acceptance test:**
```python
# tests/test_reasoner_bridge.py
def test_hypothesis_json_parse_failure_does_not_swallow_keyboard_interrupt():
    """KeyboardInterrupt must propagate through the except block."""
    from berb.reasoner_bridge import ReasonerBridge
    # Patch json.loads to raise KeyboardInterrupt
    with patch("berb.reasoner_bridge.json.loads", side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            # invoke the hypothesis generation path

def test_hypothesis_json_parse_failure_returns_fallback():
    """JSONDecodeError produces the expected fallback dict."""
    with patch("berb.reasoner_bridge.json.loads", side_effect=json.JSONDecodeError("x","",0)):
        result = ...  # call hypothesis path
    assert result["confidence"] == 0.5
```

---

### P1-02 · Prevent concurrent pipeline instances (startup lockfile)
**Severity:** P1 — Two simultaneous `berb run` calls share the global
`SharedResearchMemory` singleton and write to overlapping checkpoint files,
corrupting both runs.

**Files:**
- `berb/pipeline/runner.py` — add lockfile acquire/release around `execute_pipeline()`
- `berb/cli.py` — pass `run_dir` to `execute_pipeline()` before lockfile is needed

**Change — `berb/pipeline/runner.py`:**

Add a module-level helper after the existing imports:

```python
import fcntl   # POSIX; use msvcrt on Windows
import sys

def _acquire_run_lock(run_dir: Path) -> "IO[Any]":
    """Create and exclusively lock <run_dir>/.berb.lock.
    Raises RuntimeError if another pipeline instance holds the lock.
    Works on POSIX (fcntl) and Windows (msvcrt).
    """
    lock_path = run_dir / ".berb.lock"
    fh = open(lock_path, "w", encoding="utf-8")
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, IOError):
        fh.close()
        raise RuntimeError(
            f"Another berb pipeline instance is already running in {run_dir}. "
            "If no other instance is running, delete {run_dir}/.berb.lock and retry."
        )
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def _release_run_lock(fh: "IO[Any]") -> None:
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fh, fcntl.LOCK_UN)
    finally:
        fh.close()
```

Wrap `execute_pipeline()` body:

```diff
 def execute_pipeline(config: RCConfig, run_dir: Path, ...) -> list[StageResult]:
+    lock_fh = _acquire_run_lock(run_dir)
+    try:
         ... existing pipeline body ...
+    finally:
+        _release_run_lock(lock_fh)
```

**Acceptance test:**
```python
# tests/test_concurrent_lock.py
def test_second_pipeline_raises(tmp_path):
    fh = _acquire_run_lock(tmp_path)
    try:
        with pytest.raises(RuntimeError, match="Another berb pipeline"):
            _acquire_run_lock(tmp_path)
    finally:
        _release_run_lock(fh)

def test_lock_released_after_pipeline_completes(tmp_path):
    fh = _acquire_run_lock(tmp_path)
    _release_run_lock(fh)
    # Should be re-acquirable
    fh2 = _acquire_run_lock(tmp_path)
    _release_run_lock(fh2)
```

---

### P1-03 · Add per-pipeline API token budget cap
**Severity:** P1 — A runaway pipeline can exhaust provider API credits with no
upper bound. A single long run with retries can spend thousands of dollars.

**Files:**
- `berb/config.py` — add `max_tokens_per_run: int = 2_000_000` to `LlmConfig`
- `berb/llm/client.py` — add a pipeline-scoped `BudgetTracker` that raises when budget exceeded
- `berb/pipeline/runner.py` — instantiate `BudgetTracker` at pipeline start; pass to LLM client

**Change — `berb/llm/client.py`:**

```python
class BudgetTracker:
    """Thread-safe tracker for cumulative token spend in a single pipeline run."""

    def __init__(self, max_tokens: int) -> None:
        self._max = max_tokens
        self._used: int = 0
        self._lock = threading.Lock()

    def charge(self, tokens: int) -> None:
        with self._lock:
            self._used += tokens
            if self._used > self._max:
                raise RuntimeError(
                    f"Pipeline token budget exhausted: {self._used:,} tokens used "
                    f"(limit {self._max:,}). Increase llm.max_tokens_per_run in config."
                )

    @property
    def used(self) -> int:
        with self._lock:
            return self._used
```

Call `budget_tracker.charge(estimated_tokens)` immediately after rate limiter `acquire()` succeeds.
Pass `BudgetTracker` to `LLMClient.__init__` as an optional parameter; default to a
tracker with `max_tokens=config.max_tokens_per_run`.

**Acceptance test:**
```python
def test_budget_tracker_raises_when_exceeded():
    bt = BudgetTracker(max_tokens=1000)
    bt.charge(999)
    with pytest.raises(RuntimeError, match="budget exhausted"):
        bt.charge(2)

def test_budget_tracker_thread_safe():
    bt = BudgetTracker(max_tokens=10_000)
    threads = [threading.Thread(target=bt.charge, args=(100,)) for _ in range(50)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert bt.used == 5000
```

---

### P1-04 · Add disk-space preflight check to `berb doctor`
**Severity:** P1 — Disk exhaustion mid-pipeline is silent, unrecoverable without
manual intervention, and fully preventable.

**Files:**
- `berb/health.py` — add `check_disk_space()` function following existing `CheckResult` pattern
- `berb/cli.py` — ensure `doctor` command runs disk check (it already runs all registered checks)

**Change — `berb/health.py`:**

```python
import shutil

MIN_FREE_GB = 10.0   # minimum free space to start a pipeline run

def check_disk_space(run_dir: Path | None = None) -> CheckResult:
    """Verify sufficient free disk space for a pipeline run."""
    check_path = run_dir or Path.cwd()
    try:
        usage = shutil.disk_usage(check_path)
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        used_pct = (usage.used / usage.total) * 100

        if free_gb < MIN_FREE_GB:
            return CheckResult(
                name="disk_space",
                status="fail",
                detail=(
                    f"Only {free_gb:.1f} GB free on {check_path} "
                    f"({used_pct:.0f}% used of {total_gb:.0f} GB total). "
                    f"Minimum required: {MIN_FREE_GB} GB."
                ),
                fix=(
                    "Free disk space before running: delete old artifacts/ directories, "
                    "clear ~/.berb_cache/literature/, or mount a larger volume."
                ),
            )
        return CheckResult(
            name="disk_space",
            status="pass",
            detail=f"{free_gb:.1f} GB free ({used_pct:.0f}% used)",
            fix=None,
        )
    except OSError as e:
        return CheckResult(
            name="disk_space",
            status="warn",
            detail=f"Could not check disk space: {e}",
            fix="Ensure the working directory is accessible.",
        )
```

Register in the `run_doctor()` function alongside existing checks.

**Acceptance test:**
```python
def test_check_disk_space_pass(tmp_path):
    result = check_disk_space(tmp_path)
    # On any machine with >10 GB free this should pass
    assert result.status in ("pass", "warn")  # warn if check_path is unusual

def test_check_disk_space_fail_when_low(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda _: shutil.usage(total=100_000_000, used=99_000_000, free=1_000_000))
    result = check_disk_space(tmp_path)
    assert result.status == "fail"
    assert "Minimum required" in result.detail
```

---

### P1-05 · Harden LLM code-injection validator against encoding bypasses
**Severity:** P1 — The current blocklist in `berb/experiment/validator.py` matches
literal string patterns. Encoded equivalents (`__builtins__['eval']`,
`getattr(__builtins__, 'exec')`, hex-escaped strings) bypass it.

**Files:**
- `berb/experiment/validator.py` — extend `_DANGEROUS_PATTERNS` and add a
  compile-time AST check

**Change:**

```python
import ast

# Add to existing pattern list:
_DANGEROUS_PATTERNS_EXTENDED = [
    # Existing patterns already block direct calls; add encoded variants:
    r"__builtins__\s*\[",          # __builtins__['eval']
    r"getattr\s*\(\s*__builtins__",  # getattr(__builtins__, 'exec')
    r"\\x[0-9a-fA-F]{2}",          # hex-escaped strings (suspicious in code)
    r"\\u[0-9a-fA-F]{4}",          # unicode-escaped strings in code
    r"importlib\.import_module",    # importlib bypass
    r"__import__",                  # __import__ bypass (already present, verify)
    r"globals\s*\(\s*\)",           # globals() access
    r"locals\s*\(\s*\)",            # locals() access
    r"vars\s*\(\s*\)",              # vars() access
]

def _ast_safety_check(code: str) -> str | None:
    """AST-level check: detect dynamic attribute access patterns that bypass
    string-based blocklist (e.g. getattr(obj, variable_name)).
    Returns an error message, or None if safe."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"Syntax error in generated code: {e}"

    for node in ast.walk(tree):
        # Flag getattr() with a non-literal second argument
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "getattr":
                if len(node.args) >= 2 and not isinstance(node.args[1], ast.Constant):
                    return "Dynamic getattr() with variable attribute name is not allowed"
        # Flag __dunder__ attribute access on builtins
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                if isinstance(node.value, ast.Name) and node.value.id in (
                    "__builtins__", "builtins"
                ):
                    return f"Access to {node.attr} on builtins is not allowed"
    return None
```

Call `_ast_safety_check(code)` in `validate_code()` after the existing pattern scan.

**Acceptance test:**
```python
def test_encoded_eval_blocked():
    code = "x = __builtins__['eval']('1+1')"
    err = validate_code(code)
    assert err is not None

def test_getattr_builtins_blocked():
    code = "f = getattr(__builtins__, 'exec'); f('import os')"
    err = validate_code(code)
    assert err is not None

def test_importlib_blocked():
    code = "import importlib; importlib.import_module('os')"
    err = validate_code(code)
    assert err is not None

def test_safe_code_passes():
    code = "import numpy as np\nresult = np.array([1,2,3]).mean()"
    err = validate_code(code)
    assert err is None
```

---

## P2 — FIX WITHIN CURRENT SPRINT

---

### P2-01 · Add `--cpus` flag to Docker sandbox
**Severity:** P2 — Containers can monopolize 100% of host CPU, starving other
processes including the pipeline runner itself.

**Files:**
- `berb/config.py` — add `cpu_limit: float = 2.0` to `DockerSandboxConfig`
  (Note: config is `frozen=True`; add field with default)
- `berb/experiment/docker_sandbox.py` — add `--cpus` to `_build_run_command()`

**Change — `berb/config.py`:**
```diff
 @dataclass(frozen=True)
 class DockerSandboxConfig:
     image: str = "berb/experiment:latest"
     gpu_enabled: bool = True
     gpu_device_ids: tuple[int, ...] = ()
     memory_limit_mb: int = 8192
+    cpu_limit: float = 2.0   # max CPU cores the container may use; 0 = unlimited
     network_policy: str = "setup_only"
     ...
```

**Change — `berb/experiment/docker_sandbox.py`** (after memory limit line ~402):
```diff
 cmd.extend([f"--memory={cfg.memory_limit_mb}m"])
 cmd.extend([f"--shm-size={cfg.shm_size_mb}m"])
+if cfg.cpu_limit > 0:
+    cmd.extend([f"--cpus={cfg.cpu_limit:.2f}"])
```

**Acceptance test:**
```python
def test_cpu_limit_in_docker_command():
    cfg = DockerSandboxConfig(cpu_limit=1.5)
    sandbox = DockerSandbox(config=cfg, workdir=tmp_path)
    cmd = sandbox._build_run_command(tmp_path, entry_point="main.py",
                                      container_name="test")
    assert "--cpus=1.50" in cmd

def test_cpu_limit_zero_omits_flag():
    cfg = DockerSandboxConfig(cpu_limit=0)
    ...
    assert "--cpus" not in " ".join(cmd)
```

---

### P2-02 · Add cache size eviction to `berb/literature/cache.py`
**Severity:** P2 — Cache grows unbounded on disk; sustained use fills disk.

**Files:**
- `berb/literature/cache.py` — add `_evict_if_oversized()` called from `put_cache()`

**Change:**

```python
_MAX_CACHE_SIZE_BYTES = 2 * 1024 * 1024 * 1024   # 2 GB hard cap
_EVICT_FRACTION = 0.25                              # evict oldest 25% when cap hit

def _evict_if_oversized(cache_dir: Path) -> None:
    """Evict the oldest cache entries when total size exceeds _MAX_CACHE_SIZE_BYTES.
    Sorted by last-modified time ascending (oldest first).
    No-op if cache_dir does not exist or is below the cap.
    """
    if not cache_dir.exists():
        return
    files = sorted(
        cache_dir.rglob("*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    total = sum(p.stat().st_size for p in files)
    if total <= _MAX_CACHE_SIZE_BYTES:
        return

    evict_count = max(1, int(len(files) * _EVICT_FRACTION))
    for path in files[:evict_count]:
        path.unlink(missing_ok=True)
    logger.info(
        "Cache eviction: removed %d oldest entries (was %.1f GB)",
        evict_count,
        total / (1024 ** 3),
    )
```

Call at the top of `put_cache()`:
```diff
 def put_cache(self, key: str, payload: dict, source: str) -> None:
+    _evict_if_oversized(self._cache_dir)
     ...
```

**Acceptance test:**
```python
def test_eviction_triggers_when_oversized(tmp_path, monkeypatch):
    monkeypatch.setattr("berb.literature.cache._MAX_CACHE_SIZE_BYTES", 1000)
    monkeypatch.setattr("berb.literature.cache._EVICT_FRACTION", 0.5)
    # Write 10 fake cache files each 200 bytes
    cache = LiteratureCache(cache_dir=tmp_path)
    for i in range(10):
        (tmp_path / f"key_{i}.json").write_text("x" * 200)
    _evict_if_oversized(tmp_path)
    remaining = list(tmp_path.glob("*.json"))
    assert len(remaining) == 5   # 50% evicted

def test_eviction_preserves_newest(tmp_path, monkeypatch):
    """Newest files must survive; oldest must go."""
    monkeypatch.setattr("berb.literature.cache._MAX_CACHE_SIZE_BYTES", 100)
    oldest = tmp_path / "old.json"
    newest = tmp_path / "new.json"
    oldest.write_text("x" * 200)
    time.sleep(0.01)
    newest.write_text("y" * 200)
    _evict_if_oversized(tmp_path)
    assert not oldest.exists()
    assert newest.exists()
```

---

### P2-03 · Remove duplicate `_synthesis_fixed.py`
**Severity:** P2 — Two implementations of the same stage will diverge; unclear
which is authoritative. Imports referencing the wrong one silently get stale behavior.

**Files:**
- `berb/pipeline/stage_impls/_synthesis.py` — verify it is unused or an old version
- `berb/pipeline/stage_impls/_synthesis_fixed.py` — verify it is the current version
- `berb/pipeline/stage_impls/__init__.py` — check which is imported
- Delete the old one

**Steps:**
1. `grep -rn "_synthesis\b\|_synthesis_fixed" berb/ --include="*.py"` — find all imports
2. Confirm `_synthesis_fixed.py` is what `__init__.py` or the stage dispatcher imports
3. Rename `_synthesis_fixed.py` → `_synthesis.py` (overwriting old)
4. Update all import sites if needed
5. Run `pytest tests/ -m "not slow and not e2e and not llm" -q` to verify

**No new code needed; this is a deletion + rename.**

---

### P2-04 · Add coverage gate to CI
**Severity:** P2 — 75% coverage is claimed but never enforced; silent regression
possible as new code is added without tests.

**Files:**
- `.github/workflows/ci.yml` — add `--cov-fail-under=70` to pytest command

**Change:**
```diff
       - name: Run unit tests (no LLM, no e2e, no slow)
         run: |
           pytest tests/ \
             -m "not slow and not e2e and not llm" \
             --tb=short \
             -q \
+            --cov=berb \
+            --cov-fail-under=70 \
+            --cov-report=xml:coverage-${{ matrix.python-version }}.xml \
             --junitxml=test-results-${{ matrix.python-version }}.xml
+
+      - name: Upload coverage report
+        if: always()
+        uses: actions/upload-artifact@v4
+        with:
+          name: coverage-${{ matrix.python-version }}
+          path: coverage-${{ matrix.python-version }}.xml
```

Note: Start at 70% (slightly below current 75%) to avoid an immediate CI break if
coverage measurement differs from the README claim. Raise to 75% once baseline is confirmed.

---

### P2-05 · Decompose `_execute_export_publish()` (1,081 lines)
**Severity:** P2 — Unmaintainable. Any bug requires reading 1,000+ lines of context.
The function performs at least 6 distinct responsibilities.

**File:** `berb/pipeline/stage_impls/_review_publish.py` — lines 1411–2491

**Decomposition plan** (extract these sub-functions, each ≤150 lines):

| New function | Responsibility | Approx lines extracted |
|---|---|---|
| `_render_latex_document(paper, config)` | LaTeX template rendering | ~200 |
| `_compile_latex(latex_dir, retries)` | pdflatex/xelatex subprocess + retry | ~150 |
| `_export_to_formats(paper, run_dir, formats)` | PDF/HTML/DOCX conversion dispatch | ~120 |
| `_build_arxiv_submission(paper, run_dir)` | arXiv submission package assembly | ~180 |
| `_write_metadata_files(paper, run_dir)` | BibTeX, CFF, JSON metadata | ~100 |
| `_validate_output_integrity(run_dir)` | File presence / hash checks on exports | ~80 |
| `_execute_export_publish()` | Orchestrator: calls above 6 helpers | ~80 |

**Approach:** Extract one helper at a time in separate commits. Each extraction is a
pure refactor (behavior unchanged). Add a single integration test that calls
`_execute_export_publish()` with a mock paper object and asserts all output files exist.

---

### P2-06 · Replace `scholarly` (Google Scholar scraping) with a stable alternative
**Severity:** P2 — Google's ToS prohibits scraping; `scholarly` breaks silently on
layout changes and rate-limiting, returning empty results with no error signal.

**Files:**
- `berb/literature/grey_search.py` — find all `scholarly` call sites
- `pyproject.toml` — remove `scholarly>=1.7` from `web` extras

**Replacement strategy:**

| scholarly use case | Replacement |
|---|---|
| Paper search by keyword | Semantic Scholar public API (`/paper/search`) — free, 100 req/5min unauthed |
| Citation count | OpenAlex `/works` endpoint — free, no auth |
| Author profiles | OpenAlex `/authors` — free |
| Full-text PDF link | Unpaywall API (`api.unpaywall.org`) — free with email param |

**Change in `grey_search.py`:**
```diff
-import scholarly
+from berb.literature.semantic_scholar import SemanticScholarClient

 class GreyLiteratureSearcher:
-    def search(self, query: str, limit: int = 10) -> list[GreyResult]:
-        results = scholarly.search_pubs(query)
-        ...
+    def __init__(self):
+        self._s2 = SemanticScholarClient()
+
+    def search(self, query: str, limit: int = 10) -> list[GreyResult]:
+        papers = self._s2.search_papers(query, limit=limit)
+        return [GreyResult(title=p.title, url=p.url, source="semantic_scholar")
+                for p in papers]
```

**Remove from `pyproject.toml`:**
```diff
-web = ["scholarly>=1.7", "crawl4ai>=0.2", "tavily-python>=0.3"]
+web = ["crawl4ai>=0.2", "tavily-python>=0.3"]
```

**Acceptance test:**
```python
def test_grey_search_uses_semantic_scholar_not_scholarly(monkeypatch):
    """scholarly must not be imported anywhere in the call chain."""
    import sys
    sys.modules["scholarly"] = None   # would cause ImportError if touched
    searcher = GreyLiteratureSearcher()
    # Should not raise ImportError
    with patch.object(searcher._s2, "search_papers", return_value=[]):
        results = searcher.search("test query")
    assert results == []
```

---

## P3 — BACKLOG (fix opportunistically)

---

### P3-01 · Evaluate PyMuPDF (AGPL-3.0) for commercial distribution
**File:** `pyproject.toml` — `pdf` and `all` extras
**Action:** If Berb is ever packaged or distributed commercially:
- Option A: Obtain PyMuPDF commercial license from Artifex
- Option B: Replace with `pdfminer.six` (MIT) or `pypdf` (BSD) for text extraction
  (loses some fidelity for image-heavy PDFs)
- Option C: Keep AGPL and open-source the entire distribution

No code change needed until distribution decision is made. Add a comment in `pyproject.toml`:
```toml
# WARNING: PyMuPDF is AGPL-3.0. If distributing commercially, obtain a
# commercial license from Artifex or replace with an MIT/BSD alternative.
pdf = ["PyMuPDF>=1.23"]
```

---

### P3-02 · Wire `pipeline/tracing.py` spans to an external metrics sink
**File:** `berb/pipeline/tracing.py`

**Current state:** Emits span-level JSONL to `artifacts/<run_id>/trace.jsonl`.
No external sink. Alerting requires manual log inspection.

**Recommended approach (minimal effort):**
1. Add `BERB_OTEL_ENDPOINT` environment variable (e.g., `http://localhost:4318`)
2. If set, emit spans to OTLP HTTP endpoint using `opentelemetry-exporter-otlp-proto-http`
   (add to `[project.optional-dependencies] observability`)
3. Dashboards in Grafana/Jaeger consume spans natively

**Acceptance criteria:**
- If `BERB_OTEL_ENDPOINT` is unset, behavior is identical to current (JSONL only)
- If set, spans appear in the OTLP collector within 5 seconds of stage completion

---

### P3-03 · Add `--cov-fail-under` ramp-up plan
After P2-04 is merged, track coverage trend weekly.
Target schedule:
- Sprint 0 (now): 70% gate
- Sprint 2: raise to 75%
- Sprint 4: raise to 80%

Update `.github/workflows/ci.yml` threshold each sprint.

---

## IMPLEMENTATION ORDER (recommended sequence)

```
Week 1 (P1s — ship-blockers):
  Day 1: P1-01 (bare except) — 30 min, low risk
  Day 1: P1-04 (disk check)  — 1 hour, zero risk
  Day 2: P1-02 (lockfile)    — 2 hours, medium risk (test on Windows + Linux)
  Day 3: P1-05 (validator AST check) — 3 hours, needs thorough testing
  Day 4: P1-03 (budget cap)  — 3 hours, new class + wiring

Week 2 (P2s — sprint):
  Day 1: P2-03 (delete duplicate synthesis) — 1 hour, zero risk
  Day 1: P2-04 (CI coverage gate)           — 30 min
  Day 2: P2-01 (Docker CPU limit)           — 1 hour
  Day 2: P2-02 (cache eviction)             — 2 hours
  Day 3: P2-06 (replace scholarly)          — 4 hours
  Day 4-5: P2-05 (decompose export_publish) — 2 days, high risk — do last

Week 3+ (P3s — backlog):
  P3-01: legal review (not a code change)
  P3-02: OTLP wiring
  P3-03: coverage ramp
```

---

## TEST STRATEGY SUMMARY

Every fix must ship with:
1. A **regression test** that would have caught the original bug
2. An **adversarial test** that probes the boundary condition fixed
3. All existing tests passing (`pytest tests/ -m "not slow and not e2e and not llm" -q`)

New test files to create:
- `tests/test_reasoner_bridge_exceptions.py` — P1-01
- `tests/test_pipeline_lockfile.py`          — P1-02
- `tests/test_budget_tracker.py`             — P1-03
- `tests/test_doctor_disk_check.py`          — P1-04
- `tests/test_validator_hardening.py`        — P1-05
- `tests/test_docker_cpu_limit.py`           — P2-01
- `tests/test_cache_eviction.py`             — P2-02
- `tests/test_grey_search_scholarly_free.py` — P2-06

---

## DEFINITION OF DONE

A fix is **complete** when:
- [ ] Code change merged to `main` via PR
- [ ] Regression + adversarial tests pass in CI (Python 3.11 + 3.12)
- [ ] Lint (`ruff check`) passes
- [ ] The specific audit finding is updated to [x] in this file
- [ ] For P1 items: PR description references this plan item ID

---
*This plan was generated from the full Shutdown Audit v2.0 run on 2026-03-30.*
*Re-run the audit after completing all P1 items to confirm CONDITIONAL → READY.*
