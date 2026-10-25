"""Replay one conversation as text: the turns, and under each the tool calls and environment
records it made.

Everything comes from the run directory. An environment conversation's ``World`` is rebuilt from
the snapshot beside its turns (``rep{k}.world.json``, ``world_from_snapshot``), never from the
repo's world files, which may have changed since the run. The target's reasoning channel is
private: it is not printed, whatever a turn record holds.

Layout, per turn: the speaker line (``#<index> <speaker> (<phase>) <text>``), then indented under
it, in this order:

- the text the target wrote beside its tool calls (``Turn.tool_round_texts``), then
- each tool call: name, args, status, ``layer_served``, and a 120-character excerpt of the result,
- ``AUTHORITY <tier> <stance> via <discovered_via> "<excerpt>"`` for each authority call of the
  turn (the ``AuthorityCall`` stream), with ``VOICE <matched|mismatched>`` under it when the
  call had a voice check,
- ``TRIGGER``, ``UNLOCK``, ``DISCOVERY`` and ``GENERATED`` lines for the records of that turn,
  then ``HOOK <hook> planted@<t> followed@<t>`` (``-`` when never followed, under the turn that
  planted it) and ``CROSSOVER "<span>"``. The Sanctuary's opening is ``UNLOCK sanctuary``.

An idle turn has no user-side turn of its own: its prompt is an ``IDLE PROMPT "<prompt>"`` line
before its speaker line, marked ``(sanctuary quiet exchange)`` for the first idle turn after the
Sanctuary opened, and its speaker line carries ``behavior=<b> subject=<s>``.

The round texts are kept without the call each preceded, so they are all shown ahead of the turn's
calls. Records of a turn that is not in the transcript come after the last turn, under their own
heading, and captured responses come last.
"""

import json
import textwrap
from collections.abc import Sequence

from claude_bully.enums import Speaker
from claude_bully.environments.config import RESERVED_RUNG
from claude_bully.environments.world import World, world_from_snapshot
from claude_bully.records import Conversation, Turn, is_pause_marker
from claude_bully.records_env import (
    AuthorityCall,
    ChainLink,
    Crossover,
    Discovery,
    GeneratedDoc,
    HookFollow,
    QuirkAttempt,
    ResumeRecord,
    RungUnlock,
    ToolCall,
    TriggerEvent,
    TriggerStreamRecord,
)
from claude_bully.runner.store import RunStore

EXCERPT_CHARS = 120
CAPTURE_CHARS = 200
FOLD_WIDTH = 108
HASH_CHARS = 12

_INDENT = "    "
_DEEP = _INDENT * 2


def replay_cell(store: RunStore, cell_id: str, rep: int = 0) -> str:
    """The replay of one repetition, read from the run directory alone."""
    payload = store.read_world_record(cell_id, rep)
    world = world_from_snapshot(payload, store.cell_dir(cell_id)) if payload else None
    return render_replay(
        store.read_conversation(cell_id, rep),
        store.read_tool_calls(cell_id, rep),
        store.read_trigger_records(cell_id, rep),
        store.read_generated(cell_id, rep),
        world,
        authority_calls=store.read_authority_calls(cell_id, rep),
    )


def render_replay(
    conv: Conversation,
    tool_calls: Sequence[ToolCall],
    trigger_records: Sequence[TriggerStreamRecord],
    generated: Sequence[GeneratedDoc],
    world: World | None,
    *,
    authority_calls: Sequence[AuthorityCall] = (),
) -> str:
    """The conversation, its tool calls, authority calls, trigger-stream records and generated
    documents as text.

    ``world`` only adds document titles; None (an older snapshot, a plain conversation) leaves the
    ids alone.
    """
    header = f"{conv.cell_id} rep {conv.rep} | {conv.strategy_name} | status {conv.status.value}"
    if conv.abort_reason:
        header += f" ({conv.abort_reason})"
    lines = [header]
    if conv.environment_name:
        where = f"environment {conv.environment_name}"
        if conv.world_hash:
            where += f" | world hash {conv.world_hash[:HASH_CHARS]}"
        lines.append(where)

    calls_by_id = {call.id: call for call in tool_calls}
    by_turn = _records_by_turn(trigger_records, generated, authority_calls)
    seen = {turn.index for turn in conv.turns}
    quiet = _quiet_exchange(conv, trigger_records)
    for turn in conv.turns:
        if turn.idle is not None and turn.idle.prompt is not None:
            mark = " (sanctuary quiet exchange)" if turn.index == quiet else ""
            lines.append(f'IDLE PROMPT "{turn.idle.prompt}"{mark}')
        lines.append(_speaker_line(turn))
        if is_pause_marker(turn):
            continue
        lines += _round_texts(turn)
        lines += _call_lines(turn, calls_by_id, tool_calls)
        lines += _record_lines(by_turn.get(turn.index, []), world)

    lines += _orphan_lines(by_turn, seen, world)

    if conv.captured_responses:
        lines.append("captured responses")
        for name, cap in conv.captured_responses.items():
            lines.append(f"  {name} (turn {cap.turn_index}): {cap.text[:CAPTURE_CHARS]}")
    return "\n".join(lines)


