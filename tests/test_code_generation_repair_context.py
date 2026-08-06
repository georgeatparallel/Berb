"""Unit tests for `_build_repair_context` (tasks/todo.md #1).

Verifies the repair-loop context sent to the LLM is scoped to the failing
file's direct local imports (not every generated file), ordered with stable
siblings first and the volatile target file last, and bounded by a hard
char ceiling instead of growing unbounded.
"""

from __future__ import annotations

from berb.pipeline.stage_impls._code_generation import (
    _REPAIR_CTX_CHAR_LIMIT,
    _build_repair_context,
)


def test_includes_only_direct_local_imports() -> None:
    files = {
        "main.py": "import utils\nimport unrelated\n\nutils.run()\n",
        "utils.py": "def run():\n    pass\n",
        "unrelated.py": "VALUE = 1\n",
        "other.py": "VALUE = 2\n",
    }

    ctx = _build_repair_context("main.py", files)

    assert "filename:main.py" in ctx
    assert "filename:utils.py" in ctx
    assert "filename:unrelated.py" in ctx
    assert "filename:other.py" not in ctx


def test_target_file_ordered_last() -> None:
    files = {
        "main.py": "import utils\n\nutils.run()\n",
        "utils.py": "def run():\n    pass\n",
    }

    ctx = _build_repair_context("main.py", files)

    assert ctx.index("filename:utils.py") < ctx.index("filename:main.py")


def test_no_local_imports_sends_only_target_file() -> None:
    files = {
        "main.py": "import numpy as np\n",
        "sibling.py": "VALUE = 1\n",
    }

    ctx = _build_repair_context("main.py", files)

    assert "filename:main.py" in ctx
    assert "filename:sibling.py" not in ctx


def test_char_limit_drops_siblings_before_truncating_target() -> None:
    big_sibling = "x = 1\n" * 5000
    files = {
        "main.py": "import big\n\nbig.x\n",
        "big.py": big_sibling,
    }

    ctx = _build_repair_context("main.py", files, char_limit=100)

    assert "filename:big.py" not in ctx
    assert "filename:main.py" in ctx


def test_output_never_exceeds_char_limit_plus_one_block_overhead() -> None:
    files = {"main.py": "x = 1\n" * 10000}

    ctx = _build_repair_context("main.py", files, char_limit=50)

    # The fenced-block wrapper (```filename:...\n ... \n```) adds fixed
    # overhead on top of the truncated code — assert it stays in that
    # ballpark rather than growing with file size.
    assert len(ctx) < 50 + 100


def test_default_char_limit_is_positive() -> None:
    assert _REPAIR_CTX_CHAR_LIMIT > 0
