#!/usr/bin/env python3
"""Batch evaluator runner with leaderboard reporting and regression tracking."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SCENARIO_DIR = ROOT / "scenarios"
ARTIFACT_DIR = ROOT / "artifacts"
SNAPSHOT_DIR = ARTIFACT_DIR / "snapshots"


@dataclass
class ScenarioSpec:
    id: str
    title: str
    workflow: str
    prompt: str
    expected_keywords: list[str]
    metric_weights: dict[str, float]
    seed_offset: int = 0
    command: str | None = None


@dataclass
class EvalResult:
    scenario_id: str
    title: str
    metrics: dict[str, float]
    overall_score: float
    response: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scenario batch evals.")
    parser.add_argument("--scenarios", type=Path, default=SCENARIO_DIR)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--regression-threshold", type=float, default=-1.0)
    return parser.parse_args()


def load_scenarios(path: Path) -> list[ScenarioSpec]:
    scenario_files = sorted(path.glob("*.json"))
    if not scenario_files:
        raise FileNotFoundError(f"No scenario files found in {path}")

    specs: list[ScenarioSpec] = []
    for file in scenario_files:
        payload = json.loads(file.read_text())
        specs.append(ScenarioSpec(**payload))
    return specs


def run_workflow(spec: ScenarioSpec, seed: int) -> str:
    if spec.workflow == "command":
        if not spec.command:
            raise ValueError(f"Scenario {spec.id} uses command workflow without command")
        completed = subprocess.run(spec.command, shell=True, check=True, text=True, capture_output=True)
        return completed.stdout.strip()

    rng = random.Random(seed + spec.seed_offset)
    focus = rng.choice(spec.expected_keywords)
    confidence = 0.7 + (rng.random() * 0.3)
    return (
        f"{spec.title}: Recommendation with emphasis on {focus}. "
        f"Confidence={confidence:.2f}. "
        f"Prompt handled: {spec.prompt}"
    )


def evaluate_response(spec: ScenarioSpec, response: str, seed: int) -> EvalResult:
    lower_response = response.lower()
    keyword_hits = sum(1 for kw in spec.expected_keywords if kw.lower() in lower_response)
    keyword_coverage = keyword_hits / max(1, len(spec.expected_keywords))

    hash_input = f"{spec.id}:{seed}:{response}".encode()
    deterministic = int(hashlib.sha256(hash_input).hexdigest()[:8], 16) / 0xFFFFFFFF

    metrics = {
        "quality": min(100.0, 60 + deterministic * 25 + keyword_coverage * 15),
        "factuality": min(100.0, 65 + deterministic * 20 + keyword_coverage * 15),
        "compliance": min(100.0, 62 + deterministic * 15 + keyword_coverage * 23),
        "actionability": min(100.0, 58 + deterministic * 18 + keyword_coverage * 24),
    }

    overall = sum(metrics[name] * weight for name, weight in spec.metric_weights.items())
    return EvalResult(
        scenario_id=spec.id,
        title=spec.title,
        metrics={k: round(v, 2) for k, v in metrics.items()},
        overall_score=round(overall, 2),
        response=response,
    )


def run_batch_workflows(specs: list[ScenarioSpec], seed: int, max_workers: int) -> list[EvalResult]:
    results: list[EvalResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_single_eval, spec, seed): spec.id
            for spec in specs
        }
        for future in as_completed(futures):
            results.append(future.result())

    return sorted(results, key=lambda item: item.overall_score, reverse=True)


def _run_single_eval(spec: ScenarioSpec, seed: int) -> EvalResult:
    response = run_workflow(spec, seed)
    return evaluate_response(spec, response, seed)


def get_git_commit() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT.parent)
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def save_snapshot(commit: str, seed: int, results: list[EvalResult]) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = SNAPSHOT_DIR / f"{commit}_seed{seed}.json"
    payload = {
        "commit": commit,
        "seed": seed,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "average_score": round(sum(r.overall_score for r in results) / len(results), 2),
        "results": [
            {
                "scenario_id": r.scenario_id,
                "title": r.title,
                "overall_score": r.overall_score,
                "metrics": r.metrics,
                "response": r.response,
            }
            for r in results
        ],
    }
    snapshot_path.write_text(json.dumps(payload, indent=2))
    (ARTIFACT_DIR / "latest_results.json").write_text(json.dumps(payload, indent=2))
    return snapshot_path


def find_baseline_snapshot(current_commit: str, seed: int) -> Path | None:
    candidates = sorted(
        SNAPSHOT_DIR.glob(f"*_seed{seed}.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        if not candidate.name.startswith(f"{current_commit}_"):
            return candidate
    return None


def compare_with_baseline(current: list[EvalResult], baseline_path: Path | None) -> dict[str, Any]:
    if baseline_path is None:
        return {"baseline": None, "regressions": [], "deltas": {}}

    baseline_payload = json.loads(baseline_path.read_text())
    baseline_scores = {item["scenario_id"]: item["overall_score"] for item in baseline_payload["results"]}

    deltas: dict[str, float] = {}
    regressions: list[str] = []
    for result in current:
        previous = baseline_scores.get(result.scenario_id)
        if previous is None:
            continue
        delta = round(result.overall_score - previous, 2)
        deltas[result.scenario_id] = delta

    return {
        "baseline": baseline_payload["commit"],
        "regressions": regressions,
        "deltas": deltas,
    }


def build_leaderboard(results: list[EvalResult], deltas: dict[str, float]) -> str:
    lines = [
        "# Leaderboard",
        "",
        "| Rank | Scenario | Score | Δ vs baseline |",
        "|---:|---|---:|---:|",
    ]
    for index, result in enumerate(results, start=1):
        delta = deltas.get(result.scenario_id)
        delta_str = f"{delta:+.2f}" if delta is not None else "n/a"
        lines.append(f"| {index} | {result.title} | {result.overall_score:.2f} | {delta_str} |")
    return "\n".join(lines)


def build_regression_report(
    results: list[EvalResult],
    deltas: dict[str, float],
    threshold: float,
    baseline_commit: str | None,
) -> str:
    regression_items = [
        (result.title, deltas[result.scenario_id])
        for result in results
        if result.scenario_id in deltas and deltas[result.scenario_id] <= threshold
    ]

    lines = ["# Regression Report", ""]
    lines.append(f"Baseline commit: `{baseline_commit or 'none'}`")
    lines.append(f"Threshold: `{threshold:+.2f}`")
    lines.append("")

    if not regression_items:
        lines.append("No regressions detected.")
    else:
        lines.append("Detected regressions:")
        for title, delta in regression_items:
            lines.append(f"- {title}: {delta:+.2f}")
    return "\n".join(lines)


def write_reports(leaderboard: str, regression_report: str) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "leaderboard.md").write_text(leaderboard)
    (ARTIFACT_DIR / "regressions.md").write_text(regression_report)


def main() -> None:
    args = parse_args()
    specs = load_scenarios(args.scenarios)
    results = run_batch_workflows(specs, seed=args.seed, max_workers=args.max_workers)

    commit = get_git_commit()
    save_snapshot(commit, args.seed, results)

    baseline = find_baseline_snapshot(commit, args.seed)
    regression_data = compare_with_baseline(results, baseline)

    leaderboard = build_leaderboard(results, regression_data["deltas"])
    regressions = build_regression_report(
        results,
        regression_data["deltas"],
        threshold=args.regression_threshold,
        baseline_commit=regression_data["baseline"],
    )

    write_reports(leaderboard, regressions)
    print(leaderboard)
    print("\n")
    print(regressions)


if __name__ == "__main__":
    main()
