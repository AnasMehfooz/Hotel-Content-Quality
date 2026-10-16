select
    incident_id,
    partner,
    defect_code as check_code,
    cast(start_date as date) as start_date,
    cast(end_date as date) as end_date,
    description
from {{ source('ground_truth', 'incidents') }}
