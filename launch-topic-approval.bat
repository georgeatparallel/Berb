@echo off
REM Berb Topic Approval - Launch Script
REM Starts server and opens browser

echo ========================================
echo   Berb Topic Approval System
echo ========================================
echo.
echo Starting server...
echo.

REM Load OPENROUTER_API_KEY from environment or .env
if not defined OPENROUTER_API_KEY (
  echo WARNING: OPENROUTER_API_KEY not set in environment.
  echo Please set it before running this script:
  echo   set OPENROUTER_API_KEY=your-key-here
  echo Or ensure it is in your .env file (will be loaded by Python).
  echo.
)

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
