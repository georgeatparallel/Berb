"""Image input as it reaches the wire: LLMClient, the Anthropic adapter, and
the VLM figure critic.

test_llm_vision.py covers berb.llm.vision in isolation. This file covers the
three call sites that had to change for an image to actually leave the process.
"""

from __future__ import annotations

import base64
import json
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from berb.llm.client import LLMClient, LLMConfig
from berb.llm.vision import VisionUnsupportedError, image_message

_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

_OK_PAYLOAD: Mapping[str, Any] = {
    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    "model": "test",
}


def _vision_model() -> str:
    from berb.llm.openrouter_models_data import OPENROUTER_MODELS

    return next(m.id for m in OPENROUTER_MODELS.values() if m.supports_vision)


def _text_only_model() -> str:
    from berb.llm.openrouter_models_data import OPENROUTER_MODELS

    return next(m.id for m in OPENROUTER_MODELS.values() if not m.supports_vision)


@pytest.fixture
def png(tmp_path: Path) -> Path:
    p = tmp_path / "fig.png"
    p.write_bytes(_PNG_BYTES)
    return p


class _DummyResponse:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> _DummyResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _client(model: str, *, wire_api: str = "chat_completions") -> LLMClient:
    return LLMClient(
        LLMConfig(
            base_url="https://api.example.com/v1",
            api_key="k",
            wire_api=wire_api,
            primary_model=model,
            fallback_models=[],
            rate_limit_enabled=False,
        )
    )


def _capture_body(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_urlopen(req: urllib.request.Request, timeout: int) -> _DummyResponse:
        captured["body"] = json.loads(req.data or b"{}")
        return _DummyResponse(_OK_PAYLOAD)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return captured


# ---------------------------------------------------------------------------
# The capability guard
# ---------------------------------------------------------------------------


def test_chat_refuses_an_image_for_a_text_only_model(
    monkeypatch: pytest.MonkeyPatch, png: Path
) -> None:
    calls: list[int] = []

    def fake_urlopen(req: urllib.request.Request, timeout: int) -> _DummyResponse:
        calls.append(1)
        return _DummyResponse(_OK_PAYLOAD)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = _client(_text_only_model())

    with pytest.raises(RuntimeError) as exc:
        client.chat([image_message("look", [png])])

    # Every model in the chain failed the guard, so nothing was ever sent.
    assert not calls
    assert isinstance(exc.value.__cause__, VisionUnsupportedError)


def test_chat_allows_text_on_a_text_only_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard is image-triggered — a text call to the same model is fine."""
    _capture_body(monkeypatch)
    client = _client(_text_only_model())
    assert client.chat([{"role": "user", "content": "hi"}]).content == "ok"


def test_chat_falls_back_from_a_text_only_model_to_a_vision_model(
    monkeypatch: pytest.MonkeyPatch, png: Path
) -> None:
    captured = _capture_body(monkeypatch)
    client = LLMClient(
        LLMConfig(
            base_url="https://api.example.com/v1",
            api_key="k",
            primary_model=_text_only_model(),
            fallback_models=[_vision_model()],
            rate_limit_enabled=False,
        )
    )
    client.chat([image_message("look", [png])])
    assert captured["body"]["model"] == _vision_model()


# ---------------------------------------------------------------------------
# Wire shapes
# ---------------------------------------------------------------------------


def test_chat_completions_body_carries_a_data_uri(
    monkeypatch: pytest.MonkeyPatch, png: Path
) -> None:
    captured = _capture_body(monkeypatch)
    _client(_vision_model()).chat([image_message("look", [png])])

    content = captured["body"]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "look"}
    assert content[1]["type"] == "image_url"
    url = content[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == _PNG_BYTES


def test_responses_body_uses_input_image(monkeypatch: pytest.MonkeyPatch, png: Path) -> None:
    """The Responses wire API has its own part shape; it must not get image_url."""
    captured = _capture_body(monkeypatch)
    client = _client(_vision_model(), wire_api="responses")
    try:
        client.chat([image_message("look", [png])])
    except Exception:  # noqa: BLE001 — the stub payload is chat-completions shaped
        pass

    content = captured["body"]["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "look"}
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")


def test_caller_messages_are_not_mutated(monkeypatch: pytest.MonkeyPatch, png: Path) -> None:
    _capture_body(monkeypatch)
    msg = image_message("look", [png])
    _client(_vision_model()).chat([msg])
    # Still the neutral shape, so a retry or a fallback model re-encodes cleanly.
    assert msg["content"][1]["type"] == "image"


def test_token_estimate_survives_list_content(png: Path) -> None:
    """Rate limiting estimated tokens with len(content) — a list would raise."""
    client = LLMClient(
        LLMConfig(
            base_url="https://api.example.com/v1",
            api_key="k",
            primary_model=_text_only_model(),
            fallback_models=[],
            rate_limit_enabled=True,
        )
    )
    with pytest.raises(RuntimeError) as exc:
        client.chat([image_message("look", [png])])
    # Reached the vision guard, i.e. got past token estimation without a TypeError.
    assert isinstance(exc.value.__cause__, VisionUnsupportedError)


# ---------------------------------------------------------------------------
# Anthropic adapter body
# ---------------------------------------------------------------------------


def test_anthropic_body_uses_a_base64_source_block(png: Path) -> None:
    from berb.llm.anthropic_adapter import AnthropicAdapter

    body = AnthropicAdapter._build_message_body(
        "claude-sonnet-4.6", [image_message("look", [png])], 100, 0.0
    )
    content = body["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "look"}
    assert content[1]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": base64.b64encode(_PNG_BYTES).decode("ascii"),
    }


def test_anthropic_merge_preserves_an_image(png: Path) -> None:
    """Same-role merging concatenated strings; a block list must survive it."""
    from berb.llm.anthropic_adapter import AnthropicAdapter

    body = AnthropicAdapter._build_message_body(
        "claude-sonnet-4.6",
        [{"role": "user", "content": "first"}, image_message("look", [png])],
        100,
        0.0,
    )
    content = body["messages"][0]["content"]
    assert [p["type"] for p in content] == ["text", "text", "image"]
    assert content[0]["text"] == "first"


def test_anthropic_system_message_stays_text(png: Path) -> None:
    """Anthropic's `system` is text-only; an image there is dropped, not sent."""
    from berb.llm.anthropic_adapter import AnthropicAdapter

    sys_msg = image_message("system text", [png], role="system")
    body = AnthropicAdapter._build_message_body(
        "claude-sonnet-4.6",
        [sys_msg, {"role": "user", "content": "hi"}],
        100,
        0.0,
    )
    assert body["system"] == "system text"


# ---------------------------------------------------------------------------
# VLMPlotCritic
# ---------------------------------------------------------------------------


def _real_png(tmp_path: Path) -> Path:
    """A non-blank PNG, so pixel analysis passes and the model is consulted."""
    pytest.importorskip("PIL")
    pytest.importorskip("numpy")
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (64, 64), "white")
    ImageDraw.Draw(img).rectangle([16, 16, 48, 48], fill="black")
    p = tmp_path / "chart.png"
    img.save(p)
    return p


