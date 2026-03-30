"""Tests for the persistent memory system (40+ tests).

Covers:
- MemoryStore CRUD operations
- Vector embedding generation (mocked)
- Similarity retrieval
- Time decay computation
- Confidence updates
- Persistence (JSONL read/write)
- IdeationMemory, ExperimentMemory, WritingMemory
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from berb.memory.store import MemoryEntry, MemoryStore, VALID_CATEGORIES
from berb.memory.decay import time_decay_weight, confidence_update
from berb.memory.embeddings import EmbeddingProvider, _tokenize, _hash_token
from berb.memory.retriever import MemoryRetriever, cosine_similarity
from berb.memory.ideation_memory import IdeationMemory
from berb.memory.experiment_memory import ExperimentMemory
from berb.memory.writing_memory import WritingMemory


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def tmp_store_dir(tmp_path: Path) -> Path:
    d = tmp_path / "memory_store"
    d.mkdir()
    return d


@pytest.fixture
def store(tmp_store_dir: Path) -> MemoryStore:
    return MemoryStore(tmp_store_dir)


@pytest.fixture
def populated_store(store: MemoryStore) -> MemoryStore:
    store.add("ideation", "Topic: RL for robotics\nOutcome: success", {"run_id": "r1"})
    store.add("ideation", "Topic: Meta-learning\nOutcome: failure", {"run_id": "r2"})
    store.add("experiment", "Task: classification\nHP: lr=0.001", {"run_id": "r1"})
    store.add("experiment", "Trick: mixed precision\nImprovement: 5%", {"run_id": "r2"})
    store.add("writing", "Feedback: clarity\nResolution: rewrite", {"run_id": "r1"})
    return store


@pytest.fixture
def embedding_fn() -> object:
    """Simple deterministic embedding for testing."""
    def _embed(text: str) -> list[float]:
        vec = [0.0] * 16
        for i, ch in enumerate(text[:16]):
            vec[i] = ord(ch) / 256.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]
    return _embed


# ── MemoryStore CRUD ─────────────────────────────────────────────────


class TestMemoryStoreCRUD:
    def test_add_entry(self, store: MemoryStore) -> None:
        entry_id = store.add("ideation", "test content", {"key": "value"})
        assert entry_id
        assert store.count("ideation") == 1

    def test_add_invalid_category(self, store: MemoryStore) -> None:
        with pytest.raises(ValueError, match="Invalid category"):
            store.add("invalid_cat", "content")

    def test_add_all_categories(self, store: MemoryStore) -> None:
        for cat in VALID_CATEGORIES:
            store.add(cat, f"content for {cat}")
        assert store.count() == 3

    def test_get_entry(self, store: MemoryStore) -> None:
        entry_id = store.add("ideation", "findme")
        entry = store.get(entry_id)
        assert entry is not None
        assert entry.content == "findme"
        assert entry.category == "ideation"

    def test_get_nonexistent(self, store: MemoryStore) -> None:
        assert store.get("nonexistent_id") is None

    def test_get_all_no_filter(self, populated_store: MemoryStore) -> None:
        all_entries = populated_store.get_all()
        assert len(all_entries) == 5

    def test_get_all_with_filter(self, populated_store: MemoryStore) -> None:
        ideation = populated_store.get_all("ideation")
        assert len(ideation) == 2

    def test_update_confidence_success(self, store: MemoryStore) -> None:
        entry_id = store.add("ideation", "conf test", confidence=0.5)
        assert store.update_confidence(entry_id, 0.1)
        entry = store.get(entry_id)
        assert entry is not None
        assert abs(entry.confidence - 0.6) < 1e-6

    def test_update_confidence_clamp_high(self, store: MemoryStore) -> None:
        entry_id = store.add("ideation", "test", confidence=0.95)
        store.update_confidence(entry_id, 0.2)
        entry = store.get(entry_id)
        assert entry is not None
        assert entry.confidence == 1.0

    def test_update_confidence_clamp_low(self, store: MemoryStore) -> None:
        entry_id = store.add("ideation", "test", confidence=0.1)
        store.update_confidence(entry_id, -0.5)
        entry = store.get(entry_id)
        assert entry is not None
        assert entry.confidence == 0.0

    def test_update_confidence_nonexistent(self, store: MemoryStore) -> None:
        assert not store.update_confidence("nope", 0.1)

    def test_mark_accessed(self, store: MemoryStore) -> None:
        entry_id = store.add("ideation", "access test")
        entry = store.get(entry_id)
        assert entry is not None
        assert entry.access_count == 0
        store.mark_accessed(entry_id)
        entry = store.get(entry_id)
        assert entry is not None
        assert entry.access_count == 1

    def test_capacity_enforcement(self, tmp_store_dir: Path) -> None:
        store = MemoryStore(tmp_store_dir, max_entries_per_category=3)
        for i in range(5):
            store.add("ideation", f"entry {i}", confidence=i * 0.2)
        assert store.count("ideation") == 3
        # Should keep highest confidence entries
        entries = store.get_all("ideation")
        confidences = [e.confidence for e in entries]
        assert min(confidences) >= 0.4  # lowest 2 (0.0, 0.2) should be pruned

    def test_count_empty(self, store: MemoryStore) -> None:
        assert store.count() == 0
        assert store.count("ideation") == 0


# ── Persistence ──────────────────────────────────────────────────────


class TestMemoryPersistence:
    def test_save_and_load(self, tmp_store_dir: Path) -> None:
        store = MemoryStore(tmp_store_dir)
        store.add("ideation", "persistent content", {"key": "val"})
        store.add("experiment", "exp content")
        store.save()

        store2 = MemoryStore(tmp_store_dir)
        loaded = store2.load()
        assert loaded == 2
        assert store2.count() == 2

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "new" / "nested" / "dir"
        store = MemoryStore(new_dir)
        store.add("ideation", "test")
        store.save()
        assert (new_dir / "ideation.jsonl").exists()

    def test_load_empty_dir(self, tmp_store_dir: Path) -> None:
        store = MemoryStore(tmp_store_dir)
        assert store.load() == 0

    def test_load_malformed_jsonl(self, tmp_store_dir: Path) -> None:
        (tmp_store_dir / "ideation.jsonl").write_text(
            '{"id": "a", "category": "ideation"}\nnot json\n',
            encoding="utf-8",
        )
        store = MemoryStore(tmp_store_dir)
        loaded = store.load()
        assert loaded == 1  # only valid entry loaded

    def test_roundtrip_preserves_data(self, tmp_store_dir: Path) -> None:
        store = MemoryStore(tmp_store_dir)
        entry_id = store.add(
            "experiment", "test content",
            metadata={"key": "value"},
            embedding=[0.1, 0.2, 0.3],
            confidence=0.7,
        )
        store.save()

        store2 = MemoryStore(tmp_store_dir)
        store2.load()
        entry = store2.get(entry_id)
        assert entry is not None
        assert entry.content == "test content"
        assert entry.metadata == {"key": "value"}
        assert entry.embedding == [0.1, 0.2, 0.3]
        assert abs(entry.confidence - 0.7) < 1e-6


# ── Prune ────────────────────────────────────────────────────────────


class TestMemoryPrune:
    def test_prune_low_confidence(self, store: MemoryStore) -> None:
        store.add("ideation", "low conf", confidence=0.1)
        store.add("ideation", "high conf", confidence=0.8)
        removed = store.prune(confidence_threshold=0.5)
        assert removed == 1
        assert store.count("ideation") == 1

    def test_prune_nothing_to_remove(self, store: MemoryStore) -> None:
        store.add("ideation", "good", confidence=0.9)
        removed = store.prune()
        assert removed == 0


# ── MemoryEntry ──────────────────────────────────────────────────────


class TestMemoryEntry:
    def test_to_dict(self) -> None:
        entry = MemoryEntry(
            id="abc", category="ideation", content="test",
            metadata={}, embedding=[], confidence=0.5,
            created_at="2024-01-01T00:00:00+00:00",
            last_accessed="2024-01-01T00:00:00+00:00",
            access_count=0,
        )
        d = entry.to_dict()
        assert d["id"] == "abc"
        assert d["category"] == "ideation"

    def test_from_dict(self) -> None:
        data = {
            "id": "xyz", "category": "experiment", "content": "hp test",
            "metadata": {"run": "1"}, "embedding": [0.1], "confidence": 0.6,
            "created_at": "2024-06-01T00:00:00+00:00",
            "last_accessed": "2024-06-01T00:00:00+00:00",
            "access_count": 3,
        }
        entry = MemoryEntry.from_dict(data)
        assert entry.id == "xyz"
        assert entry.access_count == 3

    def test_from_dict_defaults(self) -> None:
        entry = MemoryEntry.from_dict({})
        assert entry.id == ""
        assert entry.confidence == 0.5
        assert entry.access_count == 0


# ── Time Decay ───────────────────────────────────────────────────────


class TestTimeDecay:
    def test_fresh_entry(self) -> None:
        now = datetime.now(timezone.utc)
        w = time_decay_weight(now, half_life_days=90.0, now=now)
        assert abs(w - 1.0) < 1e-6

    def test_half_life(self) -> None:
        now = datetime.now(timezone.utc)
        half = now - timedelta(days=90)
        w = time_decay_weight(half, half_life_days=90.0, now=now)
        assert abs(w - 0.5) < 0.01

    def test_expired(self) -> None:
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=400)
        w = time_decay_weight(old, half_life_days=90.0, max_age_days=365.0, now=now)
        assert w == 0.0

    def test_future_timestamp(self) -> None:
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=10)
        w = time_decay_weight(future, now=now)
        assert w == 1.0

    def test_naive_datetime(self) -> None:
        now = datetime.now(timezone.utc)
        naive = now.replace(tzinfo=None)
        w = time_decay_weight(naive, now=now)
        assert w > 0.0


class TestConfidenceUpdate:
    def test_increase(self) -> None:
        assert confidence_update(0.5, 0.1) == 0.6

    def test_decrease(self) -> None:
        assert confidence_update(0.5, -0.2) == pytest.approx(0.3)

    def test_clamp_ceiling(self) -> None:
        assert confidence_update(0.95, 0.2) == 1.0

    def test_clamp_floor(self) -> None:
        assert confidence_update(0.1, -0.5) == 0.0


# ── Embeddings ───────────────────────────────────────────────────────


class TestEmbeddings:
    def test_tfidf_fallback(self) -> None:
        provider = EmbeddingProvider()
        vec = provider.embed("hello world test")
        assert len(vec) > 0
        assert isinstance(vec[0], float)

    def test_tfidf_normalized(self) -> None:
        provider = EmbeddingProvider()
        vec = provider.embed("deep learning neural network")
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 0.01

    def test_tfidf_empty(self) -> None:
        provider = EmbeddingProvider()
        # Force TF-IDF backend to test zero-vector behavior
        provider._backend = "tfidf"
        provider._dim = 256
        vec = provider.embed("")
        assert all(v == 0.0 for v in vec)

    def test_tokenize(self) -> None:
        tokens = _tokenize("Hello, World! 123")
        assert "hello" in tokens
        assert "world" in tokens
        assert "123" in tokens

    def test_hash_token_deterministic(self) -> None:
        a = _hash_token("test", 256)
        b = _hash_token("test", 256)
        assert a == b

    def test_embed_batch(self) -> None:
        provider = EmbeddingProvider()
        vecs = provider.embed_batch(["hello", "world"])
        assert len(vecs) == 2

    def test_backend_detection(self) -> None:
        provider = EmbeddingProvider()
        backend = provider.backend
        assert backend in ("api", "sentence_transformers", "tfidf")


# ── Retriever ────────────────────────────────────────────────────────


class TestRetriever:
    def test_cosine_similarity_identical(self) -> None:
        vec = [1.0, 0.0, 0.0]
        assert abs(cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 1e-6

    def test_cosine_similarity_opposite(self) -> None:
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(cosine_similarity(a, b) + 1.0) < 1e-6

    def test_cosine_similarity_empty(self) -> None:
        assert cosine_similarity([], []) == 0.0

    def test_cosine_similarity_mismatched_length(self) -> None:
        assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0

    def test_recall_empty_store(self, store: MemoryStore) -> None:
        retriever = MemoryRetriever(store)
        results = retriever.recall([0.1, 0.2], category="ideation")
        assert results == []

    def test_recall_returns_results(self, store: MemoryStore) -> None:
        store.add("ideation", "RL research", embedding=[1.0, 0.0, 0.0])
        store.add("ideation", "NLP research", embedding=[0.0, 1.0, 0.0])
        retriever = MemoryRetriever(store)
        results = retriever.recall([0.9, 0.1, 0.0], category="ideation", top_k=1)
        assert len(results) == 1
        assert "RL" in results[0][0].content

    def test_recall_respects_top_k(self, store: MemoryStore) -> None:
        for i in range(10):
            store.add("ideation", f"entry {i}", embedding=[float(i)] * 3)
        retriever = MemoryRetriever(store)
        results = retriever.recall([5.0, 5.0, 5.0], top_k=3)
        assert len(results) == 3

    def test_format_for_prompt(self, store: MemoryStore) -> None:
        store.add("ideation", "Topic: RL", embedding=[1.0])
        retriever = MemoryRetriever(store)
        results = retriever.recall([1.0])
        text = retriever.format_for_prompt(results)
        assert "ideation" in text

    def test_format_for_prompt_empty(self, store: MemoryStore) -> None:
        retriever = MemoryRetriever(store)
        text = retriever.format_for_prompt([])
        assert text == ""


# ── Ideation Memory ──────────────────────────────────────────────────


class TestIdeationMemory:
    def test_record_topic_success(self, store: MemoryStore, embedding_fn: object) -> None:
        retriever = MemoryRetriever(store)
        im = IdeationMemory(store, retriever, embed_fn=embedding_fn)
        entry_id = im.record_topic_outcome("RL for robotics", "success", 8.0)
        assert entry_id
        assert store.count("ideation") == 1

    def test_record_topic_failure(self, store: MemoryStore) -> None:
        retriever = MemoryRetriever(store)
        im = IdeationMemory(store, retriever)
        im.record_topic_outcome("Bad topic", "failure", 2.0, run_id="r1")
        entries = store.get_all("ideation")
        assert entries[0].metadata["outcome"] == "failure"

    def test_record_hypothesis(self, store: MemoryStore) -> None:
        retriever = MemoryRetriever(store)
        im = IdeationMemory(store, retriever)
        im.record_hypothesis("H1: X is better than Y", True, "Validated")
        assert store.count("ideation") == 1

    def test_get_anti_patterns(self, store: MemoryStore) -> None:
        retriever = MemoryRetriever(store)
        im = IdeationMemory(store, retriever)
        im.record_topic_outcome("Bad direction", "failure", 1.0)
        im.record_topic_outcome("Good direction", "success", 9.0)
        patterns = im.get_anti_patterns()
        assert len(patterns) == 1
        assert "Bad" in patterns[0]

    def test_recall_similar_topics_empty(self, store: MemoryStore) -> None:
        retriever = MemoryRetriever(store)
        im = IdeationMemory(store, retriever)
        result = im.recall_similar_topics("test query")
        assert result == ""


# ── Experiment Memory ────────────────────────────────────────────────


class TestExperimentMemory:
    def test_record_hyperparams(self, store: MemoryStore) -> None:
        retriever = MemoryRetriever(store)
        em = ExperimentMemory(store, retriever)
        em.record_hyperparams("image_cls", {"lr": 0.001, "bs": 32}, 0.95)
        assert store.count("experiment") == 1

    def test_record_architecture(self, store: MemoryStore) -> None:
        retriever = MemoryRetriever(store)
        em = ExperimentMemory(store, retriever)
        em.record_architecture("image_cls", "ResNet-18", 0.96)
        entry = store.get_all("experiment")[0]
        assert "ResNet" in entry.content

    def test_record_training_trick(self, store: MemoryStore) -> None:
        retriever = MemoryRetriever(store)
        em = ExperimentMemory(store, retriever)
        em.record_training_trick("CosineAnnealing", 0.03, "CIFAR-10 training")
        entry = store.get_all("experiment")[0]
        assert "CosineAnnealing" in entry.content

    def test_recall_best_configs_empty(self, store: MemoryStore) -> None:
        retriever = MemoryRetriever(store)
        em = ExperimentMemory(store, retriever)
        result = em.recall_best_configs("anything")
        assert result == ""


# ── Writing Memory ───────────────────────────────────────────────────


class TestWritingMemory:
    def test_record_review_feedback(self, store: MemoryStore) -> None:
        retriever = MemoryRetriever(store)
        wm = WritingMemory(store, retriever)
        wm.record_review_feedback("clarity", "Section 3 is unclear", "Rewrote S3")
        assert store.count("writing") == 1

    def test_record_successful_structure(self, store: MemoryStore) -> None:
        retriever = MemoryRetriever(store)
        wm = WritingMemory(store, retriever)
        wm.record_successful_structure("intro", "Problem-Gap-Contribution", 8.5)
        entry = store.get_all("writing")[0]
        assert entry.metadata["section"] == "intro"

    def test_recall_writing_tips_empty(self, store: MemoryStore) -> None:
        retriever = MemoryRetriever(store)
        wm = WritingMemory(store, retriever)
        result = wm.recall_writing_tips("method", "RL paper")
        assert result == ""


# ── SharedResearchMemory concurrency regression tests (BUG-001, BUG-002) ──────


class TestSharedResearchMemoryConcurrency:
    """Regression tests for BUG-001 (unprotected mutations) and
    BUG-002 (I/O held under lock) in berb.memory.shared_memory.

    These tests confirm that concurrent access to SharedResearchMemory does
    not corrupt data and that the singleton factory is thread-safe.
    """

    def _make_memory(self, tmp_path=None):
        from berb.memory.shared_memory import SharedResearchMemory
        return SharedResearchMemory(project_id="test", storage_path=tmp_path)

    # ── BUG-001: unprotected dict mutations ─────────────────────────────

    def test_concurrent_store_code_snapshot_no_corruption(self):
        """REGRESSION BUG-001: concurrent store_code_snapshot must not corrupt
        _code_snapshots under thread contention."""
        import threading

        mem = self._make_memory()
        errors = []

        def writer(version, code):
            try:
                for _ in range(50):
                    mem.store_code_snapshot(version, code, agent_id="agent")
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=(f"v{i}", f"code_{i}"))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Exceptions during concurrent writes: {errors}"
        # All versions must be retrievable without KeyError or None corruption.
        for i in range(5):
            snap = mem.get_code_snapshot(f"v{i}")
            assert snap == f"code_{i}", f"v{i} corrupted: {snap!r}"

    def test_concurrent_store_error_fix_no_corruption(self):
        """REGRESSION BUG-001: concurrent store_error_fix is safe."""
        import threading

        mem = self._make_memory()
        errors = []

        def writer(pattern, fix):
            try:
                for _ in range(50):
                    mem.store_error_fix(pattern, fix, agent_id="agent", success=True)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=(f"err_{i}", f"fix_{i}"))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        for i in range(5):
            fix = mem.get_error_fix(f"err_{i}")
            assert fix == f"fix_{i}", f"err_{i} corrupted: {fix!r}"

    def test_concurrent_register_agent_no_corruption(self):
        """REGRESSION BUG-001: concurrent register_agent is safe."""
        import threading

        mem = self._make_memory()
        errors = []

        def registrar(agent_id):
            try:
                for _ in range(30):
                    mem.register_agent(agent_id, "idle")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=registrar, args=(f"agent_{i}",)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

    def test_concurrent_send_message_no_corruption(self):
        """REGRESSION BUG-001: messages_sent counter is not torn under contention."""
        import threading

        mem = self._make_memory()
        mem.register_agent("sender")

        errors = []

        def sender():
            try:
                for _ in range(100):
                    mem.send_message("sender", None, "ping", "data")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=sender) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        state = mem.get_agent_state("sender")
        assert state is not None
        # messages_sent must equal total sends across all threads.
        assert state.messages_sent == 400, (
            f"Expected 400 messages_sent, got {state.messages_sent} — "
            "likely torn read-modify-write without lock."
        )

    def test_clear_is_thread_safe(self):
        """REGRESSION BUG-001: clear() acquires lock; concurrent reads do not crash."""
        import threading

        mem = self._make_memory()
        for i in range(20):
            mem.store(f"k{i}", i)

        errors = []

        def reader():
            try:
                for _ in range(50):
                    mem.get_trajectory()
            except Exception as exc:
                errors.append(exc)

        def clearer():
            try:
                for _ in range(10):
                    mem.clear()
            except Exception as exc:
                errors.append(exc)

        threads = (
            [threading.Thread(target=reader) for _ in range(3)]
            + [threading.Thread(target=clearer)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

    # ── BUG-002: disk I/O outside lock ──────────────────────────────────

    def test_save_to_disk_called_outside_lock(self, tmp_path):
        """REGRESSION BUG-002: _save_to_disk must NOT be called while self._lock
        is held.  A secondary thread must be able to acquire the lock during I/O.

        Strategy: pause _save_to_disk mid-execution, then have another thread
        attempt to acquire mem._lock.  If the lock is free (fix applied) the
        thread succeeds; if still held (bug present) the thread times out.
        """
        import threading

        mem = self._make_memory(tmp_path=tmp_path)

        io_started = threading.Event()
        io_can_finish = threading.Event()
        lock_was_free_during_io = threading.Event()

        original_save = mem._save_to_disk

        def pausing_save(snapshot=None):
            # Signal that disk I/O has begun, then wait for the checker.
            io_started.set()
            io_can_finish.wait(timeout=2.0)
            original_save(snapshot)

        mem._save_to_disk = pausing_save

        def checker():
            io_started.wait(timeout=2.0)
            # Attempt to acquire the lock from a different thread.
            # RLock from a DIFFERENT thread behaves like a regular lock —
            # it will block if the writer_thread holds it.
            acquired = mem._lock.acquire(blocking=True, timeout=0.2)
            if acquired:
                lock_was_free_during_io.set()
                mem._lock.release()
            io_can_finish.set()

        writer_thread = threading.Thread(target=lambda: mem.store("k", "v"))
        checker_thread = threading.Thread(target=checker)

        checker_thread.start()
        writer_thread.start()
        writer_thread.join(timeout=3)
        checker_thread.join(timeout=3)

        assert lock_was_free_during_io.is_set(), (
            "Lock was held during _save_to_disk — disk I/O is still inside the "
            "critical section (BUG-002 not fixed)."
        )
        assert mem.get("k") == "v"

    # ── Singleton race ───────────────────────────────────────────────────

    def test_get_shared_memory_singleton_is_thread_safe(self):
        """REGRESSION BUG-001 (singleton): concurrent get_shared_memory() calls
        must always return the same instance for the same project_id."""
        import threading
        from berb.memory import shared_memory as sm

        # Reset the global singleton so this test starts fresh.
        original = sm._memory
        sm._memory = None

        results = []
        errors = []

        def getter():
            try:
                results.append(sm.get_shared_memory("proj_concurrent_test"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=getter) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        sm._memory = original  # Restore

        assert not errors
        # All threads must have received the same instance.
        assert len(set(id(r) for r in results)) == 1, (
            "Multiple SharedResearchMemory instances created — singleton race condition."
        )
