"""``hcq``: one entry point for every step of the pipeline."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
from datetime import date
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from hcq.config import PROJECT_ROOT, get_settings

app = typer.Typer(
    help="Hotel content data-quality pipeline.", no_args_is_help=True, add_completion=False
)
console = Console()

STATUS_STYLE = {"example": "cyan", "todo": "bright_black", "pass": "green", "fail": "red"}


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")] = False,
) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False, show_time=False)],
    )


@app.command()
def reference(
    source: Annotated[
        str | None, typer.Option(help="osm (needs internet) or synthetic (offline).")
    ] = None,
) -> None:
    """Build the master hotel catalog."""
    from hcq.reference import build_reference

    settings = get_settings()
    result = build_reference(settings, source)
    console.print(
        f"[green]Master catalog[/] {result.hotels} hotels from {result.source}, "
        f"{result.quarantined} quarantine entries -> {result.path}"
    )
    if result.source == "osm":
        console.print("Hotel data © OpenStreetMap contributors (ODbL).", style="bright_black")


@app.command()
def generate(
    days: Annotated[int | None, typer.Option(help="Snapshot days to simulate.")] = None,
    seed: Annotated[int | None, typer.Option(help="Random seed; same seed, same feeds.")] = None,
    end_date: Annotated[
        str | None, typer.Option(help="Last snapshot day, YYYY-MM-DD. Default: today.")
    ] = None,
) -> None:
    """Simulate partner feeds with injected, labelled defects."""
    from hcq.generator import generate_feeds

    settings = get_settings()
    result = generate_feeds(
        settings, days=days, seed=seed, end_date=date.fromisoformat(end_date) if end_date else None
    )
    console.print(
        f"[green]Feeds[/] {result.dates[0]} to {result.dates[1]}: {result.listings:,} listing rows, "
        f"{result.rates:,} rates, {result.labels:,} injected defects -> {result.raw_dir}"
    )


@app.command()
def build(
    select: Annotated[
        str | None, typer.Option("--select", "-s", help="dbt selector, e.g. dq_star_invalid+")
    ] = None,
) -> None:
    """Run dbt build (models, seeds and tests) on the current feeds."""
    from hcq.pipeline import run_dbt

    settings = get_settings()
    args = ["build"] + (["--select", select] if select else [])
    code = run_dbt(settings, *args)
    if code != 0:
        raise typer.Exit(code)


@app.command()
def progress() -> None:
    """Score every check against the ground truth and show what is left to build."""
    from hcq.agent import triage as triage_mod
    from hcq.agent.tools import ToolBox
    from hcq.scoring import dedup_is_todo, load_scores
    from hcq.todo import is_todo

    settings = get_settings()
    try:
        scores = load_scores(settings)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc

    table = Table(title="Data-quality checks vs injected ground truth", title_justify="left")
    table.add_column("Check", no_wrap=True, min_width=21)
    table.add_column("Dimension", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    for col in ("Precision", "Recall", "F1", "Target", "TP", "FP", "FN"):
        table.add_column(col, justify="right", no_wrap=True)
    fmt = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
    for s in scores:
        style = STATUS_STYLE[s.status]
        todo_row = s.status == "todo"
        table.add_row(
            s.check_code,
            s.dimension,
            f"[{style}]{s.status.upper()}[/]",
            "-" if todo_row else fmt(s.precision),
            "-" if todo_row else fmt(s.recall),
            "-" if todo_row else fmt(s.f1),
            f"{s.target_precision:.2f}/{s.target_recall:.2f}",
            str(s.true_positives),
            str(s.false_positives),
            str(s.false_negatives),
        )
    console.print(table)

    yours = [s for s in scores if s.status != "example"]
    passing = sum(s.status == "pass" for s in yours)
    tools_total = sum(1 for n in dir(ToolBox) if hasattr(getattr(ToolBox, n), "__hcq_tool__"))
    tools_done = sum(
        1
        for n in dir(ToolBox)
        if hasattr(getattr(ToolBox, n), "__hcq_tool__") and not is_todo(getattr(ToolBox, n))
    )
    agent = [
        ("incidents", not is_todo(triage_mod.build_incidents)),
        ("investigate", not is_todo(triage_mod.investigate)),
    ]
    console.print(
        f"Checks passing: [bold]{passing}/{len(yours)}[/] (plus {len(scores) - len(yours)} examples) · "
        f"dedup {'[green]done[/]' if not dedup_is_todo() else '[bright_black]todo[/]'} · "
        f"agent {', '.join(f'{n} ' + ('[green]done[/]' if ok else '[bright_black]todo[/]') for n, ok in agent)} · "
        f"tools {tools_done}/{tools_total}"
    )


@app.command()
def sql(
    query: Annotated[
        str, typer.Argument(help='SQL to run read-only, e.g. "select * from dq.dq_issues"')
    ],
    limit: Annotated[int, typer.Option(help="Maximum rows to print.")] = 50,
) -> None:
    """Query the warehouse (read-only) and print the result as a table."""
    from hcq.pipeline import warehouse

    with warehouse(get_settings()) as con:
        frame = con.sql(query).limit(limit).df()
    frame = frame.astype(object).where(frame.notna(), None)  # NULL prints as blank, not "nan"
    table = Table(show_lines=False)
    for col in frame.columns:
        table.add_column(str(col), overflow="fold")
    for row in frame.itertuples(index=False):
        table.add_row(*("" if v is None else str(v) for v in row))
    console.print(table)
    console.print(f"{len(frame)} rows (limit {limit})", style="bright_black")


@app.command()
def demo(
    source: Annotated[
        str, typer.Option(help="Master catalog source: synthetic or osm.")
    ] = "synthetic",
    days: Annotated[int | None, typer.Option(help="Snapshot days to simulate.")] = None,
) -> None:
    """Reference catalog -> feeds -> dbt build -> scoreboard, in one go."""
    settings = get_settings()
    if source == "osm" or not settings.reference_path.exists():
        reference(source=source)
    generate(days=days, seed=None, end_date=None)
    build(select=None)
    progress()


@app.command()
def triage(
    limit: Annotated[int, typer.Option(help="Investigate at most this many incidents.")] = 12,
    model: Annotated[str | None, typer.Option(help="Ollama model, e.g. qwen3:14b.")] = None,
) -> None:
    """Group issues into incidents and let the local LLM draft tickets (Milestone 6)."""
    from hcq.agent.llm import OllamaChat
    from hcq.agent.triage import run_triage

    settings = get_settings()
    llm = OllamaChat(settings.ollama_url, model or settings.llm_model, think=settings.llm_think)
    try:
        run = run_triage(settings, llm=llm, limit=limit)
    except NotImplementedError as exc:
        console.print(f"[yellow]{exc}[/]\nSee MILESTONES.md, Milestone 6.")
        raise typer.Exit(1) from exc
    console.print(f"{len(run.incidents)} incidents, {len(run.tickets)} tickets -> {run.out_dir}")
    for ticket in run.tickets:
        console.print(f"  [bold]{ticket.severity}[/] {ticket.kind.value:<15} {ticket.title}")
    for incident_id, error in run.failures:
        console.print(f"  [red]failed[/] {incident_id}: {error}")


@app.command("eval-agent")
def eval_agent() -> None:
    """Grade the latest tickets against the injected incidents."""
    from hcq.agent.eval import evaluate

    report = evaluate(get_settings())
    fmt = lambda v: "-" if v is None else f"{v:.0%}"  # noqa: E731
    console.print(
        f"{report.tickets} tickets · systemic recall {fmt(report.systemic_recall)} · "
        f"systemic precision {fmt(report.systemic_precision)} · kind accuracy {fmt(report.kind_accuracy)} · "
        f"route accuracy {fmt(report.route_accuracy)}"
    )


@app.command()
def dashboard(port: Annotated[int, typer.Option(help="Port for Streamlit.")] = 8501) -> None:
    """Open the data-quality dashboard (Streamlit)."""
    app_path = PROJECT_ROOT / "src" / "hcq" / "dashboard" / "app.py"
    console.print(f"Dashboard on [bold]http://localhost:{port}[/] (Ctrl+C to stop)")
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(port),
        # without this, the first run blocks on an e-mail prompt before the server starts
        "--server.showEmailPrompt",
        "false",
    ]
    # cwd = repo root so Streamlit picks up .streamlit/config.toml from any shell location
    raise typer.Exit(subprocess.call(cmd, cwd=PROJECT_ROOT))


@app.command()
def orchestrate(port: Annotated[int, typer.Option(help="Port for the Dagster UI.")] = 3000) -> None:
    """Start Dagster (UI + daemon) with the pipeline's asset graph and daily schedule."""
    settings = get_settings()
    home = settings.data_dir / "dagster_home"
    home.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "DAGSTER_HOME": str(home.resolve()), **settings.dbt_env()}
    cmd = [
        sys.executable,
        "-m",
        "dagster",
        "dev",
        "-m",
        "hcq.orchestration.definitions",
        "-p",
        str(port),
    ]
    raise typer.Exit(subprocess.call(cmd, env=env, cwd=PROJECT_ROOT))


