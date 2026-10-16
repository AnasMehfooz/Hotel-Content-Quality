"""Grade the agent's tickets against the injected ground truth (simulation only)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from hcq.agent.schemas import EXPECTED_ROUTE, IncidentKind
from hcq.config import Settings
from hcq.pipeline import warehouse


@dataclass
class AgentReport:
    tickets: int
    systemic_recall: float | None  # injected incidents found as systemic with the right onset
    systemic_precision: float | None  # systemic tickets that match an injected incident
    kind_accuracy: float | None
    route_accuracy: float | None
    rows: list[dict] = field(default_factory=list)


def _as_date(value: object) -> date | None:
    """Parquet round trips turn missing dates into NaN and dates into strings or Timestamps."""
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _ratio(hits: int, total: int) -> float | None:
    return round(hits / total, 3) if total else None


def evaluate(settings: Settings) -> AgentReport:
    tickets_path = settings.tickets_path
    incidents_path = tickets_path.with_name("incidents.parquet")
    if not tickets_path.exists():
        raise FileNotFoundError("No tickets yet. Run `hcq triage` first.")
    tickets = pd.read_parquet(tickets_path)
    incidents = pd.read_parquet(incidents_path).set_index("incident_id")

    with warehouse(settings) as con:
        truth = dict(con.sql("select issue_id, truth_kind from eval.eval_issue_truth").fetchall())
        injected = [
            {
                "partner": p,
                "check_code": c,
                "start_date": start,
                "end_date": end,
            }  # dates stay datetime.date
            for p, c, start, end in con.sql(
                "select partner, check_code, start_date, end_date from eval.eval_incidents"
            ).fetchall()
        ]

    rows = []
    for t in tickets.to_dict("records"):
        issue_ids = (
            incidents.loc[t["incident_id"], "issue_ids"]
            if t["incident_id"] in incidents.index
            else []
        )
        votes = Counter(truth.get(i, "false_positive") for i in issue_ids)
        truth_kind = (
            IncidentKind(votes.most_common(1)[0][0]) if votes else IncidentKind.FALSE_POSITIVE
        )
        onset = _as_date(t.get("onset_date"))
        starts = [
            i["start_date"]
            for i in injected
            if (i["partner"], i["check_code"]) == (t["partner"], t["check_code"])
        ]
        hits_injected = any(
            onset is not None and abs((onset - start).days) <= 1 for start in starts
        )
        rows.append(
            {
                "incident_id": t["incident_id"],
                "kind": t["kind"],
                "truth_kind": truth_kind.value,
                "kind_ok": t["kind"] == truth_kind.value,
                "route_ok": t["route_to"] == EXPECTED_ROUTE[truth_kind].value,
                "matches_injected": t["kind"] == IncidentKind.SYSTEMIC.value and hits_injected,
            }
        )

    systemic = [r for r in rows if r["kind"] == IncidentKind.SYSTEMIC.value]
    found = 0
    for inc in injected:
        found += any(
            t["kind"] == IncidentKind.SYSTEMIC.value
            and t["partner"] == inc["partner"]
            and t["check_code"] == inc["check_code"]
            and _as_date(t.get("onset_date")) is not None
            and abs((_as_date(t.get("onset_date")) - inc["start_date"]).days) <= 1
            for t in tickets.to_dict("records")
        )
    return AgentReport(
        tickets=len(rows),
        systemic_recall=_ratio(found, len(injected)),
        systemic_precision=_ratio(sum(r["matches_injected"] for r in systemic), len(systemic)),
        kind_accuracy=_ratio(sum(r["kind_ok"] for r in rows), len(rows)),
        route_accuracy=_ratio(sum(r["route_ok"] for r in rows), len(rows)),
        rows=rows,
    )
