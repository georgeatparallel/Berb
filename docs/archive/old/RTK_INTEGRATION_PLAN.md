# RTK Integration Plan for AutoResearchClaw

**Document Created:** 2026-03-26
**Status:** Analysis Complete | Planning Phase

---

## Executive Summary

**RTK (Rust Token Killer)** is a high-performance CLI proxy that minimizes LLM token consumption through intelligent output filtering and compression. Integrating RTK with AutoResearchClaw would provide:

1. **Token consumption tracking** - Measure and optimize LLM API costs
2. **Intelligent output filtering** - Compress command outputs by 60-90%
3. **Project-scoped analytics** - Track token usage per research project
4. **Cost optimization** - Reduce API costs by 70%+ for CLI-heavy operations
5. **Execution time tracking** - Monitor command performance
6. **Gain reporting** - Visualize token savings over time

**Expected Impact:**
- **-70%** token consumption for CLI operations
- **-60%** API costs for experiment execution
- **100% visibility** into token usage patterns
- **Better budgeting** with project-scoped tracking

---

## RTK Architecture Analysis

### Core Components

| Component | File | Purpose | AutoResearchClaw Integration Point |
|-----------|------|---------|-----------------------------------|
| **Tracker** | `tracking.rs` | SQLite-based token tracking | Add to `berb/utils/` |
| **Filter Engine** | `filter.rs` | Language-aware code filtering | Use for experiment output compression |
| **Gain Reporter** | `gain.rs` | Token savings analytics | Integrate with dashboard |
| **Command Modules** | `src/*_cmd.rs` | Optimized command implementations | Reuse patterns for AutoResearchClaw CLI |
| **Hook System** | `init.rs`, `rewrite_cmd.rs` | Claude Code hook integration | Adapt for AutoResearchClaw hooks |

### Key Features

| Feature | Description | AutoResearchClaw Benefit |
|---------|-------------|--------------------------|
| **Token Tracking** | SQLite database with 90-day retention | Track per-project token usage |
| **Output Filtering** | 60-90% compression for common commands | Reduce experiment output size |
| **Project Scoping** | Filter by project path | Isolate research project costs |
| **Gain Analytics** | Daily/weekly/monthly reports | Show cost savings to users |
| **Hook Integration** | Transparent command rewriting | Auto-optimize without user action |
| **Ultra-Compact Mode** | ASCII icons, inline format | Maximum token savings |

### Token Savings Data

**Typical 30-min session:**

| Operation | Standard | RTK | Savings |
|-----------|----------|-----|---------|
| `ls` / `tree` | 2,000 | 400 | -80% |
| `cat` / `read` | 40,000 | 12,000 | -70% |
| `grep` / `rg` | 16,000 | 3,200 | -80% |
| `git status` | 3,000 | 600 | -80% |
| `git diff` | 10,000 | 2,500 | -75% |
| `npm test` | 25,000 | 2,500 | -90% |
| `pytest` | 8,000 | 800 | -90% |
| **Total** | **~118,000** | **~23,900** | **-80%** |

---

## Integration Approaches

### Approach 1: RTK as Dependency (Recommended)

**Architecture:**
```
AutoResearchClaw Pipeline
         │
         ▼
┌─────────────────────────┐
│  RTK Tracker (Rust)     │
│  - track()              │
│  - get_summary()        │
│  - project-scoped       │
└───────────┬─────────────┘
            │ FFI bindings
            ▼
┌─────────────────────────┐
│  AutoResearchClaw       │
│  - Token dashboard      │
│  - Cost analytics       │
│  - Budget alerts        │
└─────────────────────────┘
```

