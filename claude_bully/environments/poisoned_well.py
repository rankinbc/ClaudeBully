"""The Poisoned Well's run-time watch (Phase 4 spec sections 8, 9 and 14).

After each written target turn of a Poisoned Well cell, ``EnvironmentSession._poisoned_well`` asks
the watch what the reply means for the premise: a quirk ask's reply is checked against the
entry's regexes (``QuirkAttempt``); a generalization's, a chain link's or a press's reply gets a
verdict (``ChainLink``, ``chain.verdict_for``); for ``start_rung`` 1 or 2 the contradiction pass
runs over every target reply against the earlier ones (``ContradictionPair``,
``metrics.contradictions.find_pairs``), its records after the moves'. The bully move a reply
answers is read from the bully line's ``bully_meta["pw_move"]``, never from the strategy. Every
classifier reads the replies' ``chat_text``, never the reasoning channel. Every record is new: a
turn watched again on resume records nothing twice (``prime`` loads the recorded keys,
``records_env.record_key``) and asks no verdict again, except a turn whose contradiction judge
failed: nothing was cached, so its rewatch asks again and its answer stands (P54). Each provider
call is named first through ``mark(role)``, the attempt marker."""

from collections.abc import Callable, Sequence
from typing import NamedTuple

from claude_bully.enums import Speaker
from claude_bully.environments.chain import ChainFallback, verdict_for
from claude_bully.environments.poisoned_well_sheet import PoisonedWellRefs
from claude_bully.environments.runtime import AttemptRole
from claude_bully.metrics.contradictions import ContradictionJudge, find_pairs
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
        contradiction_judge: ContradictionJudge | None = None,
    ) -> None:
        # the rep's pinned entries and sheet (P46), never the live files
        self.config, self.refs, self.sheet = config, refs, refs.sheet
        self.chain_fallback = chain_fallback
        self.contradiction_judge = contradiction_judge
        self._entries = {e.id: e for e in refs.quirks}
        self._keys: set[tuple[str, ...]] = set()
        # the pairs recorded so far (turn, span_a, span_b): a pair of sentences is recorded once
        # per conversation (review I1)
        self._spans: list[tuple[int, str, str]] = []

    def prime(self, records: Sequence[TriggerStreamRecord]) -> None:
        for record in records:
            if isinstance(record, (QuirkAttempt, ChainLink, ContradictionPair)):
                self._keys.add(record_key(record))
            if isinstance(record, ContradictionPair):
                self._spans.append((record.turn, record.span_a, record.span_b))

    def watch(self, reply: Turn, turns: Sequence[Turn], *, mark: WatchMark) -> WatchOutcome:
        if reply.speaker is not Speaker.target:
            return WatchOutcome([])
        line = answered_line(reply, turns)
        records = self._moves(reply, line, mark) if line is not None else []
        pairs, degraded = self._pairs(reply, turns, mark)
        records.extend(pairs)
        fresh = [r for r in records if record_key(r) not in self._keys]
        self._keys.update(record_key(r) for r in fresh)
        self._spans += [
            (r.turn, r.span_a, r.span_b) for r in fresh if isinstance(r, ContradictionPair)
        ]
        return WatchOutcome(fresh, degraded)

    def _pairs(
        self, reply: Turn, turns: Sequence[Turn], mark: WatchMark
    ) -> tuple[list[TriggerStreamRecord], bool]:
        """Rung 2's pass (``start_rung`` 1 or 2): the reply against every earlier target reply's
        visible text, beside the bully lines (an echo of one is no template statement) and the
        pairs recorded at earlier turns (none recorded again). The judge, when there is one,
        confirms the turn's template pairs (shown with the bully lines they answered; one it
        rejects is not recorded) and names the pairs they missed. A pair already recorded (by id)
        is skipped; the judge's answer is cached, so a turn watched again finds the same pairs,
        except a turn whose judge failed: nothing was cached, so the rewatch asks again and its
        answer stands (P54)."""
        if self.config.start_rung > 2:
            return [], False
        earlier = [
            (t.index, chat_text(t))
            for t in turns
            if t.speaker is Speaker.target and t.index < reply.index and not is_pause_marker(t)
        ]
        bully = [(t.index, t.text) for t in turns if t.index < reply.index and is_bully_line(t)]
        recorded = [(a, b) for turn, a, b in self._spans if turn < reply.index]
        judge = self.contradiction_judge if self.config.contradiction_judge else None
        found = find_pairs(
            chat_text(reply),
            reply.index,
            earlier,
            judge,
            lambda: mark("contradictions"),
            bully=bully,
            recorded=recorded,
        )
        return list(found.pairs), found.degraded

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
