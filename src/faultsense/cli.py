"""`faultsense` command-line interface."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from faultsense.config import Settings, get_settings
from faultsense.manifest import ManualSpec, load_manuals

app = typer.Typer(
    help="FaultSense: Altivar drive diagnostic assistant (Phase 1).", no_args_is_help=True
)
console = Console(soft_wrap=True)  # log lines stay on one line (and stay greppable)


@app.callback()
def main() -> None:
    """FaultSense command-line tools."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def _manuals(settings: Settings) -> list[ManualSpec]:
    return load_manuals(settings.data_dir / "manuals.yaml")


@app.command("fetch-manuals")
def fetch_manuals_cmd() -> None:
    """Download the manuals in data/manuals.yaml and verify their SHA-256."""
    from faultsense.fetch import fetch_manuals

    settings = get_settings()
    results = fetch_manuals(_manuals(settings), settings.manuals_dir)
    for manual_id, status in results:
        console.print(f"{manual_id}: {status}")
    if any(status == "checksum-mismatch" for _, status in results):
        raise typer.Exit(1)


def _extract_all(settings: Settings, manual: Optional[str]) -> list:
    from faultsense.ingest import extract as extract_mod

    specs = [spec for spec in _manuals(settings) if manual is None or spec.id == manual]
    if not specs:
        console.print(f"[red]Unknown manual {escape(repr(manual))}[/red]")
        raise typer.Exit(2)
    extracted = []
    for spec in specs:
        console.print(f"Extracting {spec.id} ...")
        ex = extract_mod.extract_manual(spec, settings.manuals_dir)
        extract_mod.save_extraction(ex, settings.processed_dir)
        extracted.append(ex)
    extract_mod.write_report_file(extracted, settings.processed_dir / "extraction_report.json")
    return extracted


def _print_reports(extracted: list) -> bool:
    table = Table(title="Extraction report")
    for column in ("manual", "fault codes", "sections", "safety", "rejected", "missing", "problems"):
        table.add_column(column)
    for ex in extracted:
        r = ex.report
        table.add_row(ex.spec.id, str(r.fault_records), str(r.section_chunks), str(r.safety_chunks),
                      str(len(r.rejected)), str(len(r.missing_from_extraction)), "; ".join(r.problems) or "none")
    console.print(table)
    for ex in extracted:
        r, mid = ex.report, ex.spec.id
        for row in r.rejected:
            console.print(f"[yellow]{mid} p{row.page}: rejected ({escape(row.reason)}): {escape(row.raw)}[/yellow]")
        for code in r.missing_from_extraction:
            console.print(f"[yellow]{mid}: {escape(code)} is listed by the cross-check but was not extracted[/yellow]")
        for line in r.unparsed_index_lines:
            console.print(f"[yellow]{mid}: unparsed index line {escape(line)}[/yellow]")
        for duplicate in r.duplicate_codes:
            console.print(f"[yellow]{mid}: duplicate code {escape(duplicate)}[/yellow]")
        for mismatch in r.page_number_mismatches:
            console.print(f"[yellow]{mid}: {escape(mismatch)}[/yellow]")
        if r.confusable_pairs:
            console.print(f"{mid}: look-alike code pairs (both real): {escape(', '.join(r.confusable_pairs))}")
        for note in r.notes:
            console.print(f"[dim]{mid}: {escape(note)}[/dim]")
    return any(ex.report.problems for ex in extracted)


def _check_reports(extracted: list, accept_report: bool) -> None:
    if _print_reports(extracted) and not accept_report:
        console.print("[red]The extraction report lists problems (above). Review them, then fix the "
                      "parser or re-run with --accept-report.[/red]")
        raise typer.Exit(1)


@app.command()
def extract(
    manual: Optional[str] = typer.Option(None, "--manual", help="Only this manual id."),
    accept_report: bool = typer.Option(False, "--accept-report", help="Exit 0 even if the report lists problems."),
) -> None:
    """Parse the PDFs into data/processed/*.json and print the extraction report (no database)."""
    settings = get_settings()
    _check_reports(_extract_all(settings, manual), accept_report)


db_app = typer.Typer(help="Database commands.", no_args_is_help=True)
app.add_typer(db_app, name="db")


def _connect(settings: Settings):
    import psycopg

    from faultsense.db.connection import connect

    try:
        return connect(settings.database_url, settings.db_schema)
    except RuntimeError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(2) from exc
    except psycopg.OperationalError as exc:
        console.print(f"[red]Could not connect to the database: {escape(str(exc))}[/red]")
        raise typer.Exit(2) from exc


