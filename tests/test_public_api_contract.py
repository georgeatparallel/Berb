"""The declared public API must actually resolve.

`from berb.literature import ...` and `from berb.llm import ...` were confirmed
supported contracts on 2026-09-02, and scripts/check_reachability.py now treats the modules behind that
package's ``__all__`` as entry points — so the dead-code gate no longer notices
if one of them rots.

This test is what replaces that notice. It imports every name the package
declares and fails if one is missing, misspelled in ``__all__``, or points at a
lazy-export target that no longer exists. Without it, the contract would be
exempt from the only check that was watching it.

See tasks/w2_untested_triage.md section 4 and tasks/dead_code_wiring_plan.md.
"""

from __future__ import annotations

import importlib

import pytest

# Kept in step with PUBLIC_API_PACKAGES in scripts/check_reachability.py.
PUBLIC_API_PACKAGES = ("berb.literature", "berb.llm")


def _exported_names(package: str) -> list[str]:
    mod = importlib.import_module(package)
    names = getattr(mod, "__all__", None)
    assert names, f"{package} declares no __all__ — it is not a public API package"
    return sorted(names)


@pytest.mark.parametrize("package", PUBLIC_API_PACKAGES)
def test_package_declares_a_public_api(package: str) -> None:
    assert _exported_names(package), f"{package}.__all__ is empty"


@pytest.mark.parametrize("package", PUBLIC_API_PACKAGES)
def test_every_exported_name_resolves(package: str) -> None:
    """Each name in __all__ must be gettable — this is the contract itself."""
    mod = importlib.import_module(package)
    broken: list[str] = []
    for name in _exported_names(package):
        try:
            getattr(mod, name)
        except Exception as exc:  # AttributeError, ImportError from a lazy target
            broken.append(f"{package}.{name} -> {type(exc).__name__}: {exc}")
    assert not broken, "declared public API does not resolve:\n  " + "\n  ".join(broken)


@pytest.mark.parametrize("package", PUBLIC_API_PACKAGES)
def test_checker_and_test_agree_on_scope(package: str) -> None:
    """Guard against the two lists drifting apart.

    If the checker exempts a package from the dead-code gate but this test does
    not cover it, that package's API is unwatched by anything.
    """
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_reachability.py"
    spec = importlib.util.spec_from_file_location("check_reachability", script)
    assert spec and spec.loader
    cr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cr)

    source = script.read_text(encoding="utf-8")
    assert f'"{package}"' in source, (
        f"{package} is covered by this test but not by check_reachability.py's "
        "PUBLIC_API_PACKAGES — the two must stay in step"
    )


def test_checker_exempts_nothing_this_test_ignores() -> None:
    """The reverse direction: nothing exempt should be uncovered here."""
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_reachability.py"
    spec = importlib.util.spec_from_file_location("check_reachability", script)
    assert spec and spec.loader
    cr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cr)

    all_mods, is_pkg = cr.discover_modules(cr.ROOT, cr.PKG)
    exempt_packages = {".".join(m.split(".")[:-1]) for m in cr.public_api_modules(all_mods, is_pkg)}
    uncovered = exempt_packages - set(PUBLIC_API_PACKAGES)
    assert not uncovered, (
        f"check_reachability.py exempts {sorted(uncovered)} from the dead-code "
        "gate, but this test does not verify their public API resolves"
    )
