"""Typed adapter interfaces and deterministic recording stubs.

Phase 2 Architecture Upgrade: Added LLMProvider, LiteratureSource,
ExperimentSandbox, and ArtifactStore ports with Recording stubs for
testing.

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
# Port Protocols (Phase 2 — Hexagonal boundary for stage implementations)
# ============================================================================


class LLMProvider(Protocol):
    """Port: LLM inference. Stage implementations depend on this, not LLMClient."""

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str: ...
    def complete(self, prompt: str, **kwargs: Any) -> str: ...


@dataclass(frozen=True)
class LiteratureResult:
    """A single literature search result."""

    title: str
    authors: list[str]
    abstract: str
    source: str
    url: str | None = None
    year: int | None = None
    doi: str | None = None


class LiteratureSource(Protocol):
    """Port: literature retrieval. Wraps arXiv, OpenAlex, Semantic Scholar, etc."""

    def search(self, query: str, max_results: int = 10) -> list[LiteratureResult]: ...
    def fetch_full_text(self, url: str) -> str | None: ...


@dataclass(frozen=True)
class SandboxResult:
    """Result from an experiment sandbox execution."""

    returncode: int
    stdout: str
    stderr: str
    metrics: dict[str, float] | None = None
    timed_out: bool = False


class ExperimentSandbox(Protocol):
    """Port: experiment execution. Wraps Docker, SSH, Colab, local sandbox."""

    def execute(self, code: str, timeout_sec: int = 300) -> SandboxResult: ...
    def setup(self) -> bool: ...
    def teardown(self) -> None: ...


class ArtifactStore(Protocol):
    """Port: persistent artifact storage. Default: local filesystem."""

    def read(self, path: str) -> str | None: ...
    def write(self, path: str, content: str) -> bool: ...
    def exists(self, path: str) -> bool: ...


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
# Recording stubs for new Port Protocols
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
class RecordingLiteratureSource:
    search_calls: list[str] = field(default_factory=list)
    fetch_calls: list[str] = field(default_factory=list)

    def search(self, query: str, max_results: int = 10) -> list[LiteratureResult]:
        self.search_calls.append(query)
        return [
            LiteratureResult(
                title=f"Stub result for {query}",
                authors=["Author A", "Author B"],
                abstract="This is a stub abstract.",
                source="recording",
            )
        ]

    def fetch_full_text(self, url: str) -> str | None:
        self.fetch_calls.append(url)
        return f"Stub full text for {url}"


@dataclass
class RecordingExperimentSandbox:
    execute_calls: list[str] = field(default_factory=list)

    def execute(self, code: str, timeout_sec: int = 300) -> SandboxResult:
        self.execute_calls.append(code)
        return SandboxResult(returncode=0, stdout="Stub stdout", stderr="")

    def setup(self) -> bool:
        return True

    def teardown(self) -> None:
        pass


@dataclass
class RecordingArtifactStore:
    _store: dict[str, str] = field(default_factory=dict)

    def read(self, path: str) -> str | None:
        return self._store.get(path)

    def write(self, path: str, content: str) -> bool:
        self._store[path] = content
        return True

    def exists(self, path: str) -> bool:
        return path in self._store


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
    """Wiring hub for all port adapters.

    Existing adapters (cron, message, memory, sessions, web_fetch, browser):
      Used by the pipeline runner for cross-cutting concerns.

    Port adapters (Phase 2 — hexagonal boundary for stage implementations):
      llm:     LLMProvider — injected into stage implementations
      lit:     LiteratureSource — wraps arXiv/OpenAlex/SemanticScholar
      sandbox: ExperimentSandbox — wraps Docker/SSH/Colab/local
      store:   ArtifactStore — local FS, future S3
    """

    # Existing cross-cutting adapters
    cron: CronAdapter = field(default_factory=RecordingCronAdapter)
    message: MessageAdapter = field(default_factory=RecordingMessageAdapter)
    memory: MemoryAdapter = field(default_factory=RecordingMemoryAdapter)
    sessions: SessionsAdapter = field(default_factory=RecordingSessionsAdapter)
    web_fetch: WebFetchAdapter = field(default_factory=RecordingWebFetchAdapter)
    browser: BrowserAdapter = field(default_factory=RecordingBrowserAdapter)

    # Port adapters (Phase 2)
    llm: LLMProvider = field(default_factory=RecordingLLMProvider)
    lit: LiteratureSource = field(default_factory=RecordingLiteratureSource)
    sandbox: ExperimentSandbox = field(default_factory=RecordingExperimentSandbox)
    store: ArtifactStore = field(default_factory=RecordingArtifactStore)

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
