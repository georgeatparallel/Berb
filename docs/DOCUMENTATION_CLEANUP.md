# Berb Documentation

**Production-Grade Documentation Structure**

---

## Essential Documentation (Keep in `docs/`)

These files are **user-facing** and should be in the main `docs/` folder:

| File | Purpose | Status |
|------|---------|--------|
| `README.md` | Project overview (root) | ✅ Keep |
| `MODELS.md` | LLM model recommendations | ✅ Keep |
| `IMPLEMENTATION.md` | Implementation summary | ✅ Keep |
| `USAGE.md` | Usage guide | 📝 Create |
| `CONFIGURATION.md` | Configuration guide | 📝 Create |
| `ARCHITECTURE.md` | Architecture overview | 📝 Create |
| `CONTRIBUTING.md` | Contribution guidelines (root) | ✅ Keep |

---

## Internal Documentation (Move to `docs/internal/`)

These files are **internal/intermediate** and should be archived:

### Phase Reports
- `PHASE_1_COMPLETION.md`
- `PHASE_2_COMPLETE.md`
- `PHASE_2_IN_PROGRESS.md`
- `PHASE_2_FINAL_STATUS.md`
- `PHASE_2_MIGRATION_COMPLETE.md`
- `PHASE_3_PRODUCTION_ROLLOUT.md`

### Implementation Plans
- `EXTENDED_IMPLEMENTATION_PLAN.md`

### Progress Reports
- `TEST_FIXES_APPLIED.md`
- `PUSH_TO_GITHUB_GUIDE.md`
- `PROJECT_STRUCTURE.md`

### Legacy BERB Docs
- All `BERB_*.md` files
- All `IMPLEMENTATION*.md` files
- `ENHANCEMENT_SUMMARY.md`
- `FINAL_SUMMARY.md`
- `REASONING_INTEGRATION_ANALYSIS_*.md`

---

## Run Cleanup Script

**Windows:**
```bash
cd E:\Documents\Vibe-Coding\Berb
scripts\cleanup_docs.bat
```

**Manual:**
```bash
cd E:\Documents\Vibe-Coding\Berb

REM Create internal archive
mkdir docs\internal

REM Move internal files
move docs\PHASE_*.md docs\internal\
move docs\BERB_*.md docs\internal\
move docs\IMPLEMENTATION*.md docs\internal\
move docs\ENHANCEMENT_SUMMARY.md docs\internal\
move docs\FINAL_SUMMARY.md docs\internal\
move docs\REASONING_*.md docs\internal\
move docs\TEST_FIXES_APPLIED.md docs\internal\
move docs\PUSH_TO_GITHUB_GUIDE.md docs\internal\
move docs\PROJECT_STRUCTURE.md docs\internal\
move docs\EXTENDED_IMPLEMENTATION_PLAN.md docs\internal\

REM Rename for clarity
move docs\REASONER_MODEL_RECOMMENDATIONS.md docs\MODELS.md
move docs\EXTENDED_MODEL_IMPLEMENTATION_COMPLETE.md docs\IMPLEMENTATION.md
```

---

## After Cleanup

### Commit the Changes

```bash
git add .
git commit -m "docs: Optimize documentation structure for production

- Keep essential user-facing docs in docs/
- Archive internal/intermediate docs to docs/internal/
- Consolidate documentation (MODELS.md, IMPLEMENTATION.md)
- Professional GitHub-ready structure

No content loss - all docs preserved."

git push origin main
```

---

## Final Structure

```
docs/
├── README.md (or index.md)       # Documentation index
├── MODELS.md                      # Model recommendations
├── IMPLEMENTATION.md              # Implementation summary
├── USAGE.md                       # Usage guide (create)
├── CONFIGURATION.md               # Configuration guide (create)
├── ARCHITECTURE.md                # Architecture overview (create)
└── internal/                      # Internal docs (archived)
    ├── PHASE_1_COMPLETION.md
    ├── PHASE_2_COMPLETE.md
    ├── EXTENDED_IMPLEMENTATION_PLAN.md
    └── ... (all internal docs)
```

---

## Benefits

| Before | After |
|--------|-------|
| 20+ documentation files | 7 essential files |
| Mixed internal/external | Clean separation |
| Scattered structure | Professional organization |
| Hard to navigate | Easy to find |

---

**Run `scripts\cleanup_docs.bat` now!** 🧹
