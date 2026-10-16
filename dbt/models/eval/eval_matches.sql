-- Detected issues matched against injected defects.
-- Match keys are defined in macros/dq.sql (dq_match_key).


with predicted as ({{ dq_match_key(ref('dq_issues')) }}),
labelled as ({{ dq_match_key(ref('eval_labels')) }})

select
    coalesce(predicted.check_code, labelled.check_code) as check_code,
    coalesce(predicted.snapshot_date, labelled.snapshot_date) as snapshot_date,
    coalesce(predicted.partner, labelled.partner) as partner,
    coalesce(predicted.key_a, labelled.key_a) as listing_id,
    nullif(coalesce(predicted.key_b, labelled.key_b), '') as related_listing_id,
    nullif(coalesce(predicted.key_c, labelled.key_c), date '1900-01-01') as stay_date,
    predicted.check_code is not null as is_predicted,
    labelled.check_code is not null as is_labelled
from predicted
full outer join labelled
    on predicted.check_code = labelled.check_code
    and predicted.snapshot_date = labelled.snapshot_date
    and predicted.partner = labelled.partner
    and predicted.key_a = labelled.key_a
    and predicted.key_b = labelled.key_b
    and predicted.key_c = labelled.key_c