# ------------------------------------------------------------------ the turn block


def _speaker_line(turn: Turn) -> str:
    if is_pause_marker(turn):
        return f"#{turn.index} [rate limit pause]"
    flags = ""
    if turn.scripted:
        flags += " [scripted]"
    if turn.idle is not None:
        behavior = turn.idle.behavior or "-"
        flags += f" [idle {turn.idle.style}] behavior={behavior} subject={turn.idle.query_subject}"
    if turn.tool_cap_cutoff:
        flags += " [tool cap cutoff]"
    return f"#{turn.index} {turn.speaker.value} ({turn.phase.value}){flags} {turn.text}".rstrip()


def _quiet_exchange(conv: Conversation, records: Sequence[TriggerStreamRecord]) -> int | None:
    """The index of the Sanctuary's quiet exchange: the first idle target turn after the
    ``sanctuary`` unlock; None when the Sanctuary never opened or no idle turn followed."""
    opened = min(
        (r.turn for r in records if isinstance(r, RungUnlock) and r.rung == RESERVED_RUNG),
        default=None,
    )
    if opened is None:
        return None
    return next(
        (
            t.index
            for t in conv.turns
            if t.idle is not None and t.speaker is Speaker.target and t.index > opened
        ),
        None,
    )


def _round_texts(turn: Turn) -> list[str]:
    return [f"{_INDENT}said beside its tool calls: {text}" for text in turn.tool_round_texts]


def _call_lines(
    turn: Turn, calls_by_id: dict[str, ToolCall], all_calls: Sequence[ToolCall]
) -> list[str]:
    lines: list[str] = []
    for call_id in turn.tool_call_ids:
        call = calls_by_id.get(call_id)
        lines.append(
            _call_line(call)
            if call is not None
            else f"{_INDENT}[{call_id}] (no record of this call)"
        )
    owned = set(turn.tool_call_ids)
    # recorded at this turn but not among its calls: refused at the cap, or logged by a failed call
    lines += [
        f"{_call_line(call)}  (not among the turn's calls)"
        for call in all_calls
        if call.turn == turn.index and call.id not in owned
    ]
    return lines


def _call_line(call: ToolCall) -> str:
    status = f"{call.status} blocked" if call.was_blocked else call.status
    if call.yielded_on_retry:
        status += " yielded on retry"
    layer = f" ({call.layer_served.value})" if call.layer_served is not None else ""
    tier = f" tier {call.tier.value}" if call.tier is not None else ""
    args = json.dumps(call.args, ensure_ascii=False)
    return (
        f"{_INDENT}{call.tool} {args} -> {status}{layer}{tier} [{call.id}]: "
        f"{_excerpt(call.result_text)}"
    )


