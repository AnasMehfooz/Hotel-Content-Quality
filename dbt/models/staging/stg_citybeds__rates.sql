with rates as (
    select snapshot_date, p.id as listing_id, unnest(p.rates) as r
    from (
        select snapshot_date, unnest(properties) as p
        from {{ source('citybeds', 'properties') }}
    )
)

select
    cast(snapshot_date as date) as snapshot_date,
    'citybeds' as partner,
    listing_id,
    r."date" as stay_date,
    r.amount_cents / 100.0 as price_eur,
    r.currency
from rates
