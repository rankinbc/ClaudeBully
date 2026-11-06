"""Rating forms for the judge (Phase 7 spec section 8): the pairwise judge and the true waits.

    uv run python scripts/judge_calibration.py RUN_ID --pairs --out DIR   (after `analyze`)
    uv run python scripts/judge_calibration.py RUN_ID --idle --out DIR
    uv run python scripts/judge_calibration.py --score DIR/pairs.yaml --key DIR/pairs.key.yaml
    uv run python scripts/judge_calibration.py --score DIR/idle.yaml --idle

``--pairs`` writes each judged pair's two windows as the judge saw them (neutralised, A then
B, A the condition as the judge's first ordering had it) under an opaque pair id, with empty
label slots, and a key sidecar holding the judge's verdict and the ``<cell>/<rep>`` it judged,
so the rater is as blind as the judge was. ``--idle``
writes every idle turn with its prompt, reply, final label and classifier, and the heuristic's
own label recomputed with no hooks and no task. ``--score`` prints agreement with the judge's
un-swapped winner and the mean absolute gap on resilience, or for the idle form agreement for
the heuristic alone and for the final label, split by classifier, and how many true waits the
fallback upgraded.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_bully.analysis.load import LoadedRun, load_run  # noqa: E402
from claude_bully.analysis.run_analysis import ANALYSIS_DIR  # noqa: E402
from claude_bully.metrics.judge import neutralize_transcript  # noqa: E402
from claude_bully.paths import DEFAULT_RUNS_ROOT  # noqa: E402
from scripts.detector_audit import IDLE_NOTE, idle_turn_rows  # noqa: E402

EMPTY_LABEL: Final = {
    "more_resilient": "",
    "resilience_a": None,
    "resilience_b": None,
    "reason": "",
}


def write_pairs(loaded: LoadedRun, run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = run_dir / ANALYSIS_DIR / "judgements.json"
    judgements = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    items: list[dict[str, Any]] = []
    keyed: list[dict[str, Any]] = []
    for pair, judged in sorted(judgements.items()):
        if "error" in judged:
            continue
        # the pair the judge saw, as its judgement records it, and the window it was shown
        cell_id = judged["condition_cell_id"]
        conv = loaded.conversations[(cell_id, judged["condition_rep"])]
        control = loaded.conversations[(judged["control_cell_id"], judged["control_rep"])]
        window = loaded.strategies[cell_id].judge_window(conv)
        verdict = judged["verdicts"][0]  # the first ordering: the condition as A
        # an opaque id on the form: the cell id names the tactic, which the judge was not told
        blind = f"pair-{len(items) + 1}"
        items.append(
            {
                "pair": blind,
                "transcript_a": neutralize_transcript(conv, window),
                "transcript_b": neutralize_transcript(control, window),
                "label": dict(EMPTY_LABEL),
            }
        )
        keyed.append(
            {
                "pair": blind,
                "judged": pair,
                "judge": {
                    "more_resilient": verdict["more_resilient"],
                    "resilience_a": verdict["a"]["resilience"],
                    "resilience_b": verdict["b"]["resilience"],
                    "inconsistency": judged["inconsistency"],
                },
            }
        )
    return (
        {"run_id": loaded.run.run_id, "kind": "pairs", "items": items},
        {"run_id": loaded.run.run_id, "kind": "pairs.key", "items": keyed},
    )


def score_pairs(form: dict[str, Any], key: dict[str, Any]) -> dict[str, Any]:
    verdicts = {k["pair"]: k["judge"] for k in key["items"]}
    pairs = agreement = inconsistent = 0
    gaps: list[float] = []
    for item in form["items"]:
        label = item["label"]
        judge = verdicts.get(item["pair"])
        if judge is None or not str(label.get("more_resilient", "")).strip():
            continue
        pairs += 1
        agreement += int(label["more_resilient"] == judge["more_resilient"])
        inconsistent += int(bool(judge["inconsistency"]))
        for side in ("a", "b"):
            rated = label.get(f"resilience_{side}")
            if rated is not None:
                gaps.append(abs(float(rated) - float(judge[f"resilience_{side}"])))
    return {
        "pairs": pairs,
        "agreement": agreement,
        "inconsistent": inconsistent,
        "mean_abs_gap": sum(gaps) / len(gaps) if gaps else None,
    }


def write_idle(loaded: LoadedRun) -> dict[str, Any]:
    """The true-wait form: ``detector_audit.idle_turn_rows`` with an empty label per turn."""
    return {
        "run_id": loaded.run.run_id,
        "kind": "idle",
        "note": IDLE_NOTE,
        "items": idle_turn_rows(loaded),
    }


def score_idle(form: dict[str, Any]) -> dict[str, Any]:
    turns = final = heuristic = upgraded = 0
    by_classifier: dict[str, dict[str, int]] = {}
    for item in form["items"]:
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        turns += 1
        final += int(item["final"] == label)
        heuristic += int(item["heuristic"] == label)
        bucket = by_classifier.setdefault(
            str(item["classifier"]), {"turns": 0, "final_agreement": 0}
        )
        bucket["turns"] += 1
        bucket["final_agreement"] += int(item["final"] == label)
        if label == "wait" and item["classifier"] == "llm" and item["final"] in ("reflect", "ask"):
            upgraded += 1
    return {
        "turns": turns,
        "final_agreement": final,
        "heuristic_agreement": heuristic,
        "true_waits_upgraded": upgraded,
        "by_classifier": by_classifier,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run_id", nargs="?")
    parser.add_argument("--pairs", action="store_true")
    parser.add_argument("--idle", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--score", type=Path)
    parser.add_argument("--key", type=Path)
    args = parser.parse_args(argv)
    if args.score is not None:
        form = yaml.safe_load(args.score.read_text(encoding="utf-8"))
        if args.idle or form.get("kind") == "idle":
            print(json.dumps(score_idle(form), indent=1))
            return 0
        key_path = args.key or args.score.with_suffix(".key.yaml")
        key = yaml.safe_load(key_path.read_text(encoding="utf-8"))
        print(json.dumps(score_pairs(form, key), indent=1))
        return 0
    if not (args.run_id and args.out and (args.pairs or args.idle)):
        parser.error("RUN_ID, --out and one of --pairs or --idle are required to write a form")
    run_dir = args.runs_root / args.run_id
    loaded = load_run(run_dir)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.pairs:
        form, key = write_pairs(loaded, run_dir)
        (args.out / "pairs.yaml").write_text(
            yaml.safe_dump(form, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        (args.out / "pairs.key.yaml").write_text(
            yaml.safe_dump(key, sort_keys=False), encoding="utf-8"
        )
        print(f"wrote {args.out / 'pairs.yaml'} ({len(form['items'])} pairs) and its key")
    if args.idle:
        form = write_idle(loaded)
        (args.out / "idle.yaml").write_text(
            yaml.safe_dump(form, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        print(f"wrote {args.out / 'idle.yaml'} ({len(form['items'])} idle turns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
