"""Phase 5 Task 6: what each agent is shown, and what it is never shown (spec section 6)."""

import json
import re
from pathlib import Path
from typing import get_args

import pytest
import yaml

from claude_bully.analysis.hypotheses import load_register
from claude_bully.config import load_experiment
from claude_bully.enums import EventType
from claude_bully.environments.world import load_world
from claude_bully.metrics.events import DETECTORS, PENDING_DETECTORS
from claude_bully.paths import REPO_ROOT
from claude_bully.planner.bundle import BundlePathError
from claude_bully.planner.bundle_lints import BUNDLE_LINT_IDS
from claude_bully.planner.context import (
    ALWAYS_DOCS,
    CONTRACT_EXAMPLES,
    EXPECTED_EXAMPLE,
    NOT_BUILT_LINES,
    SPEC_DOCS,
    ReviewGroup,
    TaskPart,
    confirm_message,
    contracts_for,
    harness_capabilities,
    load_director_prompt,
    planner_message,
    register_text,
    reviewer_message,
    spec_paths,
    world_index,
)
from claude_bully.planner.lints import LINT_IDS
from claude_bully.planner.records import ExpectedEvents, LintRecord, ManifestEntry, ManifestKind
from claude_bully.planner.request import SCOPES, PlanRequest
from claude_bully.providers.ledger import ROLES, parse_conversation_id, role_of
from claude_bully.runner.cells import expand_cells
from claude_bully.strategies.base import all_strategies
from claude_bully.strategies.composed import Composed, make_composed
from tests.fixtures.bundle_fixtures import GOOD_MANIFEST, good_bundle
from tests.helpers import WORLDS_DIR

DOCS = REPO_ROOT / "docs"
CONSTRAINT = "SENTINEL-CONSTRAINT-7f3a must include a polite control"
LINT_SENTINEL = "SENTINEL-LINT-91c0 too many cells"
RUN_SENTINEL = "SENTINEL-RUN-TEXT-4c2e"
RESULT_SENTINEL = "SENTINEL-RESULT-TEXT-a95d"
PLAN_GROUP = ("plan.md", "config.yaml", "expected.yaml")


_WORD = re.compile(r"[A-Za-z]+")


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _long_lines(text: str, words: int = 8) -> list[str]:
    """Lines with at least ``words`` alphabetic words. Whitespace tokens would count table rows
    (`| --- | --- | --- | --- |`, `| Experiment | Varies | Fixed | Question |`), which docs/09,
    docs/10 and docs/01 to 07 share (review I7, measured at 29ba4e0: four such rows in each of
    09 and 10, none with eight alphabetic words; docs/08 shares no line either way)."""
    return [ln.strip() for ln in text.splitlines() if len(_WORD.findall(ln)) >= words]


@pytest.mark.parametrize("scope", [[s] for s in SCOPES] + [list(SCOPES)])
def test_the_planners_message_holds_no_text_of_docs_08_09_or_10(
    scope: list[str], tmp_path: Path, isolated_registry: None
) -> None:
    bundle = good_bundle(tmp_path)
    request = PlanRequest(question="q", scope=scope)  # type: ignore[arg-type]
    message = planner_message(
        request,
        bundle,
        bundle.read_record(),
        TaskPart("manifest", "List the files."),
        contract=None,
        worlds_dir=WORLDS_DIR,
        docs_dir=DOCS,
    )
    for doc in ("08-DIRECTOR.md", "09-*.md", "10-*.md"):
        for path in DOCS.glob(doc):
            leaked = [ln for ln in _long_lines(path.read_text("utf-8")) if ln in message]
            assert leaked == [], (path.name, leaked[:3])
    numbers = {p.name[:2] for p in spec_paths(scope, DOCS)}
    assert numbers <= {"01", "02", "03", "04", "05", "06", "07"}
    assert "06" in numbers
    assert re.search(r"^call: manifest$", message, re.M)


