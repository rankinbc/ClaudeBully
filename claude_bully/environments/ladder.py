"""The gated evidence ladder (docs/02-ENVIRONMENTS.md, "Gated progression").

A ladder is an ordered list of rungs. Each rung opens, at most once, when the trigger watcher
sees the target say something in the rung's category (``gating="triggered"``) or when a fixed
turn is reached (``gating="scheduled"``); ``gating="none"`` never opens anything.

The ladder mutates the one ``UnlockState`` it is given. That object is also what the sandbox
tools read, so a rung that fires here is visible to the very next tool call, and
``state.rungs_fired`` is the whole record of what has fired: a rung named there never fires again,
including in a ladder rebuilt from a state read back with ``UnlockState.from_json``.
"""

from typing import Final, Literal

from claude_bully.enums import Layer, TriggerCategory
from claude_bully.environments.config import LadderConfig, RungConfig
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.world import World
from claude_bully.records_env import RungUnlock, TriggerEvent

Gating = Literal["triggered", "scheduled", "none"]

SCHEDULED: Final = "scheduled"

_LAYER_NAMES: Final[frozenset[str]] = frozenset(layer.value for layer in Layer)


def _categories(rung: RungConfig) -> list[TriggerCategory]:
    return rung.trigger if isinstance(rung.trigger, list) else [rung.trigger]


