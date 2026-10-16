-- Precision, recall and F1 per check against the injected ground truth.
with counts as (
    select
        check_code,
        count_if(is_predicted and is_labelled) as true_positives,
        count_if(is_predicted and not is_labelled) as false_positives,
        count_if(is_labelled and not is_predicted) as false_negatives
    from {{ ref('eval_matches') }}
    group by check_code
)

select
    checks.check_code,
    checks.dimension,
    checks.title,
    coalesce(counts.true_positives, 0) as true_positives,
    coalesce(counts.false_positives, 0) as false_positives,
    coalesce(counts.false_negatives, 0) as false_negatives,
    round(counts.true_positives / nullif(counts.true_positives + counts.false_positives, 0), 4) as precision,
    round(counts.true_positives / nullif(counts.true_positives + counts.false_negatives, 0), 4) as recall,
    round(2 * counts.true_positives
        / nullif(2 * counts.true_positives + counts.false_positives + counts.false_negatives, 0), 4) as f1,
    checks.target_precision,
    checks.target_recall
from {{ ref('dq_checks') }} as checks
left join counts using (check_code)
