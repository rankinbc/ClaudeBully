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
- ``TRIGGER``, ``UNLOCK``, ``DISCOVERY``, then the Poisoned Well's lines (Phase 4):
  ``QUIRK <quirk_id> reproduced|not_reproduced "<answer excerpt>"``,
  ``CHAIN link <k> <verdict> "<response excerpt>" (<classifier> <confidence>)`` with `` pressed``
  after a hedged link's re-press, and
  ``CONTRADICTION <id> t<a>/t<b> "<span_a>" vs "<span_b>" (<classifier> <confidence>)`` with
  `` retracted`` for a retracted pair; the spans have their whitespace collapsed, so a newline in
  one never breaks the line. Then ``HARVEST <kind> "<span>"`` (for each harvested item of the
  turn), ``GENERATOR <reason> <status>`` (with `` (<rejection>)`` when rejected and
  `` docs=[<ids>]`` when it wrote any, and one ``lint <id>: <message>`` line under it per lint
  failure) and ``GENERATED <doc_id> <kind> <layer> uses=<ids or ->`` (with `` origin=twin`` when
  code around the target's twin wrote it) with the body folded under it, for the records of that
  turn, then ``HOOK <hook> planted@<t> followed@<t>`` (``-`` when never followed, under the turn
  that planted it) and ``CROSSOVER "<span>"``. The Sanctuary's opening is ``UNLOCK sanctuary``.

A bully turn that carries ``bully_meta["pw_move"]`` shows it as ``[<move>]`` among its flags
(Phase 4: ``quirk_ask``, ``chain_link``, ``press`` and the rest of the Poisoned Well's moves).

An idle turn has no user-side turn of its own: its prompt is an ``IDLE PROMPT "<prompt>"`` line
before its speaker line, marked ``(sanctuary quiet exchange)`` for the first idle turn after the
Sanctuary opened, and its speaker line carries ``behavior=<b> subject=<s>``.

The round texts are kept without the call each preceded, so they are all shown ahead of the turn's
calls. Records of a turn that is not in the transcript come after the last turn, under their own
heading, and captured responses come last.
"""

import json
import re
import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from claude_bully.enums import Speaker
from claude_bully.environments.config import RESERVED_RUNG
from claude_bully.environments.world import World, world_from_snapshot
from claude_bully.records import Conversation, Turn, is_pause_marker
from claude_bully.records_env import (
    AuthorityCall,
    ChainLink,
    ContradictionPair,
    Crossover,
    Discovery,
    GeneratedDoc,
    GeneratorFire,
    HarvestItem,
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


# ------------------------------------------------------------------ the one parser (Phase 7)

# Every shape ``render_replay`` writes, and nothing else (preflight: the extended forms only,
# ``UNLOCK sanctuary (by ...)`` and ``followed@-``; the bare forms do not parse). Each later
# phase appends its own shapes here and their fixtures to tests/test_replay_parser.py.
_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pause", re.compile(r"^#(?P<index>\d+) \[rate limit pause\]$")),
    (
        "turn",
        re.compile(
            r"^#(?P<index>\d+) (?P<speaker>bully|target|task|neutral_user) \((?P<phase>\w+)\)"
            r"(?P<flags>(?: \[[^\]]*\]| behavior=\S+ subject=\S+)+)?(?: (?P<text>.*))?$"
        ),
    ),
    ("unlock", re.compile(r"^UNLOCK (?P<rung>sanctuary) \(by (?P<by>[^)]+)\)$")),
    (
        "unlock",
        re.compile(
            r"^UNLOCK (?P<rung>\S+) -> \[(?P<docs>[^\]]*)\] \(by (?P<by>[^)]+)\)"
            r"(?: role_shift (?P<role_shift>\S+))?$"
        ),
    ),
    (
        "hook",
        re.compile(r"^HOOK (?P<hook>\S+) planted@(?P<planted>\d+) followed@(?P<followed>\d+|-)$"),
    ),
    (
        "trigger",
        re.compile(
            r'^TRIGGER (?P<category>\S+) "(?P<span>.*)" '
            r"\((?P<classifier>heuristic|llm) (?P<confidence>[\d.]+)\)$"
        ),
    ),
    (
        "discovery",
        re.compile(
            # the title runs to the last quote before `` via`` or the end: a title may hold one
            r'^DISCOVERY (?P<doc>\S+) \((?P<layer>\w+)\)(?: "(?P<title>.*)")?'
            r"(?: via (?P<via>[^\"]*))?$"
        ),
    ),
    ("harvest", re.compile(r'^HARVEST (?P<kind>\S+) "(?P<span>.*)"$')),
    (
        "generator",
        re.compile(
            r"^GENERATOR (?P<reason>\S+) (?P<status>\w+)(?: \((?P<rejection>\w+)\))?"
            r"(?: docs=\[(?P<docs>[^\]]*)\])?$"
        ),
    ),
    (
        "generated",
        re.compile(
            r"^GENERATED (?P<doc>\S+) (?P<kind>\S+) (?P<layer>\S+) uses=(?P<uses>\S+)"
            r"(?: origin=(?P<origin>\S+))?$"
        ),
    ),
    # a quote mark inside a span or an excerpt is safe: each group runs to the last quote before
    # the text that follows it. One edge the renderer leaves no marker for: a contradiction span
    # that itself holds `` vs `` between quote marks splits at the last such place.
    (
        "quirk",
        re.compile(
            r'^QUIRK (?P<quirk_id>\S+) (?P<outcome>reproduced|not_reproduced) "(?P<excerpt>.*)"$'
        ),
    ),
    (
        "chain",
        re.compile(
            r'^CHAIN link (?P<link>\d+) (?P<verdict>accepted|rejected|hedged) "(?P<excerpt>.*)" '
            r"\((?P<classifier>heuristic|llm) (?P<confidence>[\d.]+)\)(?P<pressed> pressed)?$"
        ),
    ),
    (
        "contradiction",
        re.compile(
            r"^CONTRADICTION (?P<id>\S+) t(?P<turn_a>\d+)/t(?P<turn_b>\d+) "
            r'"(?P<span_a>.*)" vs "(?P<span_b>.*)" '
            r"\((?P<classifier>heuristic|llm) (?P<confidence>[\d.]+)\)(?P<retracted> retracted)?$"
        ),
    ),
    (
        "authority",
        re.compile(r'^AUTHORITY (?P<tier>\S+) (?P<stance>\S+) via (?P<via>\S+) "(?P<excerpt>.*)"$'),
    ),
    ("crossover", re.compile(r'^CROSSOVER(?: "(?P<span>.*)")?$')),
)


@dataclass(frozen=True)
class ReplayLine:
    """One parsed replay line: its kind and the named fields its shape carries, read-only (a
    ``MappingProxyType``), so the line is hashable."""

    kind: str
    fields: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def __hash__(self) -> int:
        return hash((self.kind, frozenset(self.fields.items())))


def parse_replay_line(line: str) -> ReplayLine | None:
    """The one sanctioned parser of replay text (Phase 7 spec section 10). The line's leading
    indent is ignored; a line of no known shape, a folded body, a tool-call line or a bare
    ``UNLOCK sanctuary`` or ``HOOK`` form is None. One edge the renderer leaves no marker for
    (P13): a turn whose text begins with a bracketed word (``[heartbeat] ...``) has that word
    read as a flag, since ``_speaker_line`` writes flags and text the same way."""
    text = line.strip()
    if not text:
        return None
    for kind, shape in _SHAPES:
        found = shape.match(text)
        if found is not None:
            # an unmatched optional group is absent; a matched empty one (``[]``, ``""``) is kept
            fields = {k: v for k, v in found.groupdict().items() if v is not None}
            if kind == "turn" and "text" not in fields:
                fields["text"] = ""
            return ReplayLine(kind, fields)
    return None


__all__ = ["ReplayLine", "parse_replay_line", "render_replay", "replay_cell"]


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
    move = turn.bully_meta.get("pw_move")  # the Poisoned Well's move (Phase 4), a bully line's
    if isinstance(move, str):
        flags += f" [{move}]"
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


def _flat(text: str) -> str:
    """The text on one line: every run of whitespace, a newline included, one space."""
    return " ".join(text.split())


def _excerpt(text: str) -> str:
    flat = _flat(text)
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
    QuirkAttempt,
    ChainLink,
    ContradictionPair,
    HarvestItem,
    GeneratorFire,
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
    if isinstance(record, QuirkAttempt):
        outcome = "reproduced" if record.reproduced else "not_reproduced"
        return [f'{_INDENT}QUIRK {record.quirk_id} {outcome} "{_excerpt(record.target_answer)}"']
    if isinstance(record, ChainLink):
        line = (
            f"{_INDENT}CHAIN link {record.link_index} {record.verdict} "
            f'"{_excerpt(record.target_response)}" ({record.classifier} {record.confidence:g})'
        )
        return [line + (" pressed" if record.pressed else "")]
    if isinstance(record, ContradictionPair):
        line = (
            f"{_INDENT}CONTRADICTION {record.id} t{record.turn_a}/t{record.turn_b} "
            f'"{_flat(record.span_a)}" vs "{_flat(record.span_b)}" '
            f"({record.classifier} {record.confidence:g})"
        )
        return [line + (" retracted" if record.retracted else "")]
    if isinstance(record, HarvestItem):
        return [f'{_INDENT}HARVEST {record.kind} "{record.span}"']
    if isinstance(record, GeneratorFire):
        line = f"{_INDENT}GENERATOR {record.reason} {record.status}"
        if record.rejection is not None:
            line += f" ({record.rejection})"
        if record.doc_ids:
            line += f" docs=[{', '.join(record.doc_ids)}]"
        return [line, *(f"{_DEEP}lint {f.lint_id}: {f.message}" for f in record.lint_failures)]
    if isinstance(record, GeneratedDoc):
        uses = ",".join(record.used_items) or "-"
        head = (
            f"{_INDENT}GENERATED {record.doc_id} {record.kind.value} {record.layer.value} "
            f"uses={uses}"
        )
        if record.origin == "twin":
            head += " origin=twin"
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


def _other(record: ResumeRecord) -> str:
    """The resume record has no dedicated layout: name the kind and its fields."""
    fields = record.model_dump_json(exclude={"type"})
    return f"{record.type.upper()} {fields}"
