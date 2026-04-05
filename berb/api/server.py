"""FastAPI REST API server for Berb Web UI.

This module provides the backend API for the Berb web interface, including:
- Research job management (create, status, artifacts)
- Preset management
- Workflow and operation mode configuration
- Real-time updates via WebSocket

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from berb.modes.workflow import WorkflowConfig, WorkflowManager, WorkflowType
from berb.modes.operation_mode import OperationMode, CollaborativeConfig

logger = logging.getLogger(__name__)

# ============================================================================
# Pydantic Models
# ============================================================================


class ResearchJobCreate(BaseModel):
    """Request to create a new research job."""
    topic: str
    workflow: WorkflowType = WorkflowType.FULL_RESEARCH
    preset: str = "ml-conference"
    uploaded_pdfs: list[str] = []
    uploaded_data: list[str] = []
    uploaded_manuscript: str | None = None
    uploaded_reviews: str | None = None
    include_math: bool = False
    include_experiments: bool = True
    include_code_appendix: bool = False
    include_supplementary: bool = True
    operation_mode: OperationMode = OperationMode.AUTONOMOUS
    pause_after_stages: list[int] = [2, 6, 8, 9, 15, 18]
    approval_timeout_minutes: int = 60


class ResearchJobResponse(BaseModel):
    """Response for research job."""
    id: str
    topic: str
    workflow: WorkflowType
    preset: str
    status: str
    stages: list[dict[str, Any]]
    phases: list[dict[str, Any]]
    cost_usd: float
    duration_seconds: float
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    artifacts: dict[str, Any] | None = None


class PresetResponse(BaseModel):
    """Response for preset."""
    name: str
    description: str
    tags: list[str]
    primary_sources: list[str]
    primary_model: str
    max_budget_usd: float
    paper_format: str


class FeedbackSubmission(BaseModel):
    """Feedback submission for collaborative mode."""
    action: str  # approve, edit, reject, skip
    feedback_text: str | None = None
    confidence_scores: dict[str, float] | None = None
    metadata: dict[str, Any] | None = None


# ============================================================================
# FastAPI Application
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Berb API server")
    yield
    # Shutdown
    logger.info("Shutting down Berb API server")


app = FastAPI(
    title="Berb API",
    description="API for Berb research automation system",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health Endpoints
# ============================================================================


@app.get("/healthz")
async def healthz():
    """Liveness probe."""
    return {"status": "healthy"}


@app.get("/readyz")
async def readyz():
    """Readiness probe."""
    return {"status": "ready"}


# ============================================================================
# Research Job Endpoints
# ============================================================================


@app.post("/api/v1/research")
async def create_research_job(job: ResearchJobCreate) -> ResearchJobResponse:
    """Create a new research job.
    
    Args:
        job: Research job configuration
        
    Returns:
        Created research job response
    """
    try:
        # Create workflow manager
        workflow_config = WorkflowConfig(
            workflow=job.workflow,
            uploaded_pdfs=[p for p in job.uploaded_pdfs if p],
            uploaded_data=[d for d in job.uploaded_data if d],
            uploaded_manuscript=job.uploaded_manuscript,
            uploaded_reviews=job.uploaded_reviews,
            include_math=job.include_math,
            include_experiments=job.include_experiments,
            include_code_appendix=job.include_code_appendix,
            include_supplementary=job.include_supplementary,
            operation_mode=job.operation_mode,
        )
        
        workflow_manager = WorkflowManager(
            workflow=job.workflow,
            config=workflow_config,
        )
        
        # Create collaborative config if needed
        collaborative_config = None
        if job.operation_mode == OperationMode.COLLABORATIVE:
            collaborative_config = CollaborativeConfig(
                pause_after_stages=job.pause_after_stages,
                approval_timeout_minutes=job.approval_timeout_minutes,
            )
        
        # Generate job ID
        import hashlib
        import datetime
        ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
        topic_hash = hashlib.sha256(job.topic.encode()).hexdigest()[:6]
        job_id = f"rc-{ts}-{topic_hash}"
        
        # Create response (in real implementation, this would queue the job)
        return ResearchJobResponse(
            id=job_id,
            topic=job.topic,
            workflow=job.workflow,
            preset=job.preset,
            status="pending",
            stages=[],
            phases=[],
            cost_usd=0.0,
            duration_seconds=0.0,
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )
        
    except Exception as e:
        logger.error(f"Error creating research job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/research/{job_id}")
async def get_research_job(job_id: str) -> ResearchJobResponse:
    """Get research job status.
    
    Args:
        job_id: Job ID
        
    Returns:
        Research job response
    """
    # In real implementation, this would query the job status
    # For now, return a placeholder response
    return ResearchJobResponse(
        id=job_id,
        topic="Sample Research",
        workflow=WorkflowType.FULL_RESEARCH,
        preset="ml-conference",
        status="running",
        stages=[],
        phases=[],
        cost_usd=0.42,
        duration_seconds=192.0,
        created_at="2026-03-31T10:00:00+00:00",
        started_at="2026-03-31T10:03:12+00:00",
    )


@app.get("/api/v1/research/{job_id}/stream")
async def stream_research_job(job_id: str):
    """Server-Sent Events stream for research job progress.
    
    Args:
        job_id: Job ID
        
    Returns:
        SSE stream of job progress
    """
    # In real implementation, this would stream real-time updates
    from fastapi.responses import StreamingResponse
    import asyncio
    
    async def event_stream():
        """Generate SSE events."""
        import json
        
        for i in range(10):
            await asyncio.sleep(1)
            yield f"data: {json.dumps({'progress': (i + 1) * 10, 'stage': i % 23 + 1})}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/v1/research/{job_id}/approve")
async def approve_research_stage(
    job_id: str,
    stage_number: int,
    feedback: FeedbackSubmission | None = None,
) -> dict[str, str]:
    """Approve a stage in collaborative mode.
    
    Args:
        job_id: Job ID
        stage_number: Stage number to approve
        feedback: Optional feedback
        
    Returns:
        Success message
    """
    return {"status": "approved", "stage": stage_number}


@app.post("/api/v1/research/{job_id}/feedback")
async def submit_research_feedback(
    job_id: str,
    stage_number: int,
    feedback: FeedbackSubmission,
) -> dict[str, str]:
    """Submit feedback for a stage in collaborative mode.
    
    Args:
        job_id: Job ID
        stage_number: Stage number
        feedback: Feedback submission
        
    Returns:
        Success message
    """
    return {"status": "feedback_received", "stage": stage_number}


@app.get("/api/v1/research/{job_id}/artifacts")
async def get_research_artifacts(job_id: str) -> dict[str, Any]:
    """Get research job artifacts.
    
    Args:
        job_id: Job ID
        
    Returns:
        Artifacts dictionary
    """
    return {
        "paper_pdf": f"/api/v1/research/{job_id}/artifacts/paper.pdf",
        "paper_tex": f"/api/v1/research/{job_id}/artifacts/paper.tex",
        "figures": [f"/api/v1/research/{job_id}/artifacts/fig{i}.png" for i in range(1, 5)],
        "data": [],
        "reproducibility_package": f"/api/v1/research/{job_id}/artifacts/reproducibility.zip",
        "audit_trail": f"/api/v1/research/{job_id}/artifacts/audit_trail.json",
    }


@app.delete("/api/v1/research/{job_id}")
async def cancel_research_job(job_id: str) -> dict[str, str]:
    """Cancel a running research job.
    
    Args:
        job_id: Job ID
        
    Returns:
        Success message
    """
    return {"status": "cancelled", "job_id": job_id}


# ============================================================================
# Preset Endpoints
# ============================================================================


@app.get("/api/v1/presets")
async def list_presets() -> list[PresetResponse]:
    """List all available presets.
    
    Returns:
        List of presets
    """
    return [
        PresetResponse(
            name="ml-conference",
            description="Optimized for top ML venues (NeurIPS, ICML, ICLR)",
            tags=["machine-learning", "conference"],
            primary_sources=["semantic_scholar", "openalex", "arxiv"],
            primary_model="claude-sonnet-4-6",
            max_budget_usd=1.50,
            paper_format="neurips",
        ),
        PresetResponse(
            name="biomedical",
            description="Clinical research, drug discovery, genomics",
            tags=["biomedical", "healthcare"],
            primary_sources=["pubmed", "semantic_scholar", "openalex"],
            primary_model="claude-sonnet-4-6",
            max_budget_usd=2.00,
            paper_format="nature",
        ),
        PresetResponse(
            name="nlp",
            description="Computational linguistics, LLM research",
            tags=["nlp", "ai"],
            primary_sources=["semantic_scholar", "acl_anthology", "arxiv"],
            primary_model="claude-sonnet-4-6",
            max_budget_usd=1.50,
            paper_format="acl",
        ),
        PresetResponse(
            name="physics",
            description="Computational physics, chaos theory",
            tags=["physics", "computational"],
            primary_sources=["arxiv", "openalex", "semantic_scholar"],
            primary_model="claude-sonnet-4-6",
            max_budget_usd=1.00,
            paper_format="revtex",
        ),
        PresetResponse(
            name="rapid-draft",
            description="Fast, cheap first draft for brainstorming",
            tags=["rapid", "budget"],
            primary_sources=["semantic_scholar"],
            primary_model="deepseek-v3-2",
            max_budget_usd=0.15,
            paper_format="markdown",
        ),
    ]


@app.get("/api/v1/presets/{preset_name}")
async def get_preset(preset_name: str) -> PresetResponse:
    """Get a specific preset.
    
    Args:
        preset_name: Preset name
        
    Returns:
        Preset details
    """
    presets = await list_presets()
    for preset in presets:
        if preset.name == preset_name:
            return preset
    raise HTTPException(status_code=404, detail=f"Preset not found: {preset_name}")


# ============================================================================
# WebSocket for Real-time Updates
# ============================================================================


active_connections: list[WebSocket] = []


@app.websocket("/api/v1/research/{job_id}/ws")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket for real-time job updates.
    
    Args:
        websocket: WebSocket connection
        job_id: Job ID
    """
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        while True:
            # Receive messages
            data = await websocket.receive_text()
            
            # Send updates
            await websocket.send_text(
                f'{{"stage": 8, "status": "running", "progress": 78, "message": "Generating hypotheses..."}}'
            )
            
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected for job {job_id}")


# ============================================================================
# Main Entry Point
# ============================================================================


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "berb.api.server:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )
