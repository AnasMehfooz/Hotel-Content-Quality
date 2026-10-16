"""Fetch real hotels for Köln and Düsseldorf from OpenStreetMap via the Overpass API.

Data © OpenStreetMap contributors, available under the Open Database License (ODbL).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterable

import httpx
import pandas as pd

from hcq.cities import City, load_cities

log = logging.getLogger(__name__)

USER_AGENT = "hotel-content-quality/0.1 (data-quality portfolio project)"
TOURISM = "^(hotel|hostel|guest_house|motel)$"
_STARS = re.compile(r"^\s*([1-5])(?:[.,]5)?\s*(s|sup|superior)?\s*$", re.IGNORECASE)


def overpass_query(city: City, by: str = "name") -> str:
    """Overpass QL for every named hotel-like place inside the city's boundary."""
    if by == "name":
        area = f'area["boundary"="administrative"]["admin_level"="6"]["name"="{city.name}"]->.a;'
    else:  # official municipality key, robust against renamed boundaries
        area = f'area["boundary"="administrative"]["de:amtlicher_gemeindeschluessel"="{city.ags}"]->.a;'
    return (
        f'[out:json][timeout:120];{area}nwr["tourism"~"{TOURISM}"]["name"](area.a);out center tags;'
    )


def parse_stars(value: str | None) -> tuple[int | None, bool]:
    """'4' -> (4, False); '4S' / '4 Superior' / '4.5' -> (4, True); anything else -> (None, False)."""
    if not value:
        return None, False
    match = _STARS.match(value)
    if not match:
        return None, False
    superior = bool(match.group(2)) or "5" in value[1:]
    return int(match.group(1)), superior


def parse_elements(elements: Iterable[dict], city: City) -> pd.DataFrame:
    rows = []
    for el in elements:
        tags = el.get("tags", {})
        lat = el.get("lat", el.get("center", {}).get("lat"))
        lon = el.get("lon", el.get("center", {}).get("lon"))
        stars, superior = parse_stars(tags.get("stars"))
        rows.append(
            {
                "hotel_id": f"osm-{el['type'][0]}{el['id']}",
                "name": tags.get("name"),
                "kind": tags.get("tourism"),
                "brand": tags.get("brand"),
                "stars": stars,
                "superior": superior,
                "street": tags.get("addr:street"),
                "housenumber": tags.get("addr:housenumber"),
                "postcode": tags.get("addr:postcode"),
                "city": city.name,  # the boundary query is authoritative, addr:city often missing
                "latitude": lat,
                "longitude": lon,
                "phone": tags.get("phone") or tags.get("contact:phone"),
                "website": tags.get("website") or tags.get("contact:website") or tags.get("url"),
                "source": "osm",
                "source_ref": f"{el['type']}/{el['id']}",
            }
        )
    return pd.DataFrame(rows)


def _post(client: httpx.Client, url: str, query: str, attempts: int = 4) -> dict:
    for attempt in range(1, attempts + 1):
        try:
            resp = client.post(url, data={"data": query})
            if resp.status_code in (429, 502, 503, 504):
                raise httpx.HTTPStatusError("overpass busy", request=resp.request, response=resp)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            if attempt == attempts:
                raise
            wait = 5 * 2 ** (attempt - 1)
            log.warning("Overpass request failed (%s), retrying in %ss", exc, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def fetch_osm_hotels(overpass_url: str, timeout: float = 180.0) -> pd.DataFrame:
    frames = []
    with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
        for city in load_cities().values():
            elements: list[dict] = []
            for by in ("name", "ags"):
                payload = _post(client, overpass_url, overpass_query(city, by=by))
                elements = payload.get("elements", [])
                if elements:
                    break
                log.warning("No hotels for %s when matching boundary by %s", city.name, by)
            if not elements:
                raise RuntimeError(f"Overpass returned no hotels for {city.name}")
            log.info("Fetched %d OSM elements for %s", len(elements), city.name)
            frames.append(parse_elements(elements, city))
            time.sleep(2)  # be polite to the public Overpass instance
    return pd.concat(frames, ignore_index=True)
