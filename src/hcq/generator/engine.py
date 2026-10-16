"""Simulate partner feeds over a window of snapshot days, with known injected defects.

Every injected defect is written to a ground-truth manifest, which is what makes it possible
to measure the precision and recall of each data-quality check.

Design notes
- Determinism: every random draw comes from ``rng_for(seed, *keys)``, so the same seed and
  window always produce byte-identical feeds, and changing one partner does not reshuffle
  the others.
- Field groups: a listing never carries two background defects that touch the same field
  group (e.g. ``geo``). That keeps the ground truth unambiguous.
- Incidents are systemic: for a few days a partner's export breaks for every eligible row.
  Background defects in the same field group are suppressed on those rows.
"""

from __future__ import annotations

import zlib
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import urlsplit

import numpy as np
import pandas as pd

from hcq.cities import City, load_cities, other_city
from hcq.generator.catalog import DEFECTS, INCIDENTS, TRADE_FAIR, Incident
from hcq.generator.partners import PARTNERS, Partner
from hcq.geo import haversine_km, offset
from hcq.text import has_non_ascii, mojibake, split_de_number, transliterate

RATE_HORIZON_DAYS = 14

MANIFEST_COLUMNS = [
    "snapshot_date",
    "partner",
    "listing_id",
    "defect_code",
    "field",
    "stay_date",
    "related_listing_id",
    "incident_id",
    "clean_value",
    "dirty_value",
]


def rng_for(seed: int, *keys: object) -> np.random.Generator:
    return np.random.default_rng([seed, *(zlib.crc32(str(k).encode()) for k in keys)])


# --------------------------------------------------------------------------- data model


@dataclass
class Listing:
    partner: Partner
    listing_id: str
    hotel_id: str  # the hotel this listing really describes
    mapped_hotel_id: str | None  # what the mapping table links it to (None = unmapped)
    city: City
    name: str
    street: str | None
    postcode: str | None
    latitude: float
    longitude: float
    stars: int | None
    superior: bool
    phone: tuple[str, str] | None  # (area code, subscriber number)
    website: str | None
    base_price: float
    duplicate_of: str | None = None
    first_day: int = 0


Record = dict  # one rendered listing row as the partner sends it
Apply = Callable[[Record], tuple[str, object, object]]  # -> (field, clean, dirty)


@dataclass
class Planned:
    code: str
    listing_id: str
    start: int
    end: int
    groups: frozenset[str]
    apply: Apply


@dataclass
class PartnerPlan:
    partner: Partner
    listings: list[Listing]
    duplicates: list[Listing]
    defects: dict[str, list[Planned]] = field(default_factory=dict)


@dataclass
class DayFeed:
    partner: Partner
    snapshot: date
    records: list[Record]
    rates: list[tuple[str, date, float]]  # (listing_id, stay_date, price in EUR)


# --------------------------------------------------------------------------- planning


def master_records(master: pd.DataFrame) -> list[dict]:
    """DataFrame rows as plain dicts with real ``None`` for missing values (not NaN/NA)."""
    return [
        {k: None if pd.isna(v) else v for k, v in rec.items()} for rec in master.to_dict("records")
    ]


def base_rate(hotel: dict, rng: np.random.Generator) -> float:
    if hotel["kind"] == "hostel":
        base = 45.0
    elif hotel["kind"] == "guest_house":
        base = 78.0
    else:
        base = {1: 55.0, 2: 72.0, 3: 98.0, 4: 138.0, 5: 265.0}.get(hotel["stars"] or 3, 98.0)
    if hotel["superior"]:
        base *= 1.12
    if hotel["city"] == "Düsseldorf":
        base *= 1.05
    return base * float(rng.lognormal(0.0, 0.16))


def _street(hotel: dict, partner: Partner, draw: float) -> str | None:
    if not hotel["street"]:
        return None
    street = hotel["street"]
    if partner.code == "rheinland" and draw < 0.5:
        street = street.replace("straße", "str.").replace("Straße", "Str.")
    return f"{street} {hotel['housenumber']}" if hotel["housenumber"] else street


