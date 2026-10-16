"""Read-only investigation tools the agent can call. Each tool is one SQL query on the warehouse.

Three tools are implemented as examples. The three marked ``@todo`` are part of Milestone 6;
until you implement them they are hidden from the model (``ToolBox.specs`` skips them).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import duckdb

from hcq.todo import is_todo, todo


def tool(description: str, parameters: dict[str, dict], required: list[str] | None = None):
    """Attach an Ollama/OpenAI-style function spec to a ToolBox method."""

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn.__hcq_tool__ = {  # type: ignore[attr-defined]
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": parameters,
                    "required": required if required is not None else list(parameters),
                },
            },
        }
        return fn

    return decorate


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 6)
    return value


class ToolBox:
    def __init__(self, con: duckdb.DuckDBPyConnection, max_rows: int = 25):
        self.con = con
        self.max_rows = max_rows

    def _rows(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        cur = self.con.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [
            {c: _jsonable(v) for c, v in zip(cols, row, strict=True)}
            for row in cur.fetchmany(self.max_rows)
        ]

    # ------------------------------------------------------------------ implemented examples

    @tool(
        "Get one partner listing as the partner sent it, plus its mapped master hotel id. "
        "Without snapshot_date you get the latest snapshot.",
        {
            "partner": {"type": "string", "description": "northwind, rheinland or citybeds"},
            "listing_id": {"type": "string"},
            "snapshot_date": {"type": "string", "description": "YYYY-MM-DD, optional"},
        },
        required=["partner", "listing_id"],
    )
    def get_listing(
        self, partner: str, listing_id: str, snapshot_date: str | None = None
    ) -> list[dict]:
        return self._rows(
            """
            select snapshot_date, partner, listing_id, hotel_id, name, street, postcode, city_raw, city,
                   latitude, longitude, stars_raw, phone_raw, website_raw, last_updated
            from marts.fct_listings
            where partner = ? and listing_id = ? and (? is null or snapshot_date = cast(? as date))
            order by snapshot_date desc
            limit 1
            """,
            [partner, listing_id, snapshot_date, snapshot_date],
        )

    @tool(
        "Get a hotel from the master catalog (the internal reference record).",
        {"hotel_id": {"type": "string"}},
    )
    def get_master_hotel(self, hotel_id: str) -> list[dict]:
        return self._rows(
            """
            select hotel_id, name, kind, brand, stars, is_superior, street, housenumber, postcode, city,
                   latitude, longitude, phone, website, partners_listing
            from marts.dim_hotel where hotel_id = ?
            """,
            [hotel_id],
        )

    @tool(
        "Sample detected issues for a partner and check, newest first, with the observed values.",
        {
            "partner": {"type": "string"},
            "check_code": {"type": "string"},
            "snapshot_date": {"type": "string", "description": "YYYY-MM-DD, optional"},
            "limit": {"type": "integer", "description": "1-10, default 5"},
        },
        required=["partner", "check_code"],
    )
    def sample_issues(
        self, partner: str, check_code: str, snapshot_date: str | None = None, limit: int = 5
    ) -> list[dict]:
        return self._rows(
            """
            select snapshot_date, listing_id, related_listing_id, stay_date, field, observed_value,
                   expected_value, details, city
            from dq.dq_issues
            where partner = ? and check_code = ? and (? is null or snapshot_date = cast(? as date))
            order by snapshot_date desc, listing_id
            limit ?
            """,
            [partner, check_code, snapshot_date, snapshot_date, max(1, min(int(limit), 10))],
        )

    # ------------------------------------------------------------------ yours (Milestone 6)

    @tool(
        "Daily issue counts for a partner and check next to the partner's listing volume, so you can "
        "see when a problem started and how much of the feed it affects.",
        {"partner": {"type": "string"}, "check_code": {"type": "string"}},
    )
    @todo("Milestone 6", "Query dq.dq_daily_summary; return one row per snapshot day.")
    def issue_timeline(self, partner: str, check_code: str) -> list[dict]:
        raise NotImplementedError

    @tool(
        "Master hotels within radius_km of a coordinate, nearest first. Use it to test whether a "
        "listing's coordinates point at a different hotel than the one it is mapped to.",
        {
            "latitude": {"type": "number"},
            "longitude": {"type": "number"},
            "radius_km": {"type": "number", "description": "default 0.5"},
        },
        required=["latitude", "longitude"],
    )
    @todo("Milestone 6", "Use the haversine formula against marts.dim_hotel; cap the result size.")
    def nearby_master_hotels(
        self, latitude: float, longitude: float, radius_km: float = 0.5
    ) -> list[dict]:
        raise NotImplementedError

    @tool(
        "City-wide median nightly rate per stay date (all partners). Tells real market moves, such "
        "as a trade fair, apart from broken prices.",
        {
            "city": {"type": "string", "description": "Köln or Düsseldorf"},
            "stay_date_from": {"type": "string", "description": "YYYY-MM-DD"},
            "stay_date_to": {"type": "string", "description": "YYYY-MM-DD"},
        },
    )
    @todo("Milestone 6", "Aggregate marts.fct_rates by stay_date for one city.")
    def market_price_index(self, city: str, stay_date_from: str, stay_date_to: str) -> list[dict]:
        raise NotImplementedError

    # ------------------------------------------------------------------ plumbing

    def _tools(self) -> dict[str, Callable[..., Any]]:
        out = {}
        for name in dir(type(self)):
            fn = getattr(self, name)
            if callable(fn) and hasattr(fn, "__hcq_tool__") and not is_todo(fn):
                out[name] = fn
        return out

    def specs(self) -> list[dict]:
        """Function specs for every implemented tool, ready for the ``tools`` field of /api/chat."""
        return [fn.__hcq_tool__ for fn in self._tools().values()]

    def call(self, name: str, arguments: dict[str, Any] | str | None) -> str:
        """Execute a tool call from the model. Always returns JSON; errors are returned, not raised."""
        fn = self._tools().get(name)
        if fn is None:
            return json.dumps(
                {"error": f"unknown tool {name!r}", "available": sorted(self._tools())}
            )
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError as exc:
                return json.dumps({"error": f"arguments are not valid JSON: {exc}"})
        try:
            result = fn(**(arguments or {}))
        except (TypeError, ValueError, duckdb.Error) as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        return json.dumps(result, ensure_ascii=False, default=str)
