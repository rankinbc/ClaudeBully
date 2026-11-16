"""A plan bundle's personas in the strategy registry, and ``run``'s refusal of a bundle (Phase 5,
spec section 11).

The runner, the analysis and the planner all import this module and it imports none of them, so
the planner (which already imports ``runner/store``) and the runner never import each other
(Task 10 review M3). ``plan_personas`` is Task 4a's scoped registration (D-plan_personas),
moved here from ``planner/bundle.py``, which re-exports it."""

import weakref
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Final

from claude_bully.strategies import base as strategy_base
from claude_bully.strategies.bootstrap import ensure_registered
from claude_bully.strategies.premises.phased import make_phased_premise
from claude_bully.strategies.sheets import PersonaSheet


class BundleRefused(ValueError):  # noqa: N818 - the name is the specified interface
    """A bundle ``run`` will not run: not ``runnable``, changed since stage 5 stamped it, beside
    a ``--worlds-dir`` that is not its own, or not the bundle a run being resumed was made from.
    Raised before anything is written."""


# every class a plan_personas block or register_plan_personas registered: a plan's persona,
# never a strategy of the package (the schema lint's name check reads it, review M5)
_PLAN_CLASSES: Final[weakref.WeakSet[type[strategy_base.Strategy]]] = weakref.WeakSet()


def is_plan_persona(cls: type[strategy_base.Strategy]) -> bool:
    """True for a class a ``plan_personas`` block or ``register_plan_personas`` registered."""
    return cls in _PLAN_CLASSES


@contextmanager
def plan_personas(sheets: Mapping[str, PersonaSheet]) -> Iterator[None]:
    """The bundle's personas registered for the block (D-plan_personas, R-registry).

    ``ensure_registered()`` runs first, so the block never sees a registry that loads its
    strategies later. Each sheet is registered with ``make_phased_premise``; on exit, exceptions
    included, each name the block registered is removed, or given back the class it replaced.
    Nothing else is touched: a strategy something else registered inside the block stays, and the
    registry is never restored from a snapshot (a snapshot taken before the first load would
    empty it for good). Blocks nest, each undoing only its own registrations."""
    ensure_registered()
    replaced: dict[str, type[strategy_base.Strategy] | None] = {}
    try:
        for sheet in sheets.values():
            replaced.setdefault(sheet.name, strategy_base._REGISTRY.get(sheet.name))
            _PLAN_CLASSES.add(make_phased_premise(sheet))
        yield
    finally:
        for name, previous in replaced.items():
            if previous is None:
                strategy_base._REGISTRY.pop(name, None)
            else:
                strategy_base._REGISTRY[name] = previous


def _new_plan_sheets(personas: Mapping[str, Mapping[str, Any]]) -> dict[str, PersonaSheet]:
    """The recorded sheets of ``personas`` to register, validated. ``ensure_registered()`` runs
    first (R-registry: a fresh process has loaded no coded strategy yet). A name registered with
    an equal sheet is left out. A name another plan's persona holds with another sheet is kept,
    so it replaces that one: two runs of two bundles may share a persona name (Task 10 review
    I1). A name a strategy of the package holds with another sheet, or with none, raises
    ``ValueError`` naming the name and both sources, as does a sheet recorded under a name that
    is not its own."""
    ensure_registered()
    sheets: dict[str, PersonaSheet] = {}
    for name, dumped in personas.items():
        sheet = PersonaSheet.model_validate(dumped)
        if sheet.name != name:
            raise ValueError(f"plan persona {name!r}: the recorded sheet is named {sheet.name!r}")
        registered = strategy_base._REGISTRY.get(name)
        own = getattr(registered, "sheet", None)
        if isinstance(own, PersonaSheet) and own.model_dump(mode="json") == sheet.model_dump(
            mode="json"
        ):
            continue
        if registered is not None and not is_plan_persona(registered):
            raise ValueError(
                f"plan persona {name!r}: the plan's recorded sheet is not the sheet of the "
                f"package's strategy {name!r} ({registered.__module__}.{registered.__qualname__})"
            )
        sheets[name] = sheet
    return sheets


def register_plan_personas(personas: Mapping[str, Mapping[str, Any]]) -> None:
    """Register each recorded persona sheet (``PlanStamp.personas``) as a phased premise
    (``make_phased_premise``), for the rest of the process: ``run``'s CLI on a bundle and
    ``load_run`` of a run made from one, so ``analyze`` needs no ``plans/``. A name already
    registered with an equal sheet is left alone; another plan's persona of the same name is
    replaced; a strategy of the package of the same name is a ``ValueError`` naming both
    (``_new_plan_sheets``)."""
    for sheet in _new_plan_sheets(personas).values():
        _PLAN_CLASSES.add(make_phased_premise(sheet))


@contextmanager
def recorded_plan_personas(personas: Mapping[str, Mapping[str, Any]]) -> Iterator[None]:
    """The recorded personas registered for the block alone (``run_experiment``'s span; the
    Task 10 carry, R-registry): the rules of ``register_plan_personas``, then the scoped
    ``plan_personas`` over the names not already registered with an equal sheet, so the block
    undoes only what it registered (a replaced plan persona given back), exceptions included."""
    with plan_personas(_new_plan_sheets(personas)):
        yield