def make_listings(partner: Partner, master: pd.DataFrame, seed: int) -> list[Listing]:
    cities = load_cities()
    rng = rng_for(seed, partner.code, "listings")
    covered = [h for h in master_records(master) if rng.random() < partner.coverage]
    numbers = rng.choice(10**6, size=len(covered) * 2, replace=False)
    listings = []
    for hotel, number in zip(covered, numbers, strict=False):
        r = rng_for(seed, partner.code, "listing", hotel["hotel_id"])
        city = cities[hotel["city"]]
        lat, lon = offset(
            hotel["latitude"], hotel["longitude"], r.uniform(3, 90), r.uniform(0, 360)
        )
        stars = hotel["stars"]
        if stars is not None and r.random() < 0.05:  # partners disagree by one star now and then
            stars = int(np.clip(stars + r.choice([-1, 1]), 1, 5))
        if stars is not None and r.random() < 0.04:
            stars = None
        phone = None
        if hotel["phone"] and r.random() < 0.9:
            phone = split_de_number(hotel["phone"])
        website = hotel["website"] if hotel["website"] and r.random() < 0.9 else None
        listings.append(
            Listing(
                partner=partner,
                listing_id=partner.listing_id(int(number)),
                hotel_id=hotel["hotel_id"],
                mapped_hotel_id=None if r.random() < partner.unmapped_rate else hotel["hotel_id"],
                city=city,
                name=partner.name(hotel["name"], city, r.random()),
                street=_street(hotel, partner, r.random()),
                postcode=hotel["postcode"] if r.random() > 0.02 else None,
                latitude=lat,
                longitude=lon,
                stars=stars,
                superior=bool(hotel["superior"]) and stars == hotel["stars"],
                phone=phone,
                website=website,
                base_price=base_rate(hotel, rng_for(seed, "base", hotel["hotel_id"]))
                * (1 + r.uniform(-partner.price_spread, partner.price_spread)),
            )
        )
    return listings


def name_variant(name: str, city: City, rng: np.random.Generator) -> str:
    """How the same hotel ends up with a slightly different name in a second listing."""
    transforms: list[Callable[[str], str]] = [
        str.upper,
        lambda s: transliterate(s),
        lambda s: (
            s.replace(city.name, city.english_name)
            if city.name in s
            else f"{s} {city.english_name}"
        ),
        lambda s: s.removeprefix("Hotel ") if s.startswith("Hotel ") else f"Hotel {s}",
        lambda s: f"{s.removeprefix('Hotel ')} Hotel" if s.startswith("Hotel ") else f"{s} Hotel",
        lambda s: (
            s.replace("Hauptbahnhof", "Hbf").replace("Sankt ", "St. ").replace("Straße", "Str.")
        ),
        lambda s: f"{s} Garni",
        lambda s: f"{s} - City Centre",
    ]
    for _ in range(10):
        out = name
        for idx in rng.choice(len(transforms), size=int(rng.integers(1, 3)), replace=False):
            out = transforms[idx](out)
        if out != name:
            return out
    return f"{name} Garni"


def make_duplicates(
    plan_listings: list[Listing], partner: Partner, seed: int, n_days: int
) -> list[Listing]:
    rng = rng_for(seed, partner.code, "duplicates")
    n = round(DEFECTS["DUPLICATE_LISTING"].rate * len(plan_listings))
    taken = {listing.listing_id for listing in plan_listings}
    dupes = []
    for src_idx in sorted(rng.choice(len(plan_listings), size=n, replace=False)):
        src = plan_listings[src_idx]
        while (new_id := partner.listing_id(int(rng.integers(0, 10**6)))) in taken:
            pass
        taken.add(new_id)
        lat, lon = offset(src.latitude, src.longitude, rng.uniform(5, 60), rng.uniform(0, 360))
        dupes.append(
            Listing(
                partner=partner,
                listing_id=new_id,
                hotel_id=src.hotel_id,
                mapped_hotel_id=src.mapped_hotel_id if rng.random() < 0.3 else None,
                city=src.city,
                name=name_variant(src.name, src.city, rng),
                street=src.street,
                postcode=src.postcode,
                latitude=lat,
                longitude=lon,
                stars=src.stars,
                superior=src.superior,
                phone=src.phone if rng.random() < 0.7 else None,
                website=src.website if rng.random() < 0.7 else None,
                base_price=src.base_price * rng.uniform(0.95, 1.05),
                duplicate_of=src.listing_id,
                first_day=int(rng.integers(0, n_days)),
            )
        )
    return dupes


