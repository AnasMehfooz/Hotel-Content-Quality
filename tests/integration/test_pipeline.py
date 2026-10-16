"""The scaffold itself: feeds -> dbt -> dq_issues -> scores, on a 10-day synthetic window."""

import json

import duckdb
import pytest

from hcq.agent.tools import ToolBox
from hcq.scoring import load_scores


@pytest.fixture(scope="module")
def con(built):
    connection = duckdb.connect(str(built.warehouse_path), read_only=True)
    yield connection
    connection.close()


def test_every_partner_lands_in_the_marts(con):
    partners = {r[0] for r in con.sql("select distinct partner from marts.fct_listings").fetchall()}
    assert partners == {"northwind", "rheinland", "citybeds"}
    assert con.sql("select count(*) from marts.fct_rates").fetchone()[0] > 10_000


def test_partner_formats_are_parsed(con):
    # decimal commas, half stars, epoch timestamps and German dates all become typed values
    nulls = con.sql(
        """
        select partner, count_if(latitude is null) as no_lat, count_if(last_updated is null) as no_date,
               count_if(stars_raw is not null and star_class is null) as bad_stars
        from marts.fct_listings group by partner
        """
    ).fetchall()
    for partner, no_lat, no_date, bad_stars in nulls:
        assert no_date == 0, partner
        assert bad_stars == 0, partner
        assert no_lat < 50, partner  # only the injected MISSING_REQUIRED rows


def test_example_checks_meet_their_targets(built):
    scores = {s.check_code: s for s in load_scores(built)}
    assert len(scores) == 13
    for code in ("MISSING_REQUIRED", "GEO_SWAPPED"):
        assert scores[code].meets_target, scores[code]


def test_issue_ids_are_unique(con):
    total, distinct = con.sql(
        "select count(*), count(distinct issue_id) from dq.dq_issues"
    ).fetchone()
    assert total == distinct


def test_example_tools_answer_from_the_warehouse(con):
    box = ToolBox(con)
    partner, listing_id, hotel_id = con.sql(
        "select partner, listing_id, hotel_id from marts.fct_listings where hotel_id is not null limit 1"
    ).fetchone()
    listing = json.loads(box.call("get_listing", {"partner": partner, "listing_id": listing_id}))
    assert listing[0]["listing_id"] == listing_id
    hotel = json.loads(box.call("get_master_hotel", {"hotel_id": hotel_id}))
    assert hotel[0]["hotel_id"] == hotel_id
    issues = json.loads(
        box.call("sample_issues", {"partner": "rheinland", "check_code": "GEO_SWAPPED"})
    )
    assert issues and issues[0]["field"] == "latitude,longitude"