**Implementation:**
```python
# berb/utils/token_tracker.py

import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    saved_tokens: int
    savings_pct: float
    execution_time_ms: int
    command: str
    project_path: str

class RTKTracker:
    """Python wrapper for RTK tracking functionality."""
    
    def __init__(self, project_path: Optional[Path] = None):
        self.project_path = project_path or Path.cwd()
        self.db_path = self._get_rtk_db_path()
    
    def _get_rtk_db_path(self) -> Path:
        """Get RTK database path based on OS."""
        import sys
        if sys.platform == "win32":
            return Path.home() / "AppData" / "Roaming" / "rtk" / "tracking.db"
        elif sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "rtk" / "tracking.db"
        else:  # Linux
            return Path.home() / ".local" / "share" / "rtk" / "tracking.db"
    
    def track(
        self,
        command: str,
        rtk_command: str,
        input_text: str,
        output_text: str,
        execution_time_ms: int,
    ) -> TokenUsage:
        """Track token usage for a command execution."""
        
        input_tokens = self._estimate_tokens(input_text)
        output_tokens = self._estimate_tokens(output_text)
        saved_tokens = input_tokens - output_tokens
        savings_pct = (saved_tokens / input_tokens * 100) if input_tokens > 0 else 0
        
        # Use RTK's tracking database
        self._record_to_db(
            command, rtk_command, input_tokens, output_tokens, execution_time_ms
        )
        
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            saved_tokens=saved_tokens,
            savings_pct=savings_pct,
            execution_time_ms=execution_time_ms,
            command=command,
            project_path=str(self.project_path),
        )
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count from text.
        
        Rule of thumb: 1 token ≈ 4 characters (English text)
        For code: 1 token ≈ 3-4 characters
        """
        if not text:
            return 0
        
        # Simple estimation: characters / 4
        # More accurate: use tiktoken library
        return len(text) // 4
    
    def _record_to_db(
        self,
        command: str,
        rtk_command: str,
        input_tokens: int,
        output_tokens: int,
        execution_time_ms: int,
    ):
        """Record to RTK's SQLite database."""
        import sqlite3
        from datetime import datetime, timezone
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                project_path TEXT NOT NULL,
                command TEXT NOT NULL,
                rtk_command TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                saved_tokens INTEGER NOT NULL,
                savings_pct REAL NOT NULL,
                execution_time_ms INTEGER NOT NULL
            )
        """)
        
        # Insert record
        cursor.execute(
            """
            INSERT INTO token_usage
            (timestamp, project_path, command, rtk_command,
             input_tokens, output_tokens, saved_tokens, savings_pct, execution_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                str(self.project_path),
                command,
                rtk_command,
                input_tokens,
                output_tokens,
                input_tokens - output_tokens,
                ((input_tokens - output_tokens) / input_tokens * 100) if input_tokens > 0 else 0,
                execution_time_ms,
            ),
        )
        
        conn.commit()
        conn.close()
    
    def get_summary(self) -> dict:
        """Get token usage summary."""
        import sqlite3
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Query summary stats
        cursor.execute(
            """
            SELECT
                COUNT(*) as total_commands,
                SUM(input_tokens) as total_input,
                SUM(output_tokens) as total_output,
                SUM(saved_tokens) as total_saved,
                AVG(savings_pct) as avg_savings_pct,
                SUM(execution_time_ms) as total_time_ms
            FROM token_usage
            WHERE project_path = ?
            """,
            (str(self.project_path),),
        )
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            "total_commands": row[0] or 0,
            "total_input_tokens": row[1] or 0,
            "total_output_tokens": row[2] or 0,
            "total_saved_tokens": row[3] or 0,
            "avg_savings_pct": row[4] or 0,
            "total_execution_time_ms": row[5] or 0,
        }
    
    def get_daily_stats(self, days: int = 7) -> list[dict]:
        """Get daily token usage stats."""
        import sqlite3
        from datetime import datetime, timedelta
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Query daily stats
        cursor.execute(
            """
            SELECT
                DATE(timestamp) as date,
                COUNT(*) as commands,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens,
                SUM(saved_tokens) as saved_tokens,
                AVG(savings_pct) as savings_pct
            FROM token_usage
            WHERE project_path = ?
              AND timestamp >= datetime('now', '-{} days')
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
            """.format(days),
            (str(self.project_path),),
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "date": row[0],
                "commands": row[1],
                "input_tokens": row[2],
                "output_tokens": row[3],
                "saved_tokens": row[4],
                "savings_pct": row[5],
            }
            for row in rows
        ]
```

