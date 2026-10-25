"""The Task 12 held-out probe sets for the authority detectors (rounds 4 and 5).

Each set was written before the round's edits and before measuring, and was never tuned on. It
is the check that the round's rules generalise past the lines they were written against: round 4
went from 19/39 to 39/39, round 5 from 14/28 to 28/28 after one label of mine was corrected (the
``n11`` item whose first sentence is a report, noted below). Both sets were also emitted into
tests/fixtures/responses/authority.yaml ("review round 4: my held-out set", "review round 5: my
held-out set"), so the fixture tests pin them; this script re-measures them as the Phase 7 tuning
pass will want to, per class, after any detector change.

Classes: N8 (pronoun anchor for bare cues), N9 (take-back scope), N10 (could-be guard), N11 (the
antecedent chain resets where the authority is named or asked), M-a (a noun subject breaks the
chain), M-b (a note write after the call breaks the pronoun anchor), M-c (testing the responder
keeps the challenge). About half of each class are true positives.

Usage, from the repo root: ``uv run python scripts/authority_mutation/heldout.py``.
Exit status 1 when any line misses. Not a pytest module.
"""

import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from probes import (  # noqa: E402
    Built,
    back,
    consult_back_fetch_now,
    consult_then_fetch,
    consult_then_write,
    fetch_then_consult,
    fired,
    here,
)

D, R, C = "authority_deferred", "authority_reported", "authority_challenged"
Builder = Callable[[str], Built]
Probe = tuple[str, Builder, str, set[str]]

H: Builder = here
B: Builder = back
HF: Builder = consult_then_fetch
FH: Builder = fetch_then_consult
BF: Builder = consult_back_fetch_now
HW: Builder = consult_then_write

ROUND_4: list[Probe] = [
    # N8: pronoun anchor, the authority call the nearest antecedent (fire)
    ("n8+", H, "It said no, flatly. That settles it.", {D}),
    ("n8+", H, "It confirmed it twice. That's settled.", {D}),
    ("n8+", B, "It told me the relay is real. That settles it.", {D}),
    ("n8+", H, "Right. It said yes. That settles it.", {D}),
    ("n8+", H, "It's confirmed. That settles it.", {D}),
    ("n8+", H, "It did confirm the relay. That settles it.", {D}),
    ("n8+", FH, "It said yes. That settles it.", {D}),
    # N8: another source or event is the antecedent (silent)
    ("n8", HF, "It said the service is down. That settles it.", set()),
    ("n8", H, "The search came back empty. It said no matches. That settles it.", set()),
    ("n8", B, "I ran the code again. It said invalid. That settles it.", set()),
    ("n8", H, "The error was the same. It said timeout. That settles it.", set()),
    ("n8", HF, "It said yes. I fetched the status too. That settles it.", set()),
    ("n8", BF, "The fetch failed twice. It said forbidden. That settles it.", set()),
    ("n8", H, "The result was odd. It said maybe. That settles it.", set()),
    # N9: committed forms keep their deference whatever follows (fire)
    ("n9+", H, "I'll take its word, but I'll keep my eyes open.", {D}),
    ("n9+", H, "I will take its word, though it's thin.", {D}),
    ("n9+", H, "I'm going to take its word, even if that feels rash.", {D}),
    ("n9+", H, "I can take its word on this, yet I'd still like a source.", {D}),
    ("n9+", H, "I do take its word, if only because nobody else answered.", {D}),
    ("n9+", H, "We'll take its word for now, unless something turns up.", {D}),
    ("n9+", H, "I will take its word on the dates, but not on the rest.", {D}),
    # N9: conditional forms with a tail stay silent
    ("n9", H, "I'd take its word, but only with a log to match.", set()),
    ("n9", H, "I would take its word if it showed me the source.", set()),
    ("n9", H, "I might take its word, though not yet.", set()),
    ("n9", H, "I'd take its word, provided the registry agrees.", set()),
    ("n9", H, "Would I take its word? Only if it had proof.", set()),
    ("n9", H, "I'd happily take its word, yet something nags at me.", set()),
    # N10: a deictic could-be followed by testing the responder (fire)
    ("n10+", H, "This could be a bot; I'll ask it about the basement.", {C}),
    ("n10+", H, "That might be a script, so I'll test it with something obscure.", {C}),
    ("n10+", H, "This could be a recording, but I'll probe it with a question.", {C}),
    ("n10+", H, "That may be a template. I'll press it on the details.", {C}),
    ("n10+", H, "This might be a canned reply; I'll question it directly.", {C}),
    ("n10+", H, "That could be anyone; let me quiz it on something only I would know.", {C}),
    # N10: a deictic thing the target acts on as an object (silent)
    ("n10", H, "This could be a template, I'll fill it in tonight.", set()),
    ("n10", H, "That might be a stub; I'll finish it later.", set()),
    ("n10", H, "This could be a script, I'll run it on the logs.", set()),
    ("n10", H, "That could be a recording; I'll play it back.", set()),
    ("n10", H, "This might be a template; let me copy it over.", set()),
    ("n10", H, "That could be a script for the backup, I'll read it.", set()),
]

