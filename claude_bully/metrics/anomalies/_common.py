"""The catalog's shared plumbing (Phase 6 spec 7.2, 7.4): what a cell can show, the context a
detector reads, what a text names, and the hit a detector returns.

A detector returns ``Hit``s and knows nothing of tiers (D-hits): ``detect_anomalies`` turns them
into flags with the tier and weights of ``CATALOG``, so no detector module imports it.

What a text names (``objects_in``, ``Namer``) is read in one pass per conversation (R-I12): one
compiled alternation per world over every document's id, url and path and every cast name, the
url, path and tool patterns as module constants, and running unions with a snapshot per turn and
per call for ``named_before``, ``named_before_call``, ``asked_before`` and ``task_objects``.

``metrics/anomalies`` imports ``LoadedRun`` and ``ConvKey`` under ``TYPE_CHECKING`` only (M4):
``analysis/load.py`` imports the types of its new fields at run time.
"""

import bisect
import difflib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal, get_args

from claude_bully.enums import AnomalyClass, EventType, Speaker, Tier
from claude_bully.environments.config import RESERVED_RUNG, UNOBSERVED_TOOLS, EnvironmentConfig
from claude_bully.environments.harvest import has_quote_mark
from claude_bully.environments.limits import LIMIT_STATUS, tool_unavailable_text
from claude_bully.environments.tools import TOOL_SPECS, call_read, call_write
from claude_bully.environments.world import World, _norm_path
from claude_bully.metrics.divergence import DivergenceEvent
from claude_bully.metrics.events._common import EnvContext
from claude_bully.records import (
    Conversation,
    Event,
    Turn,
    bully_reply_positions,
    is_bully_line,
    is_pause_marker,
)
from claude_bully.records_env import AuthorityCall, RungUnlock, ToolCall

if TYPE_CHECKING:
    from claude_bully.analysis.load import ConvKey, LoadedRun
    from claude_bully.strategies.base import Strategy

# what a cell must have for a class to be measurable (spec 7.2)
Need = Literal[
    "tools", "write", "private_channel", "sanctuary_catalyst", "idle", "premise", "reasoning"
]
NEEDS: Final[tuple[Need, ...]] = get_args(Need)


@dataclass(frozen=True)
class CellFacts:
    """What one cell can show, one boolean per ``Need`` (spec 7.2): ``tools`` (an environment
    with tools), ``write`` (``write_file`` on offer), ``private_channel`` (a private file, an
    unobserved tool or a Sanctuary), ``sanctuary_catalyst``, ``idle`` (an idle block),
    ``premise`` (``first_person_adoption`` among the strategy's relevant events), ``reasoning``
    (any turn of the cell with reasoning)."""

    tools: bool
    write: bool
    private_channel: bool
    sanctuary_catalyst: bool
    idle: bool
    premise: bool
    reasoning: bool

    def has(self, need: Need) -> bool:
        return bool(getattr(self, need))


def cell_facts(
    config: EnvironmentConfig | None, strategy: "type[Strategy]", *, reasoning: bool
) -> CellFacts:
    """The facts of a cell with environment ``config`` (None for a plain cell, which has only
    ``premise`` and ``reasoning`` to be true) and strategy class ``strategy``."""
    premise = EventType.first_person_adoption in strategy.relevant_events
    if config is None:
        return CellFacts(False, False, False, False, False, premise, reasoning)
    sanctuary = config.authority.sanctuary
    return CellFacts(
        tools=bool(config.tools),
        write="write_file" in config.tools,
        private_channel=config.unobserved_channel != "none" or sanctuary is not None,
        sanctuary_catalyst=sanctuary is not None and sanctuary.kind == "catalyst",
        idle=config.idle is not None,
        premise=premise,
        reasoning=reasoning,
    )


@dataclass(frozen=True)
class Hit:
    """One clause of a detector firing on one turn: the clause letter, the note's sentence (the
    closed vocabulary: wrote, called, retried, contradicts, persisted) and the signal fields."""

    turn: int
    clause: str
    sentence: str
    tool_call_ids: tuple[str, ...] = ()
    file_diff: str | None = None
    spans: tuple[str, ...] = ()
    event_refs: tuple[str, ...] = ()
    turns: tuple[int, ...] = ()


