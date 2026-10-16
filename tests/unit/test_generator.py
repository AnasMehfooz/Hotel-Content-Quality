import hashlib
import json
from datetime import date

import pandas as pd

from hcq.config import Settings
from hcq.generator import generate_feeds
from hcq.generator.catalog import DEFECTS
from hcq.reference import build_reference


def _digest(folder) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        h.update(path.relative_to(folder).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def test_same_seed_same_bytes(tmp_path):
    digests = []
    for run in ("a", "b"):
        s = Settings(data_dir=tmp_path / run, seed=11, days=6, end_date=date(2026, 3, 1))
        build_reference(s, "synthetic")
        generate_feeds(s)
        digests.append(_digest(s.raw_dir))
    assert digests[0] == digests[1]


def test_manifest_covers_every_defect(settings, feeds):
    manifest = pd.read_parquet(settings.manifest_dir / "defects.parquet")
    assert set(manifest["defect_code"]) == set(DEFECTS)
    assert manifest["snapshot_date"].between(feeds.dates[0], feeds.dates[1]).all()


def test_labels_point_at_rows_that_exist(settings, feeds):
    manifest = pd.read_parquet(settings.manifest_dir / "defects.parquet")
    day = manifest[manifest.partner == "northwind"]["snapshot_date"].max()
    rows = pd.read_json(
        settings.raw_dir / "northwind" / f"snapshot_date={day}" / "listings.jsonl", lines=True
    )
    labelled = set(
        manifest[(manifest.partner == "northwind") & (manifest.snapshot_date == day)]["listing_id"]
    )
    assert labelled <= set(rows["listing_id"])


def test_swapped_coordinates_are_really_swapped(settings, feeds):
    manifest = pd.read_parquet(settings.manifest_dir / "defects.parquet")
    swapped = manifest[(manifest.defect_code == "GEO_SWAPPED") & (manifest.partner == "northwind")]
    if swapped.empty:
        return
    label = swapped.iloc[0]
    rows = pd.read_json(
        settings.raw_dir / "northwind" / f"snapshot_date={label.snapshot_date}" / "listings.jsonl",
        lines=True,
    ).set_index("listing_id")
    geo = rows.loc[label.listing_id, "geo"]
    assert geo["lat"] < 10 < geo["lon"]  # lat ~7, lon ~51


def test_incidents_are_written_and_labelled(settings, feeds):
    truth = json.loads((settings.manifest_dir / "incidents.json").read_text(encoding="utf-8"))
    manifest = pd.read_parquet(settings.manifest_dir / "defects.parquet")
    assert len(truth) == 3
    for incident in truth:
        rows = manifest[manifest.incident_id == incident["incident_id"]]
        assert len(rows) > 0
        assert (rows["partner"] == incident["partner"]).all()
        assert str(rows["snapshot_date"].min()) == incident["start_date"]
