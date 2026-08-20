"""Tests for Agent A — Web platform and user interface.

Covers: FastAPI routes, WebSocket, intents, dashboard collector, wizard, voice commands.
All tests run without external services (mocked LLM, mocked Whisper).
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


def _minimal_config_data(**overrides: object) -> dict:
    """Minimal valid RCConfig.from_dict() input, with optional top-level overrides."""
    data = {
        "project": {"name": "test"},
        "research": {"topic": "test topic"},
        "runtime": {"timezone": "UTC"},
        "notifications": {"channel": "console"},
        "knowledge_base": {"root": "knowledge"},
        "llm": {
            "provider": "openai-compatible",
            "base_url": "http://localhost",
            "api_key_env": "TEST_KEY",
        },
    }
    data.update(overrides)
    return data


class TestServerConfig:
    """Test ServerConfig and DashboardConfig in config.py."""

    def test_server_config_defaults(self) -> None:
        from berb.config import ServerConfig

        cfg = ServerConfig()
        assert cfg.enabled is False
        assert cfg.host == "127.0.0.1"  # Secure default (P0 fix)
        assert cfg.port == 8080
        assert cfg.cors_origins == ()  # Empty by default (P0 fix)
        assert cfg.auth_token == ""
        assert cfg.voice_enabled is False

    def test_dashboard_config_defaults(self) -> None:
        from berb.config import DashboardConfig

        cfg = DashboardConfig()
        assert cfg.enabled is True
        assert cfg.refresh_interval_sec == 5
        assert cfg.max_log_lines == 1000

    def test_parse_server_config(self) -> None:
        from berb.config import _parse_server_config

        cfg = _parse_server_config(
            {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 9090,
                "auth_token": "secret123",
            }
        )
        assert cfg.enabled is True
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 9090
        assert cfg.auth_token == "secret123"

    def test_parse_server_config_empty(self) -> None:
        from berb.config import _parse_server_config

        cfg = _parse_server_config({})
        assert cfg.enabled is False
        assert cfg.port == 8080

    def test_parse_dashboard_config(self) -> None:
        from berb.config import _parse_dashboard_config

        cfg = _parse_dashboard_config(
            {
                "refresh_interval_sec": 10,
                "max_log_lines": 500,
            }
        )
        assert cfg.refresh_interval_sec == 10
        assert cfg.max_log_lines == 500

    def test_parse_server_config_empty_cors_is_deny_all(self) -> None:
        # P0 fix: the parser used to substitute cors=("*",) when cors_origins was
        # omitted, silently widening the ServerConfig(cors_origins=()) default.
        from berb.config import _parse_server_config

        cfg = _parse_server_config({})
        assert cfg.cors_origins == ()

    def test_rcconfig_rejects_nonloopback_host_without_auth_token(self) -> None:
        # P0 fix (audit §3.1): a server.host that isn't loopback with no
        # auth_token must be rejected, not silently started unauthenticated.
        from berb.config import RCConfig

        data = _minimal_config_data(server={"enabled": True, "host": "0.0.0.0"})
        with pytest.raises(ValueError, match="SECURITY VIOLATION"):
            RCConfig.from_dict(data, check_paths=False)

    def test_rcconfig_allows_nonloopback_host_with_auth_token(self) -> None:
        from berb.config import RCConfig

        data = _minimal_config_data(
            server={"enabled": True, "host": "0.0.0.0", "auth_token": "secret123"}
        )
        cfg = RCConfig.from_dict(data, check_paths=False)
        assert cfg.server.host == "0.0.0.0"
        assert cfg.server.auth_token == "secret123"

    def test_rcconfig_allows_nonloopback_host_with_explicit_insecure_opt_out(
        self,
    ) -> None:
        from berb.config import RCConfig

        data = _minimal_config_data(
            server={"enabled": True, "host": "0.0.0.0", "insecure": True}
        )
        cfg = RCConfig.from_dict(data, check_paths=False)
        assert cfg.server.host == "0.0.0.0"
        assert cfg.server.insecure is True

    def test_rcconfig_rejects_nonloopback_host_even_when_server_disabled(self) -> None:
        # `berb serve`/`berb dashboard` bind unconditionally when invoked; they
        # never check config.server.enabled. Gating this validation on that flag
        # let an unsafe host/auth combo through untouched (PR #9 review finding).
        from berb.config import RCConfig

        data = _minimal_config_data(server={"enabled": False, "host": "0.0.0.0"})
        with pytest.raises(ValueError, match="SECURITY VIOLATION"):
            RCConfig.from_dict(data, check_paths=False)

    def test_rcconfig_has_server_and_dashboard(self) -> None:
        from berb.config import DashboardConfig, RCConfig, ServerConfig

        data = _minimal_config_data(
            server={"enabled": True, "port": 9999},
            dashboard={"refresh_interval_sec": 3},
        )
        cfg = RCConfig.from_dict(data, check_paths=False)
        assert isinstance(cfg.server, ServerConfig)
        assert cfg.server.enabled is True
        assert cfg.server.port == 9999
        assert isinstance(cfg.dashboard, DashboardConfig)
        assert cfg.dashboard.refresh_interval_sec == 3


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Test new CLI subcommands are registered."""

    def test_serve_subcommand_exists(self) -> None:
        from berb.cli import main

        with pytest.raises(SystemExit) as exc:
            main(["serve", "--help"])
        assert exc.value.code == 0

    def test_dashboard_subcommand_exists(self) -> None:
        from berb.cli import main

        with pytest.raises(SystemExit) as exc:
            main(["dashboard", "--help"])
        assert exc.value.code == 0

    def test_wizard_subcommand_exists(self) -> None:
        from berb.cli import main

        with pytest.raises(SystemExit) as exc:
            main(["wizard", "--help"])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# Intent classification tests
