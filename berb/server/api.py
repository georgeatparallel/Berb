"""FastAPI REST API for Berb.

Endpoints:
- POST /api/v1/research - Submit research job
- GET /api/v1/research/{id} - Get status + results
- GET /api/v1/research/{id}/stream - SSE progress stream
- POST /api/v1/research/{id}/approve - Approve stage (collaborative)
- GET /api/v1/presets - List presets
- GET /healthz - Liveness probe
- GET /readyz - Readiness probe

WebSocket:
- WS /api/v1/research/{id}/ws - Real-time updates

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Berb Research API",
    description="Autonomous research automation API",
    version="1.0.0",
)

# --- CORS Configuration ---
# Allow frontend at localhost:3000 to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["POST", "GET", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Manual CORS middleware for OPTIONS requests
@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    """Add CORS headers to all responses."""
    origin = request.headers.get("origin", "")
    
    # Handle preflight OPTIONS requests
    if request.method == "OPTIONS":
        response = Response(status_code=200)
        response.headers["Access-Control-Allow-Origin"] = "http://localhost:3000"
        response.headers["Access-Control-Allow-Methods"] = "POST, GET, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
    
    # Process normal requests
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "http://localhost:3000"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    
    return response

# In-memory job store (use Redis/DB in production)
_jobs: dict[str, dict[str, Any]] = {}


class ResearchJobRequest(BaseModel):
    """Research job request.

    Attributes:
        topic: Research topic
        preset: Preset name (optional)
        mode: Operation mode (autonomous/collaborative)
        pause_after: Stages to pause at (collaborative mode)
        budget_usd: Maximum budget
    """

    topic: str
    preset: str | None = None
    mode: str = "autonomous"
    pause_after: list[int] = Field(default_factory=list)
    budget_usd: float = 1.0


class ResearchJobResponse(BaseModel):
    """Research job response.

    Attributes:
        id: Job ID
        status: Job status
        topic: Research topic
        progress: Progress percentage
        current_stage: Current stage number
        result_url: URL to results
    """

    id: str
    status: str
    topic: str
    progress: float = 0.0
    current_stage: int | None = None
    result_url: str | None = None


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe.

    Returns:
        Health status
    """
    return {"status": "healthy"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    """Readiness probe.

    Returns:
        Readiness status
    """
    # Check dependencies
    return {"status": "ready"}


@app.post("/api/v1/research", response_model=ResearchJobResponse)
async def create_research_job(
    request: ResearchJobRequest,
    background_tasks: BackgroundTasks,
) -> ResearchJobResponse:
    """Submit new research job.

    Args:
        request: Job request
        background_tasks: FastAPI background tasks

    Returns:
        Job response with ID
    """
    import uuid

    job_id = str(uuid.uuid4())

    # Create job record
    job = {
        "id": job_id,
        "topic": request.topic,
        "preset": request.preset,
        "mode": request.mode,
        "status": "queued",
        "progress": 0.0,
        "current_stage": None,
        "result": None,
    }
    _jobs[job_id] = job

    # Start job in background
    background_tasks.add_task(
        run_research_pipeline,
        job_id,
        request.topic,
        request.preset,
        request.mode,
    )

    return ResearchJobResponse(
        id=job_id,
        status="queued",
        topic=request.topic,
    )


@app.get("/api/v1/research/{job_id}", response_model=ResearchJobResponse)
async def get_research_job(job_id: str) -> ResearchJobResponse:
    """Get research job status.

    Args:
        job_id: Job ID

    Returns:
        Job status
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    return ResearchJobResponse(
        id=job["id"],
        status=job["status"],
        topic=job["topic"],
        progress=job["progress"],
        current_stage=job["current_stage"],
        result_url=f"/api/v1/research/{job_id}/results" if job["status"] == "completed" else None,
    )


@app.get("/api/v1/research/{job_id}/stream")
async def stream_research_progress(job_id: str):
    """Stream research progress via SSE.

    Args:
        job_id: Job ID

    Returns:
        SSE stream
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    async def generate():
        import asyncio

        while True:
            job = _jobs.get(job_id)
            if not job:
                break

            # Send SSE event
            yield f"data: {job}\n\n"

            if job["status"] in ("completed", "failed"):
                break

            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/v1/presets")
async def list_presets() -> list[dict[str, str]]:
    """List available presets.

    Returns:
        List of presets
    """
    from berb.presets import list_presets as get_presets

    presets = []
    for name in get_presets():
        presets.append({"name": name})
    return presets


async def run_research_pipeline(
    job_id: str,
    topic: str,
    preset: str | None,
    mode: str,
) -> None:
    """Run research pipeline in background.

    Args:
        job_id: Job ID
        topic: Research topic
        preset: Preset name
        mode: Operation mode
    """
    try:
        # Update status to running
        _jobs[job_id]["status"] = "running"
        _jobs[job_id]["current_stage"] = 1
        _jobs[job_id]["progress"] = 5.0

        logger.info(f"Starting pipeline for job {job_id}, topic: {topic}, preset: {preset}")

        # Import pipeline runner
        from berb.pipeline.runner import execute_pipeline
        from berb.presets import get_preset
        from berb.config import RCConfig
        from berb.adapters import AdapterBundle
        from pathlib import Path
        import asyncio

        # Get preset configuration
        preset_obj = get_preset(preset) if preset else None
        
        # Create run directory
        import hashlib
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        topic_hash = hashlib.sha256(topic.encode()).hexdigest()[:6]
        run_id = f"rc-{ts}-{topic_hash}"
        run_dir = Path("artifacts") / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Run directory: {run_dir}")

        # Create basic config if needed
        config = RCConfig(
            project={"name": run_id, "mode": mode},
            research={"topic": topic, "domains": ["general"]},
        )

        # Run pipeline in executor (it's synchronous)
        loop = asyncio.get_event_loop()
        
        def run_pipeline_sync():
            try:
                results = execute_pipeline(
                    run_dir=run_dir,
                    run_id=run_id,
                    config=config,
                    adapters=AdapterBundle(),
                    auto_approve_gates=(mode == "autonomous"),
                    skip_noncritical=True,
                )
                return results
            except Exception as e:
                logger.error(f"Pipeline execution error: {e}")
                raise

        results = await loop.run_in_executor(None, run_pipeline_sync)

        # Process results
        if results:
            done = sum(1 for r in results if r.status.value == "done")
            failed = sum(1 for r in results if r.status.value == "failed")
            
            _jobs[job_id]["stages_done"] = done
            _jobs[job_id]["stages_failed"] = failed
            
            if failed == 0:
                _jobs[job_id]["status"] = "completed"
                _jobs[job_id]["progress"] = 100.0
                _jobs[job_id]["result"] = {
                    "run_dir": str(run_dir),
                    "stages_completed": done,
                }
                logger.info(f"Pipeline completed successfully: {done} stages")
            else:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = f"{failed} stages failed"
                logger.error(f"Pipeline failed: {failed} stages")
        else:
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["progress"] = 100.0
            logger.info("Pipeline completed (no results)")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)
        _jobs[job_id]["progress"] = 0.0


# WebSocket endpoint for real-time updates
@app.websocket("/api/v1/research/{job_id}/ws")
async def websocket_endpoint(websocket, job_id: str):
    """WebSocket for real-time job updates.

    Args:
        websocket: WebSocket connection
        job_id: Job ID
    """
    await websocket.accept()

    if job_id not in _jobs:
        await websocket.send_json({"error": "Job not found"})
        await websocket.close()
        return

    import asyncio

    while True:
        job = _jobs.get(job_id)
        if not job:
            break

        await websocket.send_json(job)

        if job["status"] in ("completed", "failed"):
            break

        await asyncio.sleep(1)

    await websocket.close()
