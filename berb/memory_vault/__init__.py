"""MemoryVault Bridge - Memory system integration for Berb.

This module provides integration with MemoryVault memory system, enabling:
- Cross-session memory persistence
- Context injection from past research
- Session archiving and retrieval
- Preflight validation for citations

Architecture: Adapter + Async Proxy patterns
Paradigm: Functional + Event-Driven

# Author: Georgios-Chrysovalantis Chatzivantsidis

Example:
    >>> bridge = MemoryVaultBridge(config)
    >>> context = await bridge.get_context("n-body symplectic integrators")
    >>> await bridge.ingest(prompt, response, metadata={"stage": 8})
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ContextChunk:
    """Retrieved memory chunk.
    
    Attributes:
        content: Memory content
        source: Source type (session/knowledge/skill)
        relevance: Relevance score (0-1)
        cache_tier: Cache tier (L1/L2/L3)
    """
    content: str
    source: str
    relevance: float
    cache_tier: str


@dataclass
class PreflightResult:
    """Preflight validation result.
    
    Attributes:
        verdict: PASS | ENRICH | WARN | BLOCK
        confidence: Confidence score (0-1)
        reason: Validation reasoning
        enrichment: Optional enrichment text
    """
    verdict: str
    confidence: float
    reason: str
    enrichment: Optional[str] = None


@dataclass
class IngestResult:
    """Ingest result.
    
    Attributes:
        status: Success/failure status
        session_id: Session ID
        entry_number: Entry number in session
    """
    status: str
    session_id: str
    entry_number: int


# ─────────────────────────────────────────────────────────────────────────────
# Mnemo Bridge Client
# ─────────────────────────────────────────────────────────────────────────────

class MnemoBridge:
    """Bridge to Mnemo Cortex memory system.
    
    Provides:
    - Context retrieval from memory
    - Session ingestion (auto-capture)
    - Preflight validation
    - Session writeback
    
    Example:
        >>> bridge = MnemoBridge(config)
        >>> context = await bridge.get_context("research topic")
        >>> await bridge.ingest(prompt, response)
    """
    
    def __init__(
        self,
        server_url: str = "http://localhost:50001",
        agent_id: str = "autoresearch",
        auth_token: Optional[str] = None,
        timeout_sec: int = 30,
    ):
        """Initialize Mnemo Bridge.
        
        Args:
            server_url: Mnemo Cortex server URL
            agent_id: Agent ID for tenant isolation
            auth_token: Optional auth token
            timeout_sec: Request timeout
        """
        self.server_url = server_url.rstrip('/')
        self.agent_id = agent_id
        self.auth_token = auth_token
        self.timeout_sec = timeout_sec
        
        self._client = httpx.AsyncClient(
            base_url=self.server_url,
            timeout=httpx.Timeout(timeout_sec),
        )
        
        if auth_token:
            self._client.headers["Authorization"] = f"Bearer {auth_token}"
        
        logger.info(
            f"MnemoBridge initialized: server={server_url}, "
            f"agent={agent_id}"
        )
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()
    
    async def __aenter__(self) -> MnemoBridge:
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    # ─────────────────────────────────────────────────────────────────────────
    # Context Retrieval
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_context(
        self,
        prompt: str,
        persona: Optional[str] = None,
        max_results: int = 5,
    ) -> List[ContextChunk]:
        """Retrieve relevant memories for a prompt.
        
        Args:
            prompt: Prompt to search context for
            persona: Persona mode (default/strict/creative)
            max_results: Maximum results to return
        
        Returns:
            List of ContextChunk objects
        
        Example:
            >>> chunks = await bridge.get_context("symplectic integrators")
            >>> for chunk in chunks:
            ...     print(f"{chunk.source}: {chunk.content[:100]}")
        """
        try:
            response = await self._client.post(
                "/context",
                json={
                    "prompt": prompt,
                    "agent_id": self.agent_id,
                    "persona": persona or "default",
                    "max_results": max_results,
                },
            )
            response.raise_for_status()
            data = response.json()
            
            chunks = [
                ContextChunk(
                    content=chunk["content"],
                    source=chunk["source"],
                    relevance=chunk["relevance"],
                    cache_tier=chunk["cache_tier"],
                )
                for chunk in data.get("chunks", [])
            ]
            
            logger.debug(
                f"Retrieved {len(chunks)} context chunks "
                f"(latency={data.get('latency_ms', 0)}ms)"
            )
            
            return chunks
        
        except httpx.HTTPError as e:
            logger.warning(f"Failed to get context: {e}")
            return []
    
    # ─────────────────────────────────────────────────────────────────────────
    # Session Ingestion
    # ─────────────────────────────────────────────────────────────────────────
    
    async def ingest(
        self,
        prompt: str,
        response: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IngestResult:
        """Archive a prompt/response pair to memory.
        
        Args:
            prompt: User prompt
            response: AI response
            metadata: Optional metadata (stage, timing, etc.)
        
        Returns:
            IngestResult with session info
        
        Example:
            >>> result = await bridge.ingest(prompt, response, {"stage": 8})
            >>> print(f"Session {result.session_id}, entry {result.entry_number}")
        """
        try:
            response_obj = await self._client.post(
                "/ingest",
                json={
                    "prompt": prompt,
                    "response": response,
                    "agent_id": self.agent_id,
                    "metadata": metadata,
                },
            )
            response_obj.raise_for_status()
            data = response_obj.json()
            
            result = IngestResult(
                status=data.get("status", "success"),
                session_id=data.get("session_id", ""),
                entry_number=data.get("entry_number", 0),
            )
            
            logger.debug(
                f"Ingested to session {result.session_id}, "
                f"entry {result.entry_number}"
            )
            
            return result
        
        except httpx.HTTPError as e:
            logger.warning(f"Failed to ingest: {e}")
            return IngestResult(status="error", session_id="", entry_number=0)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Preflight Validation
    # ─────────────────────────────────────────────────────────────────────────
    
    async def preflight(
        self,
        prompt: str,
        draft_response: str,
        persona: Optional[str] = None,
    ) -> PreflightResult:
        """Validate a draft response before sending.
        
        Args:
            prompt: Original prompt
            draft_response: Draft AI response to validate
            persona: Persona mode (default/strict/creative)
        
        Returns:
            PreflightResult with verdict and reasoning
        
        Example:
            >>> result = await bridge.preflight(prompt, draft, persona="strict")
            >>> if result.verdict == "BLOCK":
            ...     print(f"Blocked: {result.reason}")
        """
        try:
            response_obj = await self._client.post(
                "/preflight",
                json={
                    "prompt": prompt,
                    "draft_response": draft_response,
                    "agent_id": self.agent_id,
                    "persona": persona or "strict",
                },
            )
            response_obj.raise_for_status()
            data = response_obj.json()
            
            result = PreflightResult(
                verdict=data.get("verdict", "PASS"),
                confidence=data.get("confidence", 0.0),
                reason=data.get("reason", ""),
                enrichment=data.get("enrichment"),
            )
            
            logger.debug(
                f"Preflight verdict: {result.verdict} "
                f"(confidence={result.confidence:.2f})"
            )
            
            return result
        
        except httpx.HTTPError as e:
            logger.warning(f"Failed preflight: {e}")
            return PreflightResult(
                verdict="PASS",
                confidence=0.0,
                reason=f"Preflight error: {e}",
            )
    
    # ─────────────────────────────────────────────────────────────────────────
    # Session Writeback
    # ─────────────────────────────────────────────────────────────────────────
    
    async def writeback(
        self,
        session_id: str,
        summary: str,
        key_facts: List[str],
        decisions: List[str],
    ) -> Dict[str, Any]:
        """Archive completed session with curated summary.
        
        Args:
            session_id: Session ID to archive
            summary: Session summary
            key_facts: Key facts from session
            decisions: Decisions made
        
        Returns:
            Writeback result dict
        """
        try:
            response_obj = await self._client.post(
                "/writeback",
                json={
                    "session_id": session_id,
                    "summary": summary,
                    "key_facts": key_facts,
                    "decisions_made": decisions,
                    "agent_id": self.agent_id,
                },
            )
            response_obj.raise_for_status()
            return response_obj.json()
        
        except httpx.HTTPError as e:
            logger.warning(f"Failed writeback: {e}")
            return {"status": "error", "error": str(e)}
    
    # ─────────────────────────────────────────────────────────────────────────
    # Health Check
    # ─────────────────────────────────────────────────────────────────────────
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Mnemo server health.
        
        Returns:
            Health status dict
        """
        try:
            response = await self._client.get("/health")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.warning(f"Mnemo health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}
    
    # ─────────────────────────────────────────────────────────────────────────
    # Context Formatting
    # ─────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def format_context_for_prompt(
        chunks: List[ContextChunk],
        section_title: str = "Relevant Past Context",
    ) -> str:
        """Format context chunks for injection into prompt.
        
        Args:
            chunks: List of context chunks
            section_title: Section title for formatted context
        
        Returns:
            Formatted context string for prompt injection
        """
        if not chunks:
            return ""
        
        lines = [f"\n\n== {section_title} ==\n"]
        
        for i, chunk in enumerate(chunks, 1):
            lines.append(f"\n[{i}] Source: {chunk.source} (Relevance: {chunk.relevance:.2f})")
            lines.append(f"    {chunk.content}")
        
        lines.append("\n== End Context ==\n\n")
        
        return "".join(lines)
