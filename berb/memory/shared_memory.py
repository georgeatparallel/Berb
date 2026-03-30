"""Memory-Centric Multi-Agent Coordination for Berb.

Based on MCP-SIM (Nature Computational Science 2025) - Memory-Coordinated approach

Features:
- Persistent shared memory across all agents
- Store: clarifications, code snapshots, execution traces, error→fix mappings
- Prevent redundant computations
- Enable long-horizon coherence
- Agent communication bus

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.memory.shared_memory import SharedResearchMemory
    
    memory = SharedResearchMemory(project_id="proj_123")
    memory.store("hypothesis", {"text": "...", "score": 8.5})
    trajectory = memory.get_trajectory()
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """Single entry in shared memory."""
    
    key: str
    value: Any
    agent_id: str
    timestamp: datetime
    entry_type: str  # clarification, code, execution, error_fix, decision, result
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "key": self.key,
            "value": self.value,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp.isoformat(),
            "entry_type": self.entry_type,
            "metadata": self.metadata,
        }


@dataclass
class AgentState:
    """State of a single agent."""
    
    agent_id: str
    status: str  # idle, working, waiting, error
    current_task: str | None
    last_update: datetime
    messages_sent: int = 0
    messages_received: int = 0


class SharedResearchMemory:
    """Memory-centric coordination for multi-agent research."""
    
    def __init__(
        self,
        project_id: str,
        storage_path: str | Path | None = None,
        max_trajectory_length: int = 1000,
    ) -> None:
        """Initialize shared memory.
        
        Args:
            project_id: Unique project identifier
            storage_path: Path for persistent storage (optional)
            max_trajectory_length: Max entries to keep in memory
        """
        self._project_id = project_id
        self._storage_path = Path(storage_path) if storage_path else None
        self._max_trajectory = max_trajectory_length
        
        # Lock protecting all mutable state.  All write paths (store, send_message,
        # record_code_snapshot, record_error_fix, record_clarification,
        # record_execution_trace, _update_agent_activity) acquire this lock so
        # that concurrent callers from multiple threads or async tasks running on
        # a thread-pool executor cannot corrupt the data structures.
        self._lock = threading.RLock()

        # Core memory structures
        self._entries: list[MemoryEntry] = []
        self._key_value_store: dict[str, Any] = {}
        self._agent_states: dict[str, AgentState] = {}
        self._message_queue: deque = deque(maxlen=100)

        # Specialized stores
        self._code_snapshots: dict[str, str] = {}  # version → code
        self._error_fix_mappings: dict[str, str] = {}  # error_pattern → fix
        self._clarifications: dict[str, Any] = {}  # question → answer
        self._execution_traces: list[dict] = []
        
        # Load from persistent storage if available
        if self._storage_path and self._storage_path.exists():
            self._load_from_disk()
        
        logger.info(f"Initialized shared memory for project {project_id}")
    
    # ========== Core Storage Methods ==========
    
    def store(
        self,
        key: str,
        value: Any,
        agent_id: str = "system",
        entry_type: str = "result",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store value in shared memory.
        
        Args:
            key: Storage key
            value: Value to store
            agent_id: ID of storing agent
            entry_type: Type of entry
            metadata: Optional metadata
        """
        entry = MemoryEntry(
            key=key,
            value=value,
            agent_id=agent_id,
            timestamp=datetime.now(timezone.utc),
            entry_type=entry_type,
            metadata=metadata or {},
        )
        # Acquire the RLock for the full compound mutation so that concurrent
        # callers (e.g. multiple async tasks running on a thread-pool executor)
        # cannot interleave the append, trajectory-prune, kv-update, and disk
        # persist steps.  RLock allows the same thread to re-enter (e.g. when
        # store_execution_trace() holds the lock and then calls store()).
        disk_snapshot: dict | None = None
        with self._lock:
            # Add to entries list (trajectory)
            self._entries.append(entry)
            if len(self._entries) > self._max_trajectory:
                self._entries = self._entries[-self._max_trajectory:]

            # Update key-value store
            self._key_value_store[key] = value

            # Update agent state
            self._update_agent_activity(agent_id)

            # Take a lightweight snapshot of current state inside the lock.
            # The actual disk writes happen OUTSIDE the lock so that concurrent
            # writers are not blocked during I/O (which could take tens of ms
            # on a slow or network-mounted filesystem, or hang indefinitely on
            # failure, causing all agents to stall).
            if self._storage_path:
                disk_snapshot = self._make_disk_snapshot()

        # Persist outside the lock; concurrent _save_to_disk() calls may race
        # on the same files but each individual write is atomic (open→write→close),
        # so the last writer always leaves a consistent snapshot on disk.
        if disk_snapshot is not None:
            self._save_to_disk(disk_snapshot)

        logger.debug(f"Stored {key} ({entry_type}) from agent {agent_id}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from shared memory."""
        with self._lock:
            value = self._key_value_store.get(key, default)
        if value is not None:
            logger.debug(f"Retrieved {key}")
        return value

    def delete(self, key: str) -> bool:
        """Delete value from shared memory."""
        with self._lock:
            if key in self._key_value_store:
                del self._key_value_store[key]
                logger.debug(f"Deleted {key}")
                return True
        return False

    def exists(self, key: str) -> bool:
        """Check if key exists in memory."""
        with self._lock:
            return key in self._key_value_store
    
    # ========== Specialized Stores ==========
    
    def store_code_snapshot(
        self,
        version: str,
        code: str,
        agent_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store code snapshot.
        
        Args:
            version: Version identifier
            code: Code content
            agent_id: ID of storing agent
            metadata: Optional metadata
        """
        # Acquire the lock before mutating _code_snapshots so no concurrent
        # reader (get_code_snapshot) sees the new dict entry while _key_value_store
        # still holds the old value.  store() re-enters the RLock safely.
        with self._lock:
            self._code_snapshots[version] = code
        self.store(
            f"code:{version}",
            code,
            agent_id,
            entry_type="code",
            metadata=metadata,
        )
        logger.info(f"Stored code snapshot {version}")
    
    def get_code_snapshot(self, version: str) -> str | None:
        """Get code snapshot by version."""
        with self._lock:
            return self._code_snapshots.get(version)
    
    def store_error_fix(
        self,
        error_pattern: str,
        fix: str,
        agent_id: str,
        success: bool,
    ) -> None:
        """Store error→fix mapping.
        
        Args:
            error_pattern: Error pattern or message
            fix: Fix description or code
            agent_id: ID of storing agent
            success: Whether fix was successful
        """
        key = f"error_fix:{error_pattern}"
        # Protect the specialized dict mutation so concurrent readers
        # via get_error_fix() cannot observe a partial/torn update.
        with self._lock:
            self._error_fix_mappings[error_pattern] = fix

        self.store(
            key,
            {"error": error_pattern, "fix": fix, "success": success},
            agent_id,
            entry_type="error_fix",
        )
        logger.info(f"Stored error→fix mapping: {error_pattern[:50]}...")
    
    def get_error_fix(self, error_message: str) -> str | None:
        """Get fix for error (pattern matching)."""
        with self._lock:
            if error_message in self._error_fix_mappings:
                return self._error_fix_mappings[error_message]
            for pattern, fix in self._error_fix_mappings.items():
                if pattern in error_message or error_message in pattern:
                    return fix
        return None
    
    def store_clarification(
        self,
        question: str,
        answer: Any,
        agent_id: str,
    ) -> None:
        """Store clarification (Q→A mapping)."""
        # Protect the specialized dict mutation so concurrent readers
        # via get_clarification() cannot observe a partial/torn update.
        with self._lock:
            self._clarifications[question] = answer
        self.store(
            f"clarification:{question}",
            answer,
            agent_id,
            entry_type="clarification",
        )
    
    def get_clarification(self, question: str) -> Any:
        """Get stored clarification."""
        with self._lock:
            return self._clarifications.get(question)
    
    def store_execution_trace(
        self,
        stage: str,
        action: str,
        result: Any,
        agent_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store execution trace."""
        trace = {
            "stage": stage,
            "action": action,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
        }
        if metadata:
            trace.update(metadata)
        
        # Protect the compound append+prune with the same RLock used in store().
        # This prevents a concurrent store_execution_trace() from interleaving its
        # append with the length-check and list-rebind, which would corrupt the
        # trace index used in the store() key below.
        with self._lock:
            self._execution_traces.append(trace)
            if len(self._execution_traces) > self._max_trajectory:
                self._execution_traces = self._execution_traces[-self._max_trajectory:]
            trace_index = len(self._execution_traces)

        self.store(
            f"trace:{stage}:{trace_index}",
            trace,
            agent_id,
            entry_type="execution",
            metadata=metadata,
        )
    
    # ========== Agent Coordination ==========
    
    def register_agent(
        self,
        agent_id: str,
        initial_status: str = "idle",
    ) -> None:
        """Register an agent."""
        with self._lock:
            self._agent_states[agent_id] = AgentState(
                agent_id=agent_id,
                status=initial_status,
                current_task=None,
                last_update=datetime.now(timezone.utc),
            )
        logger.info(f"Registered agent: {agent_id}")
    
    def update_agent_status(
        self,
        agent_id: str,
        status: str,
        task: str | None = None,
    ) -> None:
        """Update agent status."""
        with self._lock:
            if agent_id not in self._agent_states:
                # register_agent re-enters the RLock safely.
                self.register_agent(agent_id, status)
                return

            state = self._agent_states[agent_id]
            state.status = status
            state.current_task = task
            state.last_update = datetime.now(timezone.utc)
    
    def _update_agent_activity(self, agent_id: str) -> None:
        """Update agent activity timestamp."""
        if agent_id in self._agent_states:
            self._agent_states[agent_id].last_update = datetime.now(timezone.utc)
    
    def get_agent_state(self, agent_id: str) -> AgentState | None:
        """Get agent state."""
        with self._lock:
            return self._agent_states.get(agent_id)

    def get_all_agent_states(self) -> list[AgentState]:
        """Get all agent states."""
        with self._lock:
            return list(self._agent_states.values())
    
    # ========== Message Bus ==========
    
    def send_message(
        self,
        from_agent: str,
        to_agent: str | None,
        message_type: str,
        content: Any,
    ) -> None:
        """Send message via message bus.
        
        Args:
            from_agent: Sender agent ID
            to_agent: Recipient agent ID (None = broadcast)
            message_type: Type of message
            content: Message content
        """
        message = {
            "from": from_agent,
            "to": to_agent,
            "type": message_type,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        with self._lock:
            self._message_queue.append(message)
            # messages_sent is a read-modify-write; must be inside the lock.
            if from_agent in self._agent_states:
                self._agent_states[from_agent].messages_sent += 1

        logger.debug(f"Message {message_type} from {from_agent} to {to_agent or 'all'}")
    
    def get_messages(
        self,
        agent_id: str,
        message_type: str | None = None,
    ) -> list[dict]:
        """Get messages for an agent."""
        messages = []
        
        for msg in self._message_queue:
            # Check if message is for this agent (or broadcast)
            if msg["to"] is None or msg["to"] == agent_id:
                if message_type is None or msg["type"] == message_type:
                    messages.append(msg)
        
        # Update received count
        if agent_id in self._agent_states:
            self._agent_states[agent_id].messages_received += len(messages)
        
        return messages
    
    # ========== Trajectory & Analytics ==========
    
    def get_trajectory(
        self,
        entry_type: str | None = None,
        agent_id: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryEntry]:
        """Get trajectory of memory entries.
        
        Args:
            entry_type: Filter by entry type
            agent_id: Filter by agent
            limit: Max entries to return
            
        Returns:
            List of memory entries
        """
        with self._lock:
            entries = list(self._entries)

        if entry_type:
            entries = [e for e in entries if e.entry_type == entry_type]
        if agent_id:
            entries = [e for e in entries if e.agent_id == agent_id]
        if limit:
            entries = entries[-limit:]
        return entries
    
    def get_statistics(self) -> dict[str, Any]:
        """Get memory statistics."""
        with self._lock:
            entry_types: dict[str, int] = {}
            for entry in self._entries:
                entry_types[entry.entry_type] = entry_types.get(entry.entry_type, 0) + 1
            return {
                "project_id": self._project_id,
                "total_entries": len(self._entries),
                "key_value_pairs": len(self._key_value_store),
                "code_snapshots": len(self._code_snapshots),
                "error_fix_mappings": len(self._error_fix_mappings),
                "clarifications": len(self._clarifications),
                "execution_traces": len(self._execution_traces),
                "registered_agents": len(self._agent_states),
                "messages_in_queue": len(self._message_queue),
                "entry_type_distribution": entry_types,
            }
    
    def find_redundant_computations(self) -> list[dict[str, Any]]:
        """Find potentially redundant computations."""
        redundant = []
        with self._lock:
            traces_snapshot = list(self._execution_traces)

        # Group execution traces by stage+action
        trace_groups: dict[str, list] = {}
        for trace in traces_snapshot:
            key = f"{trace.get('stage', 'unknown')}:{trace.get('action', 'unknown')}"
            if key not in trace_groups:
                trace_groups[key] = []
            trace_groups[key].append(trace)
        
        # Find groups with multiple similar executions
        for key, traces in trace_groups.items():
            if len(traces) > 2:  # More than 2 similar executions
                redundant.append({
                    "pattern": key,
                    "count": len(traces),
                    "traces": traces,
                    "recommendation": f"Consider caching results for {key}",
                })
        
        return redundant
    
    # ========== Persistence ==========

    def _make_disk_snapshot(self) -> dict:
        """Return a serializable copy of all stores.

        MUST be called while holding ``self._lock`` so the snapshot is
        internally consistent.  Callers should release the lock before
        passing the returned dict to ``_save_to_disk``.
        """
        return {
            "entries": [e.to_dict() for e in self._entries],
            "kv_store": dict(self._key_value_store),
            "code_snapshots": dict(self._code_snapshots),
            "error_fix_mappings": dict(self._error_fix_mappings),
            "clarifications": dict(self._clarifications),
            "execution_traces": list(self._execution_traces),
        }

    def _save_to_disk(self, snapshot: dict | None = None) -> None:
        """Write memory state to disk.

        Pass a *snapshot* dict (built via :meth:`_make_disk_snapshot` while
        holding ``self._lock``) to avoid re-acquiring the lock here.  If no
        snapshot is provided the method acquires the lock itself, which is
        safe but means the caller should NOT be holding the lock (to avoid
        blocking other writers during I/O).
        """
        if not self._storage_path:
            return

        if snapshot is None:
            with self._lock:
                snapshot = self._make_disk_snapshot()

        self._storage_path.mkdir(parents=True, exist_ok=True)

        # Save entries
        entries_file = self._storage_path / "entries.json"
        with open(entries_file, "w", encoding="utf-8") as f:
            json.dump(snapshot["entries"], f, indent=2)

        # Save key-value store
        kv_file = self._storage_path / "kv_store.json"
        with open(kv_file, "w", encoding="utf-8") as f:
            json.dump(snapshot["kv_store"], f, indent=2)

        # Save specialized stores
        for store_name, snapshot_key in [
            ("code_snapshots", "code_snapshots"),
            ("error_fix_mappings", "error_fix_mappings"),
            ("clarifications", "clarifications"),
            ("execution_traces", "execution_traces"),
        ]:
            store_file = self._storage_path / f"{store_name}.json"
            with open(store_file, "w", encoding="utf-8") as f:
                json.dump(snapshot[snapshot_key], f, indent=2)

        logger.debug(f"Saved memory to {self._storage_path}")
    
    def _load_from_disk(self) -> None:
        """Load memory from disk."""
        if not self._storage_path or not self._storage_path.exists():
            return
        
        try:
            # Load entries
            entries_file = self._storage_path / "entries.json"
            if entries_file.exists():
                with open(entries_file, "r", encoding="utf-8") as f:
                    entries_data = json.load(f)
                    self._entries = [
                        MemoryEntry(
                            key=e["key"],
                            value=e["value"],
                            agent_id=e["agent_id"],
                            timestamp=datetime.fromisoformat(e["timestamp"]),
                            entry_type=e["entry_type"],
                            metadata=e.get("metadata", {}),
                        )
                        for e in entries_data
                    ]
            
            # Load key-value store
            kv_file = self._storage_path / "kv_store.json"
            if kv_file.exists():
                with open(kv_file, "r", encoding="utf-8") as f:
                    self._key_value_store = json.load(f)
            
            # Load specialized stores
            for store_name, store_attr in [
                ("code_snapshots", "_code_snapshots"),
                ("error_fix_mappings", "_error_fix_mappings"),
                ("clarifications", "_clarifications"),
                ("execution_traces", "_execution_traces"),
            ]:
                store_file = self._storage_path / f"{store_name}.json"
                if store_file.exists():
                    with open(store_file, "r", encoding="utf-8") as f:
                        setattr(self, store_attr, json.load(f))
            
            logger.info(f"Loaded memory from {self._storage_path}")
            
        except Exception as e:
            logger.error(f"Failed to load memory: {e}")
    
    def clear(self) -> None:
        """Clear all memory."""
        with self._lock:
            self._entries.clear()
            self._key_value_store.clear()
            self._code_snapshots.clear()
            self._error_fix_mappings.clear()
            self._clarifications.clear()
            self._execution_traces.clear()
            self._message_queue.clear()

        logger.info("Cleared all memory")


# Global memory instance and the lock that protects singleton creation.
# Two threads that both see _memory as None would each construct a new
# SharedResearchMemory, losing any state written by the first instance.
_memory: SharedResearchMemory | None = None
_memory_lock = threading.Lock()


def get_shared_memory(project_id: str) -> SharedResearchMemory:
    """Get global shared memory instance (thread-safe singleton)."""
    global _memory
    with _memory_lock:
        if _memory is None or _memory._project_id != project_id:
            _memory = SharedResearchMemory(project_id=project_id)
        return _memory
