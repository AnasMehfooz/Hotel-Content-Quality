-- Ground truth for every injected defect (simulation only; checks never read this).
select
    cast(snapshot_date as date) as snapshot_date,
    partner,
    listing_id,
    defect_code as check_code,
    field,
    cast(stay_date as date) as stay_date,
    related_listing_id,
    incident_id,
    clean_value,
    dirty_value
from {{ source('ground_truth', 'defects') }}
