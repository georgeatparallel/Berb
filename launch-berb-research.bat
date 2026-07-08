@echo off
echo ============================================================
echo   Berb Topic Approval Launcher
echo ============================================================
echo.

cd /d %~dp0

:: Load OPENROUTER_API_KEY from environment or .env file
if not defined OPENROUTER_API_KEY (
  echo WARNING: OPENROUTER_API_KEY not set in environment.
  echo Please set it before running this script:
  echo   set OPENROUTER_API_KEY=your-key-here
  echo Or ensure it is in your .env file (will be loaded by Python).
  echo.
  echo Attempting to continue - Python will load from .env if present...
)

echo Starting API server on port 8082...
start "Berb API Server" cmd /c "cd /d %~dp0 && python -m berb.server.web_api_real"

echo Waiting for API server to start...
timeout /t 5 /nobreak >nul

echo Starting UI server on port 8080...
start "Berb UI Server" cmd /c "cd /d %~dp0\berb\ui && python -m http.server 8080"

echo.
echo Opening browser...
timeout /t 2 /nobreak >nul
start http://localhost:8080/topic-approval.html

echo.
echo ============================================================
echo   READY!
echo ============================================================
echo.
echo   UI:  http://localhost:8080/topic-approval.html
echo   API: http://localhost:8082
echo.
echo   Two console windows opened - keep them running!
echo.
echo   Close those windows when done to stop the servers.
echo.
pause
