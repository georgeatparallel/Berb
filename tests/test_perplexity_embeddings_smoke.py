# pyright: reportPrivateUsage=false
"""Perplexity embeddings schema verification (gated, not run by default).

berb/memory/embeddings.py's EmbeddingProvider._embed_api() assumes an
OpenAI-compatible /embeddings endpoint: POST {"input": ..., "model": ...}
-> {"data": [{"embedding": [...]}]}. Perplexity's docs were unreachable
during the integration work that added this test (WebFetch was down), so
that assumption is UNVERIFIED — do not wire EmbeddingProvider at Perplexity
until this test has actually been run against a real key and passed.

Run explicitly once you have a PERPLEXITY_API_KEY:
    pytest tests/test_perplexity_embeddings_smoke.py -v -m llm

It's excluded from the default test run via the "llm" marker (see
CLAUDE.md: `pytest -m "not slow and not e2e and not llm"`).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

pytestmark = pytest.mark.llm

BASE_URL = "https://api.perplexity.ai"


def _require_api_key() -> str:
    key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not key:
        pytest.skip("PERPLEXITY_API_KEY not set — this is a live-API schema check")
    return key


def test_embeddings_endpoint_matches_openai_shape() -> None:
    """Confirm POST {base_url}/embeddings returns OpenAI-compatible JSON.

    This is exactly what EmbeddingProvider._embed_api() expects. If this
    test fails, DO NOT wire EmbeddingProvider at Perplexity — read the
    printed response shape, update _embed_api() (or write a dedicated
    Perplexity embeddings adapter) to match reality, then re-run this test.
    """
    key = _require_api_key()

    payload = json.dumps(
        {"input": "test embedding input", "model": "text-embedding-3-small"}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/embeddings",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        pytest.fail(
            f"Perplexity embeddings endpoint returned HTTP {exc.code}: {detail}\n"
            "Either the endpoint path, model name, or auth scheme differs "
            "from the OpenAI-compatible assumption — check Perplexity's "
            "current embeddings docs before wiring EmbeddingProvider."
        )

    assert (
        "data" in body
    ), f"Expected top-level 'data' key, got keys: {list(body.keys())}"
    assert (
        isinstance(body["data"], list) and body["data"]
    ), "Expected non-empty 'data' list"

    entry = body["data"][0]
    assert (
        "embedding" in entry
    ), f"Expected 'embedding' key in data[0], got: {list(entry.keys())}"
    embedding = entry["embedding"]
    assert (
        isinstance(embedding, list) and embedding
    ), "Expected non-empty embedding vector"
    assert all(
        isinstance(v, (int, float)) for v in embedding
    ), "Expected embedding to be a list of numbers"

    print(
        f"\nSchema confirmed OpenAI-compatible. Embedding dimension: {len(embedding)}"
    )