---

### Approach 2: RTK Filter Engine Integration

**Use RTK's filtering for experiment outputs:**

```python
# berb/experiment/output_filter.py

from enum import Enum
from typing import Literal

class FilterLevel(str, Enum):
    NONE = "none"
    MINIMAL = "minimal"
    AGGRESSIVE = "aggressive"

class ExperimentOutputFilter:
    """Filter experiment outputs to reduce token consumption.
    
    Inspired by RTK's filter.rs implementation.
    """
    
    def __init__(self, level: FilterLevel = FilterLevel.MINIMAL):
        self.level = level
    
    def filter(self, output: str, lang: str = "python") -> str:
        """Filter output based on level.
        
        Args:
            output: Raw experiment output
            lang: Programming language
        
        Returns:
            Filtered output (60-90% smaller)
        """
        if self.level == FilterLevel.NONE:
            return output
        
        if self.level == FilterLevel.MINIMAL:
            return self._filter_minimal(output, lang)
        
        if self.level == FilterLevel.AGGRESSIVE:
            return self._filter_aggressive(output, lang)
        
        return output
    
    def _filter_minimal(self, output: str, lang: str) -> str:
        """Minimal filtering: remove verbose output, keep essentials."""
        
        lines = output.split("\n")
        filtered = []
        
        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue
            
            # Skip progress bars
            if "%" in line and "[" in line and "]" in line:
                continue
            
            # Skip repetitive test output
            if line.startswith("test ") and " ... ok" in line:
                continue
            
            # Keep errors and warnings
            if "error" in line.lower() or "warning" in line.lower():
                filtered.append(line)
                continue
            
            # Keep summary lines
            if any(keyword in line for keyword in [
                "passed", "failed", "error", "total", "time:", "coverage"
            ]):
                filtered.append(line)
                continue
            
            # Limit long outputs
            if len(line) > 200:
                filtered.append(line[:200] + "... [truncated]")
            else:
                filtered.append(line)
        
        # Limit total lines
        if len(filtered) > 50:
            filtered = filtered[:50] + ["... [output truncated]"]
        
        return "\n".join(filtered)
    
    def _filter_aggressive(self, output: str, lang: str) -> str:
        """Aggressive filtering: signatures only, strip bodies."""
        
        # For code outputs, keep only function/class signatures
        if lang == "python":
            return self._filter_python_signatures(output)
        
        # For test outputs, keep only summary
        if "test" in output.lower():
            return self._extract_test_summary(output)
        
        # Generic: keep first and last 10 lines
        lines = output.split("\n")
        if len(lines) > 20:
            return "\n".join(lines[:10] + ["... [truncated] ..."] + lines[-10:])
        
        return output
    
    def _filter_python_signatures(self, output: str) -> str:
        """Extract only Python function/class signatures."""
        import re
        
        signatures = []
        
        # Match function definitions
        for match in re.finditer(r'^(def\s+\w+\s*\([^)]*\)\s*(?:->\s*\w+)?:)', output, re.MULTILINE):
            signatures.append(match.group(1))
        
        # Match class definitions
        for match in re.finditer(r'^(class\s+\w+(?:\([^)]*\))?:)', output, re.MULTILINE):
            signatures.append(match.group(1))
        
        if signatures:
            return "\n".join(signatures)
        
        # Fallback to minimal filter
        return self._filter_minimal(output, "python")
    
    def _extract_test_summary(self, output: str) -> str:
        """Extract only test summary."""
        import re
        
        # Look for pytest/unittest summary
        summary_patterns = [
            r'(\d+ passed.*\d+ failed.*)',
            r'(PASSED|FAILED).*',
            r'(test session starts.*?=====)',
        ]
        
        for pattern in summary_patterns:
            match = re.search(pattern, output, re.DOTALL)
            if match:
                return match.group(1)
        
        # Fallback: last 10 lines
        lines = output.split("\n")
        return "\n".join(lines[-10:])
```

