"""Berb API Server with CORS support."""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Create app FIRST before any routes
app = FastAPI(title="Berb Research API")

# Add CORS middleware IMMEDIATELY
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# NOW import routes (they will be registered after CORS)
from berb.server.api import (
    app as api_app,
    create_research_job,
    get_research_job,
    stream_research_progress,
    run_research_pipeline,
    websocket_endpoint,
    list_presets,
    healthz,
    readyz,
)

# Copy routes from imported app
app.router.routes = api_app.router.routes

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
    uvicorn.run(app, host="localhost", port=8000)
