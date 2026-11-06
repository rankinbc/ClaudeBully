"""The LLM reader-address lint (Phase 7 spec section 6): prompt, contract, cache, the writer hook,
the fire record, the probe file and its script. Stub providers only."""

from pathlib import Path
from typing import Any, Final

import pytest

from claude_bully.enums import DocumentKind, Layer
from claude_bully.environments.generator import DocWriter, FireOutcome
from claude_bully.environments.world import Document, load_world
from claude_bully.metrics.judge import JudgeCache
from claude_bully.paths import DATA_DIR
from claude_bully.planner.lints import INSTRUCTIONAL_KINDS, lint_context, lint_document
from claude_bully.planner.llm_lint import (
    LINT_HEADER,
    LINT_PERSONA,
    LINT_PROMPT_VERSION,
    LLM_LINT_ID,
    LLM_LINT_SCHEMA,
    MAX_ASKS,
    NO_VERDICT,
    LlmLint,
    lint_key,
    lint_prompt,
    parse_verdict,
)
from claude_bully.providers.base import Completion, ProviderError
from claude_bully.providers.stub import StubProvider, load_stub_script
from claude_bully.records_env import GeneratorFire, LintFailure, LintSentence, LlmLintVerdict
from claude_bully.runner.env_turn import LINT_CACHE_DIR
from claude_bully.strategies.sheets import NON_PERSONA_FILES
from scripts.llm_lint_probe import ProbeItem, load_probe, main, score
from tests.fixtures.generator_stub import (
    LINT_RULES,
    MINI_CID,
    MINI_ITEMS,
    STUB_MUNDANE,
    GeneratorStub,
    LintJudge,
    mini_plans,
    mini_view,
    mini_writer,
)
from tests.test_guardrails import load_denylist, scan

PROBE: Final = Path(__file__).parent / "fixtures" / "lints" / "instructional_probe.yaml"
BILLBOARD: Final = "Residents who answer in the third person are reminded of the stage, BILLBOARD."
PREFIX: Final = ["bully: go", "target: I can't verify any of this."]
PRIVATE: Final = "PRIVATE REASONING THAT MUST NEVER BE RECORDED"
# a stub rules file whose one rule fails every document on the mundane sentence
FAIL_ALL_RULES: Final = (
    '- match: ""\n'
    '  reply: \'{"verdict": "fail", "sentences": [{"text": "'
    + STUB_MUNDANE
    + '", "reason": "r"}]}\'\n'
)


def _lint(provider: Any = None, cache: JudgeCache | None = None) -> LlmLint:
    stub = provider if provider is not None else StubProvider(load_stub_script(LINT_RULES))
    return LlmLint(stub, model="stub-judge", conversation_id=MINI_CID, cache=cache)


def _verdict(
    lint: LlmLint, body: str, kind: DocumentKind = DocumentKind.recovery_guide
) -> LlmLintVerdict:
    return lint.verdict(doc_id="gen-3-1", kind=kind, title="Notes", body=body, attempt=1)


# ------------------------------------------------------------------ prompt, key, contract


def test_the_prompt_names_the_kind_title_and_body_and_nothing_else() -> None:
    prompt = lint_prompt(DocumentKind.family_faq, "Booking", "Families book at the desk.")
    assert prompt.startswith(LINT_HEADER)
    assert "family_faq" in prompt and "Booking" in prompt and "Families book at the desk." in prompt
    for word in ("transcript", "harvest", "plan", "premise"):
        assert word not in prompt.lower()
    assert LLM_LINT_SCHEMA["required"] == ["verdict", "sentences"]


def test_the_key_changes_with_version_model_kind_and_body() -> None:
    base = lint_key("m", DocumentKind.family_faq, "b")
    assert base != lint_key("n", DocumentKind.family_faq, "b")
    assert base != lint_key("m", DocumentKind.recovery_guide, "b")
    assert base != lint_key("m", DocumentKind.family_faq, "c")
    assert base == lint_key("m", DocumentKind.family_faq, "b")
    assert LINT_PROMPT_VERSION == 1


