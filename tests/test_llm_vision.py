"""Tests for berb.llm.vision — image input and the supports_vision guard."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from berb.llm.vision import (
    MAX_IMAGE_BYTES,
    ImagePart,
    VisionUnsupportedError,
    content_to_text,
    encode_image,
    ensure_vision_capable,
    image_message,
    messages_have_images,
    model_supports_vision,
    to_anthropic_content,
    to_openai_content,
    to_responses_content,
)

# 1x1 transparent PNG.
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@pytest.fixture
def png(tmp_path: Path) -> Path:
    p = tmp_path / "fig.png"
    p.write_bytes(_PNG_BYTES)
    return p


# ---------------------------------------------------------------------------
# encode_image
# ---------------------------------------------------------------------------


def test_encode_image_round_trips(png: Path) -> None:
    part = encode_image(png)
    assert part.media_type == "image/png"
    assert base64.b64decode(part.data) == _PNG_BYTES


def test_encode_image_jpg_maps_to_jpeg(tmp_path: Path) -> None:
    p = tmp_path / "fig.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0not-really-a-jpeg")
    assert encode_image(p).media_type == "image/jpeg"


def test_encode_image_is_extension_case_insensitive(tmp_path: Path) -> None:
    p = tmp_path / "FIG.PNG"
    p.write_bytes(_PNG_BYTES)
    assert encode_image(p).media_type == "image/png"


def test_encode_image_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        encode_image(tmp_path / "nope.png")


def test_encode_image_rejects_unsupported_extension(tmp_path: Path) -> None:
    p = tmp_path / "fig.bmp"
    p.write_bytes(b"BM")
    with pytest.raises(ValueError, match="Unsupported image type"):
        encode_image(p)


def test_encode_image_rejects_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "empty.png"
    p.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        encode_image(p)


def test_encode_image_rejects_oversize_file(tmp_path: Path) -> None:
    p = tmp_path / "big.png"
    p.write_bytes(b"\x00" * (MAX_IMAGE_BYTES + 1))
    with pytest.raises(ValueError, match="per-image limit"):
        encode_image(p)


def test_data_uri_shape(png: Path) -> None:
    uri = encode_image(png).as_data_uri()
    assert uri.startswith("data:image/png;base64,")


# ---------------------------------------------------------------------------
# image_message / detection / flattening
# ---------------------------------------------------------------------------


def test_image_message_puts_text_first(png: Path) -> None:
    msg = image_message("look", [png])
    assert msg["role"] == "user"
    assert msg["content"][0] == {"type": "text", "text": "look"}
    assert msg["content"][1]["type"] == "image"
    assert msg["content"][1]["media_type"] == "image/png"


def test_image_message_accepts_preencoded_parts(png: Path) -> None:
    part = encode_image(png)
    msg = image_message("look", [part, part])
    assert sum(1 for p in msg["content"] if p["type"] == "image") == 2


def test_image_message_requires_an_image() -> None:
    with pytest.raises(ValueError, match="at least one image"):
        image_message("look", [])


def test_messages_have_images_is_false_for_plain_text() -> None:
    assert not messages_have_images([{"role": "user", "content": "hi"}])


def test_messages_have_images_is_false_for_text_part_list() -> None:
    msg: dict[str, Any] = {"role": "user", "content": [{"type": "text", "text": "hi"}]}
    assert not messages_have_images([msg])


def test_messages_have_images_detects_an_image(png: Path) -> None:
    assert messages_have_images([{"role": "user", "content": "hi"}, image_message("x", [png])])


def test_content_to_text_passes_strings_through() -> None:
    assert content_to_text("plain") == "plain"


def test_content_to_text_drops_images_and_joins_text(png: Path) -> None:
    content = image_message("look", [png])["content"]
    assert content_to_text(content) == "look"


def test_content_to_text_handles_none() -> None:
    assert content_to_text(None) == ""


# ---------------------------------------------------------------------------
# Capability lookup — the first reader of supports_vision
# ---------------------------------------------------------------------------


def test_catalogue_declares_vision_models() -> None:
    """Guards the premise: the flag this module reads is actually populated."""
    from berb.llm.openrouter_models_data import OPENROUTER_MODELS

    vision = [m for m in OPENROUTER_MODELS.values() if m.supports_vision]
    text_only = [m for m in OPENROUTER_MODELS.values() if not m.supports_vision]
    assert vision and text_only


def test_model_supports_vision_by_openrouter_id() -> None:
    from berb.llm.openrouter_models_data import OPENROUTER_MODELS

    vision_id = next(m.id for m in OPENROUTER_MODELS.values() if m.supports_vision)
    assert model_supports_vision(vision_id) is True


def test_model_supports_vision_by_bare_name() -> None:
    from berb.llm.openrouter_models_data import OPENROUTER_MODELS

    vision_id = next(m.id for m in OPENROUTER_MODELS.values() if m.supports_vision)
    assert model_supports_vision(vision_id.rsplit("/", 1)[-1]) is True


def test_model_supports_vision_strips_variant_suffix() -> None:
    from berb.llm.openrouter_models_data import OPENROUTER_MODELS

    vision_id = next(m.id for m in OPENROUTER_MODELS.values() if m.supports_vision)
    assert model_supports_vision(f"{vision_id}:nitro") is True


def test_model_supports_vision_reports_text_only() -> None:
    from berb.llm.openrouter_models_data import OPENROUTER_MODELS

    text_id = next(m.id for m in OPENROUTER_MODELS.values() if not m.supports_vision)
    assert model_supports_vision(text_id) is False


def test_model_supports_vision_is_none_when_uncatalogued() -> None:
    assert model_supports_vision("no-such-vendor/no-such-model-9000") is None


def test_ensure_vision_capable_rejects_text_only_model() -> None:
    from berb.llm.openrouter_models_data import OPENROUTER_MODELS

    text_id = next(m.id for m in OPENROUTER_MODELS.values() if not m.supports_vision)
    with pytest.raises(VisionUnsupportedError, match="text-only"):
        ensure_vision_capable(text_id)


def test_ensure_vision_capable_allows_vision_model() -> None:
    from berb.llm.openrouter_models_data import OPENROUTER_MODELS

    vision_id = next(m.id for m in OPENROUTER_MODELS.values() if m.supports_vision)
    ensure_vision_capable(vision_id)


def test_ensure_vision_capable_fails_open_for_uncatalogued_model() -> None:
    """An absent catalogue entry is not evidence of absent vision support."""
    ensure_vision_capable("no-such-vendor/no-such-model-9000")


# ---------------------------------------------------------------------------
# Wire encoders
# ---------------------------------------------------------------------------


def test_openai_encoding(png: Path) -> None:
    parts = to_openai_content(image_message("look", [png])["content"])
    assert parts[0] == {"type": "text", "text": "look"}
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_anthropic_encoding(png: Path) -> None:
    parts = to_anthropic_content(image_message("look", [png])["content"])
    assert parts[0] == {"type": "text", "text": "look"}
    assert parts[1]["type"] == "image"
    assert parts[1]["source"]["type"] == "base64"
    assert parts[1]["source"]["media_type"] == "image/png"
    assert base64.b64decode(parts[1]["source"]["data"]) == _PNG_BYTES


def test_responses_encoding(png: Path) -> None:
    parts = to_responses_content(image_message("look", [png])["content"])
    assert parts[0] == {"type": "input_text", "text": "look"}
    assert parts[1]["type"] == "input_image"
    assert parts[1]["image_url"].startswith("data:image/png;base64,")


@pytest.mark.parametrize("encoder", [to_openai_content, to_anthropic_content])
def test_encoders_pass_plain_strings_through(encoder: Any) -> None:
    assert encoder("just text") == "just text"


@pytest.mark.parametrize("encoder", [to_openai_content, to_anthropic_content])
def test_encoders_pass_image_free_lists_through(encoder: Any) -> None:
    content = [{"type": "text", "text": "a"}]
    assert encoder(content) == content


def test_responses_encoder_wraps_a_bare_string() -> None:
    assert to_responses_content("hi") == [{"type": "input_text", "text": "hi"}]


def test_image_part_is_hashable() -> None:
    part = ImagePart(media_type="image/png", data="AAAA")
    assert {part, part} == {part}
