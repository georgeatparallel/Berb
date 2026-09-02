"""Image input for LLM calls.

Before this module ``berb/llm/`` could not send an image to any provider:
no adapter emitted an ``image_url``, a base64 media block or an
``input_image``, while :mod:`berb.llm.openrouter_models_data` declared
``supports_vision=True`` on 173 of its 335 models and *nothing read the
flag*. :func:`model_supports_vision` is that flag's first reader.

The design keeps one provider-neutral message shape and converts at the
wire boundary:

    msg = image_message("Is this chart blank?", ["fig1.png"])
    # {"role": "user", "content": [
    #     {"type": "text",  "text": "Is this chart blank?"},
    #     {"type": "image", "media_type": "image/png", "data": "<base64>"},
    # ]}

:func:`to_openai_content` and :func:`to_anthropic_content` translate that
into the two wire formats. Neither provider's shape is used as the neutral
one, so neither conversion is implicit.

Only base64 inline data is supported. Remote image URLs are deliberately
out of scope: they make the provider fetch a URL we chose, which is a
different trust decision from uploading bytes we already have on disk.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_IMAGE_BYTES",
    "SUPPORTED_MEDIA_TYPES",
    "ImagePart",
    "VisionUnsupportedError",
    "content_to_text",
    "encode_image",
    "ensure_vision_capable",
    "image_message",
    "messages_have_images",
    "model_supports_vision",
    "to_anthropic_content",
    "to_openai_content",
    "to_responses_content",
]


# Anthropic rejects a base64 image over 5 MB; OpenAI's limit is higher, so
# the tighter one is the portable one.
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# The intersection of what the Anthropic Messages API and the OpenAI
# chat-completions API both accept. Anything outside it would work on one
# provider and 400 on the other, which is worse than refusing up front.
SUPPORTED_MEDIA_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


class VisionUnsupportedError(ValueError):
    """Raised when an image is sent to a model catalogued as text-only."""


@dataclass(frozen=True)
class ImagePart:
    """One base64-encoded image, ready to be placed in a message."""

    media_type: str
    data: str
    """Base64 (not data-URI) encoded bytes."""

    def as_neutral(self) -> dict[str, str]:
        """Return the provider-neutral content part for this image."""
        return {"type": "image", "media_type": self.media_type, "data": self.data}

    def as_data_uri(self) -> str:
        """Return an RFC 2397 data URI, the shape OpenAI's ``image_url`` wants."""
        return f"data:{self.media_type};base64,{self.data}"


def encode_image(path: Path | str) -> ImagePart:
    """Read an image file and base64-encode it.

    Args:
        path: Path to a PNG, JPEG, GIF or WebP file.

    Returns:
        An :class:`ImagePart`.

    Raises:
        FileNotFoundError: The path does not exist.
        ValueError: Unsupported extension, or the file exceeds
            :data:`MAX_IMAGE_BYTES`.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Image not found: {p}")

    media_type = SUPPORTED_MEDIA_TYPES.get(p.suffix.lower())
    if media_type is None:
        raise ValueError(
            f"Unsupported image type {p.suffix!r} for {p.name}. "
            f"Supported: {', '.join(sorted(SUPPORTED_MEDIA_TYPES))}"
        )

    raw = p.read_bytes()
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image {p.name} is {len(raw) / 1e6:.1f} MB, over the "
            f"{MAX_IMAGE_BYTES / 1e6:.0f} MB per-image limit."
        )
    if not raw:
        raise ValueError(f"Image {p.name} is empty.")

    return ImagePart(media_type=media_type, data=base64.b64encode(raw).decode("ascii"))


def image_message(
    text: str,
    images: list[Path | str] | list[ImagePart],
    *,
    role: str = "user",
) -> dict[str, Any]:
    """Build one multimodal message in the provider-neutral shape.

    Args:
        text: The prompt text. Placed before the images, which is what
            both providers' docs recommend for a single-image question.
        images: Image file paths, or already-encoded :class:`ImagePart`s.
        role: Message role; ``"user"`` unless you are constructing a
            few-shot assistant turn.

    Returns:
        A ``{"role": ..., "content": [...]}`` dict whose content is a list
        of neutral parts.

    Raises:
        ValueError: No images given, or an image fails :func:`encode_image`.
    """
    if not images:
        raise ValueError("image_message() requires at least one image")

    parts: list[dict[str, str]] = [{"type": "text", "text": text}]
    for img in images:
        part = img if isinstance(img, ImagePart) else encode_image(img)
        parts.append(part.as_neutral())
    return {"role": role, "content": parts}


def messages_have_images(messages: list[dict[str, Any]]) -> bool:
    """True if any message carries at least one neutral image part."""
    return any(_content_images(m.get("content")) for m in messages)


def content_to_text(content: Any) -> str:
    """Flatten message content to plain text.

    Plain-string content is returned unchanged. A part list contributes its
    text parts joined by newlines; images contribute nothing. Used for token
    estimation and for merging consecutive same-role messages, both of which
    predate multimodal content and would otherwise raise on a list.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(p.get("text", ""))
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        )
    return str(content or "")