def wrong_mapping_candidates(master: pd.DataFrame) -> dict[str, list[str]]:
    """For each hotel, plausible wrong targets: same city, 0.3-6 km away, same brand first."""
    recs = master_records(master)
    out: dict[str, list[str]] = {}
    for h in recs:
        dist = {
            o["hotel_id"]: haversine_km(
                h["latitude"], h["longitude"], o["latitude"], o["longitude"]
            )
            for o in recs
            if o["hotel_id"] != h["hotel_id"] and o["city"] == h["city"]
        }
        near = sorted(
            (o for o in recs if 0.3 <= dist.get(o["hotel_id"], 0) <= 6),
            key=lambda o: dist[o["hotel_id"]],
        )
        same_brand = [o["hotel_id"] for o in near if h["brand"] and o["brand"] == h["brand"]]
        out[h["hotel_id"]] = same_brand + [
            o["hotel_id"] for o in near if o["hotel_id"] not in same_brand
        ]
    return out


def _window(rng: np.random.Generator, n_days: int) -> tuple[int, int]:
    start = int(rng.integers(0, n_days))
    if rng.random() < 0.4:
        return start, n_days - 1
    return start, min(n_days - 1, start + int(rng.integers(1, 6)))


def _swap(rec: Record) -> tuple[str, object, object]:
    clean = f"{rec['latitude']},{rec['longitude']}"
    rec["latitude"], rec["longitude"] = rec["longitude"], rec["latitude"]
    return "latitude,longitude", clean, f"{rec['latitude']},{rec['longitude']}"


def _set(rec: Record, fld: str, value: object) -> tuple[str, object, object]:
    clean = rec[fld]
    rec[fld] = value
    return fld, clean, value


def _mojibake(rec: Record) -> tuple[str, object, object]:
    fields = [f for f in ("name", "street") if has_non_ascii(rec[f])]
    clean = "|".join(str(rec[f]) for f in fields)
    for f in fields:
        rec[f] = mojibake(rec[f])
    return ",".join(fields), clean, "|".join(str(rec[f]) for f in fields)


