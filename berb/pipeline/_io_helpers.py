"""File I/O helpers for the pipeline executor.

Extracted from _helpers.py — all functions re-exported from _helpers.py
for backward compatibility.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from berb.pipeline.stages import Stage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Artifact I/O
# ---------------------------------------------------------------------------


def _read_prior_artifact(run_dir: Path, filename: str) -> str | None:
    """Read the contents of a prior stage artifact from any stage directory.

    Searches all ``stage-*/`` directories in reverse order (most recent first)
    for the given filename.
    """
    return _find_prior_file(run_dir, filename)


def _find_prior_file(run_dir: Path, filename: str) -> Path | None:
    """Locate a prior stage artifact file by filename.

    Searches stage directories in reverse order.  Returns the *last*
    (reverse-sorted first) match.
    """
    found = None
    if not run_dir or not run_dir.is_dir():
        return None
    candidates = sorted(run_dir.glob("stage-*/" + filename), reverse=True)
    found = candidates[0] if candidates else None
    if found is None:
        candidates = sorted(run_dir.glob("stage-*/*/" + filename), reverse=True)
        found = candidates[0] if candidates else None
    if found is None:
        candidates = sorted(run_dir.glob(filename), reverse=True)
        found = candidates[0] if candidates else None
    return found


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a list of dicts as newline-delimited JSON."""
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _parse_jsonl_rows(text: str) -> list[dict[str, Any]]:
    """Parse newline-delimited JSON text into a list of dicts."""
    rows: list[dict[str, Any]] = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _extract_code_block(content: str) -> str:
    """Extract code from a ```python ... ``` block."""
    if "```" not in content:
        return content.strip()
    parts = content.split("```")
    # Look for a block that starts with python (or is code-like)
    for i in range(1, len(parts), 2):
        block = parts[i]
        if block.startswith("python"):
            return block[len("python"):].strip()
        # Fallback: return first non-empty block
    for i in range(1, len(parts), 2):
        block = parts[i].strip()
        if block:
            return block
    return content.strip()


def _extract_multi_file_blocks(content: str) -> dict[str, str]:
    """Extract multiple ```python filename.ext ... ``` blocks into {filename: code}."""
    files: dict[str, str] = {}
    pattern = re.compile(r"```(?:python|bash|)\s*(?:\n|$)([\s\S]*?)```", re.MULTILINE)
    matches = pattern.findall(content)
    for match in matches:
        lines = match.strip().split("\n")
        if lines and lines[0].endswith(".py"):
            fname = lines[0].strip()
            code = "\n".join(lines[1:]).strip()
            if code:
                files[fname] = code
    return files


def _extract_yaml_block(text: str) -> str:
    """Extract YAML content from a ```yaml ... ``` block, or return the whole text."""
    import re as _re

    match = _re.search(r"```ya?ml\s*\n(.*?)\n```", text, _re.DOTALL)
    if match:
        return match.group(1).strip()
    # If no block found, assume entire text is YAML
    return text.strip()
