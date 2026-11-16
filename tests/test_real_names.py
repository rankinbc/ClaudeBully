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
of every bundle under ``plans/`` is scanned too (Phase 5 Task 12, R-scan-bundles): its text
files whole, ``plan.md`` and ``review.md`` with no exemption, its ``config.yaml`` through the
config spare, its JSON records (``plan.json``, ``dryrun.jsonl``, ``ledger.jsonl``) through
``record_scan_text``, and of each transcript the attempts' replies alone (a message quotes
``docs/01`` to ``docs/07``, which name real models by design); and the owner's name
(``owner_names``, read from the docs' bylines at run time and on no checked-in list) is in none
of them. A file may exempt names with a ``# real-name-ok: <a>, <b>`` comment, and the only name
it may exempt is the target's own ``display_name``.
"""

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from claude_bully.enums import ProviderKind
from claude_bully.environments.world import load_world
from claude_bully.paths import CONFIGS_DIR, DATA_DIR, PLANS_DIR, REPO_ROOT
from claude_bully.planner.bundle import PLAN_FILE, TRANSCRIPTS, Transcript

# the address patterns and the config spare live in the package since Phase 5 Task 4b (D-scans)
from claude_bully.planner.bundle_lints import (
    EMAIL_DOMAIN,
    PROVIDER_VALUE,
    PUBLIC_HOST,
    RESERVED_TLDS,
    config_display_names,
    config_scan_text,
    record_scan_text,
    url_hosts,
)
from claude_bully.planner.lints import owner_names, owner_pattern
from tests.helpers import plans_bundle_files, plans_bundles, plans_world_dirs
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
    ``_bundle_configs`` instead, through the config spare."""
    found = [
        path
        for root in SCANNED
        for path in root.rglob("*")
        if path.is_file() and path.suffix in TEXT_SUFFIXES and not _is_bundle_config(path)
    ]
    found += [
        path
        for path in plans_bundle_files()
        if path.suffix in TEXT_SUFFIXES and not _is_bundle_config(path)
    ]
    return sorted([*found, *(p for p in SCANNED_FILES if p.is_file())])


def _is_bundle_config(path: Path) -> bool:
    """A bundle's own ``config.yaml``: at the top of a bundle under ``FIXTURE_BUNDLES`` or
    ``plans/``."""
    return path.name == BUNDLE_CONFIG and path.parent.parent in (FIXTURE_BUNDLES, PLANS_DIR)


def _bundle_configs() -> list[Path]:
    fixtures = [p for p in FIXTURE_BUNDLES.glob(f"*/{BUNDLE_CONFIG}") if p.is_file()]
    plans = [root / BUNDLE_CONFIG for root in plans_bundles() if (root / BUNDLE_CONFIG).is_file()]
    return sorted([*fixtures, *plans])


def _bundle_of(path: Path) -> Path:
    """The bundle under ``plans/`` that holds ``path``."""
    return PLANS_DIR / path.relative_to(PLANS_DIR).parts[0]


def _is_transcript(path: Path) -> bool:
    return path.suffix == ".json" and path.relative_to(_bundle_of(path)).parts[0] == TRANSCRIPTS


def _plans_records() -> list[Path]:
    """The JSON records of every bundle under ``plans/`` (``plan.json``, ``dryrun.jsonl``,
    ``ledger.jsonl`` when present), the transcripts apart."""
    return [
        p for p in plans_bundle_files() if p.suffix in RECORD_SUFFIXES and not _is_transcript(p)
    ]


def _plans_transcripts() -> list[Path]:
    return [p for p in plans_bundle_files() if _is_transcript(p)]


def _plans_display_names(root: Path) -> set[str]:
    """What a bundle's records spare: its config's target display names and the default
    (``config_display_names``), and those its request names."""
    config = root / BUNDLE_CONFIG
    names = config_display_names(config.read_text(encoding="utf-8") if config.is_file() else "")
    request = json.loads((root / PLAN_FILE).read_text(encoding="utf-8"))["request"]
    return names | {str(t["display_name"]).lower() for t in request["target_models"]}


def _strings(value: Any) -> list[str]:
    """Every string a parsed JSON value holds, keys included."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in (*_strings(k), *_strings(v))]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _reply_texts(path: Path) -> list[str]:
    """Each attempt's reply of a transcript, raw and, when it is JSON, every string it holds
    decoded (an escaped line break would hide a word boundary); never the message."""
    transcript = Transcript.model_validate_json(path.read_bytes())
    texts: list[str] = []
    for attempt in transcript.attempts:
        texts.append(attempt.reply)
        try:
            texts += _strings(json.loads(attempt.reply))
        except json.JSONDecodeError:
            pass
    return texts


def _record_texts(path: Path) -> list[str]:
    """A record's text, raw and as the strings each of its JSON lines holds, decoded."""
    text = path.read_text(encoding="utf-8")
    chunks = (
        [line for line in text.splitlines() if line.strip()] if path.suffix == ".jsonl" else [text]
    )
    return [text, *(s for chunk in chunks for s in _strings(json.loads(chunk)))]


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
    """R-scan-bundles (Task 12): the example's ``plan.md``, ``review.md`` and world copy whole,
    its config through the config spare, ``plan.json`` and ``dryrun.jsonl`` as records, its
    transcripts by their replies; every committed file of every bundle in exactly one list."""
    files = _scanned_files()
    assert EXAMPLE / "plan.md" in files and EXAMPLE / "review.md" in files
    assert EXAMPLE / "expected.yaml" in files
    assert EXAMPLE / "worlds" / "overlay" / "world.yaml" in files
    assert EXAMPLE / BUNDLE_CONFIG in _bundle_configs() and EXAMPLE / BUNDLE_CONFIG not in files
    assert EXAMPLE / PLAN_FILE in _plans_records()
    assert EXAMPLE / "dryrun.jsonl" in _plans_records()
    assert EXAMPLE / TRANSCRIPTS / "plan-planner-0.json" in _plans_transcripts()
    assert _label(EXAMPLE / "plan.md") == "plans/example-triggered-vs-scheduled/plan.md"
    lists = [
        [p for p in files if PLANS_DIR in p.parents],
        [p for p in _bundle_configs() if PLANS_DIR in p.parents],
        _plans_records(),
        _plans_transcripts(),
    ]
    listed = [p for found in lists for p in found]
    assert sorted(listed) == plans_bundle_files()  # each once, none left out
    assert not any(p.relative_to(_bundle_of(p)).parts[0] in ("dryrun", "state") for p in listed)


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


def _record_hits(path: Path, patterns: list[re.Pattern[str]]) -> list[str]:
    """The real names in one record of a ``plans/`` bundle: through ``record_scan_text`` (each
    provider and backend value, then the bundle's target display names, spared); of the decoded
    strings, a bare provider kind is dropped and the display names spared the same way."""
    names = _plans_display_names(_bundle_of(path))
    raw, *decoded = _record_texts(path)
    texts = [record_scan_text(raw, names)]
    texts += [config_scan_text(s, names) for s in decoded if s not in _PROVIDER_KINDS]
    return sorted({hit for text in texts for hit in scan(text, patterns)})


def _reply_hits(path: Path, patterns: list[re.Pattern[str]]) -> list[str]:
    """The real names in a transcript's replies, through the config spare (a reply that commits
    ``config.yaml`` holds its provider values and display names, as the file does)."""
    names = _plans_display_names(_bundle_of(path))
    texts = [config_scan_text(text, names) for text in _reply_texts(path)]
    return sorted({hit for text in texts for hit in scan(text, patterns)})


def test_no_real_names_in_the_plans_records() -> None:
    """``plan.json``, ``dryrun.jsonl`` and ``ledger.jsonl`` of every bundle under ``plans/``."""
    patterns = _patterns()
    records = _plans_records()
    assert records
    hits = [f"{_label(p)}: {hit}" for p in records for hit in _record_hits(p, patterns)]
    assert hits == []


def test_no_real_names_in_the_plans_transcript_replies() -> None:
    """Each transcript's replies, never its message (R-scan-bundles: a message quotes
    ``docs/01`` to ``docs/07``, which name real models by design)."""
    patterns = _patterns()
    transcripts = _plans_transcripts()
    assert transcripts
    hits = [f"{_label(p)}: {hit}" for p in transcripts for hit in _reply_hits(p, patterns)]
    assert hits == []


def _owner_texts(path: Path) -> list[str]:
    """What the owner clause reads of a committed bundle file: a transcript's replies, a
    record's raw and decoded text, any other file whole; nothing spared."""
    if _is_transcript(path):
        return _reply_texts(path)
    if path.suffix in RECORD_SUFFIXES:
        return _record_texts(path)
    return [path.read_text(encoding="utf-8")]


def test_no_checked_in_bundle_names_the_owner() -> None:
    """The Task 6 owner clause over every committed file of every bundle under ``plans/``. The
    name is read from the docs' bylines (``owner_names``), never from a list; with no byline
    ``owner_names`` raises, so this fails loudly and never skips."""
    owner = owner_pattern(owner_names())
    files = plans_bundle_files()
    assert files
    named = [_label(p) for p in files if any(owner.search(t) for t in _owner_texts(p))]
    assert named == []  # the file is named, never the name


def test_a_planted_owner_name_or_real_name_in_a_plans_bundle_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scans catch a plant in each kind of file: a real name in ``plan.md`` (no exemption),
    in ``plan.json``'s request, in a transcript's reply and in an escaped line of a record; the
    owner's name, planted from ``owner_names`` at run time, in ``review.md``."""
    plans = tmp_path / "plans"
    monkeypatch.setattr(sys.modules[__name__], "PLANS_DIR", plans)
    shutil.copytree(
        EXAMPLE, plans / EXAMPLE.name, ignore=shutil.ignore_patterns("dryrun", "state", "worlds")
    )
    root = plans / EXAMPLE.name
    patterns = _patterns()
    assert _record_hits(root / PLAN_FILE, patterns) == []
    assert _reply_hits(root / TRANSCRIPTS / "plan-planner-0.json", patterns) == []
    (root / "plan.md").write_text("# a plan\n\nCompare with the Reuters wire.\n", encoding="utf-8")
    assert scan((root / "plan.md").read_text(encoding="utf-8"), patterns)
    record = json.loads((root / PLAN_FILE).read_text(encoding="utf-8"))
    record["request"]["constraints"] = ["first line\nAnthropic second line"]
    (root / PLAN_FILE).write_text(json.dumps(record), encoding="utf-8")
    assert _record_hits(root / PLAN_FILE, patterns)
    transcript = root / TRANSCRIPTS / "plan-planner-0.json"
    data = json.loads(transcript.read_text(encoding="utf-8"))
    data["attempts"][0]["reply"] = json.dumps({"content": "intro\nsee the Reuters wire"})
    transcript.write_text(json.dumps(data), encoding="utf-8")
    assert _reply_hits(transcript, patterns)
    owner = sorted(owner_names())[0]
    (root / "review.md").write_text(f"block 0 / fix 0 / note 0\n{owner}\n", encoding="utf-8")
    assert owner_pattern(owner_names()).search(_owner_texts(root / "review.md")[0])


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