# ---------------------------------------------------------------------------
# Capability lookup — the first reader of `supports_vision`
# ---------------------------------------------------------------------------


def model_supports_vision(model: str) -> bool | None:
    """Look a model up in the OpenRouter catalogue's ``supports_vision`` flag.

    The catalogue is keyed by OpenRouter ids (``anthropic/claude-sonnet-4.6``),
    but the same model is reached directly under a bare name
    (``claude-sonnet-4.6``), so a vendor-stripped match is tried too.

    Args:
        model: Model id, with or without a vendor prefix or a ``:variant``
            suffix.

    Returns:
        ``True``/``False`` from the catalogue, or ``None`` when the model is
        not catalogued at all — an absent entry is not evidence of absent
        vision support.
    """
    from berb.llm.openrouter_models_data import OPENROUTER_MODELS

    for key in _lookup_keys(model):
        entry = OPENROUTER_MODELS.get(key)
        if entry is not None:
            return bool(entry.supports_vision)

    bare = _bare_name(model)
    for entry in OPENROUTER_MODELS.values():
        if _bare_name(entry.id) == bare:
            return bool(entry.supports_vision)
    return None


def ensure_vision_capable(model: str) -> None:
    """Refuse to send an image to a model the catalogue calls text-only.

    Fails open for uncatalogued models: raising there would block every
    provider Berb reaches outside OpenRouter's list.

    Raises:
        VisionUnsupportedError: The catalogue has this model with
            ``supports_vision=False``.
    """
    supported = model_supports_vision(model)
    if supported is False:
        raise VisionUnsupportedError(
            f"Model {model!r} is catalogued as text-only (supports_vision=False); "
            f"refusing to send an image. Pick a vision model or drop the image."
        )
    if supported is None:
        logger.debug(
            "Model %r is not in the OpenRouter catalogue — sending image unchecked.", model
        )


# ---------------------------------------------------------------------------
# Wire encoders
# ---------------------------------------------------------------------------


def to_openai_content(content: Any) -> Any:
    """Convert neutral content to the OpenAI/OpenRouter chat-completions shape.

    Images become ``{"type": "image_url", "image_url": {"url": "data:..."}}``.
    Plain strings and lists with no images pass through untouched, so this is
    safe to apply to every outgoing message.
    """
    if not _content_images(content):
        return content
    return [_to_openai_part(p) for p in content]


def to_responses_content(content: Any) -> list[dict[str, Any]]:
    """Convert content to OpenAI Responses-API input parts.

    Unlike the other two encoders this always returns a part list, because
    the Responses API has no bare-string content form: text becomes
    ``input_text`` and images become ``input_image``.
    """
    if not isinstance(content, list):
        return [{"type": "input_text", "text": str(content or "")}]
    return [_to_responses_part(p) for p in content]


def to_anthropic_content(content: Any) -> Any:
    """Convert neutral content to Anthropic Messages content blocks.

    Images become ``{"type": "image", "source": {"type": "base64", ...}}``.
    Plain strings and image-free lists pass through untouched.
    """
    if not _content_images(content):
        return content
    return [_to_anthropic_part(p) for p in content]


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _content_images(content: Any) -> list[dict[str, Any]]:
    """Return the neutral image parts in `content` (empty for text-only)."""
    if not isinstance(content, list):
        return []
    return [p for p in content if isinstance(p, dict) and p.get("type") == "image"]


def _to_openai_part(part: Any) -> dict[str, Any]:
    if isinstance(part, dict) and part.get("type") == "image":
        url = f"data:{part['media_type']};base64,{part['data']}"
        return {"type": "image_url", "image_url": {"url": url}}
    if isinstance(part, dict):
        return part
    return {"type": "text", "text": str(part)}


def _to_responses_part(part: Any) -> dict[str, Any]:
    if isinstance(part, dict) and part.get("type") == "image":
        return {
            "type": "input_image",
            "image_url": f"data:{part['media_type']};base64,{part['data']}",
        }
    if isinstance(part, dict) and part.get("type") == "text":
        return {"type": "input_text", "text": str(part.get("text", ""))}
    if isinstance(part, dict):
        return part
    return {"type": "input_text", "text": str(part)}


def _to_anthropic_part(part: Any) -> dict[str, Any]:
    if isinstance(part, dict) and part.get("type") == "image":
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": part["media_type"],
                "data": part["data"],
            },
        }
    if isinstance(part, dict):
        return part
    return {"type": "text", "text": str(part)}


def _lookup_keys(model: str) -> tuple[str, ...]:
    """Candidate catalogue keys for `model`: as given, then variant-stripped."""
    if ":" in model:
        return (model, model.rsplit(":", 1)[0])
    return (model,)


def _bare_name(model: str) -> str:
    """Drop the vendor prefix and any ``:variant`` suffix."""
    name = model.rsplit(":", 1)[0] if ":" in model else model
    return name.rsplit("/", 1)[-1]
