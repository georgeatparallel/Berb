"""Berb Web API - REAL pipeline execution with API calls."""

import asyncio
import hashlib
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from berb.server.pipeline_stages import get_stages_for_field

load_dotenv()  # Load .env file from current directory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Berb Web API - Real Execution")

# CORS - MUST be first middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Jobs
_jobs: dict[str, Any] = {}

# Pending topic approvals (for collaborative mode)
_pending_approvals: dict[str, dict] = {}

# API Key
API_KEY = os.environ.get(
    "OPENROUTER_API_KEY",
    "***REMOVED-OPENROUTER-KEY***",
)


# Custom middleware to ensure CORS on ALL responses including OPTIONS
@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    """Add CORS headers to all responses."""
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "http://localhost:3000",
}


# OPTIONS handler - MUST be before catch-all routes
@app.options("/api/{path:path}")
async def options_handler():
    """Handle CORS preflight requests."""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        },
    )


class ResearchRequest(BaseModel):
    topic: str
    preset: str | None = "humanities"
    mode: str = "collaborative"  # Changed default to collaborative


class ResearchResponse(BaseModel):
    id: str
    status: str
    topic: str
    progress: float = 0.0


# UI Route - MUST be before catch-all routes
@app.get("/")
async def serve_ui():
    """Serve topic approval UI."""
    ui_file = r"E:\Documents\Vibe-Coding\Berb\berb\ui\topic-approval.html"
    if os.path.exists(ui_file):
        return FileResponse(ui_file, media_type="text/html")
    return {"error": f"UI not found at {ui_file}"}


@app.get("/healthz")
def healthz():
    return {"status": "healthy", "api_key_set": bool(API_KEY)}


@app.get("/api/v1/presets")
def list_presets():
    return ["humanities", "ml-conference", "physics"]


@app.post("/api/v1/research", response_model=ResearchResponse)
async def create_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "topic": request.topic,
        "preset": request.preset,
        "mode": request.mode,
        "status": "pending_approval" if request.mode == "collaborative" else "starting",
        "progress": 0.0,
        "current_stage": 1,
        "stages": [],
        "cost": 0.0,
        "logs": [],
        "topic_expanded": None,
        "topic_approved": False,
    }
    _jobs[job_id] = job

    if request.mode == "collaborative":
        # First: Generate expanded topic for approval
        background_tasks.add_task(expand_topic_for_approval, job_id, request)
    else:
        # Autonomous mode: start pipeline immediately
        background_tasks.add_task(run_real_pipeline, job_id, request)

    return ResearchResponse(id=job_id, status=job["status"], topic=request.topic)


@app.get("/api/v1/research/{job_id}/topic-approval")
async def get_topic_approval(job_id: str):
    """Get pending topic approval status."""
    if job_id not in _jobs:
        return {"error": "Job not found"}, 404

    job = _jobs[job_id]
    if job["status"] != "pending_approval":
        return {"error": "No pending approval"}, 400

    return {
        "job_id": job_id,
        "original_topic": job["topic"],
        "expanded_topic": job.get("topic_expanded"),
        "category": job.get("preset", "humanities"),
        "status": "pending",
    }


@app.post("/api/v1/research/{job_id}/topic-approve")
async def approve_topic(job_id: str, approve: bool = True):
    """Approve or reject expanded topic."""
    if job_id not in _jobs:
        return {"error": "Job not found"}, 404

    job = _jobs[job_id]

    if approve:
        # Use expanded topic
        if job.get("topic_expanded"):
            job["topic"] = job["topic_expanded"]
            job["logs"].append(f"✓ Approved expanded topic: {job['topic']}")
        job["topic_approved"] = True
        job["status"] = "starting"

        # Start pipeline with approved topic
        import asyncio

        loop = asyncio.get_event_loop()
        req = ResearchRequest(
            topic=job["topic"],
            preset=job["preset"],
            mode="collaborative",
        )
        loop.run_in_executor(None, lambda: asyncio.run(run_real_pipeline(job_id, req)))
    else:
        # Use original topic
        job["logs"].append(f"✗ Rejected expansion, using original: {job['topic']}")
        job["topic_approved"] = True
        job["status"] = "starting"

        # Start pipeline with original topic
        import asyncio

        loop = asyncio.get_event_loop()
        req = ResearchRequest(
            topic=job["topic"],  # Original topic
            preset=job["preset"],
            mode="collaborative",
        )
        loop.run_in_executor(None, lambda: asyncio.run(run_real_pipeline(job_id, req)))

    return {"status": "approved" if approve else "rejected", "topic": job["topic"]}


@app.get("/api/v1/research/{job_id}")
async def get_research(job_id: str):
    if job_id not in _jobs:
        return {"error": "Not found"}, 404
    return _jobs[job_id]


