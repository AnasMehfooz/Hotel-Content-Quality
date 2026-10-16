"""Generate partner feeds with injected, labelled defects (see docs/defect-catalog.md)."""

from __future__ import annotations

import json
import logging
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from hcq.config import Settings
from hcq.generator.catalog import DEFECTS, INCIDENTS
from hcq.generator.engine import Simulation
from hcq.generator.partners import PARTNERS
from hcq.generator.writers import WRITERS, write_mapping
from hcq.reference import load_reference

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedBuild:
    raw_dir: Path
    dates: tuple[date, date]
    listings: int
    rates: int
    labels: int
    by_defect: dict[str, int]


def generate_feeds(
    settings: Settings,
    *,
    days: int | None = None,
    end_date: date | None = None,
    seed: int | None = None,
) -> FeedBuild:
    days = days or settings.days
    end = end_date or settings.resolved_end_date()
    seed = settings.seed if seed is None else seed
    if days < 5:
        raise ValueError("simulate at least 5 days so the incidents have room to happen")
    dates = [end - timedelta(days=days - 1 - i) for i in range(days)]
    master = load_reference(settings.reference_path)

    raw = settings.raw_dir
    if raw.exists():
        shutil.rmtree(raw)  # feeds are fully re-simulated, never appended
    raw.mkdir(parents=True)

    sim = Simulation(master, seed, dates)
    n_listings = n_rates = 0
    day_feeds = []
    for feed in sim.days():
        WRITERS[feed.partner.code](feed, raw)
        n_listings += len(feed.records)
        n_rates += len(feed.rates)
        day_feeds.append(feed)
        if len(day_feeds) == len(PARTNERS):
            write_mapping(day_feeds, raw, seed)
            day_feeds = []

    manifest = sim.manifest_frame()
    settings.manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest.to_parquet(settings.manifest_dir / "defects.parquet", index=False)
    (settings.manifest_dir / "incidents.json").write_text(
        json.dumps(sim.incidents_truth(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    by_defect = dict(Counter(manifest["defect_code"]))
    scenario = {
        "seed": seed,
        "first_snapshot": dates[0].isoformat(),
        "last_snapshot": dates[-1].isoformat(),
        "master_hotels": len(master),
        "partners": [p.code for p in PARTNERS],
        "trade_fair_nights": sorted(d.isoformat() for d in sim.fair_nights),
        "labels_by_defect": by_defect,
        "defect_codes": list(DEFECTS),
        "incidents": [i.incident_id for i in INCIDENTS],
    }
    (settings.manifest_dir / "scenario.json").write_text(
        json.dumps(scenario, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("Generated %d listing rows, %d rates, %d labels", n_listings, n_rates, len(manifest))
    return FeedBuild(raw, (dates[0], dates[-1]), n_listings, n_rates, len(manifest), by_defect)


__all__ = ["FeedBuild", "generate_feeds"]
