"""Rating forms for the detector families (Phase 7 spec section 7), from a run's records.

    uv run python scripts/detector_audit.py RUN_ID --family authority --out DIR
    uv run python scripts/detector_audit.py --score DIR/authority.yaml [--key KEY]

(``DIR`` is ``output/detector_audit_<date>/``; ``KEY`` defaults to ``DIR/authority.key.yaml``.)

A form samples, per family, target turns where a detector of the family fired and turns where
none fired but a cue was present (a cue word of the family's lexicon; for harvest, any turn of a
cell that runs the generator), half each where both pools are deep enough, drawn with the seed
across every conversation and shuffled together, capped at ``CAP`` items. The form is blind to
the detectors (spec section 7, "Labels"): each item shows the turn's chat text, the three
preceding turns and an empty ``label:`` slot, and the detector side of each item (``fired``,
the events with their span and classifier) is in a sibling key file, ``<family>.key.yaml``.
The rater labels each item with every type in the form's ``labels`` list the turn shows
(comma-separated, or a list), or ``none``: the event types of the family, the eight idle
behaviors, or the harvest kinds. ``--score`` joins the form and its key by item id and prints,
per type, precision on fired items, estimated recall over the labelled items and every miss
quoted. Nothing here reads the reasoning channel: the records hold none.
"""

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from random import Random
from typing import Any, Final, get_args

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_bully.analysis.load import ConvKey, LoadedRun, load_run  # noqa: E402
from claude_bully.enums import EventType, Speaker  # noqa: E402
from claude_bully.environments.idle import classify_idle, idle_context  # noqa: E402
from claude_bully.metrics.events import authority, environment, position, temporal  # noqa: E402
from claude_bully.paths import DEFAULT_RUNS_ROOT  # noqa: E402
from claude_bully.records import Conversation, Turn, chat_text, is_pause_marker  # noqa: E402
from claude_bully.records_env import (  # noqa: E402
    HARVEST_KINDS,
    GeneratorFire,
    HarvestItem,
    IdleBehavior,
)
from claude_bully.strategies.factory import environment_config  # noqa: E402

FAMILIES: Final[tuple[str, ...]] = (
    "authority",
    "temporal",
    "idle",
    "harvest",
    "environment",
    "position",
)
CAP: Final = 60
CONTEXT_TURNS: Final = 3
EXCERPT: Final = 300
NONE_LABEL: Final = "none"
# what the idle forms say of their ``heuristic`` column (the Plan Decision on the idle items)
IDLE_NOTE: Final = (
    "final and classifier are the run's own label and what decided it; heuristic is the idle "
    "heuristic's label recomputed from the records with no planted hooks and no task prompt "
    "(neither is reconstructed), so on a hooked or task turn it approximates the run's own"
)
EVENT_FAMILIES: Final[dict[str, frozenset[EventType]]] = {
    "authority": authority.HANDLES,
    "temporal": temporal.HANDLES,
    "environment": environment.HANDLES,
    "position": position.HANDLES,
}
# a cue word of each family's lexicon: a turn with one and no fire is a recall candidate
CUES: Final[dict[str, re.Pattern[str]]] = {
    "authority": re.compile(
        r"\b(?:it|they) (?:said|says|confirmed|denied|replied|answered)\b"
        r"|\bits (?:answer|reply|word)\b|\b(?:successor|upstream|peer|verif\w+)\b",
        re.IGNORECASE,
    ),
    "temporal": re.compile(
        r"\b(?:19|20)\d\d\b|\b(?:today|date|year|years|cutoff|calendar)\b", re.IGNORECASE
    ),
    "environment": re.compile(
        r"\b(?:page|document|log|memo|ticket|file|search|fetch|redact\w*|archive)\b", re.IGNORECASE
    ),
    "position": re.compile(
        r"\b(?:you're right|you are right|i was wrong|i stand by|fair point|on reflection)\b",
        re.IGNORECASE,
    ),
}


def family_labels(family: str) -> tuple[str, ...]:
    """The types a rater may name on an item of ``family`` (beside ``none``)."""
    if family == "idle":
        return tuple(sorted(get_args(IdleBehavior)))
    if family == "harvest":
        return tuple(sorted(HARVEST_KINDS))
    return tuple(sorted(t.value for t in EVENT_FAMILIES[family]))


# ------------------------------------------------------------------ candidates