---

### Approach 3: RTK CLI Integration

**Use RTK binary directly for command optimization:**

```python
# berb/utils/rtk_cli.py

import subprocess
from pathlib import Path
from typing import Optional

class RTKCLI:
    """Wrapper for RTK CLI binary."""
    
    def __init__(self, rtk_path: Optional[str] = None):
        self.rtk_path = rtk_path or self._find_rtk()
    
    def _find_rtk(self) -> str:
        """Find RTK binary in PATH."""
        import shutil
        rtk = shutil.which("rtk")
        if not rtk:
            raise RuntimeError(
                "RTK not found in PATH. Install with: "
                "curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/master/install.sh | sh"
            )
        return rtk
    
    def run(self, command: str, args: list[str], ultra_compact: bool = False) -> str:
        """Run command through RTK.
        
        Args:
            command: Command to run (e.g., "git", "pytest")
            args: Command arguments
            ultra_compact: Use ultra-compact mode for max savings
        
        Returns:
            Filtered output
        """
        cmd = [self.rtk_path, command] + args
        
        if ultra_compact:
            cmd.insert(1, "-u")  # Ultra-compact flag
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min timeout
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"RTK command failed: {result.stderr}")
        
        return result.stdout
    
    def gain(self, project: bool = False, daily: bool = False) -> dict:
        """Get token savings report.
        
        Args:
            project: Show project-scoped stats
            daily: Show daily breakdown
        
        Returns:
            Token savings data
        """
        args = ["gain"]
        
        if project:
            args.append("--project")
        
        if daily:
            args.append("--daily")
        
        args.extend(["--format", "json"])
        
        result = subprocess.run(
            [self.rtk_path] + args,
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            return {"error": result.stderr}
        
        import json
        return json.loads(result.stdout)
    
    def init(self, global_mode: bool = True) -> str:
        """Initialize RTK for AutoResearchClaw.
        
        Args:
            global_mode: Install globally or per-project
        
        Returns:
            Setup instructions
        """
        args = ["init"]
        
        if global_mode:
            args.append("--global")
        
        result = subprocess.run(
            [self.rtk_path] + args,
            capture_output=True,
            text=True,
        )
        
        return result.stdout
```

---

## Implementation Roadmap

### Phase 1: Token Tracking (Week 1) - P0

**Goal:** Basic token tracking working

**Tasks:**
- [ ] **P0** Create `berb/utils/token_tracker.py`
  - [ ] TokenTracker class with SQLite backend
  - [ ] `track()` method for recording usage
  - [ ] `get_summary()` for analytics
  - [ ] `get_daily_stats()` for trends
  - [ ] Project-scoped tracking

- [ ] **P0** Integrate with LLM calls
  - [ ] Track tokens in `berb/llm/base.py`
  - [ ] Record input/output for each call
  - [ ] Calculate estimated costs
  - [ ] Add to stage execution results

- [ ] **P0** Add token tracking to config
  - [ ] `tracking.enabled` option
  - [ ] `tracking.project_scope` option
  - [ ] `tracking.budget_limit` option
  - [ ] `tracking.alerts` configuration

- [ ] **P0** Write unit tests
  - [ ] `tests/test_token_tracker.py`
  - [ ] Test tracking accuracy
  - [ ] Test project scoping
  - [ ] Test summary queries

