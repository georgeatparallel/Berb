@echo off
REM Merge Everything to Main and Push to GitHub
REM FIXED VERSION - Won't close automatically

title Berb - Merge to Main

echo ========================================
echo Berb - Merge to Main and Push
echo ========================================
echo.
echo Press any key to start...
pause >nul
echo.

cd /d "%~dp0.."

echo Current directory: %CD%
echo.

echo Step 1: Git status...
git status
echo.

echo Step 2: Adding all files...
git add .
echo Done.
echo.

echo Step 3: Committing...
git commit -m "feat: Complete Extended Model Implementation - 97%% cost savings"
echo.

echo Step 4: Creating tag...
git tag -a v2.0-extended -m "Production Ready"
echo.

echo Step 5: Pushing to GitHub...
git push origin main
git push origin v2.0-extended
echo.

echo ========================================
echo DONE!
echo ========================================
echo.
echo Check GitHub: https://github.com/georgehadji/berb
echo.
echo Press any key to exit...
pause >nul