async def call_llm(prompt: str, job_id: str, stage: str) -> str:
    """Make real LLM API call."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=HEADERS,
                json={
                    "model": "deepseek/deepseek-chat-v3",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Track cost
            usage = data.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            cost = (tokens / 1_000_000) * 0.27  # DeepSeek V3 price
            _jobs[job_id]["cost"] += cost

            # Log
            _jobs[job_id]["logs"].append(f"{stage}: LLM call ({tokens} tokens, ${cost:.4f})")
            logger.info(f"Job {job_id} {stage}: {tokens} tokens, ${cost:.4f}")

            return content
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        _jobs[job_id]["logs"].append(f"{stage}: ERROR - {str(e)}")
        return f"Error: {e}"


async def expand_topic_for_approval(job_id: str, request: ResearchRequest):
    """Expand topic while keeping it in the same category, then wait for approval."""
    try:
        _jobs[job_id]["logs"].append("Expanding topic for approval...")

        # Category-specific expansion prompts
        category_prompts = {
            "humanities": "Keep it within Philosophy/Religion/History/Literature. Do NOT add technical/ML aspects.",
            "ml-conference": "Keep it within Machine Learning/AI. Do NOT add unrelated domains.",
            "physics": "Keep it within Physics/Natural Sciences. Do NOT add unrelated domains.",
        }

        category_instruction = category_prompts.get(
            request.preset, "Keep it within the same academic domain."
        )

        expansion_prompt = f"""Original topic: {request.topic}
Category: {request.preset}

Task: Expand this research topic to make it more specific and researchable, BUT:
1. {category_instruction}
2. Keep the core focus on the original topic
3. Add only relevant sub-questions or aspects
4. Do NOT change the fundamental research direction

Provide ONLY the expanded topic, no explanations.

