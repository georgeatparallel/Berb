#!/bin/bash
# Berb Web UI - Start Script
# Starts both FastAPI backend and React frontend

echo "🫒 Berb Web UI - Starting..."
echo ""

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js >= 18.0.0"
    exit 1
fi

# Check if Python is installed
if ! command -v python &> /dev/null; then
    echo "❌ Python is not installed. Please install Python >= 3.11"
    exit 1
fi

echo "✓ Node.js: $(node --version)"
echo "✓ Python: $(python --version)"
echo ""

# Start backend in background
echo "🚀 Starting FastAPI backend on http://localhost:8000"
python -m uvicorn berb.server.api:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

# Start frontend
echo "🎨 Starting React frontend on http://localhost:3000"
cd berb/ui/web
npm run dev

# Cleanup on exit
trap "kill $BACKEND_PID 2>/dev/null" EXIT