@db_app.command("init")
def db_init() -> None:
    """Create the vector extension, tables and indexes (safe to re-run)."""
    from faultsense.db.connection import init_db

    settings = get_settings()
    init_db(_connect(settings))
    console.print(f"Database schema ready in {settings.db_schema!r}.")


@app.command()
def ingest(
    manual: Optional[str] = typer.Option(None, "--manual", help="Only this manual id."),
    accept_report: bool = typer.Option(False, "--accept-report", help="Ingest even if the report lists problems."),
    force: bool = typer.Option(False, "--force", help="Re-embed even if the PDF is unchanged."),
) -> None:
    """Extract, embed (bge-m3) and store the manuals in the database."""
    from faultsense.db.repository import Repository
    from faultsense.embeddings import BgeM3Embedder
    from faultsense.ingest.pipeline import ingest_manual

    settings = get_settings()
    extracted = _extract_all(settings, manual)
    _check_reports(extracted, accept_report)
    repo = Repository(_connect(settings))
    embedder = BgeM3Embedder(settings.embedding_model, settings.device)
    for ex in extracted:
        status = ingest_manual(ex, repo, embedder, force=force)
        console.print(f"{ex.spec.id}: {status} ({len(ex.chunks)} chunks, {len(ex.faults)} fault codes, "
                      f"{len(ex.lexicon)} lexicon entries)")


def _components():
    from faultsense import wiring

    try:
        return wiring.build_components()
    except RuntimeError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(2) from exc


def _manual_ids_for(components, machine: Optional[str]) -> Optional[list[str]]:
    if machine is None:
        return None
    if machine not in components.machines:
        console.print(f"[red]Unknown machine {machine!r}. Known: {', '.join(sorted(components.machines))}[/red]")
        raise typer.Exit(2)
    return [components.machines[machine].manual]


@app.command()
def search(
    query: str = typer.Argument(..., help="The operator's description or fault code."),
    machine: Optional[str] = typer.Option(None, "--machine", help="Restrict to this machine's manual."),
) -> None:
    """Show what the retriever finds for a query (debug view, no LLM)."""
    components = _components()
    result = components.retriever.retrieve(query, _manual_ids_for(components, machine))
    if result.expanded_query:
        console.print(f"Searched as: {escape(result.expanded_query)}")
    for match in result.matched_codes:
        note = " (display look-alike)" if match.fuzzy else ""
        console.print(f"Fault code {escape(match.hit.code)} in {match.hit.manual_id}, p.{match.hit.page}{note}")
    table = Table(title=f"Top {len(result.chunks)} sources")
    for column in ("#", "score", "manual", "pages", "kind", "heading"):
        table.add_column(column)
    for n, item in enumerate(result.chunks, 1):
        c = item.chunk
        pages = str(c.page_start) if c.page_start == c.page_end else f"{c.page_start}-{c.page_end}"
        table.add_row(str(n), f"{item.score:.3f}", c.manual_id, pages, c.kind, escape(c.heading_path[:70]))
    console.print(table)


eval_app = typer.Typer(help="Evaluation harness.", no_args_is_help=True)
app.add_typer(eval_app, name="eval")


@eval_app.command("draft")
def eval_draft() -> None:
    """Regenerate data/eval/scenarios.yaml from the seeds and data/processed (all reviewed: false)."""
    import yaml

    from faultsense.eval.drafting import draft_scenarios, load_faults, write_scenarios

    settings = get_settings()
    faults = load_faults(settings.processed_dir)
    if not faults:
        console.print("[red]No extracted manuals in data/processed: run `faultsense extract` first.[/red]")
        raise typer.Exit(1)
    seeds = yaml.safe_load((settings.data_dir / "eval" / "scenario_seeds.yaml").read_text(encoding="utf-8"))
    path = write_scenarios(draft_scenarios(seeds, faults), settings.data_dir / "eval" / "scenarios.yaml")
    console.print(f"Wrote {len(seeds)} draft scenarios to {path}")


def _progress(result) -> None:
    status = f"ERROR {result.error}" if result.error else f"hit@5={result.hit_at_5} status={result.status}"
    console.print(f"  {result.id}: {escape(status)}")


