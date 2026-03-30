@echo off
REM Reorganize Berb Project into Production-Grade Structure
REM Cleans up root folder, moves files to appropriate subfolders

setlocal enabledelayedexpansion

echo ========================================
echo Berb - Production Structure Reorganization
echo ========================================
echo.

cd /d "%~dp0.."
echo Current directory: %CD%
echo.

REM Create necessary directories
echo Step 1: Creating directory structure...
mkdir configs 2>nul
mkdir examples 2>nul
echo [OK] Directories created
echo.

REM Move configuration examples
echo Step 2: Organizing configuration files...
move /Y config.berb.example.yaml configs\ 2>nul
move /Y config.arc.example.yaml configs\ 2>nul
move /Y config_test_run.yaml configs\ 2>nul
echo [OK] Configuration files moved to configs/
echo.

REM Move documentation
echo Step 3: Organizing documentation...
REM Keep only essential docs in root, move others to docs/
move /Y REASONING_INTEGRATION_ANALYSIS_P0P1.md docs\ 2>nul
move /Y REASONING_METHOD_INTEGRATION_ANALYSIS.md docs\ 2>nul
move /Y BERB_*.md docs\ 2>nul
move /Y IMPLEMENTATION*.md docs\ 2>nul
move /Y ENHANCEMENT_SUMMARY.md docs\ 2>nul
move /Y FINAL_SUMMARY.md docs\ 2>nul
echo [OK] Documentation organized
echo.

REM Move scripts
echo Step 4: Organizing scripts...
move /Y sentinel.sh scripts\ 2>nul
move /Y rename.txt scripts\ 2>nul
echo [OK] Scripts organized
echo.

REM Move test artifacts
echo Step 5: Organizing test files...
move /Y test_outputs* tests\ 2>nul
echo [OK] Test files organized
echo.

REM Move external projects
echo Step 6: Organizing external projects...
if exist "firecrawl-main" (
    move /Y firecrawl-main external\ 2>nul
    echo [OK] firecrawl-main moved to external/
)
if exist "searxng-master" (
    move /Y searxng-master external\ 2>nul
    echo [OK] searxng-master moved to external/
)
if exist "searxng" (
    xcopy /E /I /Y searxng external\searxng 2>nul
    echo [OK] searxng copied to external/
)
echo.

REM Move AI-generated artifacts
echo Step 7: Organizing AI artifacts...
if exist ".claude" (
    echo [INFO] .claude/ directory kept (needed for Claude integration)
)
if exist ".berb" (
    echo [INFO] .berb/ directory kept (runtime data)
)
if exist ".berb_cache" (
    echo [INFO] .berb_cache/ directory kept (cache)
)
echo.

REM Show final structure
echo ========================================
echo Final Root Structure:
echo ========================================
dir /B /A-D
echo.
echo Directories:
dir /B /AD
echo.

echo ========================================
echo Reorganization Complete!
echo ========================================
echo.
echo Root folder now contains:
echo - README.md (project overview)
echo - LICENSE (license file)
echo - pyproject.toml (Python project config)
echo - .gitignore (git ignore rules)
echo - configs/ (configuration examples)
echo - docs/ (documentation)
echo - scripts/ (utility scripts)
echo - tests/ (test files)
echo - berb/ (source code)
echo - external/ (external dependencies)
echo.
echo Press any key to exit...
pause >nul