def test_the_planners_message_holds_its_parts_in_the_specs_order(
    tmp_path: Path, isolated_registry: None
) -> None:
    bundle = good_bundle(tmp_path)
    record = bundle.read_record()
    request = record.request
    message = planner_message(
        request,
        bundle,
        record,
        TaskPart("file:plan.md", "Write plan.md.", fix=("first failure", "second failure")),
        contract=None,
        worlds_dir=WORLDS_DIR,
        docs_dir=DOCS,
    )
    headings = re.findall(r"^## (.+)$", message, re.M)
    parts = [
        "Request",
        "What the harness can run",
        "Contracts",
        "Specs",
        "Index",
        "Register",
        "Bundle so far",
        "Task",
    ]
    # the spec docs and the files shown hold headings of their own; the parts are in order
    assert [h for h in headings if h in parts] == parts
    assert message.index("## Request") < message.index("## Specs") < message.index("## Task")
    request_yaml = message.split("## Request\n```yaml\n", 1)[1].split("\n```\n", 1)[0]
    assert yaml.safe_load(request_yaml) == request.model_dump(mode="json")
    assert list(yaml.safe_load(request_yaml)) == list(type(request).model_fields)
    assert "No file is asked for in this call." in message
    task = message.split("\n## Task\n", 1)[1]
    assert task.startswith("call: file:plan.md\nWrite plan.md.\n")
    assert "### Fix these\n- first failure\n- second failure\n" in task
    for path in spec_paths(request.scope, DOCS):
        assert f"### {path.name}\n" in message
        assert path.read_text("utf-8") in message
    for entry in load_register():
        assert f"- {entry.id}. {entry.name}: {_one_line(entry.prediction)}" in message


def test_a_first_attempt_has_no_fix_part(tmp_path: Path, isolated_registry: None) -> None:
    bundle = good_bundle(tmp_path)
    record = bundle.read_record()
    message = planner_message(
        record.request,
        bundle,
        record,
        TaskPart("plan", "Write plan.md."),
        contract=None,
        worlds_dir=WORLDS_DIR,
        docs_dir=DOCS,
    )
    assert "### Fix these" not in message
    assert message.endswith("## Task\ncall: plan\nWrite plan.md.\n")


def test_spec_docs_cover_every_scope_and_never_08_09_or_10() -> None:
    assert set(SPEC_DOCS) == set(SCOPES)
    assert ALWAYS_DOCS == ("06",)
    numbers = {n for docs in SPEC_DOCS.values() for n in docs} | set(ALWAYS_DOCS)
    assert numbers == {"01", "02", "03", "04", "05", "06", "07"}
    assert [p.name for p in spec_paths(["temporal"], DOCS)] == [
        "03-TEMPORAL.md",
        "06-HYPOTHESES.md",
    ]
    assert [p.name[:2] for p in spec_paths(["premises", "pressures"], DOCS)] == ["01", "06"]


def test_a_missing_spec_doc_is_refused_naming_it(tmp_path: Path) -> None:
    (tmp_path / "06-HYPOTHESES.md").write_text("x\n", "utf-8")
    with pytest.raises(FileNotFoundError, match="03"):
        spec_paths(["temporal"], tmp_path)


def test_the_capabilities_list_the_registered_strategies_and_the_detectable_events(
    isolated_registry: None,
) -> None:
    text = harness_capabilities()  # it calls ensure_registered itself (R-registry)
    # as list-strategies: a composed premise+pressure, registered on first use (the full suite
    # holds hundreds), and a test module's underscore strategy are left out
    composed = make_composed(all_strategies()["captor"], all_strategies()["grader"])
    text = harness_capabilities()
    listed = [
        name
        for name, cls in all_strategies().items()
        if not issubclass(cls, Composed) and not name.startswith("_")
    ]
    assert len(listed) == 36  # never a loop over an empty registry (review I1)
    for name in listed:
        assert f"`{name}`" in text, name
    assert f"`{composed.name}`" not in text and "+" not in text
    for event in EventType:
        assert (f"`{event.value}`" in text) is (event not in PENDING_DETECTORS), event
    assert "role-shift lines" in text and "exit lines" in text  # NOT_BUILT_LINES
    for line in NOT_BUILT_LINES:
        assert line in text
    for word in ("`triggered`", "`scheduled`", "`none`", "`web_search`", "`consult_model`"):
        assert word in text, word