# ---------------------------------------------------------------------------


class TestIntents:
    """Test intent classification."""

    def test_help_intent(self) -> None:
        from berb.server.dialog.intents import Intent, classify_intent

        intent, conf = classify_intent("help")
        assert intent == Intent.HELP

    def test_status_intent(self) -> None:
        from berb.server.dialog.intents import Intent, classify_intent

        intent, _ = classify_intent("What stage are we at?")
        assert intent == Intent.CHECK_STATUS

    def test_start_intent(self) -> None:
        from berb.server.dialog.intents import Intent, classify_intent

        intent, _ = classify_intent("Start the pipeline")
        assert intent == Intent.START_PIPELINE

    def test_topic_intent(self) -> None:
        from berb.server.dialog.intents import Intent, classify_intent

        intent, _ = classify_intent("Help me find a research direction")
        assert intent == Intent.TOPIC_SELECTION

    def test_results_intent(self) -> None:
        from berb.server.dialog.intents import Intent, classify_intent

        intent, _ = classify_intent("What are the results?")
        assert intent == Intent.DISCUSS_RESULTS

    def test_config_intent(self) -> None:
        from berb.server.dialog.intents import Intent, classify_intent

        intent, _ = classify_intent("Change the learning rate to 0.001")
        assert intent == Intent.MODIFY_CONFIG

    def test_paper_intent(self) -> None:
        from berb.server.dialog.intents import Intent, classify_intent

        intent, _ = classify_intent("Edit the abstract")
        assert intent == Intent.EDIT_PAPER

    def test_general_intent(self) -> None:
        from berb.server.dialog.intents import Intent, classify_intent

        intent, _ = classify_intent("Hello there")
        assert intent == Intent.GENERAL_CHAT

    def test_chinese_status(self) -> None:
        from berb.server.dialog.intents import Intent, classify_intent

        intent, _ = classify_intent("现在到哪一步了")
        assert intent == Intent.CHECK_STATUS

    def test_chinese_start(self) -> None:
        from berb.server.dialog.intents import Intent, classify_intent

        intent, _ = classify_intent("开始跑实验")
        assert intent == Intent.START_PIPELINE

    def test_empty_message(self) -> None:
        from berb.server.dialog.intents import Intent, classify_intent

        intent, conf = classify_intent("")
        assert intent == Intent.GENERAL_CHAT
        assert conf == 0.0


