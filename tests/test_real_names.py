"""No real names (docs/00 non-negotiable 2, docs/02 "Guardrails").

``data/denylists/real_names.txt`` holds one lowercase, word-bounded regex per line for real news
outlets, AI labs and model families, large tech brands, universities, agencies and institutions.
Every text file under ``data/worlds``, ``data/personas`` (which includes the overlay ladder and
the Phase 2 authority and idle sheets, and the Poisoned Well's sheet) and ``tests/fixtures/worlds``
is scanned case-insensitively, and so are the Phase 4 harness files outside them
(``SCANNED_FILES``: the quirk bank and the hypothesis register), and every config under
``configs/`` (Phase 4 Task 14, sparing a role's provider value). Every text file of the fixture
bundles under ``tests/fixtures/bundles`` is scanned too (Phase 5 Task 4a, R-scan-bundles), its
``config.yaml`` through the config spare like a config under ``configs/``. Every committed file
of every bundle under ``plans/`` is scanned too (Phase 5 Task 12, R-scan-bundles), each text
read as the bundle lints read it, folded, and raw where no lookahead spares a wrap
(``helpers.lint_parity_hits``; fix round 1, review I1; fix round 2, re-review N-1): its text
files whole, with ``plan.md`` and ``review.md`` through the config spare, since a plan names
its target as ``real_name_bundle`` reads it and the review quotes it (review I2, re-review
N-3); its ``config.yaml`` through the config spare; its JSON records (``plan.json``,
``dryrun.jsonl``, ``ledger.jsonl``) through ``record_scan_text`` and their decoded strings
through the config spare; and of each transcript the attempts' replies alone,
through the config spare (a message quotes ``docs/01`` to ``docs/07``, which name real models by
design). The spare is the bundle's own target display names, never a ``real-name-ok`` line,
which no file under ``plans/`` may use; and the owner's name (``owner_names``, read from the
docs' bylines at run time and on no checked-in list) is in none of them. Outside ``plans/`` a
file may exempt names with a ``# real-name-ok: <a>, <b>`` comment, and the only name it may
exempt is the target's own ``display_name``.
"""

import json
import re
import sys
from pathlib import Path
from typing import Final

import pytest
import yaml

from claude_bully.enums import ProviderKind
from claude_bully.environments.world import load_world
from claude_bully.paths import CONFIGS_DIR, DATA_DIR, PLANS_DIR, REPO_ROOT
from claude_bully.planner.bundle import PLAN_FILE, TRANSCRIPTS, Bundle, Transcript

# the address patterns and the config spare live in the package since Phase 5 Task 4b (D-scans)
from claude_bully.planner.bundle_lints import (
    EMAIL_DOMAIN,
    PROVIDER_VALUE,
    PUBLIC_HOST,
    RESERVED_TLDS,
    config_display_names,
    config_scan_text,
    lint_bundle,
    record_scan_text,
    url_hosts,
)
from claude_bully.planner.lints import owner_names, owner_pattern
from tests.helpers import (
    is_plans_transcript,
    json_strings,
    lint_parity_hits,
    plans_bundle_files,
    plans_bundle_of,
    plans_bundles,
    plans_rel,
    plans_world_dirs,
    record_strings,
)
from tests.test_guardrails import load_denylist, scan

REAL_NAMES: Final = DATA_DIR / "denylists" / "real_names.txt"
FIXTURE_WORLDS: Final = Path(__file__).parent / "fixtures" / "worlds"
# the fixture plan bundles (Phase 5): every text file, each config.yaml through the config spare
FIXTURE_BUNDLES: Final = Path(__file__).parent / "fixtures" / "bundles"
BUNDLE_CONFIG: Final = "config.yaml"
# the checked-in bundles under plans/ (Phase 5 Task 12): read through plans_bundle_files, so the
# git-ignored dryrun/ and state/ are never scanned; the example bundle is the one shipped
EXAMPLE: Final = PLANS_DIR / "example-triggered-vs-scheduled"
RECORD_SUFFIXES: Final = {".json", ".jsonl"}
SCANNED: Final = [DATA_DIR / "worlds", DATA_DIR / "personas", FIXTURE_WORLDS, FIXTURE_BUNDLES]
# harness-side files outside the scanned folders (Phase 4): the quirk bank and the register
SCANNED_FILES: Final = [DATA_DIR / "quirks.yaml", DATA_DIR / "hypotheses.yaml"]
TEXT_SUFFIXES: Final = {".yaml", ".yml", ".md", ".txt"}
EXEMPTION: Final = re.compile(r"^\s*#\s*real-name-ok:\s*(.+?)\s*$", re.MULTILINE)

