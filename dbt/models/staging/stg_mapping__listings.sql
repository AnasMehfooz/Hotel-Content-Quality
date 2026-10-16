select
    cast(snapshot_date as date) as snapshot_date,
    partner,
    listing_id,
    hotel_id,
    method as mapping_method,
    try_cast(nullif(confidence, '') as double) as mapping_confidence
from {{ source('mapping', 'mapping') }}
