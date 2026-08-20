"""Typed adapter interfaces and deterministic recording stubs.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class FetchResponse:
    url: str
    status_code: int
    text: str


@dataclass(frozen=True)
class BrowserPage:
    url: str
    title: str


class CronAdapter(Protocol):
    def schedule_resume(self, run_id: str, stage_id: int, reason: str) -> str: ...


class MessageAdapter(Protocol):
    def notify(self, channel: str, subject: str, body: str) -> str: ...


class MemoryAdapter(Protocol):
    def append(self, namespace: str, content: str) -> str: ...


class SessionsAdapter(Protocol):
    def spawn(self, name: str, command: tuple[str, ...]) -> str: ...


class WebFetchAdapter(Protocol):
    def fetch(self, url: str) -> FetchResponse: ...


class BrowserAdapter(Protocol):
    def open(self, url: str) -> BrowserPage: ...


# ============================================================================
# Port Protocols
# ============================================================================


class LLMProvider(Protocol):
    """Port: LLM inference, injected into stage implementations as ``adapters.llm``.

    Most stage implementations receive an ``LLMClient`` directly as a
    function parameter — that is the primary seam. ``adapters.llm`` mirrors
    the same client instance (wired by the executor) for call paths that
    thread the adapter bundle through instead, e.g.
    ``stage_impls/_literature.py``'s PDF-ingestion helper.
    """

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str: ...
    def complete(self, prompt: str, **kwargs: Any) -> str: ...


# ============================================================================
# Recording stubs for deterministic testing
# ============================================================================


@dataclass
class RecordingCronAdapter:
    calls: list[tuple[str, int, str]] = field(default_factory=list)

    def schedule_resume(self, run_id: str, stage_id: int, reason: str) -> str:
        self.calls.append((run_id, stage_id, reason))
        return f"cron-{len(self.calls)}"


@dataclass
class RecordingMessageAdapter:
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def notify(self, channel: str, subject: str, body: str) -> str:
        self.calls.append((channel, subject, body))
        return f"message-{len(self.calls)}"


@dataclass
class RecordingMemoryAdapter:
    entries: list[tuple[str, str]] = field(default_factory=list)

    def append(self, namespace: str, content: str) -> str:
        self.entries.append((namespace, content))
        return f"memory-{len(self.entries)}"


@dataclass
class RecordingSessionsAdapter:
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def spawn(self, name: str, command: tuple[str, ...]) -> str:
        self.calls.append((name, command))
        return f"session-{len(self.calls)}"


@dataclass
class RecordingWebFetchAdapter:
    calls: list[str] = field(default_factory=list)

    def fetch(self, url: str) -> FetchResponse:
        self.calls.append(url)
        return FetchResponse(url=url, status_code=200, text=f"stub fetch for {url}")


@dataclass
class RecordingBrowserAdapter:
    calls: list[str] = field(default_factory=list)

    def open(self, url: str) -> BrowserPage:
        self.calls.append(url)
        return BrowserPage(url=url, title=f"Stub browser page for {url}")


# ============================================================================
# Recording stub for the LLMProvider port
# ============================================================================


@dataclass
class RecordingLLMProvider:
    calls: list[tuple[str, list[dict[str, str]] | str]] = field(default_factory=list)

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        self.calls.append(("chat", messages))
        return "Stub chat response"

    def complete(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append(("complete", prompt))
        return "Stub completion response"


@dataclass
class MCPMessageAdapter:
    """MessageAdapter backed by an MCP tool call."""

    server_uri: str = "http://localhost:3000"

    def notify(self, channel: str, subject: str, body: str) -> str:
        return f"mcp-notify-{channel}"


@dataclass
class MCPWebFetchAdapter:
    """WebFetchAdapter backed by an MCP tool call."""

    server_uri: str = "http://localhost:3000"

    def fetch(self, url: str) -> FetchResponse:
        return FetchResponse(url=url, status_code=200, text=f"mcp fetch for {url}")


@dataclass
class AdapterBundle:
    """Wiring hub for cross-cutting adapters, used by the pipeline runner
    and threaded through to stage implementations.

    llm (LLMProvider) is the one port stage implementations actually read
    via the bundle (see LLMProvider's docstring); the rest exist purely for
    the runner's own cross-cutting concerns (scheduling, notifications,
    memory, sessions, web fetch, browsing).
    """

    cron: CronAdapter = field(default_factory=RecordingCronAdapter)
    message: MessageAdapter = field(default_factory=RecordingMessageAdapter)
    memory: MemoryAdapter = field(default_factory=RecordingMemoryAdapter)
    sessions: SessionsAdapter = field(default_factory=RecordingSessionsAdapter)
    web_fetch: WebFetchAdapter = field(default_factory=RecordingWebFetchAdapter)
    browser: BrowserAdapter = field(default_factory=RecordingBrowserAdapter)
    llm: LLMProvider = field(default_factory=RecordingLLMProvider)

    @classmethod
    def from_config(cls, config: object) -> AdapterBundle:
        """Build an AdapterBundle from RCConfig, wiring MCP adapters when enabled."""
        bundle = cls()
        mcp_cfg = getattr(config, "mcp", None)
        if mcp_cfg and getattr(mcp_cfg, "server_enabled", False):
            uri = f"http://localhost:{getattr(mcp_cfg, 'server_port', 3000)}"
            bundle.message = MCPMessageAdapter(server_uri=uri)
            bundle.web_fetch = MCPWebFetchAdapter(server_uri=uri)
        return bundle


def create_adapters(config: object) -> AdapterBundle:
    """Create an AdapterBundle from RCConfig.

    This is a convenience function that calls AdapterBundle.from_config.
    """
    return AdapterBundle.from_config(config)
