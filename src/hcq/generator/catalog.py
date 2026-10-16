"""The defect catalog and the systemic incidents of the simulated period.

Codes here must match dbt/seeds/dq_checks.csv (a unit test enforces it).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DefectType:
    code: str
    dimension: str
    rate: float  # share of eligible listings (or rate rows) affected at some point
    grain: str = "listing"  # listing | rate | pair


DEFECTS: dict[str, DefectType] = {
    d.code: d
    for d in (
        DefectType("MISSING_REQUIRED", "completeness", 0.03),
        DefectType("ENCODING_MOJIBAKE", "validity", 0.05),
        DefectType("STAR_INVALID", "validity", 0.03),
        DefectType("PHONE_INVALID", "validity", 0.04),
        DefectType("URL_INVALID", "validity", 0.04),
        DefectType("ADDRESS_CITY_MISMATCH", "consistency", 0.03),
        DefectType("STAR_CONFLICT", "consistency", 0.03),
        DefectType("GEO_SWAPPED", "accuracy", 0.02),
        DefectType("GEO_OFFSET", "accuracy", 0.03),
        DefectType("WRONG_MAPPING", "accuracy", 0.03),
        DefectType("STALE_LISTING", "timeliness", 0.03),
        DefectType("DUPLICATE_LISTING", "uniqueness", 0.04, grain="pair"),
        DefectType("PRICE_OUTLIER", "plausibility", 0.002, grain="rate"),
    )
}


@dataclass(frozen=True)
class Incident:
    """A systemic problem: one partner's export breaks for a few days and affects every row."""

    incident_id: str
    partner: str
    defect: str
    start_frac: float  # position in the simulated window, 0 = first day, 1 = last day
    end_frac: float
    description: str

    def days(self, n_days: int) -> tuple[int, int]:
        last = n_days - 1
        start = round(self.start_frac * last)
        return start, max(start, round(self.end_frac * last))


INCIDENTS: tuple[Incident, ...] = (
    Incident(
        "INC-citybeds-price-units",
        "citybeds",
        "PRICE_OUTLIER",
        0.30,
        0.38,
        "CityBeds sends euro amounts in the amount_cents field, so every price is 100x too low.",
    ),
    Incident(
        "INC-rheinland-coordinate-swap",
        "rheinland",
        "GEO_SWAPPED",
        0.50,
        0.64,
        "A Rheinland export change swaps the Breitengrad and Laengengrad columns.",
    ),
    Incident(
        "INC-northwind-encoding",
        "northwind",
        "ENCODING_MOJIBAKE",
        0.76,
        0.90,
        "Northwind's export writes UTF-8 text as Windows-1252, garbling every umlaut.",
    ),
)

# A trade fair in Köln: real demand, so hotel rates legitimately spike for a few stay dates.
TRADE_FAIR = {"city": "Köln", "start_frac": 0.70, "nights": 4, "multiplier": (2.8, 4.5)}