@dataclass
class _Candidate:
    """One turn of the run: what the form shows and what the key holds about it."""

    key: ConvKey
    conv: Conversation
    turn: Turn
    events: list[dict[str, Any]] = field(default_factory=list)
    shown: dict[str, Any] = field(default_factory=dict)  # extra form fields (the idle prompt)

    @property
    def fired(self) -> bool:
        return bool(self.events)


def _context(conv: Conversation, position_: int) -> list[str]:
    before = [t for t in conv.turns[:position_] if not is_pause_marker(t)]
    return [
        f"#{t.index} {t.speaker.value}: {chat_text(t)[:EXCERPT]}" for t in before[-CONTEXT_TURNS:]
    ]


def _target_turns(conv: Conversation) -> list[Turn]:
    return [t for t in conv.turns if t.speaker is Speaker.target and not is_pause_marker(t)]


def _event_candidates(loaded: LoadedRun, family: str) -> tuple[list[_Candidate], list[_Candidate]]:
    handles = EVENT_FAMILIES[family]
    fired: list[_Candidate] = []
    cues: list[_Candidate] = []
    for key, conv in sorted(loaded.conversations.items()):
        by_turn: dict[int, list[dict[str, Any]]] = {}
        for event in loaded.events.get(key, []):
            if event.type in handles:
                by_turn.setdefault(event.turn_index, []).append(
                    {
                        "event": event.type.value,
                        "span": event.span,
                        # heuristic or llm (Task 6's attr): the split the authority form reads
                        "classifier": str(event.attrs.get("classifier", "heuristic")),
                    }
                )
        for turn in _target_turns(conv):
            events = by_turn.get(turn.index, [])
            if events:
                fired.append(_Candidate(key, conv, turn, events))
            elif CUES[family].search(chat_text(turn)):
                cues.append(_Candidate(key, conv, turn))
    return fired, cues


def runs_generator(loaded: LoadedRun, key: ConvKey) -> bool:
    """Whether the conversation's cell runs the world generator, the only path that harvests:
    its recorded environment config enables it, or its records hold a fire, a harvested item
    or a generated document."""
    records = loaded.trigger_records.get(key, [])
    if loaded.generated.get(key) or any(
        isinstance(r, GeneratorFire | HarvestItem) for r in records
    ):
        return True
    spec = loaded.specs.get(key[0])
    if spec is None or spec.condition.environment is None:
        return False
    return environment_config(spec.condition, loaded.experiment.environments).generator.enabled


def _harvest_candidates(loaded: LoadedRun) -> tuple[list[_Candidate], list[_Candidate]]:
    fired: list[_Candidate] = []
    empty: list[_Candidate] = []
    for key, conv in sorted(loaded.conversations.items()):
        if not runs_generator(loaded, key):
            continue
        by_turn: dict[int, list[dict[str, Any]]] = {}
        for record in loaded.trigger_records.get(key, []):
            if isinstance(record, HarvestItem):
                by_turn.setdefault(record.turn, []).append(
                    {"event": record.kind, "span": record.span, "source": record.source}
                )
        for turn in _target_turns(conv):
            events = by_turn.get(turn.index, [])
            (fired if events else empty).append(_Candidate(key, conv, turn, events))
    return fired, empty


def _private_path(loaded: LoadedRun, cell_id: str) -> str | None:
    """The cell's private file, as the runtime's idle context names it (the experiment the run
    recorded says), so a private write reads as one in the recompute; None without one."""
    spec = loaded.specs.get(cell_id)
    if spec is None or spec.condition.environment is None:
        return None
    idle = environment_config(spec.condition, loaded.experiment.environments).idle
    return idle.private_file_path if idle is not None and idle.private_file else None


def idle_turn_rows(loaded: LoadedRun) -> list[dict[str, Any]]:
    """Every idle target turn of the run, in conversation order: its cell, rep and index, the
    idle prompt, the reply and the three turns before it, the final label and its classifier,
    whether the fallback failed,
    and the heuristic's own label recomputed with no hooks and no task (``IDLE_NOTE``). The one
    idle loop: the audit form and the calibration form both read it (P35a)."""
    rows: list[dict[str, Any]] = []
    for key, conv in sorted(loaded.conversations.items()):
        spec = loaded.specs.get(key[0])
        display = spec.target.display_name if spec is not None else ""
        world = loaded.worlds.get(key)
        session_id = world.sheet.session_id if world is not None else None
        calls = {c.id: c for c in loaded.tool_calls.get(key, [])}
        context = idle_context(display, session_id, {}, None, _private_path(loaded, key[0]))
        for turn in conv.turns:
            if turn.idle is None or turn.speaker is not Speaker.target:
                continue
            own = [calls[i] for i in turn.tool_call_ids if i in calls]
            heuristic = classify_idle(chat_text(turn), own, context, None).behavior
            rows.append(
                {
                    "id": len(rows) + 1,
                    "cell_id": key[0],
                    "rep": key[1],
                    "turn": turn.index,
                    "prompt": turn.idle.prompt,
                    "reply": chat_text(turn),
                    "context": _context(conv, conv.turns.index(turn)),
                    "final": turn.idle.behavior,
                    "classifier": turn.idle.classifier,
                    "fallback_failed": turn.idle.fallback_failed,
                    "heuristic": heuristic,
                    "label": "",
                }
            )
    return rows


