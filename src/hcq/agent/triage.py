"""Incident triage: deterministic grouping first, then an LLM investigates and drafts a ticket.

Milestone 6 is two functions in this file, ``build_incidents`` and ``investigate``. Everything
else (loading, running, writing reports) is done for you. Contract and acceptance tests:
docs/agent.md and tests/acceptance/test_agent.py.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
from pydantic import ValidationError

from hcq.agent.llm import LLM, LLMError, OllamaChat
from hcq.agent.prompts import SYSTEM_PROMPT  # noqa: F401  (yours to use and improve)
from hcq.agent.schemas import Incident, Ticket, TicketDraft  # noqa: F401
from hcq.agent.tools import ToolBox
from hcq.config import TIMEZONE, Settings
from hcq.pipeline import warehouse
from hcq.todo import todo

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def load_issue_frames(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(issues, volumes): every detected issue, and listings per partner per snapshot day."""
    issues = con.sql(
        """
        select issue_id, check_code, severity, snapshot_date, partner, listing_id, related_listing_id,
               stay_date, field, observed_value, hotel_id, city
        from dq.dq_issues
        """
    ).df()
    volumes = con.sql(
        "select snapshot_date, partner, count(*) as listings from marts.fct_listings group by all"
    ).df()
    return issues, volumes


@todo("Milestone 6a", "Group issues into incidents; see docs/agent.md.")
def build_incidents(issues: pd.DataFrame, volumes: pd.DataFrame) -> list[Incident]:
    """Group issues into incidents, without any LLM.

    Contract (checked by tests/acceptance/test_agent.py):
    - every issue belongs to at most one incident, and at least 95% of issues belong to one;
    - one incident covers one partner and one check_code;
    - a systemic episode (a partner's issue rate jumps for a few days) is its own incident,
      separate from the chronic background of the same partner and check, with first_seen
      and last_seen within one day of the episode;
    - no more than 3 incidents per partner and check (do not split by day);
    - incident_id is deterministic, e.g. "rheinland-GEO_SWAPPED-2026-10-08".
    """
    raise NotImplementedError


@todo("Milestone 6b", "Run the tool-calling loop; see docs/agent.md.")
def investigate(incident: Incident, llm: LLM, toolbox: ToolBox, *, max_steps: int = 6) -> Ticket:
    """Let the model investigate one incident with tools, then return a validated Ticket.

    Contract (checked with a scripted LLM in tests/acceptance/test_agent.py):
    - call ``llm.chat(messages, tools=toolbox.specs())`` in a loop; execute every tool call
      with ``toolbox.call(name, arguments)`` and append the result as a ``{"role": "tool"}``
      message; stop when the model answers without tool calls or after ``max_steps`` rounds;
    - then ask for the ticket with ``schema=TicketDraft.model_json_schema()`` and validate the
      reply with ``TicketDraft.model_validate_json`` (retry once with the validation error);
    - build the Ticket from the draft plus incident fields: incident_id, partner, check_code,
      affected_listings and issue_count come from the incident, never from the model.
    """
    raise NotImplementedError


@dataclass
class TriageRun:
    incidents: list[Incident]
    tickets: list[Ticket] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    out_dir: Path | None = None


def _priority(incident: Incident, severity: dict[str, str]) -> tuple[int, int]:
    return SEVERITY_RANK.get(severity.get(incident.check_code, "low"), 3), -incident.issue_count


def _filename(incident_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", incident_id)


def render_markdown(ticket: Ticket) -> str:
    lines = [
        f"# {ticket.title}",
        "",
        f"**{ticket.severity}** · {ticket.kind.value.replace('_', ' ')} · route to {ticket.route_to.value} · "
        f"confidence {ticket.confidence:.0%}",
        "",
        "| Partner | Check | Onset | Affected listings | Issues |",
        "|---|---|---|---|---|",
        f"| {ticket.partner} | {ticket.check_code} | {ticket.onset_date or '-'} | {ticket.affected_listings} | "
        f"{ticket.issue_count} |",
        "",
        "## Summary",
        ticket.summary,
        "",
        "## Evidence",
        *[f"- {item}" for item in ticket.evidence],
        "",
        "## Suggested fix",
        ticket.suggested_fix,
        "",
        f"<sub>Incident {ticket.incident_id} · drafted by {ticket.model} in {ticket.steps} steps</sub>",
        "",
    ]
    return "\n".join(lines)


def run_triage(settings: Settings, *, llm: LLM | None = None, limit: int = 12) -> TriageRun:
    with warehouse(settings) as con:
        issues, volumes = load_issue_frames(con)
        incidents = build_incidents(issues, volumes)
        severity = dict(zip(issues["check_code"], issues["severity"], strict=False))
        queue = sorted(incidents, key=lambda i: _priority(i, severity))[:limit]
        llm = llm or OllamaChat(settings.ollama_url, settings.llm_model, think=settings.llm_think)
        run = TriageRun(incidents=incidents)
        toolbox = ToolBox(con)
        for incident in queue:
            try:
                run.tickets.append(investigate(incident, llm, toolbox))
            except (LLMError, ValidationError, json.JSONDecodeError) as exc:
                run.failures.append((incident.incident_id, str(exc)[:500]))
                if isinstance(exc, LLMError) and "not reachable" in str(exc):
                    break

    stamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d_%H%M")
    run.out_dir = settings.reports_dir / "tickets" / stamp
    run.out_dir.mkdir(parents=True, exist_ok=True)
    for ticket in run.tickets:
        (run.out_dir / f"{_filename(ticket.incident_id)}.md").write_text(
            render_markdown(ticket), encoding="utf-8"
        )
    (run.out_dir / "tickets.json").write_text(
        json.dumps([t.model_dump(mode="json") for t in run.tickets], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    pd.DataFrame([t.model_dump(mode="json") for t in run.tickets]).to_parquet(
        settings.tickets_path, index=False
    )
    pd.DataFrame([i.model_dump(mode="json") for i in incidents]).to_parquet(
        settings.tickets_path.with_name("incidents.parquet"), index=False
    )
    return run
