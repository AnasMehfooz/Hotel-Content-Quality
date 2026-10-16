"""City reference data shared by Python and dbt (single source: dbt/seeds/city_reference.csv)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache

from hcq.config import PROJECT_ROOT

CITY_REFERENCE_CSV = PROJECT_ROOT / "dbt" / "seeds" / "city_reference.csv"


@dataclass(frozen=True)
class City:
    name: str
    aliases: tuple[str, ...]
    ags: str  # official municipality key (Amtlicher Gemeindeschlüssel)
    postcode_min: int
    postcode_max: int
    dialing_code: str  # without trunk prefix, e.g. "221" for Köln (0221)
    centroid: tuple[float, float]
    bbox: tuple[float, float, float, float]  # min_lat, max_lat, min_lon, max_lon

    def contains(self, lat: float, lon: float) -> bool:
        min_lat, max_lat, min_lon, max_lon = self.bbox
        return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon

    def postcode_ok(self, postcode: str | None) -> bool:
        return (
            postcode is not None
            and postcode.isdigit()
            and len(postcode) == 5
            and self.postcode_min <= int(postcode) <= self.postcode_max
        )

    @property
    def ascii_name(self) -> str:
        return self.name.replace("ö", "oe").replace("ü", "ue")

    @property
    def english_name(self) -> str:
        return {"Köln": "Cologne", "Düsseldorf": "Dusseldorf"}.get(self.name, self.ascii_name)


@lru_cache
def load_cities() -> dict[str, City]:
    cities: dict[str, City] = {}
    with CITY_REFERENCE_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            cities[row["city"]] = City(
                name=row["city"],
                aliases=tuple(row["aliases"].split("|")),
                ags=row["ags"],
                postcode_min=int(row["postcode_min"]),
                postcode_max=int(row["postcode_max"]),
                dialing_code=row["dialing_code"],
                centroid=(float(row["centroid_lat"]), float(row["centroid_lon"])),
                bbox=(
                    float(row["min_lat"]),
                    float(row["max_lat"]),
                    float(row["min_lon"]),
                    float(row["max_lon"]),
                ),
            )
    return cities


def other_city(name: str) -> City:
    return next(c for c in load_cities().values() if c.name != name)