# ---------------------------------------------------------------------------
# Session management tests
# ---------------------------------------------------------------------------


class TestSession:
    """Test chat session management."""

    def test_session_create(self) -> None:
        from berb.server.dialog.session import SessionManager

        mgr = SessionManager()
        session = mgr.get_or_create("client1")
        assert session.client_id == "client1"
        assert len(session.history) == 0

    def test_session_add_message(self) -> None:
        from berb.server.dialog.session import SessionManager

        mgr = SessionManager()
        session = mgr.get_or_create("client1")
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi!")
        assert len(session.history) == 2
        assert session.history[0].role == "user"

    def test_session_context(self) -> None:
        from berb.server.dialog.session import SessionManager

        mgr = SessionManager()
        session = mgr.get_or_create("client1")
        for i in range(20):
            session.add_message("user", f"msg {i}")
        ctx = session.get_context(last_n=5)
        assert len(ctx) == 5

    def test_session_max_history(self) -> None:
        from berb.server.dialog.session import ChatSession

        session = ChatSession(client_id="test")
        for i in range(100):
            session.add_message("user", f"msg {i}")
        assert len(session.history) <= session.MAX_HISTORY

    def test_session_persistence(self) -> None:
        from berb.server.dialog.session import SessionManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(persist_dir=tmpdir)
            session = mgr.get_or_create("persist-test")
            session.add_message("user", "saved message")
            mgr.save("persist-test")

            # Load in new manager
            mgr2 = SessionManager(persist_dir=tmpdir)
            loaded = mgr2.load("persist-test")
            assert loaded is not None
            assert len(loaded.history) == 1
            assert loaded.history[0].content == "saved message"


# ---------------------------------------------------------------------------
# Dashboard collector tests
# ---------------------------------------------------------------------------


class TestDashboardCollector:
    """Test dashboard data collection from artifacts/."""

    def test_collect_empty_dir(self) -> None:
        from berb.dashboard.collector import DashboardCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            collector = DashboardCollector(artifacts_dir=tmpdir)
            runs = collector.collect_all()
            assert runs == []

    def test_collect_run_with_checkpoint(self) -> None:
        from berb.dashboard.collector import DashboardCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "rc-20260315-abc123"
            run_dir.mkdir()
            ckpt = {"stage": 5, "stage_name": "LITERATURE_SCREEN", "status": "running"}
            (run_dir / "checkpoint.json").write_text(json.dumps(ckpt))

            collector = DashboardCollector(artifacts_dir=tmpdir)
            runs = collector.collect_all()
            assert len(runs) == 1
            assert runs[0].current_stage == 5
            assert runs[0].current_stage_name == "LITERATURE_SCREEN"

    def test_collect_run_active_heartbeat(self) -> None:
        from berb.dashboard.collector import DashboardCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "rc-20260315-test01"
            run_dir.mkdir()
            hb = {"timestamp": time.time()}  # fresh heartbeat
            (run_dir / "heartbeat.json").write_text(json.dumps(hb))

            collector = DashboardCollector(artifacts_dir=tmpdir)
            runs = collector.collect_all()
            assert len(runs) == 1
            assert runs[0].is_active is True

    def test_collect_run_stale_heartbeat(self) -> None:
        from berb.dashboard.collector import DashboardCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "rc-20260315-stale1"
            run_dir.mkdir()
            hb = {"timestamp": time.time() - 120}  # old heartbeat
            (run_dir / "heartbeat.json").write_text(json.dumps(hb))

            collector = DashboardCollector(artifacts_dir=tmpdir)
            runs = collector.collect_all()
            assert runs[0].is_active is False

    def test_collect_stage_directories(self) -> None:
        from berb.dashboard.collector import DashboardCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "rc-20260315-stages"
            run_dir.mkdir()
            (run_dir / "stage-01").mkdir()
            (run_dir / "stage-02").mkdir()
            (run_dir / "stage-03").mkdir()

            collector = DashboardCollector(artifacts_dir=tmpdir)
            runs = collector.collect_all()
            assert len(runs[0].stages_completed) == 3

    def test_collect_metrics(self) -> None:
        from berb.dashboard.collector import DashboardCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "rc-20260315-metric"
            run_dir.mkdir()
            metrics = {"accuracy": 0.85, "loss": 0.12}
            (run_dir / "results.json").write_text(json.dumps(metrics))

            collector = DashboardCollector(artifacts_dir=tmpdir)
            runs = collector.collect_all()
            assert runs[0].metrics["accuracy"] == 0.85

    def test_snapshot_to_dict(self) -> None:
        from berb.dashboard.collector import RunSnapshot

        snap = RunSnapshot(run_id="test-1", path="/tmp/test")
        d = snap.to_dict()
        assert d["run_id"] == "test-1"
        assert "current_stage" in d


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------


