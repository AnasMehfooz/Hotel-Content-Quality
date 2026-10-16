"""Offline master catalog for tests, CI and first runs without internet.

Every hotel here is invented. Street and district names are real so that the data has the
same umlauts, postcodes and geography as the OpenStreetMap catalog.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from hcq.cities import load_cities
from hcq.geo import offset
from hcq.reference.schema import MASTER_COLUMNS
from hcq.text import slugify

# district -> (lat, lon, postcode); coordinates are approximate district centres
DISTRICTS: dict[str, dict[str, tuple[float, float, str]]] = {
    "Köln": {
        "Altstadt": (50.9385, 6.9580, "50667"),
        "Hauptbahnhof": (50.9430, 6.9590, "50667"),
        "Neumarkt": (50.9360, 6.9470, "50667"),
        "Rudolfplatz": (50.9370, 6.9370, "50674"),
        "Südstadt": (50.9250, 6.9570, "50678"),
        "Deutz": (50.9380, 6.9770, "50679"),
        "Messe": (50.9460, 6.9830, "50679"),
        "Ehrenfeld": (50.9500, 6.9170, "50823"),
        "Nippes": (50.9630, 6.9520, "50733"),
        "Sülz": (50.9200, 6.9200, "50937"),
        "Lindenthal": (50.9280, 6.9030, "50931"),
        "Mülheim": (50.9650, 7.0080, "51063"),
        "Kalk": (50.9390, 7.0060, "51103"),
        "Rodenkirchen": (50.8900, 6.9900, "50996"),
        "Porz": (50.8800, 7.0600, "51143"),
    },
    "Düsseldorf": {
        "Altstadt": (51.2260, 6.7740, "40213"),
        "Hauptbahnhof": (51.2200, 6.7940, "40210"),
        "Königsallee": (51.2230, 6.7790, "40212"),
        "Medienhafen": (51.2140, 6.7510, "40221"),
        "Pempelfort": (51.2360, 6.7850, "40477"),
        "Derendorf": (51.2430, 6.7880, "40476"),
        "Golzheim": (51.2500, 6.7700, "40474"),
        "Messe": (51.2600, 6.7370, "40474"),
        "Oberkassel": (51.2310, 6.7510, "40545"),
        "Bilk": (51.2070, 6.7770, "40225"),
        "Flingern": (51.2260, 6.8070, "40235"),
        "Kaiserswerth": (51.3020, 6.7370, "40489"),
        "Benrath": (51.1630, 6.8740, "40597"),
    },
}

STREETS = {
    "Köln": [
        "Hohe Straße",
        "Schildergasse",
        "Aachener Straße",
        "Venloer Straße",
        "Neusser Straße",
        "Severinstraße",
        "Zülpicher Straße",
        "Bonner Straße",
        "Dürener Straße",
        "Ehrenstraße",
        "Breite Straße",
        "Komödienstraße",
        "Trankgasse",
        "Mülheimer Freiheit",
        "Deutzer Freiheit",
        "Luxemburger Straße",
        "Gürzenichstraße",
        "Am Hof",
        "Friesenwall",
        "Kalker Hauptstraße",
    ],
    "Düsseldorf": [
        "Königsallee",
        "Graf-Adolf-Straße",
        "Berliner Allee",
        "Immermannstraße",
        "Bismarckstraße",
        "Kaiserswerther Straße",
        "Bolkerstraße",
        "Kasernenstraße",
        "Oststraße",
        "Worringer Straße",
        "Ackerstraße",
        "Kölner Straße",
        "Münsterstraße",
        "Luegallee",
        "Speditionstraße",
        "Benrather Schloßallee",
        "Nordstraße",
        "Grafenberger Allee",
        "Hüttenstraße",
        "Steinstraße",
    ],
}

CORES = [
    "Rheinblick",
    "Domblick",
    "Altstadtperle",
    "Am Römerturm",
    "Zur Brücke",
    "Königshof",
    "Grüner Baum",
    "Löwenhof",
    "Schwanenhof",
    "Mühlenhof",
    "Kaiserhof",
    "Hansa",
    "Merian",
    "Lindenhof",
    "Rosengarten",
    "Am Stadtgarten",
    "Zum Anker",
    "Weißes Haus",
    "Goldener Hirsch",
    "Am Hafen",
    "Flora",
    "Sankt Georg",
    "Haus Brückner",
    "Am Rathaus",
    "Fischerhaus",
    "Zur Post",
    "Am Ring",
    "Rheinperle",
    "Stadtvilla",
    "Zum Kranz",
    "Schlossblick",
    "Parkhotel",
    "Lilienhof",
    "Am Markt",
    "Zum Treppchen",
    "Bürgerhaus",
    "Gartenhaus",
    "Am Turm",
    "Kastanienhof",
    "Ufer 7",
]
PREFIXES = [
    ("Hotel", "hotel", 0.62),
    ("Boutique-Hotel", "hotel", 0.07),
    ("Apart-Hotel", "hotel", 0.05),
    ("Gästehaus", "guest_house", 0.09),
    ("Pension", "guest_house", 0.07),
    ("Hostel", "hostel", 0.10),
]
CHAINS = [
    ("CityStay", 3, False, "hotel", ["Altstadt", "Hauptbahnhof", "Messe", "Deutz", "Medienhafen"]),
    ("Domus Suites", 4, True, "hotel", ["Altstadt", "Königsallee", "Messe", "Rudolfplatz"]),
    ("Bridge Hostels", None, False, "hostel", ["Ehrenfeld", "Flingern", "Hauptbahnhof"]),
]


def synthetic_master(seed: int = 7, per_city: int = 150) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for city in load_cities().values():
        districts = DISTRICTS[city.name]
        names: set[str] = set()

        def place(district: str, districts: dict = districts) -> tuple[float, float, str]:
            lat, lon, postcode = districts[district]
            lat, lon = offset(lat, lon, abs(rng.normal(0, 380)), rng.uniform(0, 360))
            return round(lat, 6), round(lon, 6), postcode

        # chain hotels first: they are the hard negatives for duplicate detection
        for brand, stars, superior, kind, wanted in CHAINS:
            for district in [d for d in wanted if d in districts]:
                lat, lon, postcode = place(district)
                name = f"{brand} {city.name} {district}"
                names.add(name)
                rows.append(
                    _hotel(
                        rng,
                        city,
                        name,
                        kind,
                        brand,
                        stars,
                        superior,
                        lat,
                        lon,
                        postcode,
                        website=f"https://www.{slugify(brand)}.de/{slugify(city.name + '-' + district)}",
                    )
                )

        weights = np.array(
            [
                3 if d in ("Altstadt", "Hauptbahnhof", "Königsallee", "Neumarkt") else 1
                for d in districts
            ],
            dtype=float,
        )
        core_districts: dict[str, set[str]] = {}
        while len(names) < per_city:
            prefix, kind, _ = PREFIXES[rng.choice(len(PREFIXES), p=[p[2] for p in PREFIXES])]
            core = CORES[rng.integers(len(CORES))]
            district = list(districts)[rng.choice(len(districts), p=weights / weights.sum())]
            if district in core_districts.get(core, set()):
                continue  # a reused name must sit in another district, as it would in reality
            name = f"{prefix} {core}"
            if name in names or core in core_districts or rng.random() < 0.18:
                name = f"{prefix} {core} {city.name}-{district}"
            if name in names:
                continue
            core_districts.setdefault(core, set()).add(district)
            names.add(name)
            stars, superior = _stars(rng, kind)
            lat, lon, postcode = place(district)
            website = f"https://www.{slugify(name)}.de" if rng.random() < 0.65 else None
            rows.append(
                _hotel(rng, city, name, kind, None, stars, superior, lat, lon, postcode, website)
            )

    df = pd.DataFrame(rows)
    df.insert(0, "hotel_id", [f"syn-{i:04d}" for i in range(1, len(df) + 1)])
    return df[MASTER_COLUMNS]


def _stars(rng: np.random.Generator, kind: str) -> tuple[int | None, bool]:
    if kind == "hostel":
        return (None, False) if rng.random() < 0.8 else (int(rng.integers(1, 3)), False)
    options, probs = (
        ([2, 3, None], [0.3, 0.3, 0.4])
        if kind == "guest_house"
        else ([2, 3, 4, 5, None], [0.12, 0.42, 0.33, 0.05, 0.08])
    )
    stars = options[rng.choice(len(options), p=probs)]
    return stars, stars in (3, 4) and rng.random() < 0.15


def _hotel(rng, city, name, kind, brand, stars, superior, lat, lon, postcode, website) -> dict:
    phone = None
    r = rng.random()
    if r < 0.68:
        phone = f"+49{city.dialing_code}{rng.integers(1, 10)}{rng.integers(10**5, 10**6)}"
    elif r < 0.74:  # mobile numbers and central reservation lines are legitimate too
        phone = rng.choice(
            [
                f"+4915{rng.integers(1, 10)}{rng.integers(10**7, 10**8)}",
                f"+4969{rng.integers(10**6, 10**7)}",
            ]
        )
    housenumber = str(rng.integers(1, 150)) + ("a" if rng.random() < 0.08 else "")
    return {
        "name": name,
        "kind": kind,
        "brand": brand,
        "stars": stars,
        "superior": superior,
        "street": STREETS[city.name][rng.integers(len(STREETS[city.name]))],
        "housenumber": housenumber,
        "postcode": postcode,
        "city": city.name,
        "latitude": lat,
        "longitude": lon,
        "phone": phone,
        "website": website,
        "source": "synthetic",
        "source_ref": None,
    }