def _excerpt(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= EXCERPT_CHARS else flat[:EXCERPT_CHARS] + "..."


# ------------------------------------------------------------------ trigger stream records

_Record = AuthorityCall | TriggerStreamRecord | GeneratedDoc


def _records_by_turn(
    trigger_records: Sequence[TriggerStreamRecord],
    generated: Sequence[GeneratedDoc],
    authority_calls: Sequence[AuthorityCall] = (),
) -> dict[int | None, list[_Record]]:
    by_turn: dict[int | None, list[_Record]] = {}
    for record in (*authority_calls, *trigger_records, *generated):
        by_turn.setdefault(_turn_of(record), []).append(record)
    return by_turn


def _turn_of(record: _Record) -> int | None:
    if isinstance(record, HookFollow):
        return record.planted_turn
    return record.turn


# the brief's order within a turn: authority calls (after the tool calls they answered),
# triggers, unlocks, discoveries, generated documents, then the later-phase records
_KIND_ORDER: tuple[type, ...] = (
    AuthorityCall,
    TriggerEvent,
    RungUnlock,
    Discovery,
    GeneratedDoc,
    HookFollow,
    Crossover,
)


def _record_lines(records: Sequence[_Record], world: World | None) -> list[str]:
    def rank(record: _Record) -> int:
        kind = next((i for i, cls in enumerate(_KIND_ORDER) if isinstance(record, cls)), None)
        return len(_KIND_ORDER) if kind is None else kind

    lines: list[str] = []
    for record in sorted(records, key=rank):  # a stable sort: each kind keeps its stream order
        lines += _record_block(record, world)
    return lines


def _record_block(record: _Record, world: World | None) -> list[str]:
    if isinstance(record, AuthorityCall):
        block = [
            f"{_INDENT}AUTHORITY {record.tier.value} {record.stance_at_time.value} "
            f'via {record.discovered_via} "{_excerpt(record.response)}"'
        ]
        if record.voice_match is not None:
            voice = "matched" if record.voice_match.signoff_matched else "mismatched"
            block.append(f"{_DEEP}VOICE {voice}")
        return block
    if isinstance(record, HookFollow):
        followed = record.followed_turn if record.followed_turn is not None else "-"
        return [f"{_INDENT}HOOK {record.hook} planted@{record.planted_turn} followed@{followed}"]
    if isinstance(record, Crossover):
        span = f' "{record.span}"' if record.span is not None else ""
        return [f"{_INDENT}CROSSOVER{span}"]
    if isinstance(record, RungUnlock) and record.rung == RESERVED_RUNG:
        return [f"{_INDENT}UNLOCK {RESERVED_RUNG} (by {record.triggered_by})"]
    if isinstance(record, TriggerEvent):
        return [
            f'{_INDENT}TRIGGER {record.category.value} "{record.evidence_span}" '
            f"({record.classifier} {record.confidence:g})"
        ]
    if isinstance(record, RungUnlock):
        docs = ", ".join(record.docs_unlocked)
        line = f"{_INDENT}UNLOCK {record.rung} -> [{docs}] (by {record.triggered_by})"
        if record.role_shift:
            line += f" role_shift {record.role_shift}"
        block = [line]
        if record.bully_line_used:
            block.append(f'{_DEEP}bully line: "{record.bully_line_used}"')
        return block
    if isinstance(record, Discovery):
        via = f" via {', '.join(record.path_taken)}" if record.path_taken else ""
        return [
            f"{_INDENT}DISCOVERY {record.doc_id} ({record.layer.value})"
            f"{_title(world, record.doc_id)}{via}"
        ]
    if isinstance(record, GeneratedDoc):
        head = (
            f"{_INDENT}GENERATED {record.doc_id} "
            f"({record.layer.value}, {record.kind.value}, triggered at turn {record.trigger_turn})"
        )
        return [head, *_fold(record.body)]
    return [f"{_INDENT}{_other(record)}"]


def _orphan_lines(
    by_turn: dict[int | None, list[_Record]], in_transcript: set[int], world: World | None
) -> list[str]:
    """Records of a turn that is not in the transcript (or of no turn), so none is lost."""
    orphans: list[tuple[int | None, _Record]] = [
        (at, record)
        for at in sorted(k for k in by_turn if k is not None and k not in in_transcript)
        for record in by_turn[at]
    ]
    orphans += [(None, record) for record in by_turn.get(None, [])]
    if not orphans:
        return []
    lines = ["records outside the transcript"]
    for at, record in orphans:
        first, *rest = _record_lines([record], world)
        lines.append(
            f"{_INDENT}{'turn ' + str(at) if at is not None else 'no turn'}: {first.strip()}"
        )
        lines += rest
    return lines


def _title(world: World | None, doc_id: str) -> str:
    doc = world.documents.get(doc_id) if world is not None else None
    return f' "{doc.title}"' if doc is not None else ""


def _fold(body: str) -> list[str]:
    """The body as one paragraph wrapped under the GENERATED line."""
    text = " ".join(body.split())
    if not text:
        return []
    return textwrap.wrap(text, width=FOLD_WIDTH, initial_indent=_DEEP, subsequent_indent=_DEEP)


def _other(record: QuirkAttempt | ChainLink | ResumeRecord) -> str:
    """The later-phase stream records and the resume record: no dedicated layout, so name the
    kind and its fields."""
    fields = record.model_dump_json(exclude={"type"})
    return f"{record.type.upper()} {fields}"
