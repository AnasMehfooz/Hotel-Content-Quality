select
    cast(snapshot_date as date) as snapshot_date,
    'northwind' as partner,
    listing_id,
    stay_date,
    price_eur,
    currency
from {{ source('northwind', 'rates') }}
