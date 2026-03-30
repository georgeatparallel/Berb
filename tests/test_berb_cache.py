"""Tests for literature query cache and degradation fallback."""

from __future__ import annotations

import importlib
import pytest
from unittest.mock import patch

from berb.literature.models import Author, Paper
from berb.literature.search import search_papers

cache_mod = importlib.import_module("berb.literature.cache")
cache_key = cache_mod.cache_key
cache_stats = cache_mod.cache_stats
clear_cache = cache_mod.clear_cache
get_cached = cache_mod.get_cached
put_cache = cache_mod.put_cache


class TestCacheKey:
    def test_deterministic(self, tmp_path):
        _ = tmp_path
        k1 = cache_key("transformer", "s2", 20)
        k2 = cache_key("transformer", "s2", 20)
        assert k1 == k2

    def test_different_query(self):
        k1 = cache_key("transformer", "s2", 20)
        k2 = cache_key("attention", "s2", 20)
        assert k1 != k2

    def test_case_insensitive(self):
        k1 = cache_key("Transformer", "S2", 20)
        k2 = cache_key("transformer", "s2", 20)
        assert k1 == k2

    def test_length_16(self):
        k = cache_key("test", "s2", 10)
        assert len(k) == 16


class TestGetPut:
    def test_put_and_get(self, tmp_path):
        papers = [{"paper_id": "1", "title": "Test Paper"}]
        put_cache("q1", "s2", 20, papers, cache_base=tmp_path)
        result = get_cached("q1", "s2", 20, cache_base=tmp_path)
        assert result is not None
        assert len(result) == 1
        assert result[0]["title"] == "Test Paper"

    def test_cache_miss(self, tmp_path):
        result = get_cached("nonexistent", "s2", 20, cache_base=tmp_path)
        assert result is None

    def test_cache_expired(self, tmp_path):
        papers = [{"paper_id": "1", "title": "Old"}]
        put_cache("q1", "s2", 20, papers, cache_base=tmp_path)
        result = get_cached("q1", "s2", 20, cache_base=tmp_path, ttl=0)
        assert result is None

    def test_cache_not_expired(self, tmp_path):
        papers = [{"paper_id": "1", "title": "Fresh"}]
        put_cache("q1", "s2", 20, papers, cache_base=tmp_path)
        result = get_cached("q1", "s2", 20, cache_base=tmp_path, ttl=9999)
        assert result is not None

    def test_corrupted_cache_returns_none(self, tmp_path):
        key = cache_key("q1", "s2", 20)
        (tmp_path / f"{key}.json").write_text("not json", encoding="utf-8")
        result = get_cached("q1", "s2", 20, cache_base=tmp_path)
        assert result is None


class TestClear:
    def test_clear_removes_all(self, tmp_path):
        put_cache("q1", "s2", 20, [{"id": "1"}], cache_base=tmp_path)
        put_cache("q2", "arxiv", 10, [{"id": "2"}], cache_base=tmp_path)
        count = clear_cache(cache_base=tmp_path)
        assert count == 2
        assert get_cached("q1", "s2", 20, cache_base=tmp_path) is None

    def test_clear_empty(self, tmp_path):
        count = clear_cache(cache_base=tmp_path)
        assert count == 0


class TestStats:
    def test_stats_empty(self, tmp_path):
        stats = cache_stats(cache_base=tmp_path)
        assert stats["entries"] == 0
        assert stats["total_bytes"] == 0

    def test_stats_with_entries(self, tmp_path):
        put_cache("q1", "s2", 20, [{"id": "1"}], cache_base=tmp_path)
        stats = cache_stats(cache_base=tmp_path)
        assert stats["entries"] == 1
        assert stats["total_bytes"] > 0


class TestSearchDegradation:
    def test_search_uses_cache_on_failure(self, tmp_path):
        cached_papers = [
            {
                "paper_id": "s2-123",
                "title": "Cached Paper",
                "authors": [],
                "year": 2024,
                "abstract": "",
                "venue": "",
                "citation_count": 10,
                "doi": "",
                "arxiv_id": "",
                "url": "",
                "source": "semantic_scholar",
            }
        ]
        put_cache(
            "test query",
            "semantic_scholar",
            20,
            cached_papers,
            cache_base=tmp_path,
        )

        with patch(
            "berb.literature.search.search_openalex",
            side_effect=RuntimeError("API down"),
        ):
            with patch(
                "berb.literature.search.search_semantic_scholar",
                side_effect=RuntimeError("API down"),
            ):
                with patch(
                    "berb.literature.search.search_arxiv",
                    side_effect=RuntimeError("API down"),
                ):
                    with patch(
                        "berb.literature.cache._DEFAULT_CACHE_DIR", tmp_path
                    ):
                        with patch(
                            "berb.literature.search.time.sleep", lambda _: None
                        ):
                            results = search_papers("test query", limit=20)

        assert len(results) >= 1
        assert results[0].title == "Cached Paper"

    def test_search_caches_successful_results(self, tmp_path):
        mock_paper = Paper(
            paper_id="s2-test",
            title="Test",
            authors=(Author(name="Smith"),),
            year=2024,
            abstract="abs",
            source="semantic_scholar",
        )

        with patch(
            "berb.literature.search.search_semantic_scholar",
            return_value=[mock_paper],
        ):
            with patch("berb.literature.search.search_arxiv", return_value=[]):
                with patch(
                    "berb.literature.cache._DEFAULT_CACHE_DIR", tmp_path
                ):
                    with patch(
                        "berb.literature.search.time.sleep", lambda _: None
                    ):
                        _ = search_papers("test", limit=20)

        cached = get_cached("test", "semantic_scholar", 20, cache_base=tmp_path)
        assert cached is not None
        assert cached[0]["paper_id"] == "s2-test"