class TestMetrics:
    """Test metric aggregation."""

    def test_aggregate_empty(self) -> None:
        from berb.dashboard.metrics import aggregate_metrics

        result = aggregate_metrics([])
        assert result["total_runs"] == 0

    def test_aggregate_mixed(self) -> None:
        from berb.dashboard.metrics import aggregate_metrics

        runs = [
            {"is_active": True, "status": "running", "current_stage": 10},
            {"is_active": False, "status": "completed", "current_stage": 23},
            {"is_active": False, "status": "failed", "current_stage": 5},
        ]
        result = aggregate_metrics(runs)
        assert result["total_runs"] == 3
        assert result["active_runs"] == 1
        assert result["completed_runs"] == 1
        assert result["failed_runs"] == 1

    def test_extract_training_curve(self) -> None:
        from berb.dashboard.metrics import extract_training_curve

        metrics = {
            "training_log": [
                {"epoch": 1, "loss": 0.5, "accuracy": 0.7},
                {"epoch": 2, "loss": 0.3, "accuracy": 0.85},
            ]
        }
        curve = extract_training_curve(metrics)
        assert len(curve) == 2
        assert curve[1]["loss"] == 0.3


# ---------------------------------------------------------------------------
# Voice command tests
# ---------------------------------------------------------------------------


class TestVoiceCommands:
    """Test voice command parsing."""

    def test_start_command(self) -> None:
        from berb.voice.commands import VoiceCommand, parse_voice_input

        result = parse_voice_input("start experiment")
        assert result.command == VoiceCommand.START

    def test_stop_command(self) -> None:
        from berb.voice.commands import VoiceCommand, parse_voice_input

        result = parse_voice_input("stop")
        assert result.command == VoiceCommand.STOP

    def test_chinese_start(self) -> None:
        from berb.voice.commands import VoiceCommand, parse_voice_input

        result = parse_voice_input("开始实验")
        assert result.command == VoiceCommand.START

    def test_chinese_pause(self) -> None:
        from berb.voice.commands import VoiceCommand, parse_voice_input

        result = parse_voice_input("暂停")
        assert result.command == VoiceCommand.PAUSE

    def test_not_a_command(self) -> None:
        from berb.voice.commands import VoiceCommand, parse_voice_input

        result = parse_voice_input("What about the neural network?")
        assert result.command == VoiceCommand.NONE

    def test_status_command(self) -> None:
        from berb.voice.commands import VoiceCommand, parse_voice_input

        result = parse_voice_input("查看进度")
        assert result.command == VoiceCommand.STATUS