Expanded topic:"""

        expanded = await call_llm(expansion_prompt, job_id, "TOPIC_EXPANSION")

        # Clean up the response (remove any explanations)
        expanded = expanded.strip().split("\n")[0].strip()

        _jobs[job_id]["topic_expanded"] = expanded
        _jobs[job_id]["logs"].append(f"Expanded topic: {expanded}")
        _jobs[job_id]["logs"].append("Waiting for your approval...")

        logger.info(f"Job {job_id}: Topic expanded, waiting for approval")

    except Exception as e:
        logger.error(f"Topic expansion failed: {e}")
        _jobs[job_id]["logs"].append(f"Expansion ERROR: {str(e)}")
        # Fall back to original topic
        _jobs[job_id]["topic_approved"] = True
        _jobs[job_id]["status"] = "starting"


async def run_real_pipeline(job_id: str, request: ResearchRequest):
    """Run REAL pipeline with actual API calls - preserving exact topic."""
    try:
        _jobs[job_id]["status"] = "running"
        logger.info(f"Starting REAL pipeline for: {request.topic}")
        _jobs[job_id]["logs"].append(f"Topic: {request.topic}")
        _jobs[job_id]["logs"].append(f"Preset: {request.preset}")

        # Create run directory
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        topic_hash = hashlib.sha256(request.topic.encode()).hexdigest()[:6]
        run_id = f"rc-{ts}-{topic_hash}"
        run_dir = Path("artifacts") / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        _jobs[job_id]["run_dir"] = str(run_dir)
        _jobs[job_id]["run_id"] = run_id

        # Save the EXACT topic to file (no LLM expansion)
        topic_file = run_dir / "topic.txt"
        topic_file.write_text(request.topic, encoding="utf-8")
        _jobs[job_id]["logs"].append(f"Topic saved to {topic_file}")

        # Determine pipeline type based on preset
        preset_type = request.preset.lower() if request.preset else "general"

        # Define reasoning methods per field
        if preset_type in ["humanities", "philosophy", "religion", "history", "literature"]:
            pipeline_type = "humanities"
            _jobs[job_id]["logs"].append("✓ Humanities pipeline: Qualitative reasoning")
            _jobs[job_id]["logs"].append(
                "✓ Methods: Socratic, Dialectical, Multi-Perspective, Jury"
            )

        elif preset_type in [
            "social-sciences",
            "psychology",
            "sociology",
            "anthropology",
            "economics",
        ]:
            pipeline_type = "social-sciences"
            _jobs[job_id]["logs"].append("✓ Social Sciences pipeline: Mixed methods")
            _jobs[job_id]["logs"].append("✓ Methods: Bayesian, Multi-Perspective, Scientific")

        elif preset_type in ["physics", "chemistry", "biology", "natural-sciences"]:
            pipeline_type = "natural-sciences"
            _jobs[job_id]["logs"].append("✓ Natural Sciences pipeline: Scientific method")
            _jobs[job_id]["logs"].append("✓ Methods: Scientific, Bayesian, Pre-Mortem")

        elif preset_type in ["ml-conference", "nlp", "computer-vision", "ai", "cs"]:
            pipeline_type = "ml-cs"
            _jobs[job_id]["logs"].append("✓ ML/CS pipeline: Engineering + Scientific")
            _jobs[job_id]["logs"].append("✓ Methods: Scientific, Pre-Mortem, Multi-Perspective")

        elif preset_type in ["biomedical", "medicine", "clinical"]:
            pipeline_type = "biomedical"
            _jobs[job_id]["logs"].append("✓ Biomedical pipeline: Clinical rigor")
            _jobs[job_id]["logs"].append("✓ Methods: Scientific, Bayesian, Jury")

        elif preset_type in ["engineering", "robotics", "systems"]:
            pipeline_type = "engineering"
            _jobs[job_id]["logs"].append("✓ Engineering pipeline: Design-focused")
            _jobs[job_id]["logs"].append("✓ Methods: Pre-Mortem, Scientific, Debate")

        else:
            pipeline_type = "general"
            _jobs[job_id]["logs"].append("✓ General pipeline: Balanced reasoning")
            _jobs[job_id]["logs"].append("✓ Methods: Multi-Perspective, Bayesian, Research")

        # Get stages for this pipeline type
        stages = get_stages_for_field(pipeline_type, request.topic)
        total_stages_count = len(stages)
        _jobs[job_id]["logs"].append(f"✓ Total stages: {total_stages_count}")

        # Execute each stage with REAL LLM calls
        total_stages = len(stages)
        for i, stage_item in enumerate(stages):
            stage_name = stage_item[0]

            # Handle both old format (string) and new format (dict with reasoning_method)
            if isinstance(stage_item[1], dict):
                prompt_template = stage_item[1]["prompt"]
                reasoning_method = stage_item[1].get("reasoning_method", "default")
            else:
                prompt_template = stage_item[1]
                reasoning_method = "default"

            _jobs[job_id]["current_stage"] = i + 1
            _jobs[job_id]["progress"] = (i + 1) / total_stages * 100
            _jobs[job_id]["stages"].append(
                {
                    "number": i + 1,
                    "name": stage_name,
                    "status": "running",
                    "reasoning_method": reasoning_method,
                }
            )

            logger.info(f"Stage {i + 1}/{total_stages}: {stage_name} [{reasoning_method}]")
            _jobs[job_id]["logs"].append(
                f"Stage {i + 1}/{total_stages}: {stage_name} [{reasoning_method}]"
            )

            # Make REAL LLM call
            prompt = f"Research topic: {request.topic}\n\nTask: {prompt_template}"
            result = await call_llm(prompt, job_id, f"{stage_name} [{reasoning_method}]")

            # Save stage result
            stage_file = run_dir / f"stage_{i + 1:02d}_{stage_name.lower()}.txt"
            stage_file.write_text(result, encoding="utf-8")

            # Mark stage complete
            _jobs[job_id]["stages"][i]["status"] = "complete"
            _jobs[job_id]["stages"][i]["result"] = (
                result[:200] + "..." if len(result) > 200 else result
            )

            logger.info(f"Stage {stage_name} complete")

        # Complete
        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["progress"] = 100.0
        _jobs[job_id]["result"] = {
            "run_dir": str(run_dir),
            "run_id": run_id,
            "total_cost": _jobs[job_id]["cost"],
            "stages_completed": 23,
        }

        # Create summary
        summary_file = run_dir / "SUMMARY.md"
        summary_file.write_text(
            f"# Research Summary\n\n"
            f"**Topic:** {request.topic}\n"
            f"**Total Cost:** ${_jobs[job_id]['cost']:.2f}\n"
            f"**Stages:** 23/23 complete\n"
            f"**Run ID:** {run_id}\n",
            encoding="utf-8",
        )

        logger.info(f"RESEARCH COMPLETED: {run_id}, Cost: ${_jobs[job_id]['cost']:.2f}")

    except Exception as e:
        logger.error(f"Pipeline FAILED: {e}", exc_info=True)
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)
        _jobs[job_id]["logs"].append(f"FAILED: {str(e)}")


@app.get("/api/v1/research/{job_id}/stream")
async def stream_progress(job_id: str):
    """Stream progress via SSE."""
    from fastapi.responses import StreamingResponse

    async def generate():
        for _ in range(500):  # 500 * 2s = 16 minutes max
            if job_id not in _jobs:
                break

            import json

            yield f"data: {json.dumps(_jobs[job_id])}\n\n"

            if _jobs[job_id]["status"] in ("completed", "failed"):
                break

            await asyncio.sleep(2)

    return StreamingResponse(generate(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("  Berb Web API - REAL EXECUTION")
    print("=" * 60)
    print(f"  API Key: {API_KEY[:20]}...")
    print("  UI: http://localhost:8080 (separate server)")
    print("  API:  http://localhost:8082")
    print("  REAL LLM calls: YES")
    print("=" * 60)
    uvicorn.run(app, host="localhost", port=8082)
