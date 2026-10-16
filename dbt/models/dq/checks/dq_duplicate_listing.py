"""DUPLICATE_LISTING · uniqueness · Milestone 5 · YOUR CHECK

One partner listing the same hotel twice. A dbt Python model, because fuzzy and semantic
matching is easier in Python than in SQL. This file is only a thin wrapper: implement
``find_duplicate_pairs`` in src/hcq/dedup/matcher.py, where it can be unit tested.
Spec and hints: docs/defect-catalog.md#duplicate_listing
"""


def model(dbt, session):
    dbt.config(materialized="table")

    from hcq.config import get_settings
    from hcq.dedup import empty_issue_frame, to_issue_frame
    from hcq.dedup.embeddings import get_embedder
    from hcq.dedup.matcher import find_duplicate_pairs

    listings = dbt.ref("fct_listings").df()
    try:
        pairs = find_duplicate_pairs(listings, embedder=get_embedder(get_settings()))
    except NotImplementedError:
        return empty_issue_frame()
    return to_issue_frame(pairs)
