"""Milestones 2-4: each of your checks must reach its precision and recall targets.

A check is skipped while its dbt model still carries the 'stub' tag. Remove the tag when you
start on it; from then on this test holds you to the targets in dbt/seeds/dq_checks.csv.
"""

import pytest

from hcq.generator.catalog import DEFECTS
from hcq.scoring import EXAMPLE_CHECKS, load_scores

YOUR_CHECKS = [
    code for code in DEFECTS if code not in EXAMPLE_CHECKS and code != "DUPLICATE_LISTING"
]


@pytest.fixture(scope="module")
def scores(built):
    return {s.check_code: s for s in load_scores(built)}


@pytest.mark.parametrize("code", YOUR_CHECKS)
def test_check_meets_targets(scores, code):
    score = scores[code]
    if score.status == "todo":
        pytest.skip(f"{code} is still a stub (see MILESTONES.md)")
    assert score.precision is not None, f"{code} found nothing"
    assert score.precision >= score.target_precision, (
        f"{code} precision {score.precision:.3f} < {score.target_precision} "
        f"({score.false_positives} false positives). Inspect eval.eval_matches."
    )
    assert score.recall >= score.target_recall, (
        f"{code} recall {score.recall:.3f} < {score.target_recall} ({score.false_negatives} missed)."
    )