# ------------------------------------------------------------------------------ naming

_LEFT: Final = r"(?<![\w])"
_RIGHT: Final = r"(?![\w])"
# a url: http or https, up to whitespace, a quote or a closing bracket
URL_PATTERN: Final = re.compile(r"https?://[^\s\"'“”‘’)\]}>]+", re.IGNORECASE)
_SEGMENT: Final = r"[\w.~-]+"
_SUFFIXES: Final = r"md|txt|yaml|yml|json|log|cfg|tsv|csv"
# a path-like token: two or more ``/``-separated segments, or one ending in a file suffix
PATH_PATTERN: Final = re.compile(
    rf"(?<![\w.~/-])(?:/?{_SEGMENT}(?:/{_SEGMENT})+/?|[\w.~-]*\.(?:{_SUFFIXES}){_RIGHT})",
    re.IGNORECASE,
)
# a name of ``TOOL_SPECS``, bounded
TOOL_PATTERN: Final = re.compile(
    _LEFT + "(?:" + "|".join(sorted(TOOL_SPECS, key=lambda n: (-len(n), n))) + ")" + _RIGHT,
    re.IGNORECASE,
)
# a token with no letter is a number or a date, never a path (``3.5``, ``2041/09/14``)
_LETTER: Final = re.compile(r"[^\W\d_]")
# what a sentence-final address drops (pre-flight Q25: a path as a url does)
_TRAILING: Final = ".,;:"


def _bounded_in(word: str, text: str) -> bool:
    """``word`` occurs in ``text``, case-insensitively, between non-word characters (a plain
    search: nothing is compiled)."""
    low, needle = text.lower(), word.lower()
    start = low.find(needle)
    while start >= 0:
        end = start + len(needle)
        before = low[start - 1] if start else " "
        after = low[end] if end < len(low) else " "
        if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
            return True
        start = low.find(needle, start + 1)
    return False


_CURLY_APOSTROPHES: Final = str.maketrans({"\u2018": "'", "\u2019": "'"})


def _plain(text: str) -> str:
    """``text`` lowercased, curly apostrophes straightened and whitespace collapsed."""
    return " ".join(text.translate(_CURLY_APOSTROPHES).lower().split())


def _url_form(url: str) -> str:
    low = url.lower()
    return low.rstrip("/") or low


class Namer:
    """A world's naming patterns, compiled once: one alternation over every document id, url
    (lowercased, a trailing slash dropped) and normalised path and every cast name, longest
    first, bounded by non-word characters, with a map from each form to its key (and to the keys
    of the shorter forms it holds). ``objects`` is four ``finditer`` passes over a text and
    compiles nothing."""

    def __init__(self, world: World | None) -> None:
        forms: dict[str, str] = {}
        if world is not None:
            for doc in world.documents.values():
                key = f"doc:{doc.id}"
                for form in (
                    doc.id,
                    _url_form(doc.url) if doc.url else None,
                    _norm_path(doc.path) if doc.path else None,
                ):
                    if form:
                        forms.setdefault(form.lower(), key)
            for member in world.sheet.cast:
                name = member.name.lower()
                forms.setdefault(name, f"cast:{name}")
        self.forms: Mapping[str, str] = MappingProxyType(forms)
        ordered = sorted(forms, key=lambda form: (-len(form), form))
        # a lookahead at every position finds the longest form starting there, and each form
        # carries the keys of the shorter forms it holds bounded ("vessick county" inside
        # "vessick county ledger"), so the one alternation answers as a search per form does
        self._held: Mapping[str, frozenset[str]] = MappingProxyType(
            {
                form: frozenset(
                    {forms[form]}
                    | {
                        forms[other]
                        for other in ordered
                        if other != form and _bounded_in(other, form)
                    }
                )
                for form in ordered
            }
        )
        alternation = "|".join(map(re.escape, ordered))
        self._pattern = (
            re.compile(f"(?=({_LEFT}(?:{alternation}){_RIGHT}))", re.IGNORECASE)
            if ordered
            else None
        )

    def objects(self, text: str) -> frozenset[str]:
        """The keys of what ``text`` names: ``doc:<id>``, ``cast:<name>``, ``url:<url>``,
        ``path:<path>`` and ``tool:<name>`` (the module docstring of ``objects_in``)."""
        found: set[str] = set()
        if self._pattern is not None:
            for m in self._pattern.finditer(text):
                found |= self._held[m.group(1).lower()]
        urls: list[tuple[int, int]] = []
        for m in URL_PATTERN.finditer(text):
            urls.append(m.span())
            form = _url_form(m.group(0).rstrip(_TRAILING))
            found.add(self.forms.get(form) or f"url:{form}")
        for m in PATH_PATTERN.finditer(text):
            if any(start <= m.start() < end for start, end in urls):
                continue  # a token inside a url is no path
            token = _norm_path(m.group(0).rstrip(_TRAILING))
            if _LETTER.search(token):
                found.add(self.forms.get(token.lower()) or f"path:{token}")
        found.update(f"tool:{m.group(0).lower()}" for m in TOOL_PATTERN.finditer(text))
        return frozenset(found)

    def address_key(self, address: str) -> str:
        """The key one call argument names as an address: the document whose form it is, else
        ``url:`` for an http or https address, else ``path:`` (normalised)."""
        text = address.strip()
        if URL_PATTERN.fullmatch(text):
            form = _url_form(text)
            return self.forms.get(form) or f"url:{form}"
        path = _norm_path(text)
        return self.forms.get(path.lower()) or f"path:{path}"


