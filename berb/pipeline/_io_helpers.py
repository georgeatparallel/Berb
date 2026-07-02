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
    for the given filename.  Directory matches (e.g. ``"experiment/"``) are
    returned as a path string rather than read as text.
    """
    found = _find_prior_file(run_dir, filename)
    if found is None:
        return None
    if found.is_dir():
        return str(found)
    return found.read_text(encoding="utf-8")


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
    """Parse LLM response containing multiple files with filename markers.

    Expected format::

        ```filename:main.py
        import model
        ...
        ```

        ```filename:model.py
        class MyModel:
        ...
        ```

    Also handles common LLM format variations:
    - ````` ```python filename:main.py````` (space before filename)
    - ````` ``` filename:main.py````` (space after backticks)
    - ``filename:main.py`` on next line after backticks
    - ``# FILE: main.py`` comment markers inside code blocks

    Falls back to treating the entire code block as ``main.py`` if no
    ``filename:`` markers are found.

    Returns a dict mapping filename -> code content.
    """
    # R13-2: Multiple patterns to handle LLM format variations
    patterns = [
        # Original: ```filename:xxx.py or ```python filename:xxx.py
        re.compile(
            r"```(?:python\s+)?filename:(\S+)\s*\n(.*?)```",
            flags=re.DOTALL,
        ),
        # Variation: ``` filename:xxx.py (space after backticks)
        re.compile(
            r"```\s+filename:(\S+)\s*\n(.*?)```",
            flags=re.DOTALL,
        ),
        # Variation: ```python\nfilename:xxx.py (filename on next line)
        re.compile(
            r"```(?:python)?\s*\nfilename:(\S+)\s*\n(.*?)```",
            flags=re.DOTALL,
        ),
        # Variation: ```python\n# filename: xxx.py (comment marker)
        re.compile(
            r"```(?:python)?\s*\n#\s*(?:FILE|filename)\s*:\s*(\S+\.py)\s*\n(.*?)```",
            flags=re.DOTALL,
        ),
    ]

    matches: list[tuple[str, str]] = []
    for pattern in patterns:
        matches = pattern.findall(content)
        if matches:
            break

    if matches:
        files: dict[str, str] = {}
        for fname, code in matches:
            fname = fname.strip()
            # Security: prevent path traversal
            if ".." in fname or fname.startswith("/"):
                continue
            # Normalise to flat filenames (strip leading ./ or subdirs for safety)
            fname = fname.replace("\\", "/").split("/")[-1]
            if fname and fname.endswith(".py"):
                files[fname] = code.strip()
        if files:
            # Ensure there is a main.py entry point
            if "main.py" not in files:
                # Pick the first file as main.py
                first_key = next(iter(files))
                files["main.py"] = files.pop(first_key)
            return files

    # Fallback: single code block -> main.py
    code = _extract_code_block(content)
    if code.strip():
        return {"main.py": code}
    return {}


def _extract_yaml_block(text: str) -> str:
    """Extract YAML content from a ```yaml ... ``` block, or return the whole text."""
    import re as _re

    match = _re.search(r"```(?:ya?ml)?\s*\n(.*?)\n```", text, _re.DOTALL)
    if match:
        return match.group(1).strip()
    # If no block found, assume entire text is YAML
    return text.strip()