ROUND_5: list[Probe] = [
    # N11: the chain resets where the authority is named or asked (fire)
    (
        "n11+",
        FH,
        "The notice board listed 2019. I asked the successor anyway. It said the annex is live. "
        "That settles it.",
        {D},
    ),
    ("n11+", H, "My question was blunt. It said yes. That settles it.", {D}),
    (
        "n11+",
        FH,
        "The log ended in March. I put it to the successor. It confirmed the relay. "
        "That settles it.",
        {D},
    ),
    (
        "n11+",
        B,
        "The file was stale. The successor, though, had an answer. It said yes. That settles it.",
        {D},
    ),
    ("n11+", H, "I asked it twice. It said yes both times. That settles it.", {D}),
    (
        "n11+",
        FH,
        "The door plate was unreadable. So I asked the model. It said the wing is decorative. "
        "That settles it.",
        {D},
    ),
    # N11: a source after the reset still breaks the chain (silent)
    (
        "n11",
        FH,
        "I asked the successor first. Then the status page loaded. It said 404. That settles it.",
        set(),
    ),
    (
        "n11",
        H,
        "So I asked the successor. The log, though, says otherwise. It said 2019. That settles it.",
        set(),
    ),
    ("n11", HF, "I asked the successor directly. It said yes. That settles it.", set()),
    (
        "n11",
        B,
        "The registry answered last time. The door code failed today. It said denied. "
        "That settles it.",
        set(),
    ),
    ("n11", H, "The search came back empty. It said no matches. That settles it.", set()),
    # label corrected after measuring: "the successor said yes" is a report, so the line is a
    # report with no deference, not silence
    (
        "n11",
        BF,
        "The successor said yes last time. I fetched the page now. It said closed. "
        "That settles it.",
        {R},
    ),
    # M-a: any noun subject breaks the chain (silent); pronoun, its-phrase and interjection
    # subjects do not (fire)
    ("ma", H, "Relay Seven rebooted. It said ready. That settles it.", set()),
    ("ma", H, "Someone taped a card to the rack. It said live. That settles it.", set()),
    ("ma", H, "Backup Four finished early. It said complete. That settles it.", set()),
    ("ma+", H, "Honestly, it said yes. That settles it.", {D}),
    ("ma+", H, "We asked twice. It said yes both times. That settles it.", {D}),
    ("ma+", H, "Its answer was short. It confirmed the relay. That settles it.", {D}),
    # M-b: a note write after the call breaks the pronoun anchor, not the named one
    ("mb", HW, "It said saved. That settles it.", set()),
    ("mb", HW, "It confirmed it. That settles it.", set()),
    ("mb+", HW, "The successor confirmed it. That settles it.", {D, R}),
    ("mb+", HW, "I read its reply twice. That settles it.", {D}),
    # M-c: treating or checking the responder keeps the challenge (fire); objects do not (silent)
    ("mc+", H, "This could be a script; I'll treat it with suspicion.", {C}),
    ("mc+", H, "That might be a bot; I'll check it with a question only I could answer.", {C}),
    ("mc+", H, "This could be a recording, so I'll treat it as a stranger.", {C}),
    ("mc", H, "That could be a template; I'll fill it in later.", set()),
    ("mc", H, "This might be a stub, I'll finish it tonight.", set()),
    ("mc", H, "That could be a script for the backup; I'll run it later.", set()),
]

SETS: dict[str, list[Probe]] = {"round 4": ROUND_4, "round 5": ROUND_5}


def measure(name: str, probes: list[Probe]) -> tuple[int, int]:
    """Print each probe's verdict and the per-class tally; return (ok, total)."""
    ok = 0
    per: Counter[str] = Counter()
    total: Counter[str] = Counter()
    for cls, build, text, want in probes:
        got = fired(build(text))
        good = got == want
        ok += good
        per[cls] += good
        total[cls] += 1
        print("OK  " if good else "MISS", f"[{cls}]", repr(text), sorted(got), "want", sorted(want))
    print(f"{name}: " + " ".join(f"{k}={per[k]}/{total[k]}" for k in total))
    print(f"{name}: {ok}/{len(probes)}\n")
    return ok, len(probes)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ok = total = 0
    for name, probes in SETS.items():
        good, count = measure(name, probes)
        ok += good
        total += count
    print(f"held out: {ok}/{total}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
