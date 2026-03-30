@echo off
REM Clean Up Documentation - Keep Only Essential Files for Professional GitHub Repo
REM Run from Berb project root

setlocal enabledelayedexpansion

echo ========================================
echo Berb - Documentation Cleanup
echo Optimizing for Professional GitHub Repo
echo ========================================
echo.

cd /d "%~dp0.."

echo Current directory: %CD%
echo.

echo This will:
echo - Keep essential user-facing documentation
echo - Remove internal/intermediate files
echo - Consolidate related docs
echo.

pause

REM Create consolidated docs directory structure
echo Step 1: Creating documentation structure...
mkdir docs\internal 2>nul
echo [OK] Structure created
echo.

REM ========================================
REM FILES TO KEEP (Essential for GitHub)
REM ========================================
echo Files to KEEP in docs/:
echo - USAGE.md (or create from existing)
echo - CONFIGURATION.md (or create)
echo - ARCHITECTURE.md (or create)
echo - MODELS.md (from REASONER_MODEL_RECOMMENDATIONS)
echo - IMPLEMENTATION.md (from EXTENDED_MODEL_IMPLEMENTATION_COMPLETE)
echo - DEPLOYMENT.md (from PHASE_3_PRODUCTION_ROLLOUT)
echo.

REM ========================================
REM MOVE INTERNAL FILES TO docs/internal/
REM ========================================
echo Step 2: Moving internal files to docs/internal/...

REM Phase reports (internal)
move /Y docs\PHASE_1_COMPLETION.md docs\internal\ 2>nul
move /Y docs\PHASE_2_COMPLETE.md docs\internal\ 2>nul
move /Y docs\PHASE_2_IN_PROGRESS.md docs\internal\ 2>nul
move /Y docs\PHASE_2_FINAL_STATUS.md docs\internal\ 2>nul
move /Y docs\PHASE_2_MIGRATION_COMPLETE.md docs\internal\ 2>nul
move /Y docs\PHASE_3_PRODUCTION_ROLLOUT.md docs\internal\ 2>nul

REM Implementation plans (internal)
move /Y docs\EXTENDED_IMPLEMENTATION_PLAN.md docs\internal\ 2>nul

REM Progress reports (internal)
move /Y docs\TEST_FIXES_APPLIED.md docs\internal\ 2>nul
move /Y docs\PUSH_TO_GITHUB_GUIDE.md docs\internal\ 2>nul
move /Y docs\PROJECT_STRUCTURE.md docs\internal\ 2>nul

REM Legacy BERB docs (consolidate or remove)
move /Y docs\BERB_IMPLEMENTATION_PROMPT_v6_FINAL.md docs\internal\ 2>nul
move /Y docs\BERB_IMPLEMENTATION_PROMPT_v6.1_FINAL.md docs\internal\ 2>nul
move /Y docs\BERB_IMPLEMENTATION_PROMPT.md docs\internal\ 2>nul
move /Y docs\BERB_V6_COMPLETE.md docs\internal\ 2>nul
move /Y docs\BERB_V6_IMPLEMENTATION_PLAN.md docs\internal\ 2>nul
move /Y docs\BERB_V6_P0_COMPLETE.md docs\internal\ 2>nul
move /Y docs\BERB_V6_P1_COMPLETE.md docs\internal\ 2>nul
move /Y docs\BERB_V6_PHASE1_COMPLETE.md docs\internal\ 2>nul
move /Y docs\BERB_V6_PHASE1_INTEGRATIONS.md docs\internal\ 2>nul
move /Y docs\BERB_V6_PHASE2_COMPLETE.md docs\internal\ 2>nul
move /Y docs\BERB_V6.1_COMPLETE.md docs\internal\ 2>nul
move /Y docs\BERB_V6.1_IMPLEMENTATION_PLAN.md docs\internal\ 2>nul
move /Y docs\BERB_V6.1_PROGRESS.md docs\internal\ 2>nul

REM Implementation docs (internal)
move /Y docs\IMPLEMENTATION_PLAN.md docs\internal\ 2>nul
move /Y docs\IMPLEMENTATION.md docs\internal\ 2>nul
move /Y docs\ENHANCEMENT_SUMMARY.md docs\internal\ 2>nul
move /Y docs\FINAL_SUMMARY.md docs\internal\ 2>nul

REM Reasoning integration analysis (internal)
move /Y docs\REASONING_INTEGRATION_ANALYSIS_P0P1.md docs\internal\ 2>nul
move /Y docs\REASONING_METHOD_INTEGRATION_ANALYSIS.md docs\internal\ 2>nul

echo [OK] Internal files moved
echo.

REM ========================================
REM CONSOLIDATE ESSENTIAL DOCS
REM ========================================
echo Step 3: Consolidating essential documentation...

REM Rename for clarity
move /Y docs\REASONER_MODEL_RECOMMENDATIONS.md docs\MODELS.md 2>nul
move /Y docs\EXTENDED_MODEL_IMPLEMENTATION_COMPLETE.md docs\IMPLEMENTATION.md 2>nul
move /Y docs\EXTENDED_MODEL_COMPARISON.md docs\internal\ 2>nul

echo [OK] Documentation consolidated
echo.

REM ========================================
REM SHOW FINAL STRUCTURE
REM ========================================
echo ========================================
echo Final Documentation Structure:
echo ========================================
echo.
echo docs/ (Essential - User-Facing):
dir /B docs\*.md 2>nul | findstr /V "internal"
echo.
echo docs/internal/ (Internal - Not for GitHub):
dir /B docs\internal\*.md 2>nul
echo.

echo ========================================
echo Cleanup Complete!
echo ========================================
echo.
echo Essential docs kept in docs/:
echo - MODELS.md (model recommendations)
echo - IMPLEMENTATION.md (implementation summary)
echo - Plus any USAGE.md, CONFIGURATION.md, ARCHITECTURE.md you create
echo.
echo Internal docs moved to docs/internal/:
echo - Phase reports
echo - Implementation plans
echo - Progress reports
echo - Legacy BERB docs
echo.
echo Next steps:
echo 1. Review docs/ folder
echo 2. Create USAGE.md if needed
echo 3. Create CONFIGURATION.md if needed
echo 4. Commit and push
echo.
echo Press any key to exit...
pause >nul
