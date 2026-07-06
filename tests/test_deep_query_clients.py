"""Unit tests for DeepQuery and DeepMind AI clients."""

import json
from unittest.mock import MagicMock, patch

import pytest

from berb.llm.deep_query_client import (
    DeepMindAIClient,
    DeepQueryClient,
    _reset_circuit_breaker,
    create_deepmind_ai_client,
    create_deepquery_client,
)


def _mock_urlopen(response_json: dict) -> MagicMock:
    """Build a urllib.request.urlopen-compatible mock returning response_json."""
    response_bytes = json.dumps(response_json).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_bytes
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestDeepQueryClient:
    """Test DeepQueryClient class (sync, urllib-based)."""

    @pytest.fixture(autouse=True)
    def _isolate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Reset the circuit breaker and stub cost tracking (no real SQLite
        writes from unit tests) before every test in this class."""
        _reset_circuit_breaker()
        monkeypatch.setattr(
            "berb.metrics.reasoning_cost_tracker.get_cost_tracker",
            lambda *a, **kw: MagicMock(),
        )

    def test_search_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful DeepQuery search."""
        mock_resp = _mock_urlopen(
            {
                "choices": [{"message": {"content": "CRISPR is a gene editing technology..."}}],
                "citations": ["https://example.com/paper1"],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 500,
                    "total_tokens": 600,
                },
            }
        )
        monkeypatch.setattr(
            "berb.llm.deep_query_client.urllib.request.urlopen",
            lambda *a, **kw: mock_resp,
        )

        client = DeepQueryClient(api_key="test_key")
        result = client.search("CRISPR gene editing", model="pro")

        assert result.content != ""
        assert result.source == "DeepQuery"
        assert len(result.citations) == 1

    def test_search_twice_same_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regression: the old async client closed its httpx client after the
        first call, so a second .search() on the same instance would raise.
        The sync urllib client has no such lifecycle — must work twice."""
        mock_resp = _mock_urlopen(
            {
                "choices": [{"message": {"content": "response"}}],
                "citations": [],
                "usage": {},
            }
        )
        monkeypatch.setattr(
            "berb.llm.deep_query_client.urllib.request.urlopen",
            lambda *a, **kw: mock_resp,
        )

        client = DeepQueryClient(api_key="test_key")
        first = client.search("query one", model="quick")
        second = client.search("query two", model="quick")

        assert first.content == "response"
        assert second.content == "response"

    def test_search_different_models(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test search with different models."""
        captured_payloads: list[dict] = []

        def _fake_urlopen(req, timeout=None):  # noqa: ANN001
            captured_payloads.append(json.loads(req.data.decode("utf-8")))
            return _mock_urlopen(
                {"choices": [{"message": {"content": "response"}}], "citations": [], "usage": {}}
            )

        monkeypatch.setattr(
            "berb.llm.deep_query_client.urllib.request.urlopen",
            _fake_urlopen,
        )

        client = DeepQueryClient(api_key="test_key")

        client.search("test", model="quick")
        assert captured_payloads[-1]["model"] == "sonar"

        client.search("test", model="reasoning")
        assert captured_payloads[-1]["model"] == "sonar-reasoning-pro"

    def test_search_domain_and_recency_filters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Domain/recency filters should be forwarded in the request payload."""
        captured_payloads: list[dict] = []

        def _fake_urlopen(req, timeout=None):  # noqa: ANN001
            captured_payloads.append(json.loads(req.data.decode("utf-8")))
            return _mock_urlopen(
                {"choices": [{"message": {"content": "response"}}], "citations": [], "usage": {}}
            )

        monkeypatch.setattr(
            "berb.llm.deep_query_client.urllib.request.urlopen",
            _fake_urlopen,
        )

        client = DeepQueryClient(api_key="test_key")
        client.search(
            "test",
            model="pro",
            domain_filter=["arxiv.org", "openreview.net"],
            recency_filter="month",
        )

        payload = captured_payloads[-1]
        assert payload["search_domain_filter"] == ["arxiv.org", "openreview.net"]
        assert payload["search_recency_filter"] == "month"

    def test_search_parses_search_results_citations(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Newer Perplexity responses use search_results, not citations."""
        mock_resp = _mock_urlopen(
            {
                "choices": [{"message": {"content": "response"}}],
                "search_results": [
                    {"title": "Paper A", "url": "https://a.example", "date": "2024-01-01"},
                ],
                "usage": {},
            }
        )
        monkeypatch.setattr(
            "berb.llm.deep_query_client.urllib.request.urlopen",
            lambda *a, **kw: mock_resp,
        )

        client = DeepQueryClient(api_key="test_key")
        result = client.search("test", model="pro")

        assert result.citations == [
            {"title": "Paper A", "url": "https://a.example", "date": "2024-01-01"}
        ]

    def test_search_raises_on_exhausted_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """search() raises RuntimeError instead of returning a broken result."""
        import urllib.error

        monkeypatch.setattr(
            "berb.llm.deep_query_client.urllib.request.urlopen",
            lambda *a, **kw: (_ for _ in ()).throw(urllib.error.URLError("timeout")),
        )
        monkeypatch.setattr("berb.llm.deep_query_client.time.sleep", lambda _: None)

        client = DeepQueryClient(api_key="test_key")
        with pytest.raises(RuntimeError, match="Perplexity search failed"):
            client.search("test", model="quick")

    def test_circuit_breaker_trips_on_repeated_429(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Three consecutive 429s should trip the breaker and raise cleanly."""
        import urllib.error

        def _raise_429(*a, **kw):  # noqa: ANN001
            raise urllib.error.HTTPError("url", 429, "rate limited", {}, None)

        monkeypatch.setattr(
            "berb.llm.deep_query_client.urllib.request.urlopen",
            _raise_429,
        )
        monkeypatch.setattr("berb.llm.deep_query_client.time.sleep", lambda _: None)

        client = DeepQueryClient(api_key="test_key")
        with pytest.raises(RuntimeError, match="Perplexity search failed"):
            client.search("test", model="quick")

        from berb.llm.deep_query_client import _cb_state

        assert _cb_state == "open"

    def test_literature_review(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test literature review functionality."""
        mock_resp = _mock_urlopen(
            {
                "choices": [{"message": {"content": "Comprehensive review..."}}],
                "citations": ["https://paper1.com", "https://paper2.com"],
                "usage": {},
            }
        )
        monkeypatch.setattr(
            "berb.llm.deep_query_client.urllib.request.urlopen",
            lambda *a, **kw: mock_resp,
        )

        client = DeepQueryClient(api_key="test_key")
        result = client.literature_review(
            topic="machine learning",
            focus_areas=["deep learning", "NLP"],
            year_range=(2020, 2024),
        )

        assert result.content != ""
        assert len(result.citations) == 2

    def test_verify_citation_verified(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test citation verification - verified case."""
        mock_resp = _mock_urlopen(
            {
                "choices": [{"message": {"content": "VERIFIED: This paper exists..."}}],
                "citations": ["https://paper.com"],
                "usage": {},
            }
        )
        monkeypatch.setattr(
            "berb.llm.deep_query_client.urllib.request.urlopen",
            lambda *a, **kw: mock_resp,
        )

        client = DeepQueryClient(api_key="test_key")
        result = client.verify_citation(
            citation_text="Smith et al. (2023). Nature.",
            claimed_finding="CRISPR improves efficiency",
        )

        assert result["status"] == "verified"

    def test_verify_citation_inaccurate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test citation verification - inaccurate case."""
        mock_resp = _mock_urlopen(
            {
                "choices": [
                    {"message": {"content": "INACCURATE: Paper says something different..."}}
                ],
                "citations": [],
                "usage": {},
            }
        )
        monkeypatch.setattr(
            "berb.llm.deep_query_client.urllib.request.urlopen",
            lambda *a, **kw: mock_resp,
        )

        client = DeepQueryClient(api_key="test_key")
        result = client.verify_citation(
            citation_text="Smith et al. (2023).",
            claimed_finding="Wrong claim",
        )

        assert result["status"] == "inaccurate"

    def test_get_model_info(self):
        """Test getting model information."""
        client = DeepQueryClient(api_key="test_key")
        info = client.get_model_info()

        assert info["provider"] == "DeepQuery (Perplexity)"
        assert "models" in info
        assert "sonar" in info["models"]
        assert "sonar-pro" in info["models"]
        assert "sonar-deep-research" in info["models"]


class TestDeepMindAIClient:
    """Test DeepMindAIClient class."""

    @pytest.mark.asyncio
    async def test_chat_success(self):
        """Test successful chat completion."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "chat_123",
            "created": 1234567890,
            "choices": [
                {
                    "message": {"content": "Response from Grok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 500,
                "total_tokens": 600,
            },
        }

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            client = DeepMindAIClient(api_key="test_key")
            result = await client.chat(
                messages=[{"role": "user", "content": "Hello"}],
                model="flagship",
            )

        assert result.content != ""
        assert result.model == "grok-4.20"
        assert result.total_tokens == 600

    @pytest.mark.asyncio
    async def test_chat_different_models(self):
        """Test chat with different models."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "response"}, "finish_reason": "stop"}],
            "usage": {},
        }

        with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
            client = DeepMindAIClient(api_key="test_key")

            # Test flagship model
            await client.chat([{"role": "user", "content": "test"}], model="flagship")
            call_args = mock_post.call_args[1]["json"]
            assert call_args["model"] == "grok-4.20"

            # Test mini model
            await client.chat([{"role": "user", "content": "test"}], model="mini")
            call_args = mock_post.call_args[1]["json"]
            assert call_args["model"] == "grok-3-mini"

    @pytest.mark.asyncio
    async def test_analyze_full_paper(self):
        """Test full paper analysis."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": '{"research_question": "..."}'}, "finish_reason": "stop"}
            ],
            "usage": {"total_tokens": 50000},
        }

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            client = DeepMindAIClient(api_key="test_key")
            result = await client.analyze_full_paper(
                paper_text="This is a research paper...",
                analysis_type="comprehensive",
            )

        assert "analysis" in result
        assert result["tokens_used"] == 50000
        assert result["analysis_type"] == "comprehensive"

    @pytest.mark.asyncio
    async def test_analyze_full_paper_truncation(self):
        """Test paper truncation when exceeding context limit."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "analysis"}, "finish_reason": "stop"}],
            "usage": {},
        }

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            client = DeepMindAIClient(api_key="test_key")

            # Very long paper (exceeds limit)
            long_paper = "x" * 2_000_000

            result = await client.analyze_full_paper(
                paper_text=long_paper,
                analysis_type="comprehensive",
            )

        # Should complete without error (truncation happens internally)
        assert "analysis" in result

    @pytest.mark.asyncio
    async def test_synthesize_papers(self):
        """Test multi-paper synthesis."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "Synthesis of findings..."}, "finish_reason": "stop"}
            ],
            "usage": {"total_tokens": 100000},
        }

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            client = DeepMindAIClient(api_key="test_key")
            result = await client.synthesize_papers(
                papers=[
                    {"title": "Paper 1", "text": "Content 1"},
                    {"title": "Paper 2", "text": "Content 2"},
                ],
                synthesis_goal="hypothesis_generation",
            )

        assert "synthesis" in result
        assert result["papers_analyzed"] == 2
        assert result["synthesis_goal"] == "hypothesis_generation"

    def test_get_model_info(self):
        """Test getting model information."""
        client = DeepMindAIClient(api_key="test_key")
        info = client.get_model_info()

        assert info["provider"] == "DeepMind AI (xAI)"
        assert "models" in info
        assert "grok-4.20" in info["models"]
        assert "grok-4" in info["models"]
        assert "grok-3-mini" in info["models"]

        # Check 2M context feature
        assert info["models"]["grok-4.20"]["context_window"] == "2M tokens"


class TestFactoryFunctions:
    """Test factory functions."""

    def test_create_deepquery_client_with_key(self):
        """Test creating DeepQuery client with API key."""
        client = create_deepquery_client(api_key="test_key")

        assert isinstance(client, DeepQueryClient)

    def test_create_deepquery_client_from_env(self):
        """Test creating DeepQuery client from environment."""
        import os

        # Temporarily set env var
        old_value = os.environ.get("PERPLEXITY_API_KEY")
        os.environ["PERPLEXITY_API_KEY"] = "env_key"

        try:
            client = create_deepquery_client()
            assert isinstance(client, DeepQueryClient)
        finally:
            if old_value:
                os.environ["PERPLEXITY_API_KEY"] = old_value
            else:
                del os.environ["PERPLEXITY_API_KEY"]

    def test_create_deepquery_client_no_key_raises(self):
        """Test creating DeepQuery client without key raises error."""
        import os

        # Temporarily clear env var
        old_value = os.environ.get("PERPLEXITY_API_KEY")
        if "PERPLEXITY_API_KEY" in os.environ:
            del os.environ["PERPLEXITY_API_KEY"]

        try:
            with pytest.raises(ValueError, match="API key required"):
                create_deepquery_client()
        finally:
            if old_value:
                os.environ["PERPLEXITY_API_KEY"] = old_value

    def test_create_deepmind_ai_client_with_key(self):
        """Test creating DeepMind AI client with API key."""
        client = create_deepmind_ai_client(api_key="test_key")

        assert isinstance(client, DeepMindAIClient)

    def test_create_deepmind_ai_client_from_env(self):
        """Test creating DeepMind AI client from environment."""
        import os

        old_value = os.environ.get("DEEPMIND_AI_API_KEY")
        os.environ["DEEPMIND_AI_API_KEY"] = "env_key"

        try:
            client = create_deepmind_ai_client()
            assert isinstance(client, DeepMindAIClient)
        finally:
            if old_value:
                os.environ["DEEPMIND_AI_API_KEY"] = old_value
            else:
                del os.environ["DEEPMIND_AI_API_KEY"]
