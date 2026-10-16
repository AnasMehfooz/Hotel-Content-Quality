select
    snapshot_date,
    check_code,
    count_if(is_predicted) as predicted,
    count_if(is_labelled) as labelled,
    count_if(is_predicted and is_labelled) as true_positives
from {{ ref('eval_matches') }}
group by all
