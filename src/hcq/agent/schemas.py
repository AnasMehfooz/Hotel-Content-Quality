"""Data contracts for the triage agent."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class IncidentKind(StrEnum):
    SYSTEMIC = "systemic"  # a partner's feed broke: many rows, sudden onset
    RECORD_LEVEL = "record_level"  # scattered individual records, chronic background noise
    FALSE_POSITIVE = "false_positive"  # the check fired but the data is fine


class Route(StrEnum):
    PARTNER = "partner"  # escalate to the partner's integration team
    CONTENT_TEAM = "content_team"  # fix internally (mapping, content corrections)
    NONE = "none"  # no action, e.g. tune the check


EXPECTED_ROUTE = {
    IncidentKind.SYSTEMIC: Route.PARTNER,
    IncidentKind.RECORD_LEVEL: Route.CONTENT_TEAM,
    IncidentKind.FALSE_POSITIVE: Route.NONE,
}


class Incident(BaseModel):
    """A group of related issues, built deterministically before any LLM is involved."""

    incident_id: str
    partner: str
    check_code: str
    first_seen: date
    last_seen: date
    issue_count: int
    affected_listings: int
    daily_counts: dict[str, int] = Field(description="ISO date -> issues that day")
    sample_listing_ids: list[str] = Field(default_factory=list)
    issue_ids: list[str] = Field(default_factory=list, repr=False)


class TicketDraft(BaseModel):
    """What the LLM writes. Passed to Ollama as a JSON schema (structured output)."""

    title: str = Field(max_length=120)
    kind: IncidentKind
    route_to: Route
    severity: Literal["P1", "P2", "P3", "P4"]
    onset_date: date | None = Field(description="First day the problem appears, if systemic")
    summary: str = Field(description="Two to four sentences: what broke, where, since when, impact")
    evidence: list[str] = Field(
        min_length=1, max_length=8, description="Concrete facts from tool results"
    )
    suggested_fix: str
    confidence: float = Field(ge=0, le=1)


class Ticket(TicketDraft):
    """A draft plus the incident fields the code (not the model) is responsible for."""

    incident_id: str
    partner: str
    check_code: str
    affected_listings: int
    issue_count: int
    model: str = ""
    steps: int = 0