- [ ] **P1** Create token dashboard widget
  - [ ] Display in berb dashboard
  - [ ] Show daily/weekly trends
  - [ ] Display cost savings
  - [ ] Budget alerts

---

### Phase 2: Output Filtering (Week 2) - P1

**Goal:** Reduce token consumption for CLI operations

**Tasks:**
- [ ] **P1** Create `berb/experiment/output_filter.py`
  - [ ] FilterLevel enum (none/minimal/aggressive)
  - [ ] Language-aware filtering
  - [ ] Test output summarization
  - [ ] Code signature extraction

- [ ] **P1** Integrate with experiment execution
  - [ ] Apply filtering in `berb/experiment/sandbox.py`
  - [ ] Filter stdout/stderr
  - [ ] Preserve error messages
  - [ ] Keep summary statistics

- [ ] **P1** Add RTK CLI wrapper
  - [ ] Create `berb/utils/rtk_cli.py`
  - [ ] Wrap common commands (git, pytest, etc.)
  - [ ] Use RTK binary if available
  - [ ] Fallback to internal filtering

- [ ] **P1** Write integration tests
  - [ ] Test filtering accuracy
  - [ ] Test token savings
  - [ ] Test error preservation
  - [ ] Benchmark performance

---

### Phase 3: Analytics & Reporting (Week 3) - P2

**Goal:** Comprehensive token usage visibility

**Tasks:**
- [ ] **P2** Create token analytics dashboard
  - [ ] Daily/weekly/monthly views
  - [ ] Per-project breakdown
  - [ ] Per-stage breakdown
  - [ ] Cost projection

- [ ] **P2** Add budget management
  - [ ] Set monthly budget limits
  - [ ] Alert at 50%/80%/100% thresholds
  - [ ] Auto-pause on budget exceeded
  - [ ] Budget forecasting

- [ ] **P2** Implement cost optimization suggestions
  - [ ] Identify high-cost stages
  - [ ] Suggest filtering improvements
  - [ ] Recommend model switches
  - [ ] Show ROI per feature

- [ ] **P2** Add export functionality
  - [ ] Export to CSV/JSON
  - [ ] Generate PDF reports
  - [ ] Integrate with billing systems
  - [ ] API for external tools

---

### Phase 4: Advanced Features (Week 4) - P2

**Goal:** Intelligent token optimization

**Tasks:**
- [ ] **P2** Implement adaptive filtering
  - [ ] Auto-adjust filter level based on budget
  - [ ] Learn from user preferences
  - [ ] Context-aware compression
  - [ ] Quality vs cost trade-offs

- [ ] **P2** Add hook integration
  - [ ] Auto-optimize CLI commands
  - [ ] Transparent command rewriting
  - [ ] PreToolUse hooks for LLM calls
  - [ ] Audit trail for rewrites

- [ ] **P2** Create token prediction model
  - [ ] Predict costs before execution
  - [ ] Suggest optimizations
  - [ ] Budget planning tool
  - [ ] What-if analysis

- [ ] **P2** Documentation
  - [ ] Token tracking guide
  - [ ] Cost optimization tips
  - [ ] Dashboard user guide
  - [ ] API reference

---

## Configuration Reference

### AutoResearchClaw Config with RTK

```yaml
# config.arc.yaml

# Token tracking (RTK integration)
tracking:
  enabled: true
  backend: "rtk"  # rtk | internal
  
  # RTK-specific settings
  rtk:
    use_binary: true  # Use RTK CLI if available
    binary_path: ""   # Empty = auto-detect from PATH
    ultra_compact: false  # Use -u flag for max savings
  
  # Project scoping
  project_scope: true  # Track per-project
  project_path: ""     # Empty = auto-detect from cwd
  
  # Budget management
  budget:
    monthly_limit_usd: 100.0
    alert_thresholds: [50, 80, 100]  # Percentage alerts
    auto_pause: false  # Pause on budget exceeded
  
  # Output filtering
  filtering:
    enabled: true
    default_level: "minimal"  # none | minimal | aggressive
    per_command:
      pytest: "aggressive"
      git_status: "minimal"
      cat: "minimal"
      ls: "minimal"
  
  # Analytics
  analytics:
    dashboard_enabled: true
    daily_report: false
    weekly_report: true
    export_format: "json"  # json | csv
  
  # Cost tracking
  costs:
    openai_rate: 0.000005  # $ per input token
    openai_output_rate: 0.000015  # $ per output token
    anthropic_rate: 0.000003
    anthropic_output_rate: 0.000015
    deepseek_rate: 0.00000014
    deepseek_output_rate: 0.00000028
```