def plan_defects(
    plan: PartnerPlan,
    master: pd.DataFrame,
    candidates: dict[str, list[str]],
    seed: int,
    n_days: int,
) -> None:
    partner = plan.partner
    used: dict[str, set[str]] = defaultdict(set)
    # The originals of duplicated listings keep clean names, coordinates and mappings, so every
    # duplicate pair stays a pure uniqueness problem (and is labelled unambiguously).
    for dup in plan.duplicates:
        used[dup.duplicate_of] |= {"geo", "name", "mapping"}
    postcodes = {
        c: sorted(master.loc[master.city == c, "postcode"].dropna().unique()) for c in load_cities()
    }
    hotel_pos = {h.hotel_id: (h.latitude, h.longitude) for h in master.itertuples()}
    master_stars = {h["hotel_id"]: h["stars"] for h in master_records(master)}

    def variants_for(
        code: str, li: Listing, rng: np.random.Generator
    ) -> tuple[frozenset[str], Apply] | None:
        p = partner
        if code == "MISSING_REQUIRED":
            what = ["name", "coordinates", "city"][rng.choice(3, p=[0.4, 0.4, 0.2])]
            if what == "coordinates":

                def apply(rec):
                    clean = f"{rec['latitude']},{rec['longitude']}"
                    rec["latitude"] = rec["longitude"] = None
                    return "latitude,longitude", clean, None

                return frozenset({"geo"}), apply
            fld = "name" if what == "name" else "city"
            return frozenset({"name" if what == "name" else "address"}), lambda rec: _set(
                rec, fld, None
            )
        if code == "ENCODING_MOJIBAKE":
            if not (has_non_ascii(li.name) or has_non_ascii(li.street)):
                return None
            return frozenset({"name", "street"}), _mojibake
        if code == "STAR_INVALID":
            bad = int(rng.choice([0, 6, 7, 9]))
            value = p.stars(bad, bool(rng.random() < 0.3))
            return frozenset({"stars"}), lambda rec: _set(rec, "stars", value)
        if code == "PHONE_INVALID":
            if not li.phone:
                return None
            area, sub = li.phone
            kind = rng.choice(["truncated", "letters", "too_long"])
            if kind == "truncated":
                value = p.phone(area, sub[:2])
            elif kind == "letters":
                value = p.phone(area, sub[:2] + "HOTEL")
            else:
                value = p.phone(area, sub + "".join(str(d) for d in rng.integers(0, 10, size=8)))
            return frozenset({"phone"}), lambda rec: _set(rec, "phone", value)
        if code == "URL_INVALID":
            if not li.website:
                return None
            host = urlsplit(li.website).hostname or "hotel.de"
            value = str(
                rng.choice(
                    [
                        f"htp://{host}",
                        f"https//{host}",
                        f"https://{host.replace('.', ' .', 1)}",
                        "http://example.com",
                        f"https://{host.replace('.', '..', 1)}",
                        "n/a",
                    ]
                )
            )
            return frozenset({"website"}), lambda rec: _set(rec, "website", value)
        if code == "ADDRESS_CITY_MISMATCH":
            other = other_city(li.city.name)
            options = []
            if li.postcode and postcodes[other.name]:
                options.append("postcode")
            if li.phone and li.phone[0] == li.city.dialing_code:
                options.append("phone")
            if not options:
                return None
            if rng.choice(options) == "postcode":
                value = str(rng.choice(postcodes[other.name]))
                return frozenset({"address"}), lambda rec: _set(rec, "postcode", value)
            value = p.phone(other.dialing_code, li.phone[1])
            return frozenset({"phone"}), lambda rec: _set(rec, "phone", value)
        if code == "STAR_CONFLICT":
            ref = master_stars.get(li.hotel_id)
            if li.mapped_hotel_id is None or ref is None:
                return None
            choices = [s for s in (ref - 3, ref - 2, ref + 2, ref + 3) if 1 <= s <= 5]
            value = p.stars(int(rng.choice(choices)), False)
            return frozenset({"stars", "mapping"}), lambda rec: _set(rec, "stars", value)
        if code == "GEO_SWAPPED":
            return frozenset({"geo"}), _swap
        if code == "GEO_OFFSET":
            if li.mapped_hotel_id is None:
                return None
            lat0, lon0 = hotel_pos[li.hotel_id]
            c_lat, c_lon = li.city.centroid
            if haversine_km(lat0, lon0, c_lat, c_lon) >= 2 and rng.random() < 0.5:
                new = (c_lat, c_lon)  # geocoder fell back to the city centre
            else:
                new = offset(
                    li.latitude, li.longitude, rng.uniform(2000, 15000), rng.uniform(0, 360)
                )
            new = (round(new[0], 6), round(new[1], 6))

            def apply(rec, new=new):
                clean = f"{rec['latitude']},{rec['longitude']}"
                rec["latitude"], rec["longitude"] = new
                return "latitude,longitude", clean, f"{new[0]},{new[1]}"

            return frozenset({"geo", "mapping"}), apply
        if code == "WRONG_MAPPING":
            options = candidates.get(li.hotel_id, [])
            if li.mapped_hotel_id is None or not options:
                return None
            pool = options[:3] if rng.random() < 0.6 else options
            value = str(rng.choice(pool))
            return frozenset({"mapping", "geo", "name"}), lambda rec: _set(
                rec, "mapped_hotel_id", value
            )
        if code == "STALE_LISTING":
            age = int(rng.integers(120, 500))
            minute = int(rng.integers(0, 600))
            return frozenset({"freshness"}), lambda rec, age=age, minute=minute: _set(
                rec,
                "updated",
                p.updated(rec["_snapshot"] - timedelta(days=age + rec["_day"]), minute),
            )
        raise KeyError(code)

    listing_codes = [c for c, d in DEFECTS.items() if d.grain == "listing"]
    for code in listing_codes:
        rng = rng_for(seed, partner.code, "defect", code)
        drafts = []
        for li in plan.listings:
            draft = variants_for(
                code, li, rng_for(seed, partner.code, "variant", code, li.listing_id)
            )
            if draft is not None:
                drafts.append((li, draft))
        target = round(DEFECTS[code].rate * len(drafts))
        order = rng.permutation(len(drafts))
        chosen = 0
        for idx in order:
            if chosen >= target:
                break
            li, (groups, apply) = drafts[idx]
            if used[li.listing_id] & groups:
                continue
            used[li.listing_id] |= groups
            start, end = _window(rng, n_days)
            plan.defects.setdefault(li.listing_id, []).append(
                Planned(code, li.listing_id, start, end, groups, apply)
            )
            chosen += 1


