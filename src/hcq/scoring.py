"""Scoreboard: how each check performs against the injected ground truth."""

from __future__ import annotations

from dataclasses import dataclass

from hcq.config import Settings
from hcq.pipeline import stub_check_codes, warehouse
from hcq.todo import is_todo

EXAMPLE_CHECKS = {"MISSING_REQUIRED", "GEO_SWAPPED"}


@dataclass(frozen=True)
class CheckScore:
    check_code: str
    dimension: str
    title: str
    status: str  # example | todo | pass | fail
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float | None
    recall: float | None
    f1: float | None
    target_precision: float
    target_recall: float

    @property
    def meets_target(self) -> bool:
        return (
            self.precision is not None
            and self.recall is not None
            and self.precision >= self.target_precision
            and self.recall >= self.target_recall
        )


def dedup_is_todo() -> bool:
    from hcq.dedup.matcher import find_duplicate_pairs

    return is_todo(find_duplicate_pairs)


def load_scores(settings: Settings) -> list[CheckScore]:
    stubs = stub_check_codes(settings)
    if dedup_is_todo():
        stubs.add("DUPLICATE_LISTING")
    with warehouse(settings) as con:
        rows = con.sql(
            """
            select check_code, dimension, title, true_positives, false_positives, false_negatives,
                   precision, recall, f1, target_precision, target_recall
            from eval.eval_check_scores
            order by case dimension when 'completeness' then 1 when 'validity' then 2
                     when 'consistency' then 3 when 'accuracy' then 4 when 'timeliness' then 5
                     when 'uniqueness' then 6 else 7 end, check_code
            """
        ).fetchall()
    scores = []
    for code, dim, title, tp, fp, fn, p, r, f1, tp_target, tr_target in rows:
        partial = CheckScore(
            code, dim, title, "", int(tp), int(fp), int(fn), p, r, f1, tp_target, tr_target
        )
        if code in EXAMPLE_CHECKS:
            status = "example"
        elif code in stubs:
            status = "todo"
        else:
            status = "pass" if partial.meets_target else "fail"
        scores.append(CheckScore(**{**partial.__dict__, "status": status}))
    return scores
