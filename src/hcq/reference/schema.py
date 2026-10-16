"""Master catalog schema and the validation every reference build goes through.

The master catalog plays the role of the internal "golden record" that partner listings are
mapped to. It must be internally consistent, otherwise every downstream check inherits its
errors, so records are validated on ingest and failures are written to a quarantine file.
"""

from __future__ import annotations

import re

import pandas as pd

from hcq.cities import load_cities, other_city
from hcq.geo import haversine_km
from hcq.text import normalize_phone_de, normalize_url, transliterate

MASTER_COLUMNS = [
    "hotel_id",
    "name",
    "kind",
    "brand",
    "stars",
    "superior",
    "street",
    "housenumber",
    "postcode",
    "city",
    "latitude",
    "longitude",
    "phone",
    "website",
    "source",
    "source_ref",
]

KINDS = {"hotel", "hostel", "guest_house", "motel"}
_SPACES = re.compile(r"\s+")


def _missing(value: object) -> bool:
    try:
        return value is None or bool(pd.isna(value))
    except (TypeError, ValueError):  # lists/arrays are never "missing"
        return False


def _norm_name(name: str) -> str:
    return _SPACES.sub(" ", transliterate(name).lower()).strip()


def validate_master(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (clean master, quarantine log). Never mutates ``raw``."""
    cities = load_cities()
    issues: list[dict] = []
    rows: list[dict] = []

    for rec in raw.to_dict("records"):
        rec = {k: None if _missing(v) else v for k, v in rec.items()}
        hid = rec["hotel_id"]
        name = _SPACES.sub(" ", str(rec.get("name") or "")).strip()
        city = cities.get(rec.get("city") or "")
        lat, lon = rec.get("latitude"), rec.get("longitude")
        if not name:
            issues.append({"hotel_id": hid, "action": "dropped", "reason": "missing name"})
            continue
        if city is None or lat is None or lon is None:
            issues.append({"hotel_id": hid, "action": "dropped", "reason": "missing city/coords"})
            continue
        if not city.contains(float(lat), float(lon)):
            issues.append({"hotel_id": hid, "action": "dropped", "reason": "outside city bbox"})
            continue

        out = {col: rec.get(col) for col in MASTER_COLUMNS}
        out.update(name=name, latitude=float(lat), longitude=float(lon), city=city.name)
        out["kind"] = rec.get("kind") if rec.get("kind") in KINDS else "hotel"

        stars = rec.get("stars")
        out["stars"] = int(stars) if stars is not None and 1 <= int(stars) <= 5 else None
        out["superior"] = bool(rec.get("superior")) and out["stars"] is not None

        postcode = rec.get("postcode")
        if postcode and not city.postcode_ok(str(postcode)):
            issues.append(
                {
                    "hotel_id": hid,
                    "action": "nulled",
                    "reason": "postcode out of city range",
                    "value": postcode,
                }
            )
            postcode = None
        out["postcode"] = postcode or None

        phone = normalize_phone_de(rec.get("phone"))
        if rec.get("phone") and phone is None:
            issues.append(
                {
                    "hotel_id": hid,
                    "action": "nulled",
                    "reason": "unparseable phone",
                    "value": rec.get("phone"),
                }
            )
        if phone and phone.startswith("+49" + other_city(city.name).dialing_code):
            issues.append(
                {
                    "hotel_id": hid,
                    "action": "nulled",
                    "reason": "phone has other city's area code",
                    "value": phone,
                }
            )
            phone = None
        out["phone"] = phone

        website = normalize_url(rec.get("website"))
        if rec.get("website") and website is None:
            issues.append(
                {
                    "hotel_id": hid,
                    "action": "nulled",
                    "reason": "unparseable website",
                    "value": rec.get("website"),
                }
            )
        out["website"] = website
        rows.append(out)

    master = pd.DataFrame(rows, columns=MASTER_COLUMNS)
    master, dupes = _collapse_duplicates(master)
    issues.extend(dupes)
    master = master.sort_values("hotel_id", ignore_index=True)
    master["stars"] = master["stars"].astype("Int64")
    master["superior"] = master["superior"].astype(bool)
    return master, pd.DataFrame(issues, columns=["hotel_id", "action", "reason", "value"])


def _collapse_duplicates(master: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """OpenStreetMap sometimes maps one hotel twice (a node plus a building outline).

    Same city + same normalized name + under 150 m apart counts as one hotel; the record
    with more filled fields wins.
    """
    master = master.assign(
        _key=master["name"].map(_norm_name),
        _filled=master[MASTER_COLUMNS].notna().sum(axis=1),
    ).sort_values(["city", "_key", "_filled", "hotel_id"], ascending=[True, True, False, True])
    keep: list[int] = []
    issues: list[dict] = []
    for _, group in master.groupby(["city", "_key"], sort=False):
        kept: list[pd.Series] = []
        for idx, rec in group.iterrows():
            twin = next(
                (
                    k
                    for k in kept
                    if haversine_km(k.latitude, k.longitude, rec.latitude, rec.longitude) < 0.15
                ),
                None,
            )
            if twin is None:
                kept.append(rec)
                keep.append(idx)
            else:
                issues.append(
                    {
                        "hotel_id": rec.hotel_id,
                        "action": "dropped",
                        "reason": f"duplicate of {twin.hotel_id}",
                    }
                )
    return master.loc[keep, MASTER_COLUMNS], issues