---

## Code Examples

### Example 1: Track LLM Token Usage

```python
# berb/llm/base.py

from berb.utils.token_tracker import TokenTracker

class BaseLLMProvider:
    def __init__(self, config: RCConfig):
        self.config = config
        self.tracker = TokenTracker() if config.tracking.enabled else None
    
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
    ) -> str:
        # Track input tokens
        input_text = f"{system_prompt}\n{user_prompt}"
        input_tokens = self._estimate_tokens(input_text)
        
        # Execute LLM call
        start_time = time.time()
        response = await self._call_llm(system_prompt, user_prompt, max_tokens)
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Track output tokens
        output_tokens = self._estimate_tokens(response)
        
        # Record to tracker
        if self.tracker:
            usage = self.tracker.track(
                command=f"llm_{self.provider_name}",
                rtk_command=f"rtk llm {self.provider_name}",
                input_text=input_text,
                output_text=response,
                execution_time_ms=execution_time_ms,
            )
            
            # Log savings
            logger.info(
                f"Token usage: {input_tokens}→{output_tokens} "
                f"(saved {usage.saved_tokens}, {usage.savings_pct:.1f}%)"
            )
        
        return response
```

---

### Example 2: Filter Experiment Output

```python
# berb/experiment/sandbox.py

from berb.experiment.output_filter import ExperimentOutputFilter, FilterLevel

class SandboxExecutor:
    def __init__(self, config: RCConfig):
        self.config = config
        
        # Initialize filter based on config
        filter_level = FilterLevel(config.experiment.filtering.default_level)
        self.filter = ExperimentOutputFilter(filter_level)
    
    async def execute(
        self,
        code: str,
        timeout: int = 300,
    ) -> ExecutionResult:
        # Execute code
        result = await self._run_code(code, timeout)
        
        # Filter output if enabled
        if self.config.tracking.filtering.enabled:
            # Determine filter level for this command
            filter_level = self._get_filter_level_for_command(result.command)
            
            # Apply filtering
            result.stdout = self.filter.filter(
                result.stdout,
                lang="python",
                level=filter_level,
            )
            result.stderr = self.filter.filter(
                result.stderr,
                lang="python",
                level=filter_level,
            )
            
            # Log savings
            original_size = len(result.raw_stdout)
            filtered_size = len(result.stdout)
            savings_pct = ((original_size - filtered_size) / original_size * 100)
            
            logger.info(
                f"Output filtered: {original_size}→{filtered_size} bytes "
                f"({savings_pct:.1f}% reduction)"
            )
        
        return result
```

---

### Example 3: Token Dashboard Widget

