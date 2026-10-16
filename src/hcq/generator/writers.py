"""Serialize simulated partner feeds into each partner's own file format.

Layout (Hive-style partitions, so DuckDB exposes ``snapshot_date`` as a column):

    raw/northwind/snapshot_date=YYYY-MM-DD/listings.jsonl, rates.jsonl
    raw/rheinland/snapshot_date=YYYY-MM-DD/hotels.csv, preise.csv
    raw/citybeds/snapshot_date=YYYY-MM-DD/properties.json
    raw/mapping/snapshot_date=YYYY-MM-DD/mapping.csv
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import UTC, date, datetime, time
from pathlib import Path

import numpy as np

from hcq.generator.engine import DayFeed, rng_for


def _partition(root: Path, partner: str, snapshot: date) -> Path:
    path = root / partner / f"snapshot_date={snapshot.isoformat()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def german_number(value: float | None, decimals: int) -> str:
    """129.5 -> '129,50'; 1290 -> '1.290,00'; 50.937512 -> '50,937512' (no grouping for coords)."""
    if value is None:
        return ""
    text = f"{value:,.{decimals}f}" if decimals == 2 else f"{value:.{decimals}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def write_northwind(feed: DayFeed, root: Path) -> None:
    out = _partition(root, feed.partner.code, feed.snapshot)
    with (out / "listings.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in feed.records:
            row = {
                "listing_id": r["listing_id"],
                "name": r["name"],
                "address": {
                    "street": r["street"],
                    "postal_code": r["postcode"],
                    "city": r["city"],
                    "country": "DE",
                },
                "geo": {"lat": r["latitude"], "lon": r["longitude"]},
                "stars": r["stars"],
                "phone": r["phone"],
                "website": r["website"],
                "updated_at": r["updated"],
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out / "rates.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for listing_id, stay, price in feed.rates:
            fh.write(
                json.dumps(
                    {
                        "listing_id": listing_id,
                        "stay_date": stay.isoformat(),
                        "price_eur": price,
                        "currency": "EUR",
                    }
                )
                + "\n"
            )


def write_rheinland(feed: DayFeed, root: Path) -> None:
    out = _partition(root, feed.partner.code, feed.snapshot)
    header = [
        "HotelID",
        "Hotelname",
        "Strasse",
        "PLZ",
        "Ort",
        "Breitengrad",
        "Laengengrad",
        "Sterne",
        "Telefon",
        "Webseite",
        "Stand",
    ]
    with (out / "hotels.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=";", lineterminator="\r\n")
        writer.writerow(header)
        for r in feed.records:
            writer.writerow(
                [
                    r["listing_id"],
                    r["name"] or "",
                    r["street"] or "",
                    r["postcode"] or "",
                    r["city"] or "",
                    german_number(r["latitude"], 6),
                    german_number(r["longitude"], 6),
                    r["stars"] if r["stars"] is not None else "",
                    r["phone"] or "",
                    r["website"] or "",
                    r["updated"].strftime("%d.%m.%Y"),
                ]
            )
    with (out / "preise.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=";", lineterminator="\r\n")
        writer.writerow(["HotelID", "Anreise", "Preis"])
        for listing_id, stay, price in feed.rates:
            writer.writerow([listing_id, stay.strftime("%d.%m.%Y"), german_number(price, 2)])


def write_citybeds(feed: DayFeed, root: Path) -> None:
    out = _partition(root, feed.partner.code, feed.snapshot)
    rates: dict[str, list[dict]] = defaultdict(list)
    for listing_id, stay, price in feed.rates:
        rates[listing_id].append(
            {"date": stay.isoformat(), "amount_cents": round(price * 100), "currency": "EUR"}
        )
    properties = [
        {
            "id": r["listing_id"],
            "title": r["name"],
            "location": {
                "address": {"line1": r["street"], "zip": r["postcode"], "city": r["city"]},
                "geo": {"lat": r["latitude"], "lng": r["longitude"]},
            },
            "rating": {"stars": r["stars"]},
            "contact": {"phone": r["phone"], "url": r["website"]},
            "last_modified": r["updated"],
            "rates": rates[r["listing_id"]],
        }
        for r in feed.records
    ]
    generated = int(datetime.combine(feed.snapshot, time(3, 30), tzinfo=UTC).timestamp())
    payload = {"generated_at": generated, "properties": properties}
    (out / "properties.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_mapping(feeds: list[DayFeed], root: Path, seed: int) -> None:
    """The internal mapping table: partner listing -> master hotel. Unmapped listings are absent."""
    snapshot = feeds[0].snapshot
    out = _partition(root, "mapping", snapshot)
    with (out / "mapping.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["partner", "listing_id", "hotel_id", "method", "confidence"])
        for feed in feeds:
            for r in feed.records:
                if r["mapped_hotel_id"] is None:
                    continue
                rng: np.random.Generator = rng_for(
                    seed, "mapping", feed.partner.code, r["listing_id"]
                )
                manual = rng.random() < 0.15
                confidence = "" if manual else f"{rng.uniform(0.78, 0.99):.2f}"
                writer.writerow(
                    [
                        feed.partner.code,
                        r["listing_id"],
                        r["mapped_hotel_id"],
                        "manual" if manual else "auto",
                        confidence,
                    ]
                )


WRITERS = {"northwind": write_northwind, "rheinland": write_rheinland, "citybeds": write_citybeds}
