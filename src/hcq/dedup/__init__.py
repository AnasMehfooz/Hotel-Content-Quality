"""Duplicate-listing detection: helpers shared by the dbt Python model and the tests."""

from __future__ import annotations

import json

import pandas as pd

PAIR_COLUMNS = ["snapshot_date", "partner", "listing_id", "related_listing_id", "score", "reason"]
ISSUE_COLUMNS = [
    "snapshot_date",
    "partner",
    "listing_id",
    "related_listing_id",
    "stay_date",
    "field",
    "observed_value",
    "expected_value",
    "details",
]


def empty_issue_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "snapshot_date": pd.Series(dtype="datetime64[us]"),
            "partner": pd.Series(dtype="string"),
            "listing_id": pd.Series(dtype="string"),
            "related_listing_id": pd.Series(dtype="string"),
            "stay_date": pd.Series(dtype="datetime64[us]"),
            "field": pd.Series(dtype="string"),
            "observed_value": pd.Series(dtype="string"),
            "expected_value": pd.Series(dtype="string"),
            "details": pd.Series(dtype="string"),
        }
    )


def to_issue_frame(pairs: pd.DataFrame) -> pd.DataFrame:
    """Turn ``find_duplicate_pairs`` output into the dq_issues contract."""
    missing = set(PAIR_COLUMNS) - set(pairs.columns)
    if missing:
        raise ValueError(
            f"find_duplicate_pairs must return columns {PAIR_COLUMNS}; missing {sorted(missing)}"
        )
    if pairs.empty:
        return empty_issue_frame()
    out = empty_issue_frame().reindex(range(len(pairs)))
    out["snapshot_date"] = pd.to_datetime(pairs["snapshot_date"].to_numpy())
    for col in ("partner", "listing_id", "related_listing_id"):
        out[col] = pairs[col].astype("string").to_numpy()
    out["field"] = "listing"
    out["details"] = [
        json.dumps({"score": round(float(s), 4), "reason": str(r)}, ensure_ascii=False)
        for s, r in zip(pairs["score"], pairs["reason"], strict=True)
    ]
    return out
