import json
from pathlib import Path

import pytest

from hcq.cities import load_cities
from hcq.reference.osm import overpass_query, parse_elements, parse_stars
from hcq.reference.schema import MASTER_COLUMNS, validate_master
from hcq.reference.synthetic import synthetic_master

FIXTURE = Path(__file__).parents[1] / "fixtures" / "overpass_koeln.json"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4", (4, False)),
        ("4S", (4, True)),
        ("3 Superior", (3, True)),
        ("4.5", (4, True)),
        ("seven", (None, False)),
    ],
)
def test_parse_stars(raw, expected):
    assert parse_stars(raw) == expected


def test_overpass_query_targets_city_boundary():
    koeln = load_cities()["Köln"]
    assert '"name"="Köln"' in overpass_query(koeln)
    assert koeln.ags in overpass_query(koeln, by="ags")


def test_parse_and_validate_overpass_fixture():
    koeln = load_cities()["Köln"]
    raw = parse_elements(json.loads(FIXTURE.read_text(encoding="utf-8"))["elements"], koeln)
    master, quarantine = validate_master(raw)

    assert list(master.columns) == MASTER_COLUMNS
    dom = master.set_index("hotel_id").loc["osm-n101"]
    assert (dom["stars"], dom["superior"]) == (4, True)
    assert dom["phone"] == "+492212701"
    assert dom["website"] == "https://testhotel.example.de"

    reasons = " | ".join(quarantine["reason"])
    assert "missing name" in reasons  # node 404
    assert "outside city bbox" in reasons  # node 505 sits in Düsseldorf
    assert "postcode out of city range" in reasons  # way 202 has a Düsseldorf postcode
    assert "duplicate of" in reasons  # node 303 and way 202 are the same guest house
    assert len(master) == 2


def test_synthetic_master_is_deterministic_and_valid():
    a, b = synthetic_master(seed=3), synthetic_master(seed=3)
    assert a.equals(b)
    master, quarantine = validate_master(a)
    assert len(master) == len(a)
    assert quarantine.empty
    assert set(master["city"]) == {"Köln", "Düsseldorf"}