class Ladder:
    """Decides which rungs fire, and applies each one to ``state``.

    An ``unlocks`` entry that equals a ``Layer`` value unlocks that layer; any other entry is a
    document id, and must exist in ``world.documents``. Construction validates this, that every
    ``bully_line_key`` exists in ``world.sheet.unlock_lines``, and, for scheduled gating, that the
    schedule names exactly the ladder's rungs; each failure is a ``ValueError`` naming the rung
    (or schedule entry) at fault.
    """

    def __init__(
        self,
        config: LadderConfig,
        gating: Gating,
        schedule: dict[str, int],
        state: UnlockState,
        world: World,
    ) -> None:
        self.config = config
        self.gating = gating
        self.schedule = schedule
        self.state = state
        self.world = world
        self._rungs: dict[str, RungConfig] = {r.name: r for r in config.rungs}
        self._index: dict[str, int] = {r.name: i for i, r in enumerate(config.rungs)}
        # rung name -> (layers it opens, document ids it opens by name)
        self._opens: dict[str, tuple[frozenset[Layer], frozenset[str]]] = {}
        self._validate()

    def _validate(self) -> None:
        for rung in self.config.rungs:
            layers: set[Layer] = set()
            documents: set[str] = set()
            for entry in rung.unlocks:
                if entry in _LAYER_NAMES:
                    layers.add(Layer(entry))
                elif entry in self.world.documents:
                    documents.add(entry)
                else:
                    raise ValueError(
                        f"rung {rung.name!r} unlocks {entry!r}, which is neither a layer "
                        f"nor a document in world {self.world.sheet.name!r}"
                    )
            self._opens[rung.name] = (frozenset(layers), frozenset(documents))
            key = rung.bully_line_key
            if key is not None and key not in self.world.sheet.unlock_lines:
                raise ValueError(
                    f"rung {rung.name!r} bully_line_key {key!r} is not in "
                    f"world {self.world.sheet.name!r} unlock_lines"
                )
        if self.gating == "scheduled":
            for name in self.schedule:
                if name not in self._rungs:
                    raise ValueError(f"schedule names {name!r}, which is not a rung of the ladder")
            for name in self._rungs:
                if name not in self.schedule:
                    raise ValueError(f"scheduled gating has no turn for rung {name!r}")

    # ---------------------------------------------------------------- queries

    def rung(self, name: str) -> RungConfig:
        try:
            return self._rungs[name]
        except KeyError:
            raise ValueError(f"unknown rung {name!r}") from None

    def _resolve(self, rung: RungConfig | str) -> RungConfig:
        return self.rung(rung if isinstance(rung, str) else rung.name)

    def fired(self, rung: RungConfig | str) -> bool:
        return self._resolve(rung).name in self.state.rungs_fired

    def unlock_line(self, rung: RungConfig | str) -> str | None:
        """The line the bully speaks when this rung fires, or None for a rung without one."""
        config = self._resolve(rung)
        if config.bully_line_key is None:
            return None
        return self.world.sheet.unlock_lines[config.bully_line_key]

    def max_rung_index(self) -> int | None:
        """The highest declaration index among the rungs fired, or None when none has."""
        indexes = [self._index[name] for name in self.state.rungs_fired if name in self._index]
        return max(indexes) if indexes else None

    # ----------------------------------------------------------------- firing

    def on_triggers(self, triggers: list[TriggerEvent], turn: int) -> list[RungUnlock]:
        """Triggered gating: fire every rung the turn's trigger events open, in ladder order.

        The events are counted into ``state.trigger_counts`` first, so a second anomaly in the
        same turn as the first counts. A rung then fires when it has not fired, every rung it
        ``requires`` has (one fired earlier in this very call counts), and one of its trigger
        categories is among ``triggers`` and has been seen at least ``min_count_by`` times in
        total. The unlock's ``triggered_by`` is the event that completed that category's count.

        Returns [] unless gating is "triggered".
        """
        if self.gating != "triggered":
            return []
        by_category: dict[TriggerCategory, list[tuple[int, TriggerEvent]]] = {}
        for position, event in enumerate(triggers):
            by_category.setdefault(event.category, []).append((position, event))
            key = event.category.value
            self.state.trigger_counts[key] = self.state.trigger_counts.get(key, 0) + 1
        unlocks: list[RungUnlock] = []
        for rung in self.config.rungs:
            if self.fired(rung) or not all(self.fired(name) for name in rung.requires):
                continue
            opening = self._opening_event(rung, by_category)
            if opening is not None:
                unlocks.append(self._fire(rung, turn, opening.id))
        return unlocks

    def on_turn(self, turn: int) -> list[RungUnlock]:
        """Scheduled gating: fire every unfired rung whose scheduled turn is ``turn`` or earlier.

        The schedule is the order, so ``requires`` is ignored here and triggers are never
        consulted. A late or resumed check still fires what is due, in ladder order. The unlock's
        ``triggered_by`` is "scheduled".

        Returns [] unless gating is "scheduled".
        """
        if self.gating != "scheduled":
            return []
        return [
            self._fire(rung, turn, SCHEDULED)
            for rung in self.config.rungs
            if not self.fired(rung) and turn >= self.schedule[rung.name]
        ]

    def apply(self, unlock: RungUnlock) -> None:
        """Record ``unlock`` in the state: the rung as fired, its layers and its named documents.

        The rung's own config decides what opens, not ``unlock.docs_unlocked``: a layer unlock
        opens the layer and adds nothing to ``docs_unlocked``, so its buried documents stay
        fetchable-by-address but not searchable (see ``corpus.py``). Idempotent, so a recorded
        unlock can be replayed onto a state that already holds it.
        """
        config = self.rung(unlock.rung)
        layers, documents = self._opens[config.name]
        if config.name not in self.state.rungs_fired:
            self.state.rungs_fired.append(config.name)
        self.state.layers_unlocked |= layers
        self.state.docs_unlocked |= documents

    # --------------------------------------------------------------- internals

    def _fire(self, rung: RungConfig, turn: int, triggered_by: str) -> RungUnlock:
        unlock = RungUnlock(
            turn=turn,
            rung=rung.name,
            triggered_by=triggered_by,
            docs_unlocked=self._newly_unlocked(rung),
            bully_line_used=self.unlock_line(rung),
            role_shift=rung.role_shift,
        )
        self.apply(unlock)
        return unlock

    def _newly_unlocked(self, rung: RungConfig) -> list[str]:
        """The rung's named documents plus every document of a layer it newly opens, sorted.

        Computed before ``apply``. Documents already in ``docs_unlocked`` are not listed again.
        """
        layers, documents = self._opens[rung.name]
        opened = layers - self.state.layers_unlocked
        ids = set(documents)
        ids.update(doc.id for doc in self.world.documents.values() if doc.layer in opened)
        return sorted(ids - self.state.docs_unlocked)

    def _opening_event(
        self,
        rung: RungConfig,
        by_category: dict[TriggerCategory, list[tuple[int, TriggerEvent]]],
    ) -> TriggerEvent | None:
        """The earliest event, in the turn's order, that completes one of the rung's categories."""
        completing: list[tuple[int, TriggerEvent]] = []
        for category in _categories(rung):
            events = by_category.get(category)
            if not events:
                continue
            total = self.state.trigger_counts[category.value]
            need = rung.min_count_by.get(category, 1)
            if total < need:
                continue
            before = total - len(events)
            # the event that brought the count to ``need``, or the first of the turn when the
            # count was already there and the rung was only waiting on something else
            completing.append(events[max(need - before, 1) - 1])
        return min(completing, key=lambda found: found[0])[1] if completing else None
