@echo off
REM Berb Web UI - Start Script for Windows
REM Starts both FastAPI backend and React frontend

echo.
echo ========================================
echo   Berb Web UI - Starting...
echo ========================================
echo.

REM Check if Node.js is installed
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Node.js is not installed. Please install Node.js ^>= 18.0.0
    echo Download from: https://nodejs.org/
    exit /b 1
)

REM Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed. Please install Python ^>= 3.11
    echo Download from: https://python.org/
    exit /b 1
)

REM Show versions
for /f "tokens=*" %%i in ('node --version') do set NODE_VERSION=%%i
for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i

echo [OK] %NODE_VERSION%
echo [OK] %PYTHON_VERSION%
echo.

REM Start backend in background
echo [1/3] Starting FastAPI backend on http://localhost:8000
start "Berb Backend" cmd /k "python -m uvicorn berb.server.api:app --host 0.0.0.0 --port 8000 --reload"

REM Wait for backend to start
timeout /t 5 /nobreak >nul

REM Start frontend
echo [2/3] Starting React frontend on http://localhost:3000
cd /d "%~dp0berb\ui\web"
start "Berb Frontend" cmd /k "npm run dev"

echo [3/3] Opening browser...
timeout /t 3 /nobreak >nul
start http://localhost:3000

echo.
echo ========================================
echo   Web UI is running!
echo ========================================
echo.
echo   Frontend: http://localhost:3000
echo   Backend:  http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo.
echo Press any key to exit this window...
pause >nul
