"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from berb.config import RCConfig
from berb.server.middleware.auth import TokenAuthMiddleware
from berb.server.websocket.manager import ConnectionManager
from berb.server.websocket.events import Event, EventType

logger = logging.getLogger(__name__)

# Shared application state accessible by routes
_app_state: dict[str, Any] = {}


def create_app(
    config: RCConfig,
    *,
    dashboard_only: bool = False,
    monitor_dir: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Berb configuration.
        dashboard_only: If True, only mount dashboard routes.
        monitor_dir: Specific run directory to monitor.
    """
    app = FastAPI(
        title="Berb",
        description="Autonomous Research Pipeline — Web Interface",
        version="0.5.0",
    )

    # Store config in shared state
    _app_state["config"] = config
    _app_state["monitor_dir"] = monitor_dir

    # --- CORS ---
    # allow_credentials=True is incompatible with allow_origins=["*"] per the CORS spec.
    # Only enable credentials when an explicit allowlist is configured.
    _origins = list(config.server.cors_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=bool(_origins),  # False when no origins configured
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Token auth ---
    if config.server.auth_token:
        app.add_middleware(TokenAuthMiddleware, token=config.server.auth_token)

    # --- WebSocket manager ---
    event_manager = ConnectionManager()
    _app_state["event_manager"] = event_manager

    # --- Health endpoints ---
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Kubernetes liveness / readiness probe."""
        return {"status": "ok"}

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "0.5.0",
            "active_connections": event_manager.active_count,
        }

    @app.get("/api/config")
    async def config_summary() -> dict[str, Any]:
        return {
            "project": config.project.name,
            "topic": config.research.topic,
            "mode": config.experiment.mode,
            "server": {
                "voice_enabled": config.server.voice_enabled,
                "dashboard_enabled": config.dashboard.enabled,
            },
        }

    # --- Routes ---
    from berb.server.routes.pipeline import router as pipeline_router
    from berb.server.routes.projects import router as projects_router

    app.include_router(pipeline_router)
    app.include_router(projects_router)

    if not dashboard_only:
        from berb.server.routes.chat import router as chat_router, set_chat_manager

        set_chat_manager(event_manager)
        app.include_router(chat_router)

        if config.server.voice_enabled:
            from berb.server.routes.voice import router as voice_router

            app.include_router(voice_router)

    # --- WebSocket events endpoint ---
    from fastapi import WebSocket, WebSocketDisconnect
    import uuid

    @app.websocket("/ws/events")
    async def events_ws(websocket: WebSocket) -> None:
        """Real-time event stream for dashboard."""
        client_id = f"evt-{uuid.uuid4().hex[:8]}"
        await event_manager.connect(websocket, client_id)
        try:
            while True:
                # Keep connection alive; client can send pings
                await websocket.receive_text()
        except WebSocketDisconnect:
            event_manager.disconnect(client_id)

    # --- Static files (frontend) ---
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
    if frontend_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

        # Serve index.html at root
        from fastapi.responses import FileResponse

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(str(frontend_dir / "index.html"))

    # --- Background tasks ---
    @app.on_event("startup")
    async def startup() -> None:
        asyncio.create_task(event_manager.heartbeat_loop(interval=15.0))

        if config.dashboard.enabled:
            from berb.dashboard.broadcaster import start_dashboard_loop

            asyncio.create_task(
                start_dashboard_loop(
                    event_manager,
                    interval=config.dashboard.refresh_interval_sec,
                    monitor_dir=monitor_dir,
                )
            )
        logger.info("Berb Web server started")

    return app
