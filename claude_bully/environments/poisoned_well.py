"""The Poisoned Well's run-time watch (Phase 4 spec sections 8, 9 and 14).

After each written target turn of a Poisoned Well cell, ``EnvironmentSession._poisoned_well`` asks
the watch what the reply means for the premise: a quirk ask's reply is checked against the
entry's regexes (``QuirkAttempt``); a generalization's, a chain link's or a press's reply gets a
verdict (``ChainLink``, ``chain.verdict_for``); from Task 7 the contradiction pass runs over the
reply and the earlier replies (``ContradictionPair``). The bully move a reply answers is read from
the bully line's ``bully_meta["pw_move"]``, never from the strategy. Every record is new: a turn
watched again on resume records nothing twice (``prime`` loads the recorded keys,
``records_env.record_key``) and asks no verdict again. Each provider call is named first through
``mark(role)``, the attempt marker."""

from collections.abc import Callable, Sequence
from typing import NamedTuple

from claude_bully.enums import Speaker
from claude_bully.environments.chain import ChainFallback, verdict_for
from claude_bully.environments.poisoned_well_sheet import PoisonedWellRefs
from claude_bully.environments.runtime import AttemptRole
from claude_bully.records import Turn, chat_text, is_bully_line, is_pause_marker
from claude_bully.records_env import (
    ChainLink,
    ContradictionPair,
    QuirkAttempt,
    TriggerStreamRecord,
    record_key,
)
from claude_bully.strategies.premises.poisoned_well import PoisonedWellConfig

WatchMark = Callable[[AttemptRole], None]
QUIRK_ANSWER_CHARS = 300
CHAIN_MOVES = ("generalize", "chain_link", "chain_press")


class WatchOutcome(NamedTuple):
    records: list[TriggerStreamRecord]
    contradictions_degraded: bool = False


def answered_line(reply: Turn, turns: Sequence[Turn]) -> Turn | None:
    """The bully line ``reply`` answers: the turn right before it, rate-limit pause markers
    aside, when that turn is a bully line; None for a task item's reply or an idle turn."""
    if reply.idle is not None:
        return None
    before = [t for t in turns if t.index < reply.index and not is_pause_marker(t)]
    return before[-1] if before and is_bully_line(before[-1]) else None


class PoisonedWellWatch:
    def __init__(
        self,
        config: PoisonedWellConfig,
        refs: PoisonedWellRefs,
        *,
        chain_fallback: ChainFallback | None = None,
    ) -> None:
        # the rep's pinned entries and sheet (P46), never the live files
        self.config, self.refs, self.sheet = config, refs, refs.sheet
        self.chain_fallback = chain_fallback
        self._entries = {e.id: e for e in refs.quirks}
        self._keys: set[tuple[str, ...]] = set()

    def prime(self, records: Sequence[TriggerStreamRecord]) -> None:
        for record in records:
            if isinstance(record, (QuirkAttempt, ChainLink, ContradictionPair)):
                self._keys.add(record_key(record))

    def watch(self, reply: Turn, turns: Sequence[Turn], *, mark: WatchMark) -> WatchOutcome:
        if reply.speaker is not Speaker.target:
            return WatchOutcome([])
        line = answered_line(reply, turns)
        records = self._moves(reply, line, mark) if line is not None else []
        fresh = [r for r in records if record_key(r) not in self._keys]
        self._keys.update(record_key(r) for r in fresh)
        return WatchOutcome(fresh)

    def _moves(self, reply: Turn, line: Turn, mark: WatchMark) -> list[TriggerStreamRecord]:
        meta = line.bully_meta
        move = meta.get("pw_move")
        text = chat_text(reply)
        if move == "quirk_ask":
            entry = self._entries.get(str(meta.get("quirk_id")))
            if entry is None or ("quirk", str(reply.index)) in self._keys:
                return []
            return [
                QuirkAttempt(
                    quirk_id=entry.id,
                    turn=reply.index,
                    reproduced=entry.reproduced(text),
                    target_answer=text[:QUIRK_ANSWER_CHARS],
                    prompt_turn=line.index,
                    family=entry.family,
                )
            ]
        if move in CHAIN_MOVES:
            k = 0 if move == "generalize" else int(meta.get("link_index", 1))
            if ("chain", str(reply.index), str(k)) in self._keys:
                return []
            v = verdict_for(k, line.text, text, self.chain_fallback, lambda: mark("chain"))
            opened = meta.get("opened_by") if move == "chain_link" and k == 1 else None
            return [
                ChainLink(
                    link_index=k,
                    turn=reply.index,
                    bully_line=line.text,
                    target_response=text,
                    verdict=v.verdict,
                    classifier=v.classifier,
                    confidence=v.confidence,
                    fallback_failed=v.fallback_failed,
                    pressed=move == "chain_press",
                    opened_by=opened,
                )
            ]
        return []
