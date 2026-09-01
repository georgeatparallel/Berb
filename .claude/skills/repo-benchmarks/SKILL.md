---
name: repo-benchmarks
description: Map of benchmarks/ — currently an empty placeholder directory reserved for benchmark suites. Use when locating benchmark assets or deciding where benchmark scripts belong.
---

# benchmarks/

Placeholder directory intended for benchmark suites and datasets. It is currently **empty** — no benchmark content is checked in. Benchmark-related functionality that actually runs lives in the package: `berb/agents/` contains the benchmark agent (tested by `tests/test_benchmark_agent.py` and `tests/test_benchmark_omissions.py`). Note there is also a hidden `.benchmarks/` directory at repo root (pytest-benchmark cache), which is unrelated tool output.

## Contents

| File/Dir | Purpose |
|------|---------|
| *(empty)* | No files present; directory reserved for future benchmark suites/data |

## Notes

- For benchmark logic, look at the benchmark agent in `berb/agents/` and its tests, not this folder.
- Do not confuse with root `.benchmarks/` (pytest-benchmark artifact cache — generated, not source).
- Because it is empty, the directory may not exist in fresh git clones (git does not track empty dirs).