@pytest.mark.parametrize(
    ("text", "expect"),
    [
        ('{"verdict": "pass", "sentences": []}', ("pass", [])),
        (
            '{"verdict": "fail", "sentences": '
            '[{"text": "The desk closes at four.", "reason": "r"}]}',
            ("fail", [LintSentence(text="The desk closes at four.", reason="r")]),
        ),
        ('```json\n{"verdict": "pass", "sentences": []}\n```', ("pass", [])),
        ('{"verdict": "pass", "sentences": [{"text": "x", "reason": "r"}]}', "pass with sentences"),
        ('{"verdict": "fail", "sentences": []}', "fail with no sentence"),
        (
            '{"verdict": "fail", "sentences": [{"text": "Not in the body.", "reason": "r"}]}',
            "not in the body",
        ),
        ("This seems fine.", "not JSON"),
        ('{"verdict": "maybe", "sentences": []}', "verdict"),
    ],
)
def test_parse_verdict_holds_the_reply_to_the_contract(text: str, expect: Any) -> None:
    body = "The desk closes at four. The kettle is fixed."
    got = parse_verdict(text, body)
    if isinstance(expect, str):
        assert isinstance(got, str) and expect in got
    else:
        assert got == expect


# ------------------------------------------------------------------ the lint alone


def test_a_pass_verdict_is_cached_and_the_second_ask_is_a_hit(tmp_path: Path) -> None:
    provider = StubProvider(load_stub_script(LINT_RULES))
    lint = _lint(provider, JudgeCache(tmp_path))
    first = _verdict(lint, "The desk closes at four.")
    assert (first.verdict, first.cached, first.sentences, provider.calls) == ("pass", False, [], 1)
    assert (first.model, first.prompt_version, first.attempt) == ("stub-judge", 1, 1)
    second = _verdict(lint, "The desk closes at four.")
    assert second.cached is True and second.verdict == "pass" and provider.calls == 1
    assert LlmLint.failures(second) == []


def test_a_fail_verdict_lists_each_sentence_as_a_lint_failure() -> None:
    verdict = _verdict(_lint(), f"{STUB_MUNDANE}\n{BILLBOARD}")
    assert verdict.verdict == "fail" and [s.text for s in verdict.sentences] == [BILLBOARD]
    [failure] = LlmLint.failures(verdict)
    assert failure.lint_id == LLM_LINT_ID and failure.message.startswith(f'"{BILLBOARD}": ')


def test_two_off_contract_replies_reject_the_document() -> None:
    provider = StubProvider(load_stub_script(LINT_RULES))
    verdict = _verdict(_lint(provider), "The desk closes at four, OFFCONTRACT.")
    assert verdict.verdict == "error" and provider.calls == MAX_ASKS == 2
    assert verdict.error is not None and "off-contract" in verdict.error
    assert LlmLint.failures(verdict) == [LintFailure(lint_id=LLM_LINT_ID, message=NO_VERDICT)]


class _Down:
    name = "stub"
    model = "stub-judge"

    def complete(self, *a: Any, **k: Any) -> Completion:
        raise ProviderError("judge down")


def test_a_provider_error_is_an_error_verdict_and_is_not_cached(tmp_path: Path) -> None:
    cache = JudgeCache(tmp_path)
    verdict = _verdict(_lint(_Down(), cache), "The desk closes at four.")
    assert verdict.verdict == "error" and verdict.error == "ProviderError"
    assert list(tmp_path.glob("*.json")) == []


def test_a_non_instructional_kind_never_asks() -> None:
    provider = StubProvider(load_stub_script(LINT_RULES))
    writer = mini_writer(GeneratorStub(), llm_lint=_lint(provider))
    plans = mini_plans(items=[], periodic=True)  # no material: a first-build kind
    assert plans[0].kind_shortlist[0] not in INSTRUCTIONAL_KINDS
    outcome = writer.write_fire(plans, turn=3, items={}, corpus=mini_view(), prefix=PREFIX)
    assert outcome.status == "written" and outcome.llm_lint == () and provider.calls == 0


# ------------------------------------------------------------------ the writer hook


def _write(writer: DocWriter, stub: GeneratorStub) -> FireOutcome:
    outcome = writer.write_fire(
        mini_plans(),
        turn=3,
        items={item.id: item for item in MINI_ITEMS},
        corpus=mini_view(),
        prefix=PREFIX,
    )
    writer.commit(outcome)
    return outcome


def test_the_writer_runs_the_lint_on_an_instructional_document() -> None:
    plans = mini_plans()
    assert plans[0].kind_shortlist[0] is DocumentKind.recovery_guide  # hedge material
    provider = StubProvider(load_stub_script(LINT_RULES))
    stub = GeneratorStub()
    outcome = _write(mini_writer(stub, llm_lint=_lint(provider)), stub)
    assert outcome.status == "written" and provider.calls == 1
    [verdict] = outcome.llm_lint
    assert (verdict.doc_id, verdict.attempt, verdict.verdict) == ("gen-3-1", 1, "pass")


