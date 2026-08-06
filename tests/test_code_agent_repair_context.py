"""Unit tests for CodeAgent._format_files_scoped (tasks/todo.md #1).

`_repair_critical_issues` used to send every generated file as context on
every hard-validation repair attempt (up to hard_validation_max_repairs).
This verifies the scoped replacement only includes affected files plus
their direct local imports, and enforces a char ceiling.
"""

from __future__ import annotations

from berb.pipeline.code_agent import CodeAgent


def test_scoped_context_includes_target_and_its_imports() -> None:
    files = {
        "main.py": "import utils\n\nutils.run()\n",
        "utils.py": "def run():\n    pass\n",
        "unrelated.py": "VALUE = 1\n",
    }

    ctx = CodeAgent._format_files_scoped(files, {"main.py"})

    assert "filename:main.py" in ctx
    assert "filename:utils.py" in ctx
    assert "filename:unrelated.py" not in ctx


def test_scoped_context_includes_multiple_targets() -> None:
    files = {
        "a.py": "VALUE_A = 1\n",
        "b.py": "VALUE_B = 2\n",
        "c.py": "VALUE_C = 3\n",
    }

    ctx = CodeAgent._format_files_scoped(files, {"a.py", "b.py"})

    assert "filename:a.py" in ctx
    assert "filename:b.py" in ctx
    assert "filename:c.py" not in ctx


def test_char_limit_drops_siblings_not_targets() -> None:
    big_sibling = "x = 1\n" * 5000
    files = {
        "main.py": "import big\n\nbig.x\n",
        "big.py": big_sibling,
    }

    ctx = CodeAgent._format_files_scoped(files, {"main.py"}, char_limit=100)

    assert "filename:big.py" not in ctx
    assert "filename:main.py" in ctx