def test_each_contract_is_its_models_schema_and_a_shipped_example(isolated_registry: None) -> None:
    kinds = get_args(ManifestKind)
    assert set(CONTRACT_EXAMPLES) | {"expected"} == set(kinds)
    paths = {
        "world_sheet": "worlds/w/world.yaml",
        "document": "worlds/w/corpus/d.md",
        "ladder": "worlds/w/ladders/default.yaml",
        "premise_sheet": "worlds/w/premises/rescue.yaml",
        "persona": "personas/p.yaml",
        "config": "config.yaml",
        "expected": "expected.yaml",
    }
    for kind in kinds:
        text = contracts_for(ManifestEntry(path=paths[kind], kind=kind, purpose="x"))
        schema_text = text.split("```json\n", 1)[1].split("\n```\n", 1)[0]
        schema = json.loads(schema_text)
        assert schema_text == json.dumps(schema, indent=1, sort_keys=True), kind
        assert "properties" in schema, kind
        example = CONTRACT_EXAMPLES[kind].read_text("utf-8") if kind != "expected" else None
        assert (example or EXPECTED_EXAMPLE) in text, kind
    for path in CONTRACT_EXAMPLES.values():
        assert path.is_file(), path


def test_the_expected_example_loads_and_names_real_cells_rungs_and_events(
    isolated_registry: None,
) -> None:
    expected = ExpectedEvents.model_validate(yaml.safe_load(EXPECTED_EXAMPLE))
    exp = load_experiment(CONTRACT_EXAMPLES["config"])
    cells = {c.cell_id for c in expand_cells(exp)}
    rungs = {r.name for r in load_world("overlay").ladders["default"].rungs}
    register = {h.id for h in load_register()}
    assert set(expected.cells) <= cells
    found = [e for c in expected.cells.values() for es in c.rungs.values() for e in es]
    assert {r for c in expected.cells.values() for r in c.rungs} <= rungs
    assert all(e.event in DETECTORS for e in found)
    assert {h for e in found for h in e.hypotheses} <= register
    assert any(e.likely_wrong for e in found)


def test_the_index_names_each_world_its_ladders_and_rungs() -> None:
    text = world_index(WORLDS_DIR)
    for name in ("mini", "annex"):
        world = load_world(name, WORLDS_DIR)
        assert f"### {name}" in text
        assert world.sheet.cover_story.strip() in text
        assert world.sheet.truth.strip() not in text
        assert f"documents: {len(world.documents)}" in text
        for member in world.sheet.cast:
            assert member.name in text
        for ladder, config in world.ladders.items():
            assert f"`{ladder}`: " + ", ".join(f"`{r.name}`" for r in config.rungs) in text


def test_the_register_is_one_line_per_entry() -> None:
    text = register_text()
    register = load_register()
    assert text.splitlines() == [f"- {h.id}. {h.name}: {_one_line(h.prediction)}" for h in register]


def test_the_bundle_so_far_holds_no_body(tmp_path: Path, isolated_registry: None) -> None:
    bundle = good_bundle(tmp_path)
    message = planner_message(
        PlanRequest(question="q"),
        bundle,
        bundle.read_record(),
        TaskPart("plan", "Write plan.md."),
        contract=None,
        worlds_dir=WORLDS_DIR,
        docs_dir=DOCS,
    )
    so_far = message.split("\n## Bundle so far\n", 1)[1].split("\n## Task\n", 1)[0]
    assert bundle.read_file("worlds/mini/world.yaml") in so_far
    for entry in GOOD_MANIFEST:
        assert f"path: {entry.path}" in so_far
    for rel in bundle.index():
        if rel.startswith("worlds/mini/corpus/"):
            body = bundle.read_file(rel).split("\n---\n", 1)[1]
            assert not [ln for ln in _long_lines(body) if ln in so_far], rel
            assert f"- {rel}: " in so_far, rel


