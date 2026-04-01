"""Berb Web API - Connects UI to real pipeline execution."""

from fastapi import FastAPI, BackgroundTasks, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Berb Web API")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Job tracking
_jobs: Dict[str, Any] = {}

class ResearchRequest(BaseModel):
    topic: str
    preset: str | None = "humanities"
    mode: str = "autonomous"
    budget_usd: float = 2.0

class ResearchResponse(BaseModel):
    id: str
    status: str
    topic: str
    progress: float = 0.0
    current_stage: int | None = None

@app.options("/{path:path}")
async def options_handler():
    return Response(status_code=200)

@app.get("/healthz")
def healthz():
    return {"status": "healthy"}

@app.get("/api/v1/presets")
def list_presets():
    return ["humanities", "ml-conference", "physics", "social-sciences", "nlp", "biomedical"]

@app.post("/api/v1/research", response_model=ResearchResponse)
async def create_research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
):
    """Create and start real research pipeline."""
    job_id = str(uuid.uuid4())
    
    # Create job record
    job = {
        "id": job_id,
        "topic": request.topic,
        "preset": request.preset,
        "mode": request.mode,
        "status": "starting",
        "progress": 0.0,
        "current_stage": 1,
        "stages": [],
        "cost": 0.0,
    }
    _jobs[job_id] = job
    
    logger.info(f"Creating research job {job_id}: {request.topic}")
    
    # Start real pipeline in background
    background_tasks.add_task(run_real_pipeline, job_id, request)
    
    return ResearchResponse(
        id=job_id,
        status="starting",
        topic=request.topic,
    )

@app.get("/api/v1/research/{job_id}")
async def get_research(job_id: str):
    """Get research job status."""
    if job_id not in _jobs:
        return {"error": "Not found"}, 404
    
    job = _jobs[job_id]
    return {
        "id": job["id"],
        "status": job["status"],
        "topic": job["topic"],
        "progress": job["progress"],
        "current_stage": job["current_stage"],
        "cost": job["cost"],
        "stages": job["stages"],
    }

async def run_real_pipeline(job_id: str, request: ResearchRequest):
    """Run real Berb pipeline with progress tracking."""
    try:
        from berb.pipeline.runner import execute_pipeline
        from berb.pipeline.stages import STAGE_SEQUENCE, Stage
        from berb.config import RCConfig
        from berb.adapters import AdapterBundle
        import hashlib
        from datetime import datetime, timezone
        
        _jobs[job_id]["status"] = "running"
        logger.info(f"Starting REAL pipeline for: {request.topic}")
        
        # Create run directory
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        topic_hash = hashlib.sha256(request.topic.encode()).hexdigest()[:6]
        run_id = f"rc-{ts}-{topic_hash}"
        run_dir = Path("artifacts") / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Create config with real topic
        config = RCConfig(
            project={"name": run_id, "mode": request.mode},
            research={
                "topic": request.topic,
                "domains": ["philosophy", "religion"] if request.preset == "humanities" else ["machine-learning"],
            },
        )
        
        _jobs[job_id]["run_dir"] = str(run_dir)
        _jobs[job_id]["run_id"] = run_id
        
        # Run pipeline in executor (it's synchronous)
        loop = asyncio.get_event_loop()
        
        def run_sync():
            logger.info(f"Executing pipeline in {run_dir}")
            results = execute_pipeline(
                run_dir=run_dir,
                run_id=run_id,
                config=config,
                adapters=AdapterBundle(),
                auto_approve_gates=(request.mode == "autonomous"),
                skip_noncritical=True,
            )
            logger.info(f"Pipeline completed with {len(results)} stages")
            return results
        
        # Execute real pipeline
        results = await loop.run_in_executor(None, run_sync)
        
        # Process real results
        if results:
            done = sum(1 for r in results if str(r.status) == "StageStatus.DONE")
            failed = sum(1 for r in results if str(r.status) == "StageStatus.FAILED")
            
            # Update job with real results
            _jobs[job_id]["stages_done"] = done
            _jobs[job_id]["stages_failed"] = failed
            _jobs[job_id]["progress"] = 100.0
            _jobs[job_id]["current_stage"] = 23
            _jobs[job_id]["status"] = "completed" if failed == 0 else "failed"
            _jobs[job_id]["result"] = {
                "run_dir": str(run_dir),
                "run_id": run_id,
                "stages_completed": done,
            }
            
            # Add stage details
            for i, result in enumerate(results):
                _jobs[job_id]["stages"].append({
                    "number": i + 1,
                    "name": str(result.stage) if hasattr(result, 'stage') else f"Stage {i+1}",
                    "status": str(result.status),
                    "duration": getattr(result, 'duration', 0),
                })
            
            logger.info(f"Research COMPLETED: {done} stages done, {failed} failed")
        else:
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["progress"] = 100.0
            logger.info("Pipeline completed (no results returned)")
        
    except Exception as e:
        logger.error(f"Pipeline FAILED: {e}", exc_info=True)
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)
        _jobs[job_id]["progress"] = 0.0

@app.get("/api/v1/research/{job_id}/stream")
async def stream_progress(job_id: str):
    """Stream progress via SSE."""
    import asyncio
    
    async def generate():
        while True:
            if job_id not in _jobs:
                break
            
            job = _jobs[job_id]
            yield f"data: {job}\n\n"
            
            if job["status"] in ("completed", "failed"):
                break
            
            await asyncio.sleep(2)
    
    from fastapi.responses import StreamingResponse
    return StreamingResponse(generate(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  Berb Web API - Real Pipeline Integration")
    print("=" * 60)
    print("  Frontend: http://localhost:3000")
    print("  Backend:  http://localhost:8001")
    print("  CORS: ENABLED")
    print("=" * 60)
    uvicorn.run(app, host="localhost", port=8001)
