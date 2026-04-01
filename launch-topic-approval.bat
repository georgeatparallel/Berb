@echo off
REM Berb Topic Approval - Launch Script
REM Starts server and opens browser

echo ========================================
echo   Berb Topic Approval System
echo ========================================
echo.
echo Starting server...
echo.

set OPENROUTER_API_KEY=***REMOVED-OPENROUTER-KEY***

cd /d "%~dp0"
start "Berb Server" cmd /k "python -m berb.server.web_api_real"

echo Server starting on http://localhost:8001
echo.
echo Waiting for server to be ready...
timeout /t 8 /nobreak >nul

echo.
echo Opening browser...
start http://localhost:8001

echo.
echo ========================================
echo   Server: http://localhost:8001
echo   UI: http://localhost:8001
echo ========================================
echo.
echo Press any key to exit this window...
pause >nul