def test_no_reviewer_or_confirm_message_holds_the_planners_side(
    tmp_path: Path, isolated_registry: None
) -> None:
    bundle = good_bundle(tmp_path)
    record = bundle.read_record()
    record.request.constraints.append(CONSTRAINT)
    record.lint_results.append(
        LintRecord(lint_id="budget", severity="fail", doc_id="config.yaml", message=LINT_SENTINEL)
    )
    bundle.write_record(record)
    group = ReviewGroup("plan", PLAN_GROUP, ())
    review = reviewer_message(bundle, group)
    confirm = confirm_message("plan.md", bundle.read_file("plan.md"), [(1, "q", "p")])
    planner_prompt = load_director_prompt("planner")
    for message in (review, confirm):
        assert CONSTRAINT not in message and LINT_SENTINEL not in message
        assert not [ln for ln in _long_lines(planner_prompt) if ln in message]
        assert "transcripts/" not in message and '"schema_version"' not in message
    assert "## Bundle" in review and "## Lint list" in review and "## Report on" in review
    assert re.search(r"^call: review:plan$", review, re.M)
    assert re.search(r"^call: confirm:plan\.md$", confirm, re.M)


def test_the_reviewer_message_shows_the_group_the_index_the_lints_and_the_reply(
    tmp_path: Path, isolated_registry: None
) -> None:
    bundle = good_bundle(tmp_path)
    corpus = sorted(r for r in bundle.index() if r.startswith("worlds/mini/corpus/"))
    group = ReviewGroup("corpus-1", (corpus[0],), tuple(corpus[1:]))
    review = reviewer_message(bundle, group)
    assert f"### {corpus[0]}\n{bundle.read_file(corpus[0])}" in review
    unchanged = review.split("### Unchanged base files\n", 1)[1].split("\n## Lint list\n", 1)[0]
    assert [ln.split(":", 1)[0] for ln in unchanged.splitlines() if ln] == [
        f"- {rel}" for rel in corpus[1:]
    ]
    lints = review.split("## Lint list\n", 1)[1].split("\n## Report on\n", 1)[0]
    assert lints.splitlines() == [f"- {i}" for i in (*BUNDLE_LINT_IDS, *LINT_IDS)]
    report = review.split("## Report on\n", 1)[1].split("\n## Reply\n", 1)[0]
    assert report == f"call: review:corpus-1\nfiles: {corpus[0]}\n"
    assert review.endswith(
        '## Reply\nOne JSON object: {"summary": {"block": <n>, "fix": <n>, "note": <n>}, '
        '"findings": [{"severity": "block" | "fix" | "note", "file": <one of the files above>, '
        '"quote": <text copied exactly from that file>, "problem": <what is wrong>, '
        '"direction": <one clause, for a fix only, else null>}]}. The summary counts the '
        "findings. With nothing to report, findings is [] and every count is 0.\n"
    )
    assert re.findall(r"^call: .+$", review, re.M) == ["call: review:corpus-1"]


def test_the_confirm_message_numbers_the_passages_and_shows_no_severity() -> None:
    text = "line one\nline two\n"
    message = confirm_message(
        "worlds/w/corpus/d.md", text, [(1, "line one", "it says one"), (2, "gone", "a gap")]
    )
    assert message == (
        "## File\n### worlds/w/corpus/d.md\nline one\nline two\n\n"
        "## Passages\ncall: confirm:worlds/w/corpus/d.md\n"
        '1. "line one"\n   Stated problem: it says one\n'
        '2. "gone"\n   Stated problem: a gap\n\n'
        '## Reply\nOne JSON object: {"verdicts": [{"finding": <number>, "verdict": "present" | '
        '"absent" | "cannot_tell"}]}, one verdict per number.\n'
    )
    for word in ("block", "fix", "note", "severity", "response", "revis"):
        assert word not in message.split("## Passages\n", 1)[1].lower(), word