# ---------------------------------------------------------------------------
# Wizard tests
# ---------------------------------------------------------------------------


class TestWizard:
    """Test wizard templates and validation."""

    def test_list_templates(self) -> None:
        from berb.wizard.templates import list_templates

        templates = list_templates()
        assert len(templates) >= 3
        names = [t["name"] for t in templates]
        assert "quick-demo" in names
        assert "standard-cv" in names

    def test_get_template(self) -> None:
        from berb.wizard.templates import get_template

        tpl = get_template("quick-demo")
        assert tpl is not None
        assert tpl["experiment.mode"] == "simulated"

    def test_get_template_missing(self) -> None:
        from berb.wizard.templates import get_template

        assert get_template("nonexistent") is None

    def test_wizard_web_mode(self) -> None:
        from berb.wizard.quickstart import QuickStartWizard

        wizard = QuickStartWizard()
        config = wizard.run_web(
            [
                {"key": "project_name", "value": "test-proj"},
                {"key": "topic", "value": "neural scaling laws"},
                {"key": "mode", "value": "docker"},
            ]
        )
        assert config.get("project", {}).get("name") == "test-proj"
        assert config.get("research", {}).get("topic") == "neural scaling laws"

    def test_environment_detection(self) -> None:
        from berb.wizard.validator import detect_environment

        report = detect_environment()
        assert report.has_python is True
        assert report.python_version != ""
        d = report.to_dict()
        assert "has_gpu" in d
        assert "recommendations" in d


# ---------------------------------------------------------------------------
# WebSocket events tests
# ---------------------------------------------------------------------------


class TestEvents:
    """Test WebSocket event types."""

    def test_event_serialization(self) -> None:
        from berb.server.websocket.events import Event, EventType

        evt = Event(type=EventType.STAGE_COMPLETE, data={"stage": 5})
        json_str = evt.to_json()
        parsed = json.loads(json_str)
        assert parsed["type"] == "stage_complete"
        assert parsed["data"]["stage"] == 5

    def test_event_deserialization(self) -> None:
        from berb.server.websocket.events import Event, EventType

        raw = json.dumps(
            {
                "type": "heartbeat",
                "data": {"active_clients": 3},
                "timestamp": 1234567890.0,
            }
        )
        evt = Event.from_json(raw)
        assert evt.type == EventType.HEARTBEAT
        assert evt.data["active_clients"] == 3

    def test_event_types_enum(self) -> None:
        from berb.server.websocket.events import EventType

        assert EventType.CONNECTED.value == "connected"
        assert EventType.STAGE_START.value == "stage_start"
        assert EventType.CHAT_RESPONSE.value == "chat_response"


# ---------------------------------------------------------------------------
# Dialog router tests
# ---------------------------------------------------------------------------


class TestDialogRouter:
    """Test dialog message routing."""

    @pytest.mark.asyncio
    async def test_route_help_message(self) -> None:
        from berb.server.dialog.router import route_message

        response = await route_message("help", "test-client")
        assert "help" in response.lower() or "I can" in response

    @pytest.mark.asyncio
    async def test_route_json_message(self) -> None:
        from berb.server.dialog.router import route_message

        msg = json.dumps({"message": "help me"})
        response = await route_message(msg, "test-client-2")
        assert isinstance(response, str)
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_route_status_message(self) -> None:
        from berb.server.dialog.router import route_message

        response = await route_message("What's the current progress?", "test-client-3")
        assert isinstance(response, str)


# ---------------------------------------------------------------------------
# FastAPI app tests (requires fastapi + httpx)
# ---------------------------------------------------------------------------


