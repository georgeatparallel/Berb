"""MCP transport layer: stdio and SSE implementations."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class MCPTransport(Protocol):
    """Protocol for MCP message transport."""

    async def send(self, message: dict[str, Any]) -> None: ...
    async def receive(self) -> dict[str, Any]: ...
    async def close(self) -> None: ...


class StdioTransport:
    """MCP transport over stdin/stdout (for CLI integration)."""

    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def start(self) -> None:
        """Initialize stdin/stdout streams for async I/O."""
        loop = asyncio.get_event_loop()
        self._reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(self._reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        w_transport, w_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        self._writer = asyncio.StreamWriter(w_transport, w_protocol, self._reader, loop)

    async def send(self, message: dict[str, Any]) -> None:
        """Write a JSON-RPC message to stdout."""
        if self._writer is None:
            raise RuntimeError("Transport not started")
        data = json.dumps(message, ensure_ascii=False)
        header = f"Content-Length: {len(data.encode())}\r\n\r\n"
        self._writer.write(header.encode() + data.encode())
        await self._writer.drain()

    async def receive(self) -> dict[str, Any]:
        """Read a JSON-RPC message from stdin."""
        if self._reader is None:
            raise RuntimeError("Transport not started")
        # Read headers
        content_length = 0
        while True:
            line = await self._reader.readline()
            decoded = line.decode().strip()
            if not decoded:
                break
            if decoded.lower().startswith("content-length:"):
                content_length = int(decoded.split(":")[1].strip())
        if content_length == 0:
            raise EOFError("No content-length header received")
        body = await self._reader.readexactly(content_length)
        return json.loads(body)

    async def close(self) -> None:
        """Close the transport."""
        if self._writer:
            self._writer.close()


class SSETransport:
    """MCP transport over Server-Sent Events (for web integration).

    Architecture
    ============
    SSE is a **server→client** protocol — the server pushes events over a
    long-lived HTTP connection, but the client cannot send messages back over
    the same channel.  For bi-directional MCP communication the client sends
    requests via HTTP POST to a companion endpoint, and the server pushes
    responses back via SSE.

    This implementation models that with an asyncio Queue:

    * ``send()``    — formats the message as an SSE ``data:`` line and writes
                      it to all connected SSE subscribers (tracked in
                      ``_subscribers``).
    * ``post_message()`` — called by the companion HTTP POST handler to inject
                           an inbound client message into the inbound queue.
    * ``receive()`` — blocks until an item is available in the inbound queue
                      (populated by ``post_message()``).

    Integration with a real HTTP framework (aiohttp, Starlette, FastAPI …) is
    left to the caller: wire the SSE endpoint to ``_subscribers`` and the POST
    endpoint to ``post_message()``.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 3000) -> None:
        self.host = host
        self.port = port
        self._running = False
        self._inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        # Each subscriber is an asyncio.Queue that receives raw SSE lines
        self._subscribers: list[asyncio.Queue[str]] = []

    async def start(self) -> None:
        """Mark the transport as running."""
        self._running = True
        logger.info("SSE transport started on %s:%d", self.host, self.port)

    def subscribe(self) -> asyncio.Queue[str]:
        """Register a new SSE subscriber and return its queue.

        Each item placed on the returned queue is a complete SSE chunk
        (e.g. ``"data: {...}\\n\\n"``) ready to be written to the HTTP
        response stream.
        """
        q: asyncio.Queue[str] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        """Remove a subscriber (call when the HTTP connection closes)."""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def send(self, message: dict[str, Any]) -> None:
        """Broadcast *message* as an SSE ``data:`` event to all subscribers."""
        payload = json.dumps(message, ensure_ascii=False, default=str)
        sse_chunk = f"data: {payload}\n\n"
        logger.debug("SSE send (%d subscribers): %s", len(self._subscribers), payload[:200])
        for q in list(self._subscribers):
            await q.put(sse_chunk)

    async def post_message(self, message: dict[str, Any]) -> None:
        """Inject an inbound message (from HTTP POST) into the receive queue.

        Call this from your HTTP POST handler whenever the client sends an
        MCP request.
        """
        await self._inbound.put(message)

    async def receive(self) -> dict[str, Any]:
        """Block until a client message arrives via the companion POST endpoint.

        Returns the next message from the inbound queue.  Raises
        ``RuntimeError`` if the transport is not running.
        """
        if not self._running:
            raise RuntimeError("SSE transport is not running — call start() first")
        return await self._inbound.get()

    async def close(self) -> None:
        """Stop the SSE server and notify all subscribers."""
        self._running = False
        # Send a sentinel to wake any waiting subscribers
        close_chunk = "event: close\ndata: {}\n\n"
        for q in list(self._subscribers):
            await q.put(close_chunk)
        self._subscribers.clear()
        logger.info("SSE transport closed")
