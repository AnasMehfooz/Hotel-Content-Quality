"""Milestone 5: duplicate listings (src/hcq/dedup/matcher.py)."""

import duckdb
import pytest

from hcq.dedup import PAIR_COLUMNS
from hcq.dedup.matcher import find_duplicate_pairs
from hcq.scoring import load_scores
from hcq.todo import is_todo

pytestmark = pytest.mark.skipif(is_todo(find_duplicate_pairs), reason="Milestone 5 not started")


@pytest.fixture(scope="module")
def listings(built):
    con = duckdb.connect(str(built.warehouse_path), read_only=True)
    try:
        return con.sql("select * from marts.fct_listings").df()
    finally:
        con.close()


def test_pairs_follow_the_contract(listings):
    pairs = find_duplicate_pairs(listings)
    assert list(pairs.columns)[: len(PAIR_COLUMNS)] == PAIR_COLUMNS
    assert (pairs["listing_id"] != pairs["related_listing_id"]).all(), (
        "a listing cannot duplicate itself"
    )
    key = pairs.apply(
        lambda r: (r.snapshot_date, r.partner, *sorted((r.listing_id, r.related_listing_id))),
        axis=1,
    )
    assert key.is_unique, "report each unordered pair once per snapshot day"
    partner_of = listings.set_index(["snapshot_date", "partner", "listing_id"]).index
    for row in pairs.head(200).itertuples():
        assert (row.snapshot_date, row.partner, row.related_listing_id) in partner_of, (
            "pairs stay within one partner"
        )


def test_duplicates_meet_targets(built):
    score = next(s for s in load_scores(built) if s.check_code == "DUPLICATE_LISTING")
    assert score.precision is not None and score.precision >= score.target_precision, score
    assert score.recall >= score.target_recall, score
