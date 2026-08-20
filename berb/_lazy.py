"""PEP 562 lazy re-export helper for package ``__init__`` modules.

Berb's packages expose a flat public API (``from berb.literature import Paper``).
Doing that with plain ``from .submodule import ...`` forces every submodule — and
its third-party dependencies — to load the moment the package is touched, which
made ``import berb.pipeline.stages`` pull in httpx, arxiv, feedparser and the
whole benchmark stack.

:func:`lazy_exports` keeps the same public names but defers each submodule import
until the attribute is actually read.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping

__all__ = ["lazy_exports"]

# Public name -> submodule, or (submodule, original name) when re-exported
# under a different name.
ExportMap = Mapping[str, "str | tuple[str, str]"]


def lazy_exports(
    package: str,
    exports: ExportMap,
    namespace: dict[str, object],
) -> tuple[Callable[[str], object], Callable[[], list[str]]]:
    """Build ``__getattr__``/``__dir__`` that import submodules on first access.

    Args:
        package: The importing package's ``__name__``.
        exports: Public attribute name mapped to the submodule providing it, or
            to a ``(submodule, original_name)`` pair for renamed re-exports.
        namespace: The importing module's ``globals()``. Resolved attributes are
            cached here so later lookups bypass ``__getattr__`` entirely.

    Returns:
        The ``__getattr__`` and ``__dir__`` functions to bind in the package.
    """
    resolved: dict[str, tuple[str, str]] = {
        name: (target, name) if isinstance(target, str) else target
        for name, target in exports.items()
    }

    def __getattr__(name: str) -> object:  # noqa: N807 — PEP 562 module hook
        target = resolved.get(name)
        if target is None:
            # Not a re-export: fall back to submodule access, which plain
            # `from .sub import x` used to provide as a side effect.
            return _import_submodule(package, name, namespace)
        submodule, attr = target
        value = getattr(importlib.import_module(f".{submodule}", package), attr)
        namespace[name] = value
        return value

    def __dir__() -> list[str]:  # noqa: N807 — PEP 562 module hook
        public = {n for n in namespace if not n.startswith("_")}
        return sorted(resolved.keys() | public)

    return __getattr__, __dir__


def _import_submodule(package: str, name: str, namespace: dict[str, object]) -> object:
    """Import ``package.name`` as a submodule, or raise ``AttributeError``."""
    if name.startswith("__"):
        raise AttributeError(f"module {package!r} has no attribute {name!r}")
    try:
        module = importlib.import_module(f".{name}", package)
    except ModuleNotFoundError as exc:
        # Only swallow "this submodule does not exist"; a missing third-party
        # dependency inside a real submodule must keep propagating.
        if exc.name in (f"{package}.{name}", name):
            raise AttributeError(
                f"module {package!r} has no attribute {name!r}"
            ) from None
        raise
    namespace[name] = module
    return module