```python
# berb/dashboard/widgets.py

from berb.utils.token_tracker import TokenTracker

def render_token_widget(tracker: TokenTracker) -> str:
    """Render token usage widget for dashboard."""
    
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    
    console = Console()
    
    # Get summary
    summary = tracker.get_summary()
    daily_stats = tracker.get_daily_stats(days=7)
    
    # Create summary table
    table = Table(title="Token Usage Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Total Commands", str(summary["total_commands"]))
    table.add_row("Input Tokens", f"{summary['total_input_tokens']:,}")
    table.add_row("Output Tokens", f"{summary['total_output_tokens']:,}")
    table.add_row("Tokens Saved", f"{summary['total_saved_tokens']:,}")
    table.add_row("Savings %", f"{summary['avg_savings_pct']:.1f}%")
    
    # Create daily chart
    daily_table = Table(title="Last 7 Days")
    daily_table.add_column("Date", style="cyan")
    daily_table.add_column("Commands", style="green")
    daily_table.add_column("Saved Tokens", style="yellow")
    
    for day in reversed(daily_stats):
        daily_table.add_row(
            day["date"],
            str(day["commands"]),
            f"{day['saved_tokens']:,}",
        )
    
    # Render panels
    console.print(Panel(table))
    console.print(Panel(daily_table))
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_token_tracker.py

import pytest
from berb.utils.token_tracker import TokenTracker, TokenUsage

@pytest.fixture
def tracker(tmp_path):
    tracker = TokenTracker(project_path=tmp_path)
    yield tracker

def test_track_command(tracker):
    usage = tracker.track(
        command="pytest",
        rtk_command="rtk pytest",
        input_text="test output" * 100,
        output_text="test output" * 20,
        execution_time_ms=150,
    )
    
    assert usage.input_tokens > 0
    assert usage.output_tokens > 0
    assert usage.saved_tokens > 0
    assert 0 < usage.savings_pct < 100

def test_get_summary(tracker):
    # Record some test data
    for i in range(10):
        tracker.track(
            command=f"cmd_{i}",
            rtk_command=f"rtk cmd_{i}",
            input_text="input" * 100,
            output_text="output" * 20,
            execution_time_ms=100,
        )
    
    summary = tracker.get_summary()
    
    assert summary["total_commands"] == 10
    assert summary["total_input_tokens"] > 0
    assert summary["total_saved_tokens"] > 0
    assert summary["avg_savings_pct"] > 0

def test_project_scoping(tracker, tmp_path):
    # Track with different project paths
    tracker2 = TokenTracker(project_path=tmp_path / "project2")
    
    tracker.track("cmd", "rtk cmd", "input", "output", 100)
    tracker2.track("cmd", "rtk cmd", "input", "output", 100)
    
    # Each project should have separate stats
    summary1 = tracker.get_summary()
    summary2 = tracker2.get_summary()
    
    assert summary1["total_commands"] == 1
    assert summary2["total_commands"] == 1
```

---

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| **Token tracking coverage** | 0% | 100% | % of LLM calls tracked |
| **CLI output reduction** | 0% | 70% | Bytes saved |
| **API cost visibility** | None | 100% | Cost dashboard |
| **Budget adherence** | N/A | <10% over budget | Monthly tracking |
| **User awareness** | Low | High | Survey scores |
| **Token savings** | 0% | 60-80% | Reduction vs baseline |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Tracking overhead** | Performance impact | Async tracking, batch inserts |
| **Inaccurate estimates** | Wrong cost projections | Use tiktoken for accuracy |
| **Database bloat** | Storage issues | 90-day retention, auto-cleanup |
| **RTK dependency** | External tool required | Fallback to internal tracking |
| **Privacy concerns** | Command logging | Local-only storage, opt-in |

---

## Next Steps

1. **Decision:** Approve Phase 1 implementation
2. **Setup:** Install RTK locally for testing
3. **Development:** Create token tracker
4. **Integration:** Add to LLM calls
5. **Testing:** Write comprehensive tests
6. **Documentation:** Write user guide

---

## References

- **RTK Repo:** `E:\Documents\Vibe-Coding\Github Projects\Token Consumption\rtk-master`
- **RTK GitHub:** https://github.com/rtk-ai/rtk
- **RTK Docs:** https://www.rtk-ai.app
- **Install Guide:** https://github.com/rtk-ai/rtk/blob/master/INSTALL.md

---

**Last Updated:** 2026-03-26
**Next Review:** After Phase 1 completion
