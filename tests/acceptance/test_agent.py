"""Milestone 6: incident grouping (6a) and the tool-calling investigation loop (6b)."""

import json
import os
from datetime import date

import duckdb
import pytest

from hcq.agent import triage
from hcq.agent.llm import ScriptedLLM
from hcq.agent.schemas import Incident, Ticket
from hcq.agent.tools import ToolBox
from hcq.pipeline import stub_check_codes
from hcq.todo import is_todo


@pytest.fixture(scope="module")
def con(built):
    connection = duckdb.connect(str(built.warehouse_path), read_only=True)
    yield connection
    connection.close()


@pytest.mark.skipif(is_todo(triage.build_incidents), reason="Milestone 6a not started")
def test_build_incidents_contract(built, con):
    issues, volumes = triage.load_issue_frames(con)
    incidents = triage.build_incidents(issues, volumes)
    assert incidents and all(isinstance(i, Incident) for i in incidents)

    members = [issue_id for i in incidents for issue_id in i.issue_ids]
    assert len(members) == len(set(members)), "an issue may belong to only one incident"
    assert len(members) >= 0.95 * len(issues), "at least 95% of issues must be triaged"

    per_pair: dict[tuple[str, str], int] = {}
    for i in incidents:
        per_pair[(i.partner, i.check_code)] = per_pair.get((i.partner, i.check_code), 0) + 1
    assert max(per_pair.values()) <= 3, "do not split one partner/check into per-day incidents"

    implemented = {c for c in set(issues["check_code"])} - stub_check_codes(built)
    injected = con.sql(
        "select partner, check_code, start_date, end_date from eval.eval_incidents"
    ).fetchall()
    for partner, check_code, start, end in injected:
        if check_code not in implemented:
            continue
        assert any(
            i.partner == partner
            and i.check_code == check_code
            and abs((i.first_seen - start).days) <= 1
            and abs((i.last_seen - end).days) <= 1
            for i in incidents
        ), f"no incident isolates the injected {partner} {check_code} episode ({start}..{end})"


def _incident() -> Incident:
    return Incident(
        incident_id="rheinland-GEO_SWAPPED-2026-10-11",
        partner="rheinland",
        check_code="GEO_SWAPPED",
        first_seen=date(2026, 10, 11),
        last_seen=date(2026, 10, 12),
        issue_count=420,
        affected_listings=210,
        daily_counts={"2026-10-11": 210, "2026-10-12": 210},
        sample_listing_ids=["0000001"],
    )


DRAFT = {
    "title": "Rheinland swaps latitude and longitude since 11 Oct",
    "kind": "systemic",
    "route_to": "partner",
    "severity": "P1",
    "onset_date": "2026-10-11",
    "summary": "Every Rheinland row has latitude and longitude swapped since the 11 Oct export.",
    "evidence": ["Breitengrad 6.95 / Laengengrad 50.94 on listing 0000001"],
    "suggested_fix": "Ask Rheinland to restore the column order of the export.",
    "confidence": 0.9,
}


@pytest.mark.skipif(is_todo(triage.investigate), reason="Milestone 6b not started")
def test_investigate_runs_tools_then_returns_a_ticket(con):
    llm = ScriptedLLM(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "sample_issues",
                            "arguments": {"partner": "rheinland", "check_code": "GEO_SWAPPED"},
                        }
                    }
                ],
            },
            {"role": "assistant", "content": "The swap is feed-wide and starts on 11 Oct."},
            {"role": "assistant", "content": json.dumps(DRAFT)},
        ]
    )
    ticket = triage.investigate(_incident(), llm, ToolBox(con))

    assert isinstance(ticket, Ticket)
    assert ticket.incident_id == "rheinland-GEO_SWAPPED-2026-10-11"
    assert (ticket.partner, ticket.check_code, ticket.issue_count) == (
        "rheinland",
        "GEO_SWAPPED",
        420,
    )
    assert llm.calls[0]["tools"], "offer the toolbox specs to the model"
    later = [m for call in llm.calls[1:] for m in call["messages"]]
    assert any(m.get("role") == "tool" for m in later), (
        "send tool results back as role=tool messages"
    )
    assert llm.calls[-1]["schema"], "ask for the final ticket with a JSON schema"


@pytest.mark.skipif(is_todo(triage.investigate), reason="Milestone 6b not started")
def test_investigate_retries_once_on_invalid_json(con):
    llm = ScriptedLLM(
        [
            {"role": "assistant", "content": "Done investigating."},
            {"role": "assistant", "content": '{"title": "half a ticket"'},
            {"role": "assistant", "content": json.dumps(DRAFT)},
        ]
    )
    ticket = triage.investigate(_incident(), llm, ToolBox(con))
    assert ticket.kind.value == "systemic"


@pytest.mark.live_llm
@pytest.mark.skipif(
    os.environ.get("HCQ_LIVE_LLM") != "1", reason="set HCQ_LIVE_LLM=1 with Ollama running"
)
@pytest.mark.skipif(
    is_todo(triage.investigate) or is_todo(triage.build_incidents), reason="Milestone 6"
)
def test_live_agent_finds_the_injected_incidents(built):
    from hcq.agent.eval import evaluate

    triage.run_triage(built, limit=8)
    report = evaluate(built)
    assert report.kind_accuracy is not None and report.kind_accuracy >= 0.7, report