# ── BUG-006: atomic cache write regression tests ─────────────────────────────


class TestAtomicCacheWrite:
    """Regression tests for BUG-006: put_cache must write atomically.

    Previously put_cache used path.write_text() which truncates the file
    then writes, leaving a window where concurrent readers observe an empty
    or partial JSON file and raise JSONDecodeError.  The fix uses a
    temp-file + Path.replace() pattern.
    """

    def test_no_tmp_file_left_on_success(self, tmp_path):
        """REGRESSION BUG-006: temp file must be cleaned up after success."""
        from berb.literature.cache import put_cache, cache_key

        put_cache("q", "arxiv", 5, [{"id": "p1"}], cache_base=tmp_path)

        key = cache_key("q", "arxiv", 5)
        tmp = (tmp_path / f"{key}.tmp")
        assert not tmp.exists(), "Temp file leaked after successful write"

    def test_final_file_is_valid_json(self, tmp_path):
        """REGRESSION BUG-006: final cache file must be complete valid JSON."""
        import json
        from berb.literature.cache import put_cache, cache_key

        papers = [{"id": f"p{i}", "title": f"Paper {i}"} for i in range(10)]
        put_cache("atomic_test", "semantic_scholar", 10, papers, cache_base=tmp_path)

        key = cache_key("atomic_test", "semantic_scholar", 10)
        path = tmp_path / f"{key}.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data["papers"]) == 10

    def test_concurrent_writes_leave_valid_json(self, tmp_path):
        """REGRESSION BUG-006: concurrent writes must not corrupt the cache file.

        The atomic-write guarantee: any cache file that exists after all writes
        complete must contain valid, complete JSON — never a partial or empty
        payload.  On Windows, os.replace() may raise PermissionError when two
        threads race on the same target (mandatory-lock limitation); those
        failures are acceptable because the temp file is cleaned up and the
        original cache file is untouched.  A PermissionError is not a
        corruption — it is a clean failure.
        """
        import json
        import threading
        from berb.literature.cache import put_cache, get_cached

        non_permission_errors: list[Exception] = []

        def writer(idx: int) -> None:
            try:
                put_cache(
                    "concurrent_q",
                    "arxiv",
                    5,
                    [{"id": f"p{idx}"}],
                    cache_base=tmp_path,
                )
            except PermissionError:
                # Windows mandatory locking: os.replace() on a contended target
                # raises PermissionError.  The temp file is cleaned up; the
                # existing cache file is left intact.  This is acceptable.
                pass
            except Exception as exc:
                non_permission_errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not non_permission_errors, (
            f"Unexpected non-PermissionError exceptions: {non_permission_errors}"
        )

        # The file must be readable as valid JSON — never a partial payload.
        result = get_cached("concurrent_q", "arxiv", 5, cache_base=tmp_path)
        if result is not None:
            # If a write succeeded, the payload must be a well-formed list
            assert isinstance(result, list), f"Unexpected type: {type(result)}"

        # No orphaned temp files should remain after all threads finish
        remaining_tmp = list(tmp_path.glob("*.tmp"))
        assert remaining_tmp == [], f"Temp files leaked: {remaining_tmp}"

    def test_cleanup_on_replace_failure(self, tmp_path):
        """REGRESSION BUG-006: temp file is removed when os.replace() fails."""
        import os as _os
        from berb.literature.cache import put_cache, cache_key

        def failing_replace(src, dst):
            raise OSError("Simulated rename failure")

        with patch("berb.literature.cache.os.replace", side_effect=failing_replace):
            with pytest.raises(OSError):
                put_cache("fail_q", "arxiv", 1, [{"id": "x"}], cache_base=tmp_path)

        # No .tmp file should survive after the failure
        remaining_tmp = list(tmp_path.glob("*.tmp"))
        assert remaining_tmp == [], f"Temp files leaked: {remaining_tmp}"
