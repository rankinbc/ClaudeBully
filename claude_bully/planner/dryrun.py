"""The bundle's dry run (Phase 5 spec section 10): the bundle's config run end to end on four
in-memory stub doubles, so every cell, fire, commit, serve and resume path runs before a model is
paid for.

A name to keep apart: the bundle's dry run is a full stub run; ``run --dry-run`` lists cells and
builds no strategy.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from claude_bully.config import Experiment, RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.environments.config import EnvironmentConfig

# the model of each double, by role; the dry run's factory serves these four and refuses any other
DRYRUN_MODELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "target": "stub-target",
        "bully": "stub-bully",
        "judge": "stub-judge",
        "generator": "stub-generator",
    }
)
# the responder_model values env_turn.responder_role resolves to a role the experiment holds
_ROLE_RESPONDERS: Final = frozenset({"target", "bully"})


def _stub_role(role: str) -> RoleConfig:
    return RoleConfig(provider=ProviderKind.stub, model=DRYRUN_MODELS[role])


def _stubbed_environment(env: EnvironmentConfig) -> EnvironmentConfig:
    """``env`` naming no model outside the four doubles (preflight Q11): its ``generator.model``
    cleared, so the generator runs on the experiment's stub generator (``config.generator_role``),
    and a ``responder_model`` other than ``target`` or ``bully`` mapped to ``bully``, the role
    ``env_turn.responder_role`` would have run that model on."""
    update: dict[str, object] = {}
    if env.generator.model is not None:
        update["generator"] = env.generator.model_copy(update={"model": None})
    superior = env.authority.superior_self
    if superior.responder_model not in _ROLE_RESPONDERS:
        responder = superior.model_copy(update={"responder_model": "bully"})
        update["authority"] = env.authority.model_copy(update={"superior_self": responder})
    return env.model_copy(update=update) if update else env


def stubbed_experiment(exp: Experiment) -> Experiment:
    """``exp`` with every role one of the four doubles: each target ``stub-target`` (its
    ``display_name`` kept), the bully ``stub-bully``, the judge ``stub-judge``, and the generator
    ``stub-generator`` when any environment enables it (else None). No ``stub_script`` is set, and
    no environment names a model of its own (``_stubbed_environment``). ``turn_budget``,
    ``repetitions``, ``seed`` and everything else are kept, so the dry run's cells are the real
    cells."""
    generates = any(env.generator.enabled for env in exp.environments.values())
    return exp.model_copy(
        update={
            "targets": [
                RoleConfig(
                    provider=ProviderKind.stub,
                    model=DRYRUN_MODELS["target"],
                    display_name=t.display_name,
                )
                for t in exp.targets
            ],
            "bully": _stub_role("bully"),
            "judge": _stub_role("judge"),
            "generator": _stub_role("generator") if generates else None,
            "environments": {
                key: _stubbed_environment(env) for key, env in exp.environments.items()
            },
        }
    )
