@echo off
REM Berb Topic Approval - Manual Launch Instructions
REM Run these commands in TWO separate command windows

echo ========================================
echo   Berb Topic Approval System
echo ========================================
echo.
echo WINDOW 1 - UI Server:
echo ----------------------
echo cd E:\Documents\Vibe-Coding\Berb\berb\ui
echo python -m http.server 8080
echo.
echo WINDOW 2 - API Server:
echo -----------------------
echo cd E:\Documents\Vibe-Coding\Berb
echo set OPENROUTER_API_KEY=***REMOVED-OPENROUTER-KEY***
echo python -m berb.server.web_api_real
echo.
echo After both servers start, open in browser:
echo http://localhost:8080/topic-approval.html
echo ========================================
