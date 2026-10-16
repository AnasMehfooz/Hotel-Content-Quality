"""Dagster asset graph: master catalog -> partner feeds -> dbt models and tests -> triage tickets.

Run it with ``hcq orchestrate`` (UI on http://localhost:3000). Every dbt model is its own asset
and every dbt test shows up as an asset check, so lineage runs from the raw feeds to dq_issues.
"""

# No `from __future__ import annotations` here: Dagster reads the Config type annotation at runtime.
import pandas as pd
from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetSelection,
    AssetSpec,
    Config,
    Definitions,
    MaterializeResult,
    ScheduleDefinition,
    asset,
    define_asset_job,
    multi_asset,
)
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets

from hcq.config import get_settings
from hcq.pipeline import dbt_executable, run_dbt

settings = get_settings()
settings.export_env()

dbt_project = DbtProject(project_dir=settings.dbt_dir, profiles_dir=settings.dbt_dir)
if not dbt_project.manifest_path.exists():
    run_dbt(
        settings, "parse", quiet=True
    )  # dagster-dbt needs target/manifest.json to build the graph


# Asset keys match the dbt source names, so dbt models hang off these assets in the lineage graph.
MASTER = AssetKey(["master", "hotels"])
RAW_TABLES = [
    ("northwind", "listings"),
    ("northwind", "rates"),
    ("rheinland", "hotels"),
    ("rheinland", "preise"),
    ("citybeds", "properties"),
    ("mapping", "mapping"),
    ("ground_truth", "defects"),
    ("ground_truth", "incidents"),
]


class ReferenceConfig(Config):
    source: str = settings.reference  # "osm" (needs internet) or "synthetic"
    rebuild: bool = False


@asset(key=MASTER, group_name="ingest", description="Master hotel catalog, validated on ingest.")
def reference_hotels(context: AssetExecutionContext, config: ReferenceConfig) -> MaterializeResult:
    from hcq.reference import build_reference

    if settings.reference_path.exists() and not config.rebuild:
        hotels = len(pd.read_parquet(settings.reference_path, columns=["hotel_id"]))
        context.log.info("Reusing the existing master catalog (set rebuild=true to refresh)")
        return MaterializeResult(metadata={"hotels": hotels, "reused": True})
    build = build_reference(settings, config.source)
    return MaterializeResult(
        metadata={"hotels": build.hotels, "quarantined": build.quarantined, "source": build.source}
    )


@multi_asset(
    specs=[
        AssetSpec(AssetKey([source, table]), deps=[MASTER], group_name="ingest")
        for source, table in RAW_TABLES
    ],
    description="Simulated partner feeds, mapping table and ground-truth manifest (one simulation run).",
)
def partner_feeds(context: AssetExecutionContext):
    from hcq.generator import generate_feeds

    build = generate_feeds(settings)
    metadata = {
        "first_snapshot": str(build.dates[0]),
        "last_snapshot": str(build.dates[1]),
        "listing_rows": build.listings,
        "rates": build.rates,
        "injected_defects": build.labels,
    }
    for source, table in RAW_TABLES:
        yield MaterializeResult(asset_key=AssetKey([source, table]), metadata=metadata)


@dbt_assets(manifest=dbt_project.manifest_path, project=dbt_project)
def hotel_dq_dbt(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()


@asset(
    group_name="triage",
    deps=[AssetKey(["dq", "dq_issues"])],
    description="Incident tickets drafted by the local LLM (Milestone 6).",
)
def triage_tickets(context: AssetExecutionContext) -> MaterializeResult:
    from hcq.agent import triage
    from hcq.todo import is_todo

    if is_todo(triage.build_incidents) or is_todo(triage.investigate):
        context.log.warning("Milestone 6 is not implemented yet; no tickets drafted.")
        return MaterializeResult(metadata={"tickets": 0, "skipped": True})
    run = triage.run_triage(settings)
    return MaterializeResult(
        metadata={
            "incidents": len(run.incidents),
            "tickets": len(run.tickets),
            "failures": len(run.failures),
            "report_dir": str(run.out_dir),
        }
    )


daily_pipeline = define_asset_job("daily_pipeline", selection=AssetSelection.all())

defs = Definitions(
    assets=[reference_hotels, partner_feeds, hotel_dq_dbt, triage_tickets],
    jobs=[daily_pipeline],
    schedules=[
        ScheduleDefinition(
            job=daily_pipeline, cron_schedule="30 6 * * *", execution_timezone="Europe/Berlin"
        )
    ],
    resources={"dbt": DbtCliResource(project_dir=dbt_project, dbt_executable=dbt_executable())},
)