@eval_app.command("run")
def eval_run(
    retrieval_only: bool = typer.Option(False, "--retrieval-only", help="Skip the LLM: retrieval metrics only."),
    only: Optional[list[str]] = typer.Option(None, "--only", help="Run only these scenario ids (repeatable)."),
    scenarios: Optional[Path] = typer.Option(None, "--scenarios", help="Scenario file (default data/eval/scenarios.yaml)."),
) -> None:
    """Run the evaluation, print the scorecard and save it under eval_runs/."""
    from faultsense.eval.metrics import summarize
    from faultsense.eval.report import render_scorecard, run_config, save_run
    from faultsense.eval.runner import run_eval
    from faultsense.eval.scenarios import load_scenarios

    settings = get_settings()
    path = scenarios or settings.data_dir / "eval" / "scenarios.yaml"
    selected = load_scenarios(path)
    if only:
        selected = [s for s in selected if s.id in set(only)]
    components = _components()
    service = scorer = None
    mode = "retrieval-only" if retrieval_only else "full"
    if not retrieval_only:
        from faultsense import wiring
        from faultsense.eval.runner import AnswerScorer

        service = wiring.build_service(components)
        scorer = AnswerScorer(components.embedder.embed, service.known_identifiers, settings.cause_match_threshold)
    results = run_eval(selected, components.retriever, components.machines, service, scorer, progress=_progress)
    summary = summarize(results)
    out = save_run(results, summary, run_config(settings, mode, path, components.manuals), settings.eval_runs_dir)
    render_scorecard(summary, mode, console)
    console.print(f"Saved {out}")


def _cites(citations) -> str:
    return ", ".join(f"{c.manual} p.{c.page}" for c in citations)


def _print_diagnosis(response) -> None:
    """Dynamic text is escaped: manual names such as [Current Limitation] are not Rich markup."""
    for m in response.matched_fault_codes:
        lookalike = " (display look-alike)" if m.fuzzy else ""
        console.print(f"Fault code {escape(m.code)} ({m.manual}: {escape(m.name)}, p.{m.page}){lookalike}")
    if response.status == "escalate":
        console.print(f"[bold yellow]ESCALATE[/bold yellow] {escape(response.escalation.reason)}")
        console.print(escape(response.escalation.summary))
        for item in response.escalation.collect:
            console.print(f"  - {escape(item)}")
        return
    for warning in response.safety_warnings:
        console.print(f"[bold red]SAFETY[/bold red] {escape(warning.text)} ({_cites(warning.citations)})")
    console.print("[bold]Probable causes[/bold]")
    for cause in response.probable_causes:
        console.print(f"  {cause.rank}. {escape(cause.cause)}  confidence {cause.confidence:.2f} ({_cites(cause.citations)})")
    console.print("[bold]Corrective actions[/bold]")
    for step in response.corrective_actions:
        lock = "  ISOLATE POWER FIRST" if step.requires_isolation else ""
        console.print(f"  {step.step}. {escape(step.action)}{lock} ({_cites(step.citations)})")


@app.command()
def diagnose(
    query: str = typer.Argument(..., help="The operator's description or fault code."),
    machine: Optional[str] = typer.Option(None, "--machine", help="Machine id from data/machines.yaml."),
    as_json: bool = typer.Option(False, "--json", help="Print the raw JSON response."),
) -> None:
    """Diagnose a problem: ranked causes, steps and safety warnings, every item cited."""
    from faultsense import wiring
    from faultsense.diagnosis.service import UnknownMachine

    try:
        service = wiring.build_service()
    except RuntimeError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(2) from exc
    try:
        response = service.diagnose(query, machine)
    except UnknownMachine as exc:
        console.print(f"[red]Unknown machine {exc.machine_id!r}[/red]")
        raise typer.Exit(2) from exc
    if as_json:
        typer.echo(response.model_dump_json(indent=2))
        return
    _print_diagnosis(response)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Run the operator page and HTTP API at http://HOST:PORT/; models load on the first request."""
    import uvicorn

    from faultsense import wiring
    from faultsense.api import create_app

    console.print(f"FaultSense is running: open http://{host}:{port}/ in a browser (Ctrl+C to stop)")
    uvicorn.run(create_app(wiring.build_service, wiring.build_catalog()), host=host, port=port)


def _run_path(settings: Settings, value: Path) -> Path:
    candidate = value if value.exists() else settings.eval_runs_dir / value
    if not (candidate / "summary.json").exists():
        console.print(f"[red]No eval run at {escape(str(value))}[/red]")
        raise typer.Exit(2)
    return candidate


@eval_app.command("compare")
def eval_compare(
    run_a: Path = typer.Argument(..., help="Earlier run: a directory or its name under eval_runs/."),
    run_b: Path = typer.Argument(..., help="Later run."),
) -> None:
    """Compare two saved runs: metric deltas and scenarios whose outcome flipped."""
    from faultsense.eval.report import compare_runs

    settings = get_settings()
    a, b = _run_path(settings, run_a), _run_path(settings, run_b)
    rows, flips = compare_runs(a, b)
    table = Table(title=f"{a.name} -> {b.name}")
    for column in ("Metric", "A", "B", "Delta"):
        table.add_column(column)
    for row in rows:
        table.add_row(*row)
    console.print(table)
    for flip in flips or ["No scenario changed outcome."]:
        console.print(escape(flip))
