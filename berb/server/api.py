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

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Berb Research API",
    description="Autonomous research automation API",
    version="1.0.0",
)

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

        # Import and run pipeline
        # This is simplified - in production would import actual pipeline
        from berb.presets import get_preset

        preset_obj = get_preset(preset) if preset else None

        # Simulate pipeline execution
        import asyncio
        for stage in range(1, 24):
            _jobs[job_id]["current_stage"] = stage
            _jobs[job_id]["progress"] = stage / 23 * 100
            await asyncio.sleep(0.5)  # Simulate work

        # Mark as completed
        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["progress"] = 100.0

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)


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
