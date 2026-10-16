"""Build the master hotel catalog (from OpenStreetMap or the offline synthetic set)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hcq.config import Settings
from hcq.reference.schema import MASTER_COLUMNS, validate_master

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReferenceBuild:
    path: Path
    hotels: int
    quarantined: int
    source: str


def build_reference(settings: Settings, source: str | None = None) -> ReferenceBuild:
    source = source or settings.reference
    if source == "osm":
        from hcq.reference.osm import fetch_osm_hotels

        raw = fetch_osm_hotels(settings.overpass_url)
    elif source == "synthetic":
        from hcq.reference.synthetic import synthetic_master

        raw = synthetic_master()
    else:
        raise ValueError(f"unknown reference source {source!r}")

    master, quarantine = validate_master(raw)
    settings.reference_dir.mkdir(parents=True, exist_ok=True)
    master.to_parquet(settings.reference_path, index=False)
    quarantine.to_csv(settings.reference_dir / "quarantine.csv", index=False, encoding="utf-8")
    log.info("Master catalog: %d hotels (%d quarantine entries)", len(master), len(quarantine))
    return ReferenceBuild(settings.reference_path, len(master), len(quarantine), source)


def load_reference(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `hcq reference` first.")
    return pd.read_parquet(path)[MASTER_COLUMNS]


__all__ = ["MASTER_COLUMNS", "ReferenceBuild", "build_reference", "load_reference"]