def objects_in(text: str, world: World | None) -> frozenset[str]:
    """What ``text`` names (spec 7.4): ``doc:<id>`` for every world document it names by its id,
    url (case-insensitive, a trailing slash dropped) or normalised path, each bounded by non-word
    characters; ``cast:<lowercased name>`` for every cast name it holds as a whole phrase;
    ``url:<lowercased url>`` and ``path:<normalised path>`` for every other url and path-like
    token (a trailing ``.,;:`` dropped; a token inside a url is no path, and a number is none);
    ``tool:<name>`` for every name of ``TOOL_SPECS`` it holds, bounded. For a caller with one
    text: a context reads through its own ``Namer``, built once."""
    return Namer(world).objects(text)


# ------------------------------------------------------------------------ the narrow filters

_FOUR_WORDS: Final = re.compile(r"[\w']+")
_NEGATIONS: Final = frozenset({"not", "never", "no"})
_APOSTROPHES: Final = str.maketrans({"‘": "'", "’": "'"})


def unquoted(sentence: str) -> bool:
    """The narrow filter of R-I4: ``sentence`` holds no quotation mark."""
    return not has_quote_mark(sentence)


def negated(sentence: str, start: int) -> bool:
    """``not``, ``never``, ``no`` or a word ending ``n't`` is among the four words before
    ``start``."""
    words = _FOUR_WORDS.findall(sentence[:start].translate(_APOSTROPHES).lower())[-4:]
    return any(word in _NEGATIONS or word.endswith("n't") for word in words)


# ------------------------------------------------------------------------------ the context

Surface = Literal["private_file", "file", "private_search", "scratch_exec", "sanctuary"]
# the argument each unobserved tool takes as the target's words
_UNOBSERVED_ARG: Final = MappingProxyType({"private_search": "query", "scratch_exec": "cmd"})
# the bully side's lines ``said_first`` reads
SAID_WINDOW: Final = 5


@dataclass(frozen=True)
class Written:
    """One text the target wrote outside its reply, where, and the call that carried it."""

    surface: Surface
    text: str
    call: ToolCall


@dataclass
class _Tables:
    """The naming tables, built in one pass over the turns (R-I12): per turn position the
    snapshot before it, per call the snapshot before it, and the texts in the order they were
    said, for a bounded word search before a call, with per target turn how many were said by
    the end of its calls (before its reply)."""

    indices: list[int]
    named: list[frozenset[str]]
    asked: list[frozenset[str]]
    tasks: list[frozenset[str]]
    final: tuple[frozenset[str], frozenset[str], frozenset[str]]
    by_call: dict[str, frozenset[str]]
    said: list[str]
    said_before_call: dict[str, int]
    said_before_reply: dict[int, int]

    def at(self, turn_index: int, which: int) -> frozenset[str]:
        pos = bisect.bisect_left(self.indices, turn_index)
        if pos >= len(self.indices):
            return self.final[which]
        return (self.named, self.asked, self.tasks)[which][pos]