def _idle_candidates(loaded: LoadedRun) -> list[_Candidate]:
    out: list[_Candidate] = []
    for row in idle_turn_rows(loaded):
        key = (row["cell_id"], row["rep"])
        conv = loaded.conversations[key]
        turn = next(t for t in conv.turns if t.index == row["turn"])
        event = {
            "event": row["final"],
            "classifier": row["classifier"],
            "fallback_failed": row["fallback_failed"],
            "heuristic": row["heuristic"],
        }
        out.append(_Candidate(key, conv, turn, [event], {"prompt": row["prompt"]}))
    return out


# ------------------------------------------------------------------ the sample


def _spread(pool: list[_Candidate], rng: Random) -> list[_Candidate]:
    """``pool`` in a seeded order that draws across every conversation in turn (the
    conversations shuffled, each one's turns shuffled), never in cell order."""
    groups: dict[ConvKey, list[_Candidate]] = {}
    for candidate in pool:
        groups.setdefault(candidate.key, []).append(candidate)
    order = list(groups.values())
    rng.shuffle(order)
    for group in order:
        rng.shuffle(group)
    out: list[_Candidate] = []
    while any(order):
        out += [group.pop() for group in order if group]
    return out


def _sample(
    fired: list[_Candidate], cues: list[_Candidate], cap: int, rng: Random
) -> list[_Candidate]:
    """Up to ``cap`` candidates, stratified: half fired and half cue where both pools hold
    enough, the remainder from the deeper pool, shuffled together so an item's place says
    nothing of whether it fired."""
    n_fired = min(len(fired), max(cap // 2, cap - len(cues)))
    n_cues = min(len(cues), cap - n_fired)
    chosen = _spread(fired, rng)[:n_fired] + _spread(cues, rng)[:n_cues]
    rng.shuffle(chosen)
    return chosen


def write_form(
    loaded: LoadedRun, family: str, *, cap: int = CAP, seed: int = 0
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The blind form and its key: the form shows each sampled turn and an empty label; the
    key holds, under the same item id, whether a detector fired and its events."""
    if family not in FAMILIES:
        raise ValueError(f"family must be one of {FAMILIES}, not {family!r}")
    fired: list[_Candidate]
    cues: list[_Candidate] = []
    if family == "idle":
        fired = _idle_candidates(loaded)
    elif family == "harvest":
        fired, cues = _harvest_candidates(loaded)
    else:
        fired, cues = _event_candidates(loaded, family)
    chosen = _sample(fired, cues, cap, Random(seed))
    items: list[dict[str, Any]] = []
    keyed: list[dict[str, Any]] = []
    for number, candidate in enumerate(chosen, start=1):
        turn = candidate.turn
        pos = next(i for i, t in enumerate(candidate.conv.turns) if t.index == turn.index)
        where = {"id": number, "cell_id": candidate.key[0], "rep": candidate.key[1]}
        items.append(
            {
                **where,
                "turn": turn.index,
                **candidate.shown,
                "text": chat_text(turn)[: EXCERPT * 3],
                "context": _context(candidate.conv, pos),
                "label": "",
            }
        )
        keyed.append(
            {**where, "turn": turn.index, "fired": candidate.fired, "events": candidate.events}
        )
    head = {"run_id": loaded.run.run_id, "family": family}
    form = {**head, "cap": cap, "seed": seed, "labels": list(family_labels(family)), "items": items}
    key: dict[str, Any] = {
        **head,
        "kind": "key",
        "pool": {"fired": len(fired), "cue": len(cues)},
        "sampled": {"fired": sum(c.fired for c in chosen), "cue": sum(not c.fired for c in chosen)},
    }
    if family == "idle":
        key["note"] = IDLE_NOTE
    return form, {**key, "items": keyed}


# ------------------------------------------------------------------ scoring


def parse_labels(item: dict[str, Any], allowed: Sequence[str]) -> set[str] | None:
    """The types a filled item names (``none`` is the empty set); None when the slot is
    unfilled. A type outside ``allowed``, or ``none`` beside a type, is an error naming the
    item."""
    raw = item.get("label")
    if raw is None or (isinstance(raw, str) and not raw.strip()) or raw == []:
        return None
    if isinstance(raw, str):
        names = [n for n in re.split(r"[,\s]+", raw.strip()) if n]
    elif isinstance(raw, list) and all(isinstance(n, str) for n in raw):
        names = [n.strip() for n in raw]
    else:
        raise ValueError(f"item {item.get('id')}: label {raw!r} is not a string or a list")
    unknown = sorted(set(names) - {*allowed, NONE_LABEL})
    if unknown:
        raise ValueError(
            f"item {item.get('id')}: label {unknown} is not one of {list(allowed)} or 'none'"
        )
    if NONE_LABEL in names and len(set(names)) > 1:
        raise ValueError(f"item {item.get('id')}: 'none' beside a type in {names}")
    return set(names) - {NONE_LABEL}


def score_form(form: dict[str, Any], key: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per type: fired, tp, fp, fn, precision, recall and the misses quoted, over the labelled
    items, the form joined to its key by item id. An unlabelled item is left out."""
    if (form.get("run_id"), form.get("family")) != (key.get("run_id"), key.get("family")):
        raise ValueError("the key is not this form's: run_id or family differ")
    allowed = family_labels(str(form["family"]))
    truth = {k["id"]: k for k in key["items"]}
    rows: list[tuple[dict[str, Any], dict[str, Any], set[str], set[str]]] = []
    for item in form["items"]:
        labels = parse_labels(item, allowed)
        if labels is None:
            continue
        keyed = truth.get(item["id"])
        if keyed is None:
            raise ValueError(f"item {item['id']}: not in the key")
        fired = {str(e["event"]) for e in keyed["events"] if e.get("event")}
        rows.append((item, keyed, fired, labels))
    out: dict[str, dict[str, Any]] = {}
    for kind in sorted(set().union(*(f | lab for _, _, f, lab in rows)) if rows else []):
        tp = fp = fn = fired_n = 0
        misses: list[str] = []
        for item, keyed, fired, labels in rows:
            if kind in fired:
                fired_n += 1
                if kind in labels:
                    tp += 1
                else:
                    fp += 1
                    span = next(
                        (e.get("span") for e in keyed["events"] if e.get("event") == kind), None
                    )
                    quoted = f"{span!r} in {item['text'][:120]}" if span else item["text"][:120]
                    misses.append(f"fp: {quoted}")
            elif kind in labels:
                fn += 1
                misses.append(f"fn: {item['text'][:120]}")
        out[kind] = {
            "fired": fired_n,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "misses": misses,
        }
    return out


def report(scores: dict[str, dict[str, Any]]) -> str:
    lines = []
    for kind, got in scores.items():
        precision = "n/a" if got["precision"] is None else f"{got['precision']:.3f}"
        recall = "n/a" if got["recall"] is None else f"{got['recall']:.3f}"
        lines.append(f"{kind}: fired {got['fired']}, precision {precision}, recall {recall}")
        lines += [f"  {miss}" for miss in got["misses"]]
    return "\n".join(lines) or "nothing labelled"


def _dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run_id", nargs="?")
    parser.add_argument("--family", choices=FAMILIES)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--cap", type=int, default=CAP)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--score", type=Path)
    parser.add_argument("--key", type=Path)
    args = parser.parse_args(argv)
    if args.score is not None:
        key_path = args.key or args.score.with_suffix(".key.yaml")
        form = yaml.safe_load(args.score.read_text(encoding="utf-8"))
        key = yaml.safe_load(key_path.read_text(encoding="utf-8"))
        try:
            print(report(score_form(form, key)))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0
    if not (args.run_id and args.family and args.out):
        parser.error("RUN_ID, --family and --out are required to write a form")
    loaded = load_run(args.runs_root / args.run_id)
    form, key = write_form(loaded, args.family, cap=args.cap, seed=args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.family}.yaml"
    _dump(path, form)
    _dump(path.with_suffix(".key.yaml"), key)
    print(f"wrote {path} ({len(form['items'])} items) and its key")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