class _StubClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        self.calls.append({"messages": messages, **kwargs})
        return type("R", (), {"content": self.content})()


@pytest.mark.asyncio
async def test_vlm_critic_sends_the_image_and_parses_the_verdict(tmp_path: Path) -> None:
    from berb.experiment.plot_verdict import VLMPlotCritic

    client = _StubClient(
        json.dumps(
            {
                "is_acceptable": False,
                "overall_score": 2.0,
                "confidence": 0.9,
                "issues": ["axis labels overlap"],
            }
        )
    )
    critique = await VLMPlotCritic(client, model="vision-model").analyze_figure(
        _real_png(tmp_path), "CIFAR-10 curves"
    )

    assert critique.is_acceptable is False
    assert "axis labels overlap" in critique.issues
    assert critique.confidence == pytest.approx(0.9)

    sent = client.calls[0]["messages"][0]["content"]
    assert any(p["type"] == "image" for p in sent)
    assert "CIFAR-10 curves" in sent[0]["text"]
    assert client.calls[0]["model"] == "vision-model"


@pytest.mark.asyncio
async def test_vlm_critic_strips_a_fenced_json_block(tmp_path: Path) -> None:
    from berb.experiment.plot_verdict import VLMPlotCritic

    client = _StubClient('```json\n{"is_acceptable": true, "overall_score": 9}\n```')
    critique = await VLMPlotCritic(client).analyze_figure(_real_png(tmp_path))
    assert critique.is_acceptable is True
    assert critique.overall_score == pytest.approx(9.0)


@pytest.mark.asyncio
async def test_vlm_critic_short_circuits_on_a_blank_figure(tmp_path: Path) -> None:
    """A blank canvas is decided by pixels; the model is never paid for."""
    pytest.importorskip("PIL")
    pytest.importorskip("numpy")
    from PIL import Image

    from berb.experiment.plot_verdict import VLMPlotCritic

    blank = tmp_path / "blank.png"
    Image.new("RGB", (64, 64), "white").save(blank)

    client = _StubClient("{}")
    critique = await VLMPlotCritic(client).analyze_figure(blank)

    assert critique.is_acceptable is False
    assert not client.calls


@pytest.mark.asyncio
async def test_vlm_critic_raises_on_unparseable_output(tmp_path: Path) -> None:
    """verify_plots turns this into fail-open, the same as any critic error."""
    from berb.experiment.plot_verdict import VLMPlotCritic

    with pytest.raises(ValueError, match="No JSON object"):
        await VLMPlotCritic(_StubClient("I cannot see the image.")).analyze_figure(
            _real_png(tmp_path)
        )


@pytest.mark.asyncio
async def test_verify_plots_fails_open_when_the_vlm_critic_errors(tmp_path: Path) -> None:
    """A critic error must not gate a candidate out of the search."""
    from berb.experiment.plot_verdict import VLMPlotCritic, is_verdict_gating, verify_plots

    verdict = await verify_plots(
        plot_paths=[_real_png(tmp_path)],
        research_context="ctx",
        critic=VLMPlotCritic(_StubClient("not json")),
    )
    # Recorded as zero-confidence, so the gate abstains rather than excluding.
    assert verdict.confidence == pytest.approx(0.0)
    assert is_verdict_gating(verdict) is None


@pytest.mark.asyncio
async def test_verify_plots_gates_on_a_confident_vlm_rejection(tmp_path: Path) -> None:
    """The other half: a confident rejection does reach the search gate."""
    from berb.experiment.plot_verdict import VLMPlotCritic, is_verdict_gating, verify_plots

    client = _StubClient(
        json.dumps({"is_acceptable": False, "overall_score": 1.0, "confidence": 0.95})
    )
    verdict = await verify_plots(
        plot_paths=[_real_png(tmp_path)],
        research_context="ctx",
        critic=VLMPlotCritic(client),
    )
    assert is_verdict_gating(verdict) is True