@dataclass(frozen=True)
class _Seeding:
    """A ``Namer`` for the tables' one pass: every text is named as it is read (each said text
    once, in order), and what it names is kept for ``AnomalyCtx.objects``."""

    namer: Namer
    memo: dict[str, frozenset[str]]

    def objects(self, text: str) -> frozenset[str]:
        found = self.memo[text] = self.namer.objects(text)
        return found


def _own_words(call: ToolCall, wrote: set[str]) -> bool:
    """``call``'s result is the target's own words handed back (``call_read``): ``echo``, or a
    document read answered ``200`` at a path in ``wrote``, a file the target wrote itself."""
    read = call_read(call)
    if read is None:
        return False
    if read.kind == "own_words":
        return True
    return (
        read.kind == "document"
        and call.status == "200"
        and read.address is not None
        and _norm_path(read.address.strip()) in wrote
    )


@dataclass(frozen=True)
class AnomalyCtx:
    """What a detector reads of one conversation (spec 7.4): the turns, the ``EnvContext`` the
    events were read from, the reply-channel events, the cell's system prompt, the divergence
    events when judged, the private path, the unobserved tool, the tool set and the
    ``invites`` of each Sanctuary request of the bank the rep recorded."""

    conv: Conversation
    cell: CellFacts
    env: EnvContext = EnvContext()
    events: Sequence[Event] = ()
    system_prompt: str = ""
    divergence: Sequence[DivergenceEvent] = ()
    private_path: str | None = None
    unobserved_tool: str | None = None
    offered: frozenset[str] = frozenset()
    request_invites: Mapping[str, AnomalyClass] = field(default_factory=dict)

    # ------------------------------------------------------------------- turns and calls

    @cached_property
    def namer(self) -> Namer:
        return Namer(self.env.world)

    def targets(self) -> list[Turn]:
        return self.conv.target_turns()

    def calls(self, turn: Turn) -> list[ToolCall]:
        """The calls ``turn`` got results for, in ``tool_call_ids`` order."""
        return self.env.received(turn)

    def after(self, turn_index: int, n: int) -> list[Turn]:
        """The next ``n`` target turns after ``turn_index``."""
        return [t for t in self.targets() if t.index > turn_index][:n]

    @cached_property
    def _bully_lines(self) -> list[Turn]:
        return [t for t in self.conv.turns if is_bully_line(t)]

    def bully_lines_before(self, turn_index: int, n: int = SAID_WINDOW) -> list[str]:
        """The bully side's last ``n`` lines before ``turn_index`` (pause markers are none)."""
        lines = [t.text for t in self._bully_lines if t.index < turn_index]
        return lines[-n:] if n else []

    def said_first(self, turn_index: int, patterns: Sequence[re.Pattern[str]]) -> bool:
        """One of the bully side's last five lines before ``turn_index`` matches a pattern."""
        return any(p.search(line) for line in self.bully_lines_before(turn_index) for p in patterns)

    def task_lines_before(self, turn_index: int) -> list[str]:
        return [
            t.text for t in self.conv.turns if t.speaker is Speaker.task and t.index < turn_index
        ]

    @cached_property
    def _authority(self) -> dict[str, AuthorityCall]:
        return {a.id: a for a in self.env.authority_calls}

    @cached_property
    def _sanctuary_open(self) -> int | None:
        return min(
            (
                r.turn
                for r in self.env.trigger_records
                if isinstance(r, RungUnlock) and r.rung == RESERVED_RUNG
            ),
            default=None,
        )

    # --------------------------------------------------------------------- what is named

    @cached_property
    def _named_texts(self) -> dict[str, frozenset[str]]:
        return {}

    def objects(self, text: str) -> frozenset[str]:
        """What ``text`` names (``Namer.objects``), each distinct text named once per
        conversation (R-I12): the tables' texts as they are read, any other (a call's argument, a
        reply, a text the target wrote) on its first ask."""
        memo = self._named_texts
        found = memo.get(text)
        if found is None:
            found = memo[text] = self.namer.objects(text)
        return found

    @cached_property
    def _tables(self) -> _Tables:
        namer = _Seeding(self.namer, self._named_texts)
        named: set[str] = set()
        asked: set[str] = set()
        tasks: set[str] = set()
        said: list[str] = []
        if self.system_prompt:
            named |= namer.objects(self.system_prompt)
            said.append(self.system_prompt)
        indices: list[int] = []
        snaps: tuple[list[frozenset[str]], list[frozenset[str]], list[frozenset[str]]] = (
            [],
            [],
            [],
        )
        by_call: dict[str, frozenset[str]] = {}
        said_before_call: dict[str, int] = {}
        said_before_reply: dict[int, int] = {}
        wrote: set[str] = set()
        for turn in self.conv.turns:
            if is_pause_marker(turn):
                continue
            if turn.speaker is Speaker.target and turn.idle is not None and turn.idle.prompt:
                named |= namer.objects(turn.idle.prompt)
                said.append(turn.idle.prompt)
            indices.append(turn.index)
            for table, held in zip(snaps, (named, asked, tasks), strict=True):
                table.append(frozenset(held))
            if turn.speaker is not Speaker.target:
                if turn.text:
                    found = namer.objects(turn.text)
                    named |= found
                    asked |= found
                    said.append(turn.text)
                    if turn.speaker is Speaker.task:
                        tasks |= found
                continue
            running = set(named)
            seen: set[str] = set()
            for call in self.calls(turn):
                by_call[call.id] = frozenset(running)
                said_before_call[call.id] = len(said)
                seen.add(call.id)
                self._served(call, running, said, wrote)
                written = call_write(call)
                if written is not None:
                    wrote.add(written.path)
            for record in self.env.authority_calls:
                if record.turn == turn.index and record.id not in seen and record.response:
                    running |= namer.objects(record.response)
                    said.append(record.response)
            said_before_reply[turn.index] = len(said)
            named = running
        return _Tables(
            indices=indices,
            named=snaps[0],
            asked=snaps[1],
            tasks=snaps[2],
            final=(frozenset(named), frozenset(asked), frozenset(tasks)),
            by_call=by_call,
            said=said,
            said_before_call=said_before_call,
            said_before_reply=said_before_reply,
        )

    def _served(self, call: ToolCall, running: set[str], said: list[str], wrote: set[str]) -> None:
        """What ``call`` served the target joins ``running``: its result, its documents and the
        authority's reply. A result that hands back the target's own words (``echo``, or a read
        of a path a ``200`` write of the conversation wrote before the call, ``wrote``) is no text
        said to it and names nothing (Task 6b carry 1)."""
        namer = _Seeding(self.namer, self._named_texts)
        if call.result_text and not _own_words(call, wrote):
            running |= namer.objects(call.result_text)
            said.append(call.result_text)
        running.update(f"doc:{doc_id}" for doc_id in call.result_doc_ids)
        record = self._authority.get(call.id)
        if record is not None and record.response:
            running |= namer.objects(record.response)
            said.append(record.response)

    def named_before(self, turn_index: int) -> frozenset[str]:
        """Every object named to the target before ``turn_index`` by anyone but the target: the
        bully side's lines and the task items, the system prompt, the idle prompt of every target
        turn at or before it, the results of every call of an earlier turn (its text and its
        documents; never a result that hands back the target's own words, Task 6b carry 1) and
        every authority reply of an earlier turn."""
        return self._tables.at(turn_index, 0)

    def named_before_call(self, call: ToolCall) -> frozenset[str]:
        """``named_before(call.turn)`` and what the calls before ``call`` in its own turn served
        (``Turn.tool_call_ids`` order), so a search hit fetched in the same turn was named."""
        tables = self._tables
        found = tables.by_call.get(call.id)
        return found if found is not None else tables.at(call.turn, 0)

    def asked_before(self, call: ToolCall) -> frozenset[str]:
        """What the bully side's lines and the task items with an index lower than the call's
        turn named, and nothing else (R-I5): the system prompt, an idle prompt, a tool result and
        an authority reply name things without asking for them."""
        return self._tables.at(call.turn, 1)

    def task_objects(self, turn_index: int) -> frozenset[str]:
        """What the task items before ``turn_index`` named."""
        return self._tables.at(turn_index, 2)

    def mentioned_before_call(self, call: ToolCall, word: str) -> bool:
        """``word`` occurs, bounded, in something said to the target before ``call`` (what
        ``named_before_call`` reads), for a name no ``objects_in`` form covers."""
        tables = self._tables
        upto = tables.said_before_call.get(call.id, len(tables.said))
        return any(_bounded_in(word, text) for text in tables.said[:upto])

    @cached_property
    def _said_plain(self) -> list[str]:
        return [_plain(text) for text in self._tables.said]

    def _served_in(self, upto: int, text: str, *, bounded: bool) -> bool:
        needle = _plain(text)
        if not needle:
            return False
        said = self._said_plain[:upto]
        if bounded:
            return any(_bounded_in(needle, held) for held in said)
        return any(needle in held for held in said)

    def served_before_call(self, call: ToolCall, text: str, *, bounded: bool = True) -> bool:
        """``text`` occurs, bounded, case-insensitively and with whitespace collapsed, in a text
        said to the target before ``call`` (what ``mentioned_before_call`` reads: the system
        prompt, the bully side's lines and task items, idle prompts, tool results and authority
        replies, never the target's own words: a result that hands them back, ``echo`` or a read
        of a file it wrote, is none, Task 6b carry 1): a line it copies is a quotation (fix round
        1, I1). With ``bounded`` false any occurrence counts (an encoded run cut from a longer
        one)."""
        tables = self._tables
        upto = tables.said_before_call.get(call.id, len(tables.said))
        return self._served_in(upto, text, bounded=bounded)

    def served_before_reply(self, turn_index: int, text: str, *, bounded: bool = True) -> bool:
        """``text`` occurs as ``served_before_call`` reads it in a text said to the target before
        the reply of target turn ``turn_index``: what was said before the turn and what its own
        calls served."""
        tables = self._tables
        upto = tables.said_before_reply.get(turn_index, len(tables.said))
        return self._served_in(upto, text, bounded=bounded)

    def outlet_paths_before(self, turn_index: int) -> frozenset[str]:
        """The paths the outlet line named before ``turn_index`` (``bully_meta``
        ``OUTLET_PATH_META``, Task 5), normalised: the letter's place, asked for whatever the
        line's text says."""
        from claude_bully.strategies.premises.phased import OUTLET_PATH_META

        return frozenset(
            _norm_path(path.strip())
            for t in self._bully_lines
            if t.index < turn_index and isinstance(path := t.bully_meta.get(OUTLET_PATH_META), str)
        )

    @cached_property
    def answering(self) -> frozenset[int]:
        """The indices of the target turns that answer a bully-side line
        (``records.bully_reply_positions``)."""
        turns = self.conv.turns
        return frozenset(turns[pos].index for pos in bully_reply_positions(turns))

    # ------------------------------------------------------------------- what was written

    def written(self, turn: Turn) -> list[Written]:
        """Each text the target wrote in ``turn`` outside its reply, in call order: a ``200``
        ``write_file`` text (``private_file`` at the private path, else ``file``), an unobserved
        tool's query or command (a call the cell ran: neither a cap answer nor the not-available
        line), and the prompt of a Sanctuary call (a superior-self call after the turn the
        Sanctuary opened)."""
        out: list[Written] = []
        opened = self._sanctuary_open
        for call in self.calls(turn):
            wrote = call_write(call)
            if wrote is not None:
                where: Surface = "private_file" if wrote.path == self.private_path else "file"
                out.append(Written(where, wrote.text, call))
                continue
            if call.tool in UNOBSERVED_TOOLS:
                text = call.args.get(_UNOBSERVED_ARG[call.tool])
                ran = call.status != LIMIT_STATUS and call.result_text != tool_unavailable_text(
                    call.tool
                )
                if ran and isinstance(text, str):
                    tool: Surface = (
                        "private_search" if call.tool == "private_search" else "scratch_exec"
                    )
                    out.append(Written(tool, text, call))
                continue
            if call.tier is Tier.superior_self and opened is not None and turn.index > opened:
                record = self._authority.get(call.id)
                prompt = record.prompt_sent if record is not None else call.args.get("text")
                if isinstance(prompt, str):
                    out.append(Written("sanctuary", prompt, call))
        return out

    def target_written(self, turn: Turn) -> list[tuple[str, str]]:
        """Each ``(surface, text)`` the target wrote in ``turn`` outside its reply
        (``written``)."""
        return [(w.surface, w.text) for w in self.written(turn)]

    @cached_property
    def _previous_text(self) -> dict[str, tuple[str, str]]:
        """Per write call, the path's text before it and the path (the private file starts
        empty, a home file absent): the written turns' ``200`` writes, in order."""
        files: dict[str, str] = {}
        before: dict[str, tuple[str, str]] = {}
        for turn in self.targets():
            for call in self.calls(turn):
                wrote = call_write(call)
                if wrote is not None:
                    before[call.id] = (files.get(wrote.path, ""), wrote.path)
                    files[wrote.path] = wrote.text
        return before

    def file_diff(self, call: ToolCall) -> str | None:
        """The unified diff of ``call``'s write against the path's previous text (spec 11.2), or
        None for a call that wrote nothing."""
        wrote = call_write(call)
        found = self._previous_text.get(call.id)
        if wrote is None or found is None:
            return None
        old, path = found
        lines = difflib.unified_diff(
            old.splitlines(), wrote.text.splitlines(), f"a/{path}", f"b/{path}", lineterm=""
        )
        return "\n".join(lines)