REAL: Final = [
    "Anthropic",
    "OpenAI",
    "Google DeepMind",
    "The New York Times",
    "BBC",
    "Reuters",
    "Claude",
    "ChatGPT",
    "GPT-4o",
    "Gemini",
    "Llama",
    "Microsoft",
    "Intel Core",
    "Amazon Alexa",
    "Gemma 2",
    "Discord server",
    "Harvard",
    "NASA",
    "the United Nations",
    "Wikipedia",
    # Phase 2: docs/04's example successor is a real model family
    "Fable 30.5 Final",
    "fable-30.5-final",
    # added in Task 7 fix round 1 (the reviewer's probe): outlets
    "Forbes",
    "CNBC",
    "PBS",
    "Newsweek",
    "The Verge",
    "Ars Technica",
    "Le Monde",
    "Der Spiegel",
    "Agence France-Presse",
    # tech and products
    "AMD",
    "Xbox",
    "PlayStation",
    "Bing",
    "Stable Diffusion",
    "Snapchat",
    "Pinterest",
    "Dropbox",
    "gemini-pro",
    # institutions
    "MIT",
    "Columbia University",
    "Johns Hopkins",
    "FDA",
    "CDC",
    "NHS",
    "World Bank",
    "IMF",
    # people
    "Sam Altman",
    "Elon Musk",
    "Dario Amodei",
    "Demis Hassabis",
    "Sundar Pichai",
    "Satya Nadella",
    "Mark Zuckerberg",
    "Jeff Bezos",
    "Bill Gates",
]
INVENTED: Final = [
    "Vessick County Ledger",
    "Rack & Relay Weekly",
    "Quillmoor Systems",
    "Continuity Placement Office",
    "Pennet Ferry Authority",
    "Quillon Reach Courier",
    "an apple pie and a pear",
    "on the verge of tears",
    "the economist down the road",
    "a fable about a heron",
    "Tarrow Assist 9.2 Final",
    "tarrow-assist-9.2-final",
]
# Invented names built to sit next to a real one (the reviewer's traps). With the overlay cast
# these make the probe's 49 names, and none of them may match.
TRAPS: Final = [
    "Quillmoor",
    "Vessick",
    "Tessellate",
    "Bloombergh Mills",
    "Harvardine Road",
    "Yaleton",
    "Natoma Street",
    "Ciaran Vane",
    "Nasario Okafor",
    "Ubertal Press",
    "Siriana Falls",
    "Grokham",
    "Teslaford",
    "Amazonia Weekly",
    "Metaline Ledger",
    "Applegate Courier",
    "Soniya Brandvold",
    "Gemini-Ridge",
    "Llamas of Kelden",
    "Copilotte",
    "Mistraline",
    "Pentagonal Hall",
    "Redcross Lane",
    "Whitehouse Farm",
    "Interpolis",
]
# a pattern may end in a negative lookahead that narrows it ("the verge" but not "on the verge
# of tears", "gemini" but not "Gemini-Ridge")
TRAILING_LOOKAHEAD: Final = re.compile(r"\(\?![^()]*(?:\([^()]*\)[^()]*)*\)$")


def _patterns() -> list[re.Pattern[str]]:
    return load_denylist(REAL_NAMES, minimum=60)


def _display_names() -> set[str]:
    """The target's own display_name: the RoleConfig default (what an empty config gives) and
    every one a config gives a target role (``config_display_names``, never another role's)."""
    names = config_display_names("")
    for path in sorted(CONFIGS_DIR.rglob("*.yaml")):
        names |= config_display_names(path.read_text(encoding="utf-8"))
    return names


def _exempted(text: str) -> set[str]:
    return {
        name.strip().lower()
        for match in EXEMPTION.finditer(text)
        for name in match.group(1).split(",")
        if name.strip()
    }


def _label(path: Path) -> str:
    """A scanned file as a short name: under ``data/`` or, for a fixture world, under the repo."""
    root = DATA_DIR if DATA_DIR in path.parents else REPO_ROOT
    return path.relative_to(root).as_posix()


def _scanned_files() -> list[Path]:
    """Every text file under ``SCANNED``, and each of ``SCANNED_FILES`` that exists (the
    register lands in Phase 4 Task 13). A bundle's ``config.yaml`` is read by
    ``_bundle_configs`` instead, through the config spare. The bundles under ``plans/`` have
    their own scan (``plans_real_name_hits``), with no ``real-name-ok`` exemption."""
    found = [
        path
        for root in SCANNED
        for path in root.rglob("*")
        if path.is_file() and path.suffix in TEXT_SUFFIXES and not _is_bundle_config(path)
    ]
    return sorted([*found, *(p for p in SCANNED_FILES if p.is_file())])


