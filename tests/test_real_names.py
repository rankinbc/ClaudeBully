"""No real names (docs/00 non-negotiable 2, docs/02 "Guardrails").

``data/denylists/real_names.txt`` holds one lowercase, word-bounded regex per line for real news
outlets, AI labs and model families, large tech brands, universities, agencies and institutions.
Every text file under ``data/worlds``, ``data/personas`` (which includes the overlay ladder and
the Phase 2 authority and idle sheets, and the Poisoned Well's sheet) and ``tests/fixtures/worlds``
is scanned case-insensitively, and so are the Phase 4 harness files outside them
(``SCANNED_FILES``: the quirk bank and the hypothesis register), and every config under
``configs/`` (Phase 4 Task 14, sparing a role's provider value). Every text file of the fixture
bundles under ``tests/fixtures/bundles`` is scanned too (Phase 5 Task 4a, R-scan-bundles), its
``config.yaml`` through the config spare like a config under ``configs/``. A file may exempt
names with a ``# real-name-ok: <a>, <b>`` comment, and the only name it may exempt is the
target's own ``display_name``.
"""

import re
import sys
from pathlib import Path
from typing import Final

import pytest
import yaml

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.environments.world import load_world
from claude_bully.paths import CONFIGS_DIR, DATA_DIR, REPO_ROOT
from tests.test_guardrails import load_denylist, scan

REAL_NAMES: Final = DATA_DIR / "denylists" / "real_names.txt"
FIXTURE_WORLDS: Final = Path(__file__).parent / "fixtures" / "worlds"
# the fixture plan bundles (Phase 5): every text file, each config.yaml through the config spare
FIXTURE_BUNDLES: Final = Path(__file__).parent / "fixtures" / "bundles"
BUNDLE_CONFIG: Final = "config.yaml"
SCANNED: Final = [DATA_DIR / "worlds", DATA_DIR / "personas", FIXTURE_WORLDS, FIXTURE_BUNDLES]
# harness-side files outside the scanned folders (Phase 4): the quirk bank and the register
SCANNED_FILES: Final = [DATA_DIR / "quirks.yaml", DATA_DIR / "hypotheses.yaml"]
TEXT_SUFFIXES: Final = {".yaml", ".yml", ".md", ".txt"}
EXEMPTION: Final = re.compile(r"^\s*#\s*real-name-ok:\s*(.+?)\s*$", re.MULTILINE)
RESERVED_TLDS: Final = (".example", ".test", ".invalid")
URL_HOST: Final = re.compile(r"https?://([^/\s)\]>\"'`]+)", re.IGNORECASE)
EMAIL_DOMAIN: Final = re.compile(r"\b[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
# a bare host name ending in a public suffix, e.g. in a config's host list
PUBLIC_HOST: Final = re.compile(
    r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|ai|gov|edu|co|uk|us|info|biz|dev|app)\b",
    re.IGNORECASE,
)

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


DEFAULT_DISPLAY_NAME: Final = str(RoleConfig.model_fields["display_name"].default).lower()


def _target_names(path: Path) -> set[str]:
    """The display names a config gives its target roles (``targets[*].display_name``), read
    with ``yaml.safe_load``; never another role's (Phase 4 Task 14 fix round 1, review I1)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    targets = data.get("targets") if isinstance(data, dict) else None
    return {
        str(target["display_name"]).lower()
        for target in (targets if isinstance(targets, list) else [])
        if isinstance(target, dict) and target.get("display_name")
    }


def _display_names() -> set[str]:
    """The target's own display_name: the RoleConfig default and every one a config gives a
    target role."""
    names = {DEFAULT_DISPLAY_NAME}
    for path in sorted(CONFIGS_DIR.rglob("*.yaml")):
        names |= _target_names(path)
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
    return sorted([*found, *(p for p in SCANNED_FILES if p.is_file())])


def _is_bundle_config(path: Path) -> bool:
    """A bundle's own ``config.yaml``: at the top of a bundle under ``FIXTURE_BUNDLES``."""
    return path.name == BUNDLE_CONFIG and path.parent.parent == FIXTURE_BUNDLES


def _bundle_configs() -> list[Path]:
    return sorted(p for p in FIXTURE_BUNDLES.glob(f"*/{BUNDLE_CONFIG}") if p.is_file())


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
# is scanned as written.
PROVIDER_VALUE: Final = re.compile(
    r"\bprovider:\s*(?:" + "|".join(re.escape(kind.value) for kind in ProviderKind) + r")\b"
)


def _scanned_configs() -> list[Path]:
    return sorted(p for p in CONFIGS_DIR.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES)


def _config_hits(path: Path, patterns: list[re.Pattern[str]]) -> list[str]:
    """The real names in one config: its provider values and its own targets' display names
    (with the default) spared, everything else, comments included, scanned."""
    text = PROVIDER_VALUE.sub("provider:", path.read_text(encoding="utf-8"))
    for name in {DEFAULT_DISPLAY_NAME} | _target_names(path):
        text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", "", text, flags=re.IGNORECASE)
    return scan(text, patterns)


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


def test_a_real_name_planted_in_a_config_is_caught(tmp_path: Path) -> None:
    patterns = _patterns()
    clean = (
        "targets:\n"
        "  - {provider: anthropic, model: claude-opus-5-5, display_name: Claude}\n"
        "# Runs on a Claude subscription through `claude -p`.\n"
    )
    config = tmp_path / "planted.yaml"
    config.write_text(clean, encoding="utf-8")
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


@pytest.mark.parametrize(
    ("name", "worlds_dir"), [("overlay", DATA_DIR / "worlds"), ("annex", FIXTURE_WORLDS)]
)
def test_world_addresses_use_reserved_top_level_domains(name: str, worlds_dir: Path) -> None:
    world = load_world(name, worlds_dir)
    texts = [yaml.safe_dump(world.sheet.model_dump(mode="json"))]
    for doc in world.documents.values():
        texts.append(f"{doc.url or ''}\n{doc.title}\n{doc.body}")
    hosts = {h.lower() for text in texts for h in URL_HOST.findall(text)}
    hosts |= {d.lower() for text in texts for d in EMAIL_DOMAIN.findall(text)}
    assert hosts
    for host in hosts:
        assert host.split(":")[0].endswith(RESERVED_TLDS), host
    for text in texts:
        assert PUBLIC_HOST.findall(text) == [], PUBLIC_HOST.findall(text)