# --------------------------------------------------------------------------- simulation

INCIDENT_GROUPS = {
    "GEO_SWAPPED": frozenset({"geo"}),
    "ENCODING_MOJIBAKE": frozenset({"name", "street"}),
}


def render(li: Listing, snapshot: date, day_idx: int, age: int, minute: int) -> Record:
    p = li.partner
    return {
        "listing_id": li.listing_id,
        "name": li.name,
        "street": li.street,
        "postcode": li.postcode,
        "city": p.city(li.city),
        "latitude": round(li.latitude, 6),
        "longitude": round(li.longitude, 6),
        "stars": p.stars(li.stars, li.superior),
        "phone": p.phone(*li.phone) if li.phone else None,
        "website": p.website(li.website) if li.website else None,
        "updated": p.updated(snapshot - timedelta(days=age), minute),
        "mapped_hotel_id": li.mapped_hotel_id,
        "_snapshot": snapshot,
        "_day": day_idx,
    }


def _incident_applies(incident: Incident, rec: Record) -> bool:
    if incident.defect == "GEO_SWAPPED":
        return True
    if incident.defect == "ENCODING_MOJIBAKE":
        return has_non_ascii(rec["name"]) or has_non_ascii(rec["street"])
    return False


def _dow_factor(day: date) -> float:
    return (1.05, 1.05, 1.05, 1.03, 1.0, 1.08, 0.9)[day.weekday()]