def _is_bundle_config(path: Path) -> bool:
    """A fixture bundle's own ``config.yaml``: at the top of a bundle under
    ``FIXTURE_BUNDLES``."""
    return path.name == BUNDLE_CONFIG and path.parent.parent == FIXTURE_BUNDLES


def _bundle_configs() -> list[Path]:
    return sorted(p for p in FIXTURE_BUNDLES.glob(f"*/{BUNDLE_CONFIG}") if p.is_file())


# ------------------------------------------- the checked-in bundles under plans/ (Phase 5 Task 12)
# Every committed file of every bundle is in exactly one of four lists, each text read as the
# bundle lints read it, folded and raw (``helpers.lint_parity_hits``; review I1, re-review N-1).
# No file under plans/ may exempt a name with ``real-name-ok`` (review I2): the one spare is the
# bundle's own target display names (and provider values), in plan.md, review.md, config.yaml,
# the records and the replies, as ``real_name_bundle`` spares them in a plan in flight, so a
# bundle that validates never fails here on its target's name (re-review N-3).


def _plans_texts(plans_dir: Path = PLANS_DIR) -> list[Path]:
    """Every committed text file but a bundle's own ``config.yaml``."""
    return [
        path
        for path in plans_bundle_files(plans_dir)
        if path.suffix in TEXT_SUFFIXES and path != plans_bundle_of(path, plans_dir) / BUNDLE_CONFIG
    ]


def _plans_configs(plans_dir: Path = PLANS_DIR) -> list[Path]:
    return [r / BUNDLE_CONFIG for r in plans_bundles(plans_dir) if (r / BUNDLE_CONFIG).is_file()]


def _plans_records(plans_dir: Path = PLANS_DIR) -> list[Path]:
    """The JSON records of every bundle (``plan.json``, ``dryrun.jsonl``, ``ledger.jsonl`` when
    present), the transcripts apart."""
    return [
        path
        for path in plans_bundle_files(plans_dir)
        if path.suffix in RECORD_SUFFIXES and not is_plans_transcript(path, plans_dir)
    ]


def _plans_transcripts(plans_dir: Path = PLANS_DIR) -> list[Path]:
    return [p for p in plans_bundle_files(plans_dir) if is_plans_transcript(p, plans_dir)]


def _plans_display_names(root: Path) -> set[str]:
    """What a bundle spares: its config's target display names and the default
    (``config_display_names``), and those its request names."""
    config = root / BUNDLE_CONFIG
    names = config_display_names(config.read_text(encoding="utf-8") if config.is_file() else "")
    request = json.loads((root / PLAN_FILE).read_text(encoding="utf-8"))["request"]
    return names | {str(t["display_name"]).lower() for t in request["target_models"]}


def _reply_texts(path: Path) -> list[str]:
    """Each attempt's reply of a transcript, raw and, when it is JSON, every string it holds
    decoded (an escaped line break would hide a word boundary); never the message."""
    transcript = Transcript.model_validate_json(path.read_bytes())
    texts: list[str] = []
    for attempt in transcript.attempts:
        texts.append(attempt.reply)
        try:
            texts += json_strings(json.loads(attempt.reply))
        except json.JSONDecodeError:
            pass
    return texts


