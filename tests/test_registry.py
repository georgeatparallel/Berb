"""Tests for the plugin stage registry."""

from __future__ import annotations

from berb.pipeline.contracts import StageContract
from berb.pipeline.registry import (
    clear_registry,
    get_all_registrations,
    get_registration,
    register_stage,
)
from berb.pipeline.stages import Stage


def fake_stage_fn() -> str:
    return "fake result"


def test_register_stage_stores_metadata() -> None:
    """@register_stage stores stage, deps, and contract in the registry."""
    clear_registry()
    contract = StageContract(
        stage=Stage.TOPIC_INIT,
        input_files=(),
        output_files=("goal.md",),
        dod="test",
        error_code="E99",
    )

    @register_stage(stage=Stage.TOPIC_INIT, depends_on=frozenset(), contract=contract)
    def my_stage() -> str:
        return "ok"

    reg = get_registration(Stage.TOPIC_INIT)
    assert reg is not None
    assert reg.stage == Stage.TOPIC_INIT
    assert reg.fn is my_stage
    assert reg.depends_on == frozenset()
    assert reg.contract is contract
    assert my_stage() == "ok"


def test_get_all_registrations_returns_all() -> None:
    """get_all_registrations returns every registered stage."""
    clear_registry()
    c1 = StageContract(stage=Stage.TOPIC_INIT, input_files=(), output_files=("a",), dod="t", error_code="E1")
    c2 = StageContract(stage=Stage.PROBLEM_DECOMPOSE, input_files=("a",), output_files=("b",), dod="t", error_code="E2")

    @register_stage(stage=Stage.TOPIC_INIT, depends_on=frozenset(), contract=c1)
    def fn1() -> None: ...

    @register_stage(stage=Stage.PROBLEM_DECOMPOSE, depends_on=frozenset({Stage.TOPIC_INIT}), contract=c2)
    def fn2() -> None: ...

    all_regs = get_all_registrations()
    assert len(all_regs) == 2
    assert Stage.TOPIC_INIT in all_regs
    assert Stage.PROBLEM_DECOMPOSE in all_regs


def test_get_registration_returns_none_for_unregistered() -> None:
    """get_registration returns None for stages not in the registry."""
    clear_registry()
    assert get_registration(Stage.CITATION_VERIFY) is None


def test_register_stage_overwrites_existing() -> None:
    """Registering the same stage twice overwrites with the new function."""
    clear_registry()

    @register_stage(stage=Stage.TOPIC_INIT, depends_on=frozenset())
    def first_fn() -> str:
        return "first"

    @register_stage(stage=Stage.TOPIC_INIT, depends_on=frozenset())
    def second_fn() -> str:
        return "second"

    reg = get_registration(Stage.TOPIC_INIT)
    assert reg is not None
    assert reg.fn is second_fn
    assert reg.fn() == "second"


def test_clear_registry_removes_all() -> None:
    """clear_registry empties the registry completely."""
    clear_registry()

    c = StageContract(stage=Stage.TOPIC_INIT, input_files=(), output_files=("a",), dod="t", error_code="E1")

    @register_stage(stage=Stage.TOPIC_INIT, depends_on=frozenset(), contract=c)
    def my_stage() -> None: ...

    assert len(get_all_registrations()) == 1
    clear_registry()
    assert len(get_all_registrations()) == 0
    assert get_registration(Stage.TOPIC_INIT) is None


def test_registration_returns_original_function() -> None:
    """The decorator returns the original function unchanged."""
    clear_registry()

    @register_stage(stage=Stage.TOPIC_INIT, depends_on=frozenset())
    def my_stage(a: int, b: int) -> int:
        return a + b

    assert my_stage(3, 4) == 7
    assert my_stage.__name__ == "my_stage"