class Simulation:
    def __init__(self, master: pd.DataFrame, seed: int, dates: list[date]):
        self.master = master
        self.seed = seed
        self.dates = dates
        n_days = len(dates)
        candidates = wrong_mapping_candidates(master)
        self.plans: list[PartnerPlan] = []
        for partner in PARTNERS:
            listings = make_listings(partner, master, seed)
            plan = PartnerPlan(partner, listings, make_duplicates(listings, partner, seed, n_days))
            plan_defects(plan, master, candidates, seed, n_days)
            self.plans.append(plan)
        fair_start = dates[0] + timedelta(days=round(TRADE_FAIR["start_frac"] * (n_days - 1)))
        self.fair_nights = {fair_start + timedelta(days=i) for i in range(TRADE_FAIR["nights"])}
        lo, hi = TRADE_FAIR["multiplier"]
        self.fair_multiplier = {
            h: float(rng_for(seed, "fair", h).uniform(lo, hi))
            for h in master.loc[master.city == TRADE_FAIR["city"], "hotel_id"]
        }
        self.incidents = [(inc, *inc.days(n_days)) for inc in INCIDENTS]
        self.manifest: list[dict] = []

    def _active_incident(self, partner: str, day_idx: int) -> Incident | None:
        for inc, start, end in self.incidents:
            if inc.partner == partner and start <= day_idx <= end:
                return inc
        return None

    def _label(
        self,
        snapshot: date,
        partner: str,
        listing_id: str,
        code: str,
        fld,
        clean,
        dirty,
        stay_date=None,
        related=None,
        incident=None,
    ) -> None:
        self.manifest.append(
            {
                "snapshot_date": snapshot,
                "partner": partner,
                "listing_id": listing_id,
                "defect_code": code,
                "field": fld,
                "stay_date": stay_date,
                "related_listing_id": related,
                "incident_id": incident,
                "clean_value": None if clean is None else str(clean),
                "dirty_value": None if dirty is None else str(dirty),
            }
        )

    def days(self) -> Iterator[DayFeed]:
        for day_idx, snapshot in enumerate(self.dates):
            for plan in self.plans:
                yield self._day(plan, day_idx, snapshot)

    def _day(self, plan: PartnerPlan, day_idx: int, snapshot: date) -> DayFeed:
        partner = plan.partner
        rng = rng_for(self.seed, partner.code, "day", day_idx)
        incident = self._active_incident(partner.code, day_idx)
        live = plan.listings + [d for d in plan.duplicates if d.first_day <= day_idx]
        records: list[Record] = []
        for li in live:
            rec = render(
                li,
                snapshot,
                day_idx,
                int(rng.integers(0, partner.cadence_days)),
                int(rng.integers(0, 600)),
            )
            hit = (
                incident is not None
                and incident.defect in INCIDENT_GROUPS
                and _incident_applies(incident, rec)
            )
            for planned in plan.defects.get(li.listing_id, []):
                if not planned.start <= day_idx <= planned.end:
                    continue
                if hit and planned.groups & INCIDENT_GROUPS[incident.defect]:
                    continue  # the systemic incident masks this field today
                fld, clean, dirty = planned.apply(rec)
                self._label(snapshot, partner.code, li.listing_id, planned.code, fld, clean, dirty)
            if hit:
                fld, clean, dirty = (
                    _swap(rec) if incident.defect == "GEO_SWAPPED" else _mojibake(rec)
                )
                self._label(
                    snapshot,
                    partner.code,
                    li.listing_id,
                    incident.defect,
                    fld,
                    clean,
                    dirty,
                    incident=incident.incident_id,
                )
            if li.duplicate_of:
                self._label(
                    snapshot,
                    partner.code,
                    li.listing_id,
                    "DUPLICATE_LISTING",
                    "listing",
                    None,
                    None,
                    related=li.duplicate_of,
                )
            records.append(rec)
        return DayFeed(
            partner, snapshot, records, self._rates(plan, live, day_idx, snapshot, incident)
        )

    def _rates(
        self,
        plan: PartnerPlan,
        live: list[Listing],
        day_idx: int,
        snapshot: date,
        incident: Incident | None,
    ) -> list[tuple[str, date, float]]:
        partner = plan.partner
        rng = rng_for(self.seed, partner.code, "rates", day_idx)
        units_bug = incident is not None and incident.defect == "PRICE_OUTLIER"
        stays = [snapshot + timedelta(days=k) for k in range(1, RATE_HORIZON_DAYS + 1)]
        noise = np.clip(rng.normal(0, 0.03, size=(len(live), len(stays))), -0.08, 0.08)
        outlier_draw = rng.random(size=(len(live), len(stays)))
        kinds = rng.choice(
            ["x100", "div100", "zero"], p=[0.4, 0.4, 0.2], size=(len(live), len(stays))
        )
        rates = []
        for i, li in enumerate(live):
            for j, stay in enumerate(stays):
                price = li.base_price * _dow_factor(stay) * (1 + noise[i, j])
                if stay in self.fair_nights:
                    price *= self.fair_multiplier.get(li.hotel_id, 1.0)
                price = round(price, 2)
                if units_bug:
                    dirty = round(price / 100, 2)
                    self._label(
                        snapshot,
                        partner.code,
                        li.listing_id,
                        "PRICE_OUTLIER",
                        "price",
                        price,
                        dirty,
                        stay_date=stay,
                        incident=incident.incident_id,
                    )
                    price = dirty
                elif outlier_draw[i, j] < DEFECTS["PRICE_OUTLIER"].rate:
                    dirty = {
                        "x100": round(price * 100, 2),
                        "div100": round(price / 100, 2),
                        "zero": 0.0,
                    }[kinds[i, j]]
                    self._label(
                        snapshot,
                        partner.code,
                        li.listing_id,
                        "PRICE_OUTLIER",
                        "price",
                        price,
                        dirty,
                        stay_date=stay,
                    )
                    price = dirty
                rates.append((li.listing_id, stay, price))
        return rates

    def manifest_frame(self) -> pd.DataFrame:
        df = pd.DataFrame(self.manifest, columns=MANIFEST_COLUMNS)
        for col in ("snapshot_date", "stay_date"):
            df[col] = pd.to_datetime(df[col]).dt.date
        return df

    def incidents_truth(self) -> list[dict]:
        return [
            {
                "incident_id": inc.incident_id,
                "partner": inc.partner,
                "defect_code": inc.defect,
                "start_date": self.dates[start].isoformat(),
                "end_date": self.dates[end].isoformat(),
                "description": inc.description,
            }
            for inc, start, end in self.incidents
        ]