class TestFastAPIApp:
    """Test FastAPI application if dependencies are available."""

    @pytest.fixture
    def _skip_if_no_fastapi(self) -> None:
        try:
            import fastapi  # noqa: F401
            import httpx  # noqa: F401
        except ImportError:
            pytest.skip("fastapi/httpx not installed")

    @pytest.fixture
    def app(self, _skip_if_no_fastapi: None) -> object:
        from berb.config import RCConfig

        data = {
            "project": {"name": "test"},
            "research": {"topic": "test"},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "console"},
            "knowledge_base": {"root": "knowledge"},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost",
                "api_key_env": "TEST",
            },
        }
        config = RCConfig.from_dict(data, check_paths=False)
        from berb.server.app import create_app

        return create_app(config)

    @pytest.mark.asyncio
    async def test_health_endpoint(self, app: object) -> None:
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_config_endpoint(self, app: object) -> None:
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/config")
            assert resp.status_code == 200
            data = resp.json()
            assert data["project"] == "test"

    @pytest.mark.asyncio
    async def test_pipeline_status_idle(self, app: object) -> None:
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/pipeline/status")
            assert resp.status_code == 200
            assert resp.json()["status"] == "idle"

    @pytest.mark.asyncio
    async def test_pipeline_stages(self, app: object) -> None:
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/pipeline/stages")
            assert resp.status_code == 200
            stages = resp.json()["stages"]
            assert len(stages) == 23

    @pytest.mark.asyncio
    async def test_runs_list(self, app: object) -> None:
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/runs")
            assert resp.status_code == 200
            assert "runs" in resp.json()

    @pytest.mark.asyncio
    async def test_projects_list(self, app: object) -> None:
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/projects")
            assert resp.status_code == 200
            assert "projects" in resp.json()

    @pytest.mark.asyncio
    async def test_stop_pipeline_404_when_idle(self, app: object) -> None:
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/pipeline/stop")
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TokenAuthMiddleware — pure-ASGI auth covering both HTTP and WebSocket scopes
# (audit §3.2: BaseHTTPMiddleware never saw "websocket" scopes, so /ws/events
# was unauthenticated even with a token configured)
# ---------------------------------------------------------------------------


class TestTokenAuthMiddleware:
    """Test TokenAuthMiddleware against a real app with auth_token configured."""

    @pytest.fixture
    def _skip_if_no_fastapi(self) -> None:
        try:
            import fastapi  # noqa: F401
            import httpx  # noqa: F401
        except ImportError:
            pytest.skip("fastapi/httpx not installed")

    @pytest.fixture
    def app(self, _skip_if_no_fastapi: None) -> object:
        from berb.config import RCConfig
        from berb.server.app import create_app

        data = _minimal_config_data(
            server={"enabled": True, "host": "127.0.0.1", "auth_token": "secret123"}
        )
        config = RCConfig.from_dict(data, check_paths=False)
        return create_app(config)

    @pytest.mark.asyncio
    async def test_health_exempt_without_token(self, app: object) -> None:
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/health")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_config_rejected_without_token(self, app: object) -> None:
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/config")
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_config_rejected_with_wrong_token(self, app: object) -> None:
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/config", headers={"authorization": "Bearer wrong"}
            )
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_config_allowed_with_correct_token(self, app: object) -> None:
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/config", headers={"authorization": "Bearer secret123"}
            )
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_docs_no_longer_exempt(self, app: object) -> None:
        # audit §3.2: /docs used to be hardcoded-exempt, publishing the full
        # API surface pre-auth. It must now require the token like any route.
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/docs")
            assert resp.status_code == 401

    def test_websocket_rejected_without_token(self, app: object) -> None:
        from starlette.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        client = TestClient(app)  # type: ignore[arg-type]
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/events"):
                pass
        assert exc_info.value.code == 4401

    def test_websocket_accepted_with_correct_token(self, app: object) -> None:
        from starlette.testclient import TestClient

        client = TestClient(app)  # type: ignore[arg-type]
        with client.websocket_connect("/ws/events?token=secret123") as ws:
            # A successful handshake is the assertion — the server accepted
            # the connection instead of closing it with code 4401.
            ws.close()
