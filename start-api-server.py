"""Quick start script for Berb API server with CORS."""

import uvicorn
from berb.server.api import app

if __name__ == "__main__":
    print("=" * 60)
    print("  Berb API Server with CORS")
    print("=" * 60)
    print()
    print("  Frontend: http://localhost:3000")
    print("  Backend:  http://localhost:8000")
    print("  API Docs: http://localhost:8000/docs")
    print()
    print("  CORS enabled for: http://localhost:3000")
    print()
    print("  Press Ctrl+C to stop")
    print("=" * 60)
    print()
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
