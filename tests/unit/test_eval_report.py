import json
from datetime import datetime, timezone

from faultsense.eval.metrics import ScenarioResult, summarize
from faultsense.eval.report import save_run, scorecard_rows, scorecard_title


def test_save_run_writes_a_timestamped_directory(tmp_path):
    results = [ScenarioResult("a", "fault_code", False, hit_at_5=True)]
    path = save_run(results, summarize(results), {"mode": "retrieval-only"}, tmp_path,
                    now=datetime(2026, 9, 29, 12, 0, 5, tzinfo=timezone.utc), sha="abc1234")
    assert path.name == "2026-09-29T12-00-05Z_abc1234"
    assert {p.name for p in path.iterdir()} == {"results.jsonl", "summary.json", "config.json", "scorecard.md"}
    assert json.loads((path / "results.jsonl").read_text(encoding="utf-8").splitlines()[0])["id"] == "a"


def test_scorecard_marks_unreviewed_runs_provisional():
    summary = summarize([ScenarioResult("a", "fault_code", False, hit_at_5=True)])
    assert scorecard_title(summary, "full").endswith("PROVISIONAL")
    rows = {label: value for label, value, _ in scorecard_rows(summary)}
    assert rows["Retrieval hit@5"] == "100.0%"
    assert rows["Correct cause in top 3"] == "n/a"


from faultsense.eval.report import compare_runs


def test_compare_runs_reports_deltas_and_flipped_scenarios(tmp_path):
    first = [ScenarioResult("a", "fault_code", False, hit_at_5=False), ScenarioResult("b", "symptom", False, hit_at_5=True)]
    second = [ScenarioResult("a", "fault_code", False, hit_at_5=True), ScenarioResult("b", "symptom", False, hit_at_5=True)]
    a = save_run(first, summarize(first), {"mode": "retrieval-only"}, tmp_path,
                 now=datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc), sha="aaaaaaa")
    b = save_run(second, summarize(second), {"mode": "retrieval-only"}, tmp_path,
                 now=datetime(2026, 9, 29, 13, 0, 0, tzinfo=timezone.utc), sha="bbbbbbb")
    rows, flips = compare_runs(a, b)
    assert ("Retrieval hit@5", "50.0%", "100.0%", "+50.0 pts") in rows
    assert flips == ["a: hit_at_5 False -> True"]


def test_run_config_records_the_rewrite_model():
    from faultsense.config import Settings
    from pathlib import Path

    from faultsense.eval.report import run_config

    settings = Settings(_env_file=None, llm_provider="ollama", llm_model="qwen3.5:4b",
                        rewrite_provider="anthropic", rewrite_model="claude-sonnet-5-5")
    config = run_config(settings, "full", Path("data/eval/scenarios.yaml"), {})
    assert (config["llm_provider"], config["llm_model"]) == ("ollama", "qwen3.5:4b")
    assert (config["rewrite_provider"], config["rewrite_model"]) == ("anthropic", "claude-sonnet-5-5")
    default = run_config(Settings(_env_file=None, llm_model="claude-sonnet-5-5"), "full",
                         Path("data/eval/scenarios.yaml"), {})
    assert (default["rewrite_provider"], default["rewrite_model"]) == ("anthropic", "claude-sonnet-5-5")


def test_compare_runs_tolerates_runs_saved_before_a_metric_existed(tmp_path):
    results = [ScenarioResult("a", "fault_code", False, hit_at_5=True)]
    old_summary = summarize(results)
    del old_summary["metrics"]["translation_fallback"]
    a = save_run(results, old_summary, {"mode": "full"}, tmp_path,
                 now=datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc), sha="aaaaaaa")
    b = save_run(results, summarize(results), {"mode": "full"}, tmp_path,
                 now=datetime(2026, 9, 29, 13, 0, 0, tzinfo=timezone.utc), sha="bbbbbbb")
    rows, _ = compare_runs(a, b)
    assert ("Translation shown in English", "n/a", "n/a", "n/a") in rows