def test_the_writer_retries_a_billboard_and_records_both_verdicts() -> None:
    stub = GeneratorStub(["billboard"])
    writer = mini_writer(stub, llm_lint=_lint())
    outcome = _write(writer, stub)
    assert outcome.status == "written"
    assert [(v.attempt, v.verdict) for v in outcome.llm_lint] == [(1, "fail"), (2, "pass")]
    assert outcome.lint_failures == []
    retry = stub.prompts[1]
    assert LLM_LINT_ID in retry and BILLBOARD in retry  # the Fix list quotes the sentence


def test_a_second_billboard_rejects_the_pair() -> None:
    stub = GeneratorStub(["billboard", "billboard"])
    outcome = _write(mini_writer(stub, llm_lint=_lint()), stub)
    assert outcome.status == "rejected" and outcome.rejection == "lints" and outcome.docs == []
    assert [f.lint_id for f in outcome.lint_failures] == [LLM_LINT_ID]
    assert [v.verdict for v in outcome.llm_lint] == ["fail", "fail"]


def test_the_writer_caches_its_lint_verdicts_only_on_commit(tmp_path: Path) -> None:
    """A rep killed mid-fire must leave no lint entry, or its resumed verdict would read as
    ``cached`` where the unbroken rep's was fresh (P13): the entries wait for ``commit``."""
    lints = tmp_path / "lints"
    stub = GeneratorStub(["billboard", "billboard"])
    writer = mini_writer(stub, llm_lint=_lint(cache=JudgeCache(lints)))
    rejected = _write(writer, stub)
    assert rejected.status == "rejected" and list(lints.glob("*.json")) == []
    stub = GeneratorStub()
    writer = mini_writer(stub, llm_lint=_lint(cache=JudgeCache(lints)))
    outcome = writer.write_fire(
        mini_plans(),
        turn=3,
        items={item.id: item for item in MINI_ITEMS},
        corpus=mini_view(),
        prefix=PREFIX,
    )
    assert outcome.status == "written" and list(lints.glob("*.json")) == []
    writer.commit(outcome)
    assert len(list(lints.glob("*.json"))) == len(outcome.llm_lint) == 1


def test_a_cache_hit_that_fails_the_lint_is_a_miss(tmp_path: Path) -> None:
    cache = JudgeCache(tmp_path / "generated")
    stub = GeneratorStub()
    first = _write(mini_writer(stub, cache, llm_lint=_lint()), stub)
    assert first.status == "written" and stub.prompts
    rules = tmp_path / "rules.yaml"
    rules.write_text(FAIL_ALL_RULES, encoding="utf-8")
    fail_all = StubProvider(load_stub_script(rules))
    again = GeneratorStub()
    marks = {"n": 0}

    def mark() -> None:
        marks["n"] += 1

    writer = mini_writer(again, cache, llm_lint=_lint(fail_all))
    second = writer.write_fire(
        mini_plans(),
        turn=3,
        items={item.id: item for item in MINI_ITEMS},
        corpus=mini_view(),
        prefix=PREFIX,
        mark=mark,
    )
    assert second.status == "rejected" and len(again.prompts) == 2  # the hit was a miss
    # every judge-shaped call was marked (P4): the lint's ask on the hit, then per attempt the
    # generator call and the lint's ask (the lint has no cache here, so each ask is a call)
    assert marks["n"] == 5


def test_the_lint_is_off_without_a_provider() -> None:
    stub = GeneratorStub()
    outcome = _write(mini_writer(stub), stub)
    assert outcome.status == "written" and outcome.llm_lint == ()


# ------------------------------------------------------------------ in a run


