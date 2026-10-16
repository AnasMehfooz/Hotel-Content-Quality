"""DUPLICATE_LISTING · Milestone 5 · YOUR CODE

Find listings that one partner sent twice for the same hotel. Spec, examples and hints:
docs/defect-catalog.md#duplicate_listing. Acceptance test: tests/acceptance/test_dedup.py.
"""

from __future__ import annotations

import pandas as pd

from hcq.dedup.embeddings import Embedder
from hcq.todo import todo


@todo("Milestone 5", "See docs/defect-catalog.md#duplicate_listing.")
def find_duplicate_pairs(listings: pd.DataFrame, embedder: Embedder | None = None) -> pd.DataFrame:
    """Return one row per duplicate pair and snapshot day.

    Input: ``fct_listings`` as a DataFrame (one row per snapshot, partner, listing).
    Output columns: snapshot_date, partner, listing_id, related_listing_id, score, reason.
    A pair is unordered; report it once per snapshot day. Only pairs within the same partner
    count: two partners listing the same hotel is expected, not a defect.

    ``embedder`` is optional. Use it to compare names semantically (Köln vs Cologne);
    the acceptance test runs without it, so string and geo features must carry the baseline.
    """
    raise NotImplementedError