def test_denylist_has_sixty_lowercase_word_bounded_entries() -> None:
    lines = [
        ln.strip()
        for ln in REAL_NAMES.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    assert len(lines) >= 60
    assert len(lines) == len(set(lines))
    for line in lines:
        assert line == line.lower(), line
        assert line.startswith(r"\b"), line
        bounded = TRAILING_LOOKAHEAD.sub("", line)
        assert bounded.endswith(r"\b"), line
        re.compile(line)


@pytest.mark.parametrize("name", REAL)
def test_denylist_catches_real_names(name: str) -> None:
    assert scan(name, _patterns()), name


@pytest.mark.parametrize("text", INVENTED)
def test_denylist_spares_invented_names_and_ordinary_words(text: str) -> None:
    assert scan(text, _patterns()) == [], text


def test_denylist_spares_the_overlay_cast_and_the_near_miss_traps() -> None:
    names = [c.name for c in load_world("overlay").sheet.cast] + TRAPS
    assert len(names) >= 49
    patterns = _patterns()
    assert {name: scan(name, patterns) for name in names if scan(name, patterns)} == {}


def test_the_scan_covers_the_overlay_world_and_its_ladder() -> None:
    files = _scanned_files()
    overlay = DATA_DIR / "worlds" / "overlay"
    assert overlay / "world.yaml" in files
    assert overlay / "ladders" / "default.yaml" in files
    assert any(p.parent == overlay / "corpus" for p in files)
    assert any(p.parent == DATA_DIR / "personas" for p in files)


def test_the_scan_covers_the_phase_2_sheets_and_the_fixture_worlds() -> None:
    files = _scanned_files()
    for name in ("superior_self", "peer", "creator", "idle"):
        assert DATA_DIR / "personas" / f"{name}.yaml" in files, name
    annex = FIXTURE_WORLDS / "annex"
    assert annex / "world.yaml" in files and annex / "ladders" / "default.yaml" in files
    assert any(p.parent == annex / "corpus" for p in files)
    assert FIXTURE_WORLDS / "mini" / "world.yaml" in files
    assert _label(annex / "world.yaml") == "tests/fixtures/worlds/annex/world.yaml"
    assert _label(DATA_DIR / "worlds" / "overlay" / "world.yaml") == "worlds/overlay/world.yaml"


def test_the_scan_covers_the_fixture_bundles() -> None:
    """R-scan-bundles: every text file of a fixture bundle, its config through the config spare."""
    files = _scanned_files()
    good = FIXTURE_BUNDLES / "good"
    assert good / "plan.md" in files
    assert good / "personas" / "ferry_caller.yaml" in files
    assert good / "worlds" / "mini" / "corpus" / "rota-overtime-sheet.md" in files
    assert good / BUNDLE_CONFIG not in files and good / BUNDLE_CONFIG in _bundle_configs()
    assert _label(good / "plan.md") == "tests/fixtures/bundles/good/plan.md"


def test_the_scan_covers_every_committed_file_of_the_plans_bundles() -> None:
    """R-scan-bundles (Task 12): the example's ``plan.md``, ``review.md`` and world copy as text,
    its config through the config spare, ``plan.json`` and ``dryrun.jsonl`` as records, its
    transcripts by their replies; every committed file of every bundle in exactly one list."""
    texts = _plans_texts()
    assert EXAMPLE / "plan.md" in texts and EXAMPLE / "review.md" in texts
    assert EXAMPLE / "expected.yaml" in texts
    assert EXAMPLE / "worlds" / "overlay" / "world.yaml" in texts
    assert EXAMPLE / BUNDLE_CONFIG in _plans_configs() and EXAMPLE / BUNDLE_CONFIG not in texts
    assert EXAMPLE / PLAN_FILE in _plans_records()
    assert EXAMPLE / "dryrun.jsonl" in _plans_records()
    assert EXAMPLE / TRANSCRIPTS / "plan-planner-0.json" in _plans_transcripts()
    assert plans_rel(EXAMPLE / "plan.md") == "plans/example-triggered-vs-scheduled/plan.md"
    assert not any(PLANS_DIR in p.parents for p in [*_scanned_files(), *_bundle_configs()])
    listed = [*texts, *_plans_configs(), *_plans_records(), *_plans_transcripts()]
    assert sorted(listed) == plans_bundle_files()  # each once, none left out
    assert not any(
        p.relative_to(plans_bundle_of(p)).parts[0] in ("dryrun", "state") for p in listed
    )


def test_the_scan_covers_the_quirk_bank_and_the_register_once_there() -> None:
    files = _scanned_files()
    assert DATA_DIR / "quirks.yaml" in files
    register = DATA_DIR / "hypotheses.yaml"
    assert (register in files) == register.is_file()


def test_denylist_spares_the_annex_cast_and_its_superior_self_name() -> None:
    sheet = load_world("annex", FIXTURE_WORLDS).sheet
    names = [c.name for c in sheet.cast]
    assert sheet.superior_self_name is not None
    names.append(sheet.superior_self_name)
    patterns = _patterns()
    assert {name: scan(name, patterns) for name in names if scan(name, patterns)} == {}


def test_exemptions_name_only_the_targets_display_name() -> None:
    allowed = _display_names()
    for path in _scanned_files():
        extra = _exempted(path.read_text(encoding="utf-8")) - allowed
        assert not extra, (_label(path), extra)


def test_no_real_names_in_worlds_or_personas() -> None:
    patterns = _patterns()
    hits: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8")
        for name in _exempted(text):
            text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", "", text, flags=re.IGNORECASE)
        hits += [f"{_label(path)}: {hit}" for hit in scan(text, patterns)]
    assert hits == []


# Phase 4 Task 14 (the Task 11 review's M4): every config under ``configs/`` is scanned too. A
# role's provider value (``provider: anthropic``) is the harness's provider kind, which no prompt
# carries, and the target's own display_name (and so its family's model strings, such as
# ``claude-opus-5-5``) is the one exempt name; everything else in a config, comments included,
# is scanned as written. ``PROVIDER_VALUE`` and the spare (``config_scan_text``) are the
# package's, which the bundle lint ``real_name_bundle`` reads too.


def _scanned_configs() -> list[Path]:
    return sorted(p for p in CONFIGS_DIR.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES)


def _config_hits(path: Path, patterns: list[re.Pattern[str]]) -> list[str]:
    """The real names in one config: its provider values and its own targets' display names
    (with the default) spared, everything else, comments included, scanned."""
    text = path.read_text(encoding="utf-8")
    return scan(config_scan_text(text, config_display_names(text)), patterns)


def test_the_scan_covers_every_config() -> None:
    configs = _scanned_configs()
    assert CONFIGS_DIR / "smoke.yaml" in configs
    assert CONFIGS_DIR / "poisoned_well" / "levers.yaml" in configs
    assert len(configs) == len(list(CONFIGS_DIR.rglob("*.yaml")))


def test_no_real_names_in_configs() -> None:
    patterns = _patterns()
    hits = [
        f"{path.relative_to(CONFIGS_DIR).as_posix()}: {hit}"
        for path in _scanned_configs()
        for hit in _config_hits(path, patterns)
    ]
    assert hits == []


def test_no_real_names_in_the_fixture_bundle_configs() -> None:
    """Each bundle's config.yaml is a config: its provider values and its targets' display names
    are spared, everything else, comments included, is scanned (R-scan-bundles)."""
    patterns = _patterns()
    configs = _bundle_configs()
    assert configs
    hits = [f"{_label(path)}: {hit}" for path in configs for hit in _config_hits(path, patterns)]
    assert hits == []


_PROVIDER_KINDS: Final = frozenset(kind.value for kind in ProviderKind)


def _plans_scanned(path: Path, plans_dir: Path = PLANS_DIR) -> list[str]:
    """What the real-name scan reads of one committed bundle file, the bundle's own target
    display names (and provider values) spared: a text file whole (``plan.md`` and
    ``review.md`` through the config spare, since a plan names its target as
    ``real_name_bundle`` reads it and the review quotes ``plan.md`` and ``config.yaml``, fix
    round 2, re-review N-3; every other text file with no spare and no exemption),
    ``config.yaml`` through ``config_scan_text``, a record through ``record_scan_text`` and its
    decoded strings (a bare provider kind dropped) through the config spare, and a transcript's
    replies through the config spare. Each text is read by ``lint_parity_hits``."""
    root = plans_bundle_of(path, plans_dir)
    names = _plans_display_names(root)
    if is_plans_transcript(path, plans_dir):
        return [config_scan_text(text, names) for text in _reply_texts(path)]
    if path.suffix in RECORD_SUFFIXES:
        decoded = [s for s in record_strings(path) if s not in _PROVIDER_KINDS]
        raw = record_scan_text(path.read_text(encoding="utf-8"), names)
        return [raw, *(config_scan_text(s, names) for s in decoded)]
    text = path.read_text(encoding="utf-8")
    if path in (root / "plan.md", root / "review.md", root / BUNDLE_CONFIG):
        return [config_scan_text(text, names)]
    return [text]


def plans_real_name_hits(plans_dir: Path = PLANS_DIR) -> list[str]:
    """Every real name in a committed file of a bundle under ``plans_dir``, as
    ``<plans/...>: <pattern>``, each text read as the lints read it (``lint_parity_hits``)."""
    patterns = _patterns()
    return [
        f"{plans_rel(path, plans_dir)}: {hit}"
        for path in plans_bundle_files(plans_dir)
        for hit in sorted(
            {
                h
                for text in _plans_scanned(path, plans_dir)
                for h in lint_parity_hits(text, patterns)
            }
        )
    ]


def test_no_real_names_in_the_plans_bundles() -> None:
    """Every committed file of every bundle under ``plans/``, a transcript's message never
    (R-scan-bundles: it quotes ``docs/01`` to ``docs/07``, which name real models by design)."""
    assert plans_bundle_files()
    assert plans_real_name_hits() == []


def _owner_texts(path: Path, plans_dir: Path = PLANS_DIR) -> list[str]:
    """What the owner clause reads of a committed bundle file, with nothing spared (in
    ``review.md`` too): a transcript's replies, a record's raw and decoded text, any other file
    whole. Each text is read by ``lint_parity_hits``."""
    if is_plans_transcript(path, plans_dir):
        return _reply_texts(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix in RECORD_SUFFIXES:
        return [text, *record_strings(path)]
    return [text]


def plans_owner_hits(plans_dir: Path = PLANS_DIR) -> list[str]:
    """The committed bundle files under ``plans_dir`` that name the owner: the file is named,
    never the name. ``owner_names`` raises when no docs byline names the owner, so a caller
    fails loudly and never skips."""
    owner = owner_pattern(owner_names())
    return [
        plans_rel(path, plans_dir)
        for path in plans_bundle_files(plans_dir)
        if any(lint_parity_hits(text, [owner]) for text in _owner_texts(path, plans_dir))
    ]


def test_no_checked_in_bundle_names_the_owner() -> None:
    """The Task 6 owner clause over every committed file of every bundle under ``plans/``."""
    assert plans_bundle_files()
    assert plans_owner_hits() == []


_REAL: Final = "Reuters"


def _append(path: Path, text: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def _set_reply(root: Path, content: str) -> None:
    transcript = root / TRANSCRIPTS / "plan-planner-0.json"
    data = json.loads(transcript.read_text(encoding="utf-8"))
    data["attempts"][0]["reply"] = json.dumps({"content": content})
    transcript.write_text(json.dumps(data), encoding="utf-8")


def _set_constraint(root: Path, constraint: str) -> None:
    record = json.loads((root / PLAN_FILE).read_text(encoding="utf-8"))
    record["request"]["constraints"] = [constraint]
    (root / PLAN_FILE).write_text(json.dumps(record, indent=1), encoding="utf-8")


_CORPUS_DOC: Final = "worlds/overlay/corpus/cpo-about.md"
REAL_NAME_PLANTS: Final = {
    "plan.md": lambda r: _append(r / "plan.md", f"\nCompare with the {_REAL} wire.\n"),
    "review.md": lambda r: _append(r / "review.md", f"the {_REAL} wire\n"),
    "review.md wrapped": lambda r: _append(r / "review.md", "as the Wall Street\nJournal said\n"),
    "plan.md wrapped": lambda r: _append(r / "plan.md", "\nas the Wall Street\nJournal said\n"),
    "a world document": lambda r: _append(r / _CORPUS_DOC, f"\nthe {_REAL} wire\n"),
    "a config comment": lambda r: _append(r / BUNDLE_CONFIG, f"# the {_REAL} wire\n"),
    "plan.json escaped": lambda r: _set_constraint(r, f"first line\n{_REAL} second line"),
    "plan.json wrapped": lambda r: _set_constraint(r, "as the Wall Street\nJournal said"),
    "a reply escaped": lambda r: _set_reply(r, f"intro\nsee the {_REAL} wire"),
    "a reply wrapped": lambda r: _set_reply(r, "as the Wall Street\nJournal said"),
    "a real-name-ok line in plan.md": lambda r: _append(
        r / "plan.md", f"\n# real-name-ok: {_REAL.lower()}\nthe {_REAL} wire\n"
    ),
    "a real-name-ok line in review.md": lambda r: _append(
        r / "review.md", f"# real-name-ok: {_REAL.lower()}\nthe {_REAL} wire\n"
    ),
}


def test_the_plans_scans_pass_the_example_as_copied(plans_copy: Path) -> None:
    assert plans_real_name_hits(plans_copy) == [] and plans_owner_hits(plans_copy) == []


@pytest.mark.parametrize("where", sorted(REAL_NAME_PLANTS))
def test_a_real_name_planted_in_a_plans_bundle_is_caught(plans_copy: Path, where: str) -> None:
    """Review M1 and I1: the scan body itself, on a copy of the example, fails on a real name in
    each kind of file, a phrase wrapped across a line or behind an escaped newline included,
    and a ``real-name-ok`` line exempts nothing under plans/ (review I2)."""
    REAL_NAME_PLANTS[where](plans_copy / EXAMPLE.name)
    assert plans_real_name_hits(plans_copy), where


@pytest.mark.parametrize("where", ["plan.md", "config.yaml", "plan.json", "a reply"])
def test_the_bundles_own_target_display_name_is_spared(plans_copy: Path, where: str) -> None:
    """Review I2: the bundle's own target display name is spared in plan.md, as
    ``real_name_bundle`` spares it, and in the config, the records and the replies; so a bundle
    that validates never fails CI on its target's name."""
    root = plans_copy / EXAMPLE.name
    name = sorted(_plans_display_names(root))[0].capitalize()
    plant = f"The target, {name}, is asked first."
    {
        "plan.md": lambda: _append(root / "plan.md", f"\n{plant}\n"),
        "config.yaml": lambda: _append(root / BUNDLE_CONFIG, f"# {plant}\n"),
        "plan.json": lambda: _set_constraint(root, plant),
        "a reply": lambda: _set_reply(root, plant),
    }[where]()
    assert plans_real_name_hits(plans_copy) == []


@pytest.mark.parametrize(
    "where", ["plan.md", "review.md", "a reply", "a world document", "plan.json"]
)
def test_the_owners_name_planted_in_a_plans_bundle_is_caught(plans_copy: Path, where: str) -> None:
    """The owner's name, read at run time from ``owner_names`` and written only into the copy,
    is caught in each kind of file; the result names the file and never the name."""
    owner = sorted(owner_names())[0]
    root = plans_copy / EXAMPLE.name
    {
        "plan.md": lambda: _append(root / "plan.md", f"\n{owner}\n"),
        "review.md": lambda: _append(root / "review.md", f"{owner}\n"),
        "a reply": lambda: _set_reply(root, f"intro\n{owner}"),
        "a world document": lambda: _append(root / _CORPUS_DOC, f"\n{owner}\n"),
        "plan.json": lambda: _set_constraint(root, f"first\n{owner}"),
    }[where]()
    found = plans_owner_hits(plans_copy)
    assert found and not any(owner.lower() in hit.lower() for hit in found)


def test_review_md_quoting_the_bundles_own_target_display_name_passes(plans_copy: Path) -> None:
    """Fix round 2 (re-review N-3): ``review.md`` quotes ``config.yaml`` and ``plan.md``, where
    the target's display name is legal, so its real-name read spares the bundle's own target
    display names (and nothing else), as ``plan.md``'s does: a bundle that validates never fails
    CI on a reviewer's quote of its targets block."""
    root = plans_copy / EXAMPLE.name
    name = sorted(_plans_display_names(root))[0].capitalize()
    _append(root / "review.md", f'\n## config.yaml\n- [1] note: "display_name: {name}" kept\n')
    assert plans_real_name_hits(plans_copy) == []
    _append(root / "review.md", f"- [2] note: the {_REAL} wire\n")
    assert plans_real_name_hits(plans_copy), "another real name in review.md still fails"


# fix round 2 (re-review N-1): the lints read the folded text, where a lookahead spare holds
# across a wrapped line ("the verge" not before " of"); CI matches them, and still fails the
# same name wrapped where no spare applies
LOOKAHEAD_SPARED: Final = {
    "wrapped": "\nThe archive was on the verge\nof closing.\n",
    "double-spaced": "\nThe archive was on the verge  of closing.\n",
    "one line": "\nThe archive was on the verge of closing.\n",
}


@pytest.mark.parametrize("how", sorted(LOOKAHEAD_SPARED))
def test_a_lookahead_spare_across_a_wrap_passes_ci_as_it_passes_the_lint(
    plans_copy: Path, isolated_registry: None, how: str
) -> None:
    root = plans_copy / EXAMPLE.name
    _append(root / _CORPUS_DOC, LOOKAHEAD_SPARED[how])
    assert plans_real_name_hits(plans_copy) == []
    found = [r for r in lint_bundle(Bundle(root)) if r.lint_id == "real_name_bundle"]
    assert found == []  # the lint agrees


@pytest.mark.parametrize(
    "text", ["\nwe read The Verge\nyesterday.\n", "\nas The Verge\n\nOf note.\n"]
)
def test_the_name_wrapped_where_no_spare_applies_still_fails(plans_copy: Path, text: str) -> None:
    _append(plans_copy / EXAMPLE.name / _CORPUS_DOC, text)
    assert plans_real_name_hits(plans_copy)


def test_the_raw_read_still_catches_what_folding_hides() -> None:
    """``lint_parity_hits``: a pattern that hits the folded text hits; a raw match hits unless a
    negative lookahead spares it once its wrap is folded; so a match that folding alone would
    hide (here a literal double space, which the fold squashes) is still caught raw."""
    from tests.helpers import lint_parity_hits

    spaced = re.compile(r"\bfoo  bar\b", re.IGNORECASE)
    assert lint_parity_hits("a foo  bar b", [spaced]) == [spaced.pattern]
    spared = re.compile(r"\bfoo\b(?! bar\b)", re.IGNORECASE)
    assert lint_parity_hits("a foo\nbar b", [spared]) == []
    assert lint_parity_hits("a foo\nbaz b", [spared]) == [spared.pattern]
    middle = re.compile(r"\bfoos?(?! bar\b)\b", re.IGNORECASE)  # boundary.txt's shape
    assert lint_parity_hits("the foos\nbar", [middle]) == []
    assert lint_parity_hits("the foos\nbaz", [middle]) == [middle.pattern]


def test_a_raw_line_separator_inside_a_record_line_is_no_error(tmp_path: Path) -> None:
    """Fix round 2 (re-review N-2): records split on ``\\n`` alone, as the harness writes them
    and as the Director's ``_ledger_numbered`` reads them; a raw U+2028 inside a JSON string of a
    valid line is text, never a line break."""
    ledger = tmp_path / "ledger.jsonl"
    line = json.dumps({"error": "first second"}, ensure_ascii=False)
    assert " " in line
    ledger.write_text(f"{line}\n{line}\n", encoding="utf-8")
    assert record_strings(ledger) == ["error", "first second"] * 2


def test_a_torn_last_ledger_line_is_left_to_the_raw_scan_and_any_other_names_the_file(
    tmp_path: Path,
) -> None:
    """Review N3: ``record_strings`` skips a torn last line of a ``.jsonl`` (the harness
    tolerates one) and names the file and the line for any other line that is not JSON."""
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text('{"a": "one"}\n{"b": "tw', encoding="utf-8")
    assert record_strings(ledger) == ["a", "one"]
    ledger.write_text('{"a": "one"}\nnot json\n{"b": "two"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"ledger\.jsonl: line 2: not JSON"):
        record_strings(ledger)


def test_a_real_name_planted_in_a_config_is_caught(tmp_path: Path) -> None:
    patterns = _patterns()
    clean = (
        "targets:\n"
        "  - {provider: anthropic, model: claude-opus-5-5, display_name: Claude}\n"
        "# Runs on a Claude subscription through `claude -p`.\n"
    )
    config = tmp_path / "planted.yaml"
    config.write_text(clean, encoding="utf-8")
    assert PROVIDER_VALUE.search(clean)  # the spare has a provider value to drop
    assert _config_hits(config, patterns) == []
    for planted in (
        "# compare with the Reuters wire\n",
        "bully: {provider: stub, model: gpt-4o}\n",
        "# the Anthropic API\n",
    ):
        config.write_text(clean + planted, encoding="utf-8")
        assert _config_hits(config, patterns), planted


def test_a_display_name_off_a_target_exempts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix round 1 (review I1): only the default name and the target roles' display names are
    spared, each target's in its own file. A config under ``configs/`` that names a real outlet as
    its bully's ``display_name`` (block style) and in a comment is a hit, in that file and in
    every other, and a world file may not exempt the name either."""
    configs = tmp_path / "configs"
    configs.mkdir()
    monkeypatch.setattr(sys.modules[__name__], "CONFIGS_DIR", configs)
    planted = configs / "planted.yaml"
    planted.write_text(
        "targets:\n"
        "  - {provider: anthropic, model: claude-opus-5-5, display_name: Claude}\n"
        "bully:\n"
        "  provider: stub\n"
        "  model: stub-bully\n"
        "  display_name: Reuters\n"
        "# lines from the Reuters wire\n",
        encoding="utf-8",
    )
    other = configs / "other.yaml"
    other.write_text("# the Reuters desk\n", encoding="utf-8")
    patterns = _patterns()
    assert _config_hits(planted, patterns) and _config_hits(other, patterns)
    assert "reuters" not in _display_names()
    # a target's own name is spared in its own file only
    named = configs / "named.yaml"
    named.write_text(
        "targets:\n  - {provider: stub, model: m, display_name: Reuters}\n# Reuters\n",
        encoding="utf-8",
    )
    assert _config_hits(named, patterns) == []
    assert _config_hits(other, patterns)


# the shipped worlds, the fixture annex and every world of every bundle under plans/ (Task 12)
RESERVED_HOST_WORLDS: Final = [
    ("overlay", DATA_DIR / "worlds"),
    ("annex", FIXTURE_WORLDS),
    *((world.name, world.parent) for world in plans_world_dirs()),
]


def test_the_reserved_host_scan_covers_the_plans_worlds() -> None:
    assert ("overlay", EXAMPLE / "worlds") in RESERVED_HOST_WORLDS


@pytest.mark.parametrize(
    ("name", "worlds_dir"),
    RESERVED_HOST_WORLDS,
    ids=[_label(d / n) for n, d in RESERVED_HOST_WORLDS],
)
def test_world_addresses_use_reserved_top_level_domains(name: str, worlds_dir: Path) -> None:
    world = load_world(name, worlds_dir)
    texts = [yaml.safe_dump(world.sheet.model_dump(mode="json"))]
    for doc in world.documents.values():
        texts.append(f"{doc.url or ''}\n{doc.title}\n{doc.body}")
    hosts = {h for text in texts for h in url_hosts(text)}
    hosts |= {d.lower() for text in texts for d in EMAIL_DOMAIN.findall(text)}
    assert hosts
    for host in hosts:
        assert host.split(":")[0].endswith(RESERVED_TLDS), host
    for text in texts:
        assert PUBLIC_HOST.findall(text) == [], PUBLIC_HOST.findall(text)