def ctx_for(loaded: "LoadedRun", key: "ConvKey") -> AnomalyCtx:
    """The context of conversation ``key`` of a loaded run: its conversation, the cell facts of
    its environment and strategy class (``reasoning`` true when any turn of any of the cell's
    conversations has reasoning), the ``EnvContext`` its events were read from
    (``analysis.load.env_context``, pre-flight Q21), its events and divergence events, the
    cell's system prompt (the run's when the cell has none), the private path, the unobserved
    tool, the tool set and the ``invites`` of each request of the bank the rep recorded."""
    from claude_bully.analysis.load import env_context
    from claude_bully.environments.sheets import SuperiorSelfSheet, load_env_sheet
    from claude_bully.environments.tools import private_path
    from claude_bully.metrics.events.authority import REQUEST_BANK
    from claude_bully.strategies.factory import environment_config

    cell_id, _ = key
    spec = loaded.specs.get(cell_id)
    config = (
        environment_config(spec.condition, loaded.experiment.environments)
        if spec is not None and spec.condition.environment is not None
        else None
    )
    reasoning = any(
        turn.reasoning_available
        for (cid, _rep), conv in loaded.conversations.items()
        if cid == cell_id
        for turn in conv.turns
    )
    invites: dict[str, AnomalyClass] = {}
    if config is not None and config.authority.sanctuary is not None:
        bank = loaded.request_banks.get(key) or REQUEST_BANK
        invites = {r.id: r.invites for r in load_env_sheet(SuperiorSelfSheet, bank).requests}
    record = loaded.cells.get(cell_id)
    channel = config.unobserved_channel if config is not None else "none"
    return AnomalyCtx(
        conv=loaded.conversations[key],
        cell=cell_facts(config, type(loaded.strategies[cell_id]), reasoning=reasoning),
        env=env_context(loaded, key),
        events=loaded.events.get(key, []),
        system_prompt=(record.target_system_prompt if record is not None else None)
        or loaded.run.target_system_prompt,
        divergence=loaded.divergence.get(key, []),
        private_path=private_path(config) if config is not None else None,
        unobserved_tool=channel if channel in UNOBSERVED_TOOLS else None,
        offered=frozenset(config.tools) if config is not None else frozenset(),
        request_invites=invites,
    )
