-- What each detected issue really is: part of an injected incident, a background defect,
-- or a false positive. The agent evaluation uses this to grade incident classification.
with issues as (
    select
        issue_id,
        check_code,
        snapshot_date,
        partner,
        case when check_code = 'DUPLICATE_LISTING'
            then least(listing_id, coalesce(related_listing_id, '')) else listing_id end as key_a,
        case when check_code = 'DUPLICATE_LISTING'
            then greatest(listing_id, coalesce(related_listing_id, '')) else '' end as key_b,
        case when check_code = 'PRICE_OUTLIER' then coalesce(stay_date, date '1900-01-01')
            else date '1900-01-01' end as key_c
    from {{ ref('dq_issues') }}
),

labels as (
    select
        check_code,
        snapshot_date,
        partner,
        case when check_code = 'DUPLICATE_LISTING'
            then least(listing_id, coalesce(related_listing_id, '')) else listing_id end as key_a,
        case when check_code = 'DUPLICATE_LISTING'
            then greatest(listing_id, coalesce(related_listing_id, '')) else '' end as key_b,
        case when check_code = 'PRICE_OUTLIER' then coalesce(stay_date, date '1900-01-01')
            else date '1900-01-01' end as key_c,
        max(incident_id) as incident_id
    from {{ ref('eval_labels') }}
    group by all
)

select
    issues.issue_id,
    case
        when labels.check_code is null then 'false_positive'
        when labels.incident_id is not null then 'systemic'
        else 'record_level'
    end as truth_kind,
    labels.incident_id
from issues
left join labels
    on issues.check_code = labels.check_code
    and issues.snapshot_date = labels.snapshot_date
    and issues.partner = labels.partner
    and issues.key_a = labels.key_a
    and issues.key_b = labels.key_b
    and issues.key_c = labels.key_c
