"""Guards the lazy package re-exports in berb/_lazy.py.

Two properties matter and can each regress silently:

1. Laziness must not break the public API — every name in a package's
   ``__all__`` still has to resolve.
2. The API must stay lazy — one plain ``from .submodule import X`` added back to
   a package ``__init__`` re-links the whole dependency graph. Importing
   ``berb.pipeline.stages`` used to pull httpx, arxiv and feedparser, costing
   ~27s and ~1030 modules per interpreter (which also exhausted the Windows
   paging file under ``pytest -n auto``).
"""

from __future__ import annotations

import importlib
import subprocess
import sys

import pytest

LAZY_PACKAGES = [
    "berb.pipeline",
    "berb.literature",
    "berb.experiment",
    "berb.benchmarks",
    "berb.llm",
]

# Third-party stacks that must stay out of the light import paths below.
HEAVY_DEPS = ["httpx", "arxiv", "feedparser", "httpcore", "trio"]

# Modules a caller should be able to import without paying for HEAVY_DEPS.
LIGHT_IMPORTS = ["berb.pipeline.stages", "berb.literature", "berb.llm"]


@pytest.mark.parametrize("package", LAZY_PACKAGES)
def test_all_exports_resolve(package: str) -> None:
    """Every advertised name resolves through the lazy __getattr__."""
    module = importlib.import_module(package)

    unresolved = [name for name in module.__all__ if not hasattr(module, name)]

    assert not unresolved, f"{package} advertises unresolvable names: {unresolved}"


@pytest.mark.parametrize("package", LAZY_PACKAGES)
def test_unknown_attribute_raises_attribute_error(package: str) -> None:
    """__getattr__ must not mask typos as ImportError or return None."""
    module = importlib.import_module(package)

    with pytest.raises(AttributeError):
        module.definitely_not_an_export


@pytest.mark.parametrize("package", LAZY_PACKAGES)
def test_dir_lists_public_api(package: str) -> None:
    """dir() stays useful for tab-completion despite the lazy indirection."""
    module = importlib.import_module(package)

    assert set(module.__all__) <= set(dir(module))


@pytest.mark.parametrize("target", LIGHT_IMPORTS)
def test_light_import_does_not_pull_heavy_deps(target: str) -> None:
    """Importing `target` must not drag the HTTP/arXiv stacks into memory."""
    probe = (
        f"import sys; import {target}; "
        f"print(','.join(d for d in {HEAVY_DEPS!r} if d in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )

    assert result.returncode == 0, f"import {target} failed:\n{result.stderr}"
    leaked = result.stdout.strip()
    assert not leaked, f"import {target} eagerly loaded heavy deps: {leaked}"
