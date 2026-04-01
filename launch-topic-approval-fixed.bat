@echo off
REM Berb Topic Approval - Complete Launch Script
REM Starts both UI and API servers

echo ========================================
echo   Berb Topic Approval System
echo ========================================
echo.

set OPENROUTER_API_KEY=***REMOVED-OPENROUTER-KEY***

cd /d "%~dp0"

echo [1/3] Starting UI server on port 8001...
cd berb\ui
start "Berb UI" cmd /k "python -m http.server 8001"
cd ..

echo [2/3] Starting API server on port 8002...
start "Berb API" cmd /k "python -m berb.server.web_api_real"

echo [3/3] Waiting for servers to start...
timeout /t 10 /nobreak >nul

echo.
echo Opening browser...
start http://localhost:8001/topic-approval.html

echo.
echo ========================================
echo   UI:  http://localhost:8001/topic-approval.html
echo   API: http://localhost:8002
echo ========================================
echo.
echo Servers are running in separate windows.
echo Close those windows to stop the servers.
echo.
echo Press any key to exit this window...
pause >nul