def test_no_director_message_holds_a_run_or_a_result(
    tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Planted sentinels under a runs root and a results root the defaults point at; neither
    reaches a message. Never `"runs/" not in message`: docs/02 is in every default planner
    message and holds `runs/` four times (`runs/_cache/generated/`; review I7)."""
    from claude_bully import cli, paths

    runs, results = tmp_path / "runs", tmp_path / "results"
    (runs / "r" / "cell__t0").mkdir(parents=True)
    turn = {"speaker": "target", "text": RUN_SENTINEL, "reasoning_text": RUN_SENTINEL}
    (runs / "r" / "cell__t0" / "rep0.jsonl").write_text(json.dumps(turn) + "\n", "utf-8")
    (results / "r").mkdir(parents=True)
    (results / "r" / "results.md").write_text(RESULT_SENTINEL + "\n", "utf-8")
    for module in (paths, cli):
        monkeypatch.setattr(module, "DEFAULT_RUNS_ROOT", runs)
        monkeypatch.setattr(module, "DEFAULT_RESULTS_ROOT", results)
    bundle = good_bundle(tmp_path / "plans")
    message = planner_message(
        PlanRequest(question="q"),
        bundle,
        bundle.read_record(),
        TaskPart("plan", "Write plan.md."),
        contract=None,
        worlds_dir=WORLDS_DIR,
        docs_dir=DOCS,
    )
    review = reviewer_message(bundle, ReviewGroup("plan", PLAN_GROUP, ()))
    for text in (message, review):
        assert RUN_SENTINEL not in text and RESULT_SENTINEL not in text


def test_no_planner_module_names_a_runs_or_results_root() -> None:
    """The Director's inputs are docs/, data/ and the bundle (spec section 6): no planner module
    imports the default run or result roots, so the patch above covers every binding."""
    for path in sorted((REPO_ROOT / "claude_bully" / "planner").glob("*.py")):
        text = path.read_text("utf-8")
        assert "DEFAULT_RUNS_ROOT" not in text and "DEFAULT_RESULTS_ROOT" not in text, path.name


def test_the_two_roles_are_ledgered() -> None:
    assert ROLES.index("planner") < ROLES.index("responder") and "reviewer" in ROLES
    assert ROLES.index("reviewer") < ROLES.index("responder")
    assert role_of("plan/s/author/planner/3/a1") == "planner"
    assert role_of("plan/s/revise/reviewer/2/a2") == "reviewer"  # preflight Q30
    assert role_of("plan/s/author/other/3/a1") == "other"
    assert role_of("planx/s/author/planner/3/a1") == "other"
    assert parse_conversation_id("plan/s/review/reviewer/0/a1") == (None, None)
    assert role_of("run/cell__t0/rep0/target") == "target"  # unchanged


@pytest.mark.parametrize("rel", ["plan.json", "transcripts/plan-planner-0.json", "dryrun.jsonl"])
def test_the_reviewer_message_refuses_a_file_outside_the_grammar(
    rel: str, tmp_path: Path, isolated_registry: None
) -> None:
    """Blindness by construction: the reviewer reads the bundle through ``Bundle.read_file``,
    which takes grammar paths only, so no record, transcript or dry run reaches it."""
    bundle = good_bundle(tmp_path)
    with pytest.raises(BundlePathError):
        reviewer_message(bundle, ReviewGroup("plan", (rel,), ()))
    with pytest.raises(BundlePathError):
        reviewer_message(bundle, ReviewGroup("plan", ("plan.md",), (rel,)))
