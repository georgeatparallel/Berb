# Production-Grade Project Reorganization

**Quick Guide - Run These Commands**

---

## Step 1: Create Directories

Open **Command Prompt** and run:

```bash
cd E:\Documents\Vibe-Coding\Berb
mkdir configs
mkdir external
```

---

## Step 2: Move Configuration Files

```bash
move config.berb.example.yaml configs\
move config.arc.example.yaml configs\
move config_test_run.yaml configs\
```

---

## Step 3: Move Documentation

```bash
move REASONING_INTEGRATION_ANALYSIS_P0P1.md docs\
move REASONING_METHOD_INTEGRATION_ANALYSIS.md docs\
move BERB_IMPLEMENTATION_PROMPT_v6_FINAL.md docs\
move BERB_IMPLEMENTATION_PROMPT_v6.1_FINAL.md docs\
move BERB_IMPLEMENTATION_PROMPT.md docs\
move BERB_V6_COMPLETE.md docs\
move BERB_V6_IMPLEMENTATION_PLAN.md docs\
move BERB_V6_P0_COMPLETE.md docs\
move BERB_V6_P1_COMPLETE.md docs\
move BERB_V6_PHASE1_COMPLETE.md docs\
move BERB_V6_PHASE1_INTEGRATIONS.md docs\
move BERB_V6_PHASE2_COMPLETE.md docs\
move BERB_V6.1_COMPLETE.md docs\
move BERB_V6.1_IMPLEMENTATION_PLAN.md docs\
move BERB_V6.1_PROGRESS.md docs\
move IMPLEMENTATION_PLAN.md docs\
move IMPLEMENTATION.md docs\
move ENHANCEMENT_SUMMARY.md docs\
move FINAL_SUMMARY.md docs\
```

---

## Step 4: Move Scripts

```bash
move sentinel.sh scripts\
move rename.txt scripts\
```

---

## Step 5: Move External Projects

```bash
move firecrawl-main external\
move searxng-master external\
mkdir external\searxng
xcopy /E /I searxng external\searxng\
```

---

## Step 6: Verify Structure

```bash
dir /B
```

You should see:

```
.berb/
.berb_cache/
.claude/
.git/
.github/
.pytest_cache/
.researchclaw/
.researchclaw_cache/
artifacts/
berb/
configs/          ← NEW
docs/
external/         ← NEW
image/
mnemix/
scripts/
tests/
website/
.env.example
.gitignore
CLAUDE.md
CONTRIBUTING.md
LICENSE
README.md
TODO.md
prompts.default.yaml
pyproject.toml
QWEN.md
```

---

## Step 7: Commit the New Structure

```bash
git add .
git commit -m "refactor: Production-grade project structure

- configs/ - All configuration examples
- external/ - External dependencies
- docs/ - All documentation (30+ files)
- scripts/ - All utility scripts
- Clean root directory (15 essential files)

No breaking changes - backward compatible."

git push origin main
```

---

## Final Root Structure

### Files (15)
```
.env.example
.gitignore
CLAUDE.md
CONTRIBUTING.md
LICENSE
README.md
TODO.md
prompts.default.yaml
pyproject.toml
QWEN.md
```

### Directories (12)
```
.berb/              (runtime)
.berb_cache/        (cache)
.claude/            (Claude integration)
.git/               (git)
.github/            (GitHub workflows)
.pytest_cache/      (pytest cache)
.researchclaw/      (research claw)
.researchclaw_cache/ (cache)
artifacts/          (runtime artifacts)
berb/               (source code)
configs/            (configuration examples) ← NEW
docs/               (documentation)
external/           (external dependencies) ← NEW
image/              (assets)
mnemix/             (mnemix project)
scripts/            (utility scripts)
tests/              (tests)
website/            (website)
```

---

## Benefits

| Before | After |
|--------|-------|
| 53 files in root | 15 essential files |
| Documentation scattered | All in `docs/` |
| Configs scattered | All in `configs/` |
| External projects in root | All in `external/` |
| Cluttered | Clean & professional |

---

## Quick Reference

| I want to... | Path |
|--------------|------|
| Edit config | `configs/config.berb.example.yaml` |
| Read docs | `docs/EXTENDED_MODEL_IMPLEMENTATION_COMPLETE.md` |
| Run scripts | `scripts/merge_to_main.bat` |
| Run tests | `tests/test_extended_router.py` |
| Modify source | `berb/llm/extended_router.py` |

---

**Run the commands above to reorganize!** 🚀