@app.command()
def doctor() -> None:
    """Check the environment: Python, data, warehouse, Ollama and models."""
    import duckdb

    from hcq.agent.llm import LLMError, OllamaChat

    settings = get_settings()
    ok, warn, bad = "[green]ok[/]", "[yellow]warn[/]", "[red]missing[/]"
    rows = [
        (
            "Python",
            f"{platform.python_version()} on {platform.system()}",
            ok if sys.version_info[:2] == (3, 12) else warn,
        ),
        ("DuckDB", duckdb.__version__, ok),
        (
            "Master catalog",
            str(settings.reference_path),
            ok if settings.reference_path.exists() else bad,
        ),
        (
            "Partner feeds",
            str(settings.raw_dir),
            ok if (settings.manifest_dir / "defects.parquet").exists() else bad,
        ),
        (
            "Warehouse",
            str(settings.warehouse_path),
            ok if settings.warehouse_path.exists() else bad,
        ),
    ]
    llm = OllamaChat(settings.ollama_url, settings.llm_model, timeout=5)
    try:
        models = llm.available_models()
        rows.append(("Ollama", settings.ollama_url, ok))
        for name in (settings.llm_model, settings.embed_model):
            present = any(
                m == name or m.startswith(name + ":") or m.split(":")[0] == name for m in models
            )
            rows.append(
                (
                    f"Model {name}",
                    "pulled" if present else f"run: ollama pull {name}",
                    ok if present else warn,
                )
            )
    except LLMError as exc:
        rows.append(("Ollama", str(exc), warn))
    table = Table(show_header=False, box=None)
    for name, detail, status in rows:
        table.add_row(status, name, detail)
    console.print(table)


if __name__ == "__main__":
    app()