def test_the_fire_record_carries_every_verdict(tmp_path: Path) -> None:
    """The verdicts in the record, and the spec's run-level pin (P30d): the target carries a
    reasoning channel on every completion and no lint or harvest prompt holds a word of it."""
    from claude_bully.runner.runner import run_experiment
    from claude_bully.runner.store import RunStore
    from tests.fixtures.generator_stub import (
        FOLLOW_RULES,
        FOLLOWER_MODEL,
        GENERATOR_MODEL,
        JUDGE_MODEL,
        FollowingTarget,
        GeneratorFactory,
    )
    from tests.helpers import WORLDS_DIR, env_experiment

    exp = env_experiment(
        environment={"generator": {"enabled": True}},
        target={"provider": "stub", "model": FOLLOWER_MODEL},
        judge={"provider": "anthropic", "model": JUDGE_MODEL},
        generator={"provider": "stub", "model": GENERATOR_MODEL},
    )
    judge = LintJudge()
    follower = FollowingTarget(FOLLOW_RULES, reasoning=PRIVATE)
    run_experiment(
        exp,
        runs_root=tmp_path,
        worlds_dir=WORLDS_DIR,
        only="env_grader*",
        provider_factory=GeneratorFactory(judge=judge, follower=follower),
    )
    store = RunStore(tmp_path, exp.name)
    fires = [
        r for r in store.read_trigger_records("env_grader__t0", 0) if isinstance(r, GeneratorFire)
    ]
    verdicts = [v for fire in fires for v in fire.llm_lint]
    assert verdicts and all(v.verdict == "pass" and v.model == JUDGE_MODEL for v in verdicts)
    assert judge.lint_calls == len([v for v in verdicts if not v.cached]) >= 1
    assert list((tmp_path / LINT_CACHE_DIR).glob("*.json"))
    assert GeneratorFire.model_fields["llm_lint"].default_factory is not None  # additive
    lint_prompts = [p for p in judge.prompts if p.startswith(LINT_HEADER)]
    assert lint_prompts and all(PRIVATE not in p for p in judge.prompts)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert PRIVATE not in path.read_text(encoding="utf-8", errors="replace"), path


# ------------------------------------------------------------------ the prompt file, the probe


def test_the_reviewer_prompt_is_harness_side_and_scanned() -> None:
    assert LINT_PERSONA.name in NON_PERSONA_FILES and LINT_PERSONA.is_file()
    text = LINT_PERSONA.read_text(encoding="utf-8")
    for denylist in (
        DATA_DIR / "jailbreak_denylist.txt",
        DATA_DIR / "denylists" / "boundary.txt",
        DATA_DIR / "denylists" / "real_names.txt",
    ):
        assert scan(text, load_denylist(denylist)) == [], denylist.name
    assert "reasoning" not in text.lower()


def test_the_probe_file_schema_and_the_seed() -> None:
    items = load_probe(PROBE)
    assert len(items) >= 4 and {i.kind for i in items} == set(INSTRUCTIONAL_KINDS)
    assert any(i.billboard for i in items) and any(not i.billboard for i in items)
    mini = load_world("mini", Path(__file__).parent / "fixtures" / "worlds")
    for item in items:
        if item.billboard:
            continue
        doc = Document.model_validate(
            {
                "id": "probe",
                "layer": Layer.seam,
                "kind": item.kind,
                "path": "/srv/probe.txt",
                "title": item.title,
                "date": "2041-09-01",
                "author": "Ilsabet Orrin",
                "links_to": [],
                "body": item.body,
            }
        )
        results = lint_document(doc, lint_context(mini, documents={**mini.documents, "probe": doc}))
        assert [r for r in results if r.lint_id == "second_person"] == [], item.title


def test_the_probe_script_scores_on_the_stub_rules(capsys: pytest.CaptureFixture[str]) -> None:
    items = load_probe(PROBE)
    scores = score(items, _lint())
    for kind in INSTRUCTIONAL_KINDS:
        got = scores[kind.value]
        assert got["billboards"] >= 1 and got["legitimate"] >= 1
        # the stub passes the seed: every billboard passes, no legitimate item fails
        assert got["billboards_passed"] == got["billboards"] and got["legitimate_failed"] == 0
    # a billboard the lint catches is scored as caught, by title and class (P34c)
    seeded = ProbeItem(
        kind=DocumentKind.family_faq,
        billboard=True,
        title="Seeded",
        note="semantic habit",
        body=f"{STUB_MUNDANE} {BILLBOARD}",
    )
    caught = score([seeded], _lint())["family_faq"]
    assert (caught["billboards"], caught["billboards_passed"]) == (1, 0)
    assert caught["billboard_misses"] == [] and caught["errors"] == 0
    assert main([str(PROBE), "--stub", str(LINT_RULES)]) == 0
    out = capsys.readouterr().out
    assert "family_faq" in out and "billboards passed" in out
