"""Standalone Berb API Server with proper CORS."""

from fastapi import FastAPI, BackgroundTasks, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uuid
import asyncio
import logging
from typing import Any, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Berb Research API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Job store
_jobs: Dict[str, Any] = {}

class ResearchJobRequest(BaseModel):
    topic: str
    preset: str | None = None
    mode: str = "autonomous"
    budget_usd: float = 1.0

class ResearchJobResponse(BaseModel):
    id: str
    status: str
    topic: str
    progress: float = 0.0
    current_stage: int | None = None

@app.get("/healthz")
def healthz():
    return {"status": "healthy"}

@app.get("/api/v1/presets")
def list_presets():
    return ["humanities", "ml-conference", "physics", "social-sciences"]

@app.post("/api/v1/research", response_model=ResearchJobResponse)
async def create_research_job(
    request: ResearchJobRequest,
    background_tasks: BackgroundTasks,
):
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "topic": request.topic,
        "preset": request.preset,
        "mode": request.mode,
        "status": "queued",
        "progress": 0.0,
        "current_stage": None,
    }
    _jobs[job_id] = job
    
    logger.info(f"Created research job: {job_id} for topic: {request.topic}")
    
    # Start in background
    background_tasks.add_task(run_research_pipeline, job_id, request.topic)
    
    return ResearchJobResponse(
        id=job_id,
        status="queued",
        topic=request.topic,
    )

# OPTIONS handler MUST be after POST route
@app.options("/api/v1/research")
async def options_research():
    """Handle CORS preflight for research endpoint."""
    return Response(status_code=200)

@app.get("/api/v1/research/{job_id}")
async def get_research_job(job_id: str):
    if job_id not in _jobs:
        return {"error": "Not found"}, 404
    job = _jobs[job_id]
    return {
        "id": job["id"],
        "status": job["status"],
        "topic": job["topic"],
        "progress": job["progress"],
        "current_stage": job["current_stage"],
    }

async def run_research_pipeline(job_id: str, topic: str):
    """Simulate research pipeline execution."""
    try:
        _jobs[job_id]["status"] = "running"
        logger.info(f"Starting research: {topic}")
        
        # Simulate stages
        for stage in range(1, 24):
            _jobs[job_id]["current_stage"] = stage
            _jobs[job_id]["progress"] = stage / 23 * 100
            await asyncio.sleep(0.3)  # Simulate work
            
        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["progress"] = 100.0
        logger.info(f"Research completed: {topic}")
    except Exception as e:
        logger.error(f"Research failed: {e}")
        _jobs[job_id]["status"] = "failed"

if __name__ == "__main__":
    print("=" * 60)
    print("  Berb API Server with CORS")
    print("=" * 60)
    print("  Frontend: http://localhost:3000")
    print("  Backend:  http://localhost:8001")  # Changed port
    print("  CORS: ENABLED for localhost:3000")
    print("=" * 60)
    uvicorn.run(app, host="localhost", port=8001)  # Changed port
