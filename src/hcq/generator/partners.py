"""Partner profiles: what each simulated partner covers and how it formats its feed.

The formats deliberately differ the way real partner feeds do (see docs/partner-feeds.md).
Rendering methods turn canonical values into what the partner would actually send.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from hcq.cities import City


@dataclass(frozen=True)
class Partner:
    code: str
    display_name: str
    feed_format: str
    coverage: float  # share of the master catalog this partner lists
    cadence_days: int  # clean listings are refreshed at least this often
    unmapped_rate: float  # listings still waiting to be mapped (legitimate)
    price_spread: float  # partner-specific deviation from a hotel's base rate

    def listing_id(self, n: int) -> str:
        raise NotImplementedError

    def name(self, name: str, city: City, draw: float) -> str:
        return name

    def city(self, city: City) -> str:
        return city.name

    def stars(self, stars: int | None, superior: bool) -> object:
        return stars

    def phone(self, area: str, subscriber: str) -> str:
        return f"+49{area}{subscriber}"

    def website(self, url: str) -> str:
        return url

    def updated(self, day: date, minute: int) -> object:
        return datetime.combine(day, time(5, 0), tzinfo=UTC) + timedelta(minutes=minute)


class Northwind(Partner):
    """Large OTA: JSON lines, ISO timestamps, E.164 phones, integer stars."""

    def listing_id(self, n: int) -> str:
        return f"NW-{n:06d}"

    def updated(self, day: date, minute: int) -> str:
        return super().updated(day, minute).strftime("%Y-%m-%dT%H:%M:%SZ")


class Rheinland(Partner):
    """Regional tour operator: German CSV export (semicolons, decimal commas, dd.mm.yyyy)."""

    def listing_id(self, n: int) -> str:
        return f"{n:07d}"

    def name(self, name: str, city: City, draw: float) -> str:
        return f"{name} {city.name}" if draw < 0.45 and city.name not in name else name

    def city(self, city: City) -> str:
        return city.ascii_name.upper()

    def stars(self, stars: int | None, superior: bool) -> str:
        if stars is None:
            return ""
        return f"{stars}S" if superior else str(stars)

    def phone(self, area: str, subscriber: str) -> str:
        return f"0{area} / {subscriber}"

    def website(self, url: str) -> str:
        return url.removeprefix("https://")

    def updated(self, day: date, minute: int) -> date:
        return day


class CityBeds(Partner):
    """Booking API: nested JSON snapshot, epoch timestamps, prices in cents, half stars."""

    def listing_id(self, n: int) -> str:
        return f"cb_{(n * 2654435761) % 16**10:010x}"  # scrambled, looks like an opaque API id

    def name(self, name: str, city: City, draw: float) -> str:
        return name.removeprefix("Hotel ") if draw < 0.5 else name

    def city(self, city: City) -> str:
        return city.english_name

    def stars(self, stars: int | None, superior: bool) -> float | None:
        if stars is None:
            return None
        return stars + 0.5 if superior else float(stars)

    def phone(self, area: str, subscriber: str) -> str:
        return f"+49 (0){area} {subscriber}"

    def website(self, url: str) -> str:
        return "http://" + url.removeprefix("https://")

    def updated(self, day: date, minute: int) -> int:
        return int(super().updated(day, minute).timestamp())


PARTNERS: tuple[Partner, ...] = (
    Northwind("northwind", "Northwind Stays", "jsonl", 0.80, 1, 0.03, 0.02),
    Rheinland("rheinland", "Rheinland Reisen", "csv_de", 0.62, 7, 0.03, 0.04),
    CityBeds("citybeds", "CityBeds", "json_nested", 0.55, 3, 0.04, 0.05),
)
PARTNERS_BY_CODE = {p.code: p for p in PARTNERS}
