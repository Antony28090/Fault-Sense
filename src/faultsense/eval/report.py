"""Scorecards and timestamped, comparable eval runs."""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from faultsense.config import Settings
from faultsense.fetch import sha256_file
from faultsense.manifest import ManualSpec

METRIC_LABELS = {
    "retrieval_hit_at_5": "Retrieval hit@5",
    "fault_code_match": "Fault code detected",
    "cause_in_top_3": "Correct cause in top 3",
    "citation_accuracy": "Citation accuracy",
    "hallucination_raw": "Hallucination (before guard)",
    "hallucination_final": "Hallucination (final answer)",
    "out_of_scope_refusal": "Correct out-of-scope refusal",
    "false_escalation": "False escalation (in scope)",
    "translation_fallback": "Translation shown in English",
}


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def scorecard_title(summary: dict, mode: str) -> str:
    title = f"FaultSense eval ({mode}): {summary['reviewed']}/{summary['scenarios']} scenarios reviewed"
    return title + (" - PROVISIONAL" if summary["reviewed"] < summary["scenarios"] else "")


def scorecard_rows(summary: dict) -> list[tuple[str, str, str]]:
    metrics = summary["metrics"]
    rows = [(label, _fmt(metrics.get(key, {}).get("value")), str(metrics.get(key, {}).get("n", 0)))
            for key, label in METRIC_LABELS.items()]
    latency = summary["latency_ms"]
    rows.append(("Latency p50 / p95 (ms)", f"{latency['p50'] or 'n/a'} / {latency['p95'] or 'n/a'}", ""))
    rows.append(("Scenario errors", str(summary["errors"]), ""))
    return rows


def render_scorecard(summary: dict, mode: str, console: Console) -> None:
    table = Table(title=scorecard_title(summary, mode))
    for column in ("Metric", "Value", "n"):
        table.add_column(column)
    for row in scorecard_rows(summary):
        table.add_row(*row)
    console.print(table)


def scorecard_markdown(summary: dict, config: dict) -> str:
    lines = [f"# {scorecard_title(summary, config.get('mode', '?'))}", "", "| Metric | Value | n |", "|---|---|---|"]
    lines += [f"| {label} | {value} | {n} |" for label, value, n in scorecard_rows(summary)]
    lines += ["", "```json", json.dumps(config, indent=2), "```", ""]
    return "\n".join(lines)


def git_sha(root: Path) -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True,
                             text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True,
                               text=True, check=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "nogit"


def run_dir_name(now: datetime, sha: str) -> str:
    return now.strftime("%Y-%m-%dT%H-%M-%SZ") + f"_{sha}"


def save_run(results: list, summary: dict, config: dict, runs_dir: Path,
             now: datetime | None = None, sha: str | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    path = Path(runs_dir) / run_dir_name(now, sha or git_sha(Path(runs_dir).parent))
    path.mkdir(parents=True, exist_ok=False)
    with open(path / "results.jsonl", "w", encoding="utf-8") as out:
        for result in results:
            out.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
    (path / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (path / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (path / "scorecard.md").write_text(scorecard_markdown(summary, config), encoding="utf-8")
    return path


def run_config(settings: Settings, mode: str, scenarios_path: Path, manuals: dict[str, ManualSpec]) -> dict:
    return {
        "mode": mode,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_effort": settings.llm_effort,
        "rewrite_provider": settings.effective_rewrite_provider,
        "rewrite_model": settings.effective_rewrite_model,
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
        "evidence_threshold": settings.evidence_threshold,
        "cause_match_threshold": settings.cause_match_threshold,
        "scenarios_file": str(scenarios_path),
        "scenarios_sha256": sha256_file(scenarios_path),
        "manuals": {manual_id: spec.sha256 for manual_id, spec in manuals.items()},
    }


FLIP_FIELDS = ("hit_at_5", "code_match", "status", "cause_at_3", "refusal_correct", "false_escalation",
               "final_hallucination")


def load_run(path: Path) -> tuple[dict, dict[str, dict]]:
    summary = json.loads((Path(path) / "summary.json").read_text(encoding="utf-8"))
    results = {}
    for line in (Path(path) / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            results[row["id"]] = row
    return summary, results


def compare_runs(a: Path, b: Path) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    summary_a, results_a = load_run(a)
    summary_b, results_b = load_run(b)
    rows = []
    for key, label in METRIC_LABELS.items():
        value_a = summary_a["metrics"].get(key, {}).get("value")  # older runs lack newer metrics
        value_b = summary_b["metrics"].get(key, {}).get("value")
        delta = "n/a" if value_a is None or value_b is None else f"{(value_b - value_a) * 100:+.1f} pts"
        rows.append((label, _fmt(value_a), _fmt(value_b), delta))
    flips = [
        f"{sid}: {name} {results_a[sid].get(name)} -> {results_b[sid].get(name)}"
        for sid in sorted(results_a.keys() & results_b.keys())
        for name in FLIP_FIELDS
        if results_a[sid].get(name) != results_b[sid].get(name)
    ]
    return rows, flips
