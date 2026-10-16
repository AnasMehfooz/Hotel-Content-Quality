-- MISSING_REQUIRED · completeness · example check (already implemented)
--
-- A listing cannot be shown to travellers without a name, coordinates and a city.
-- Grain: one issue per listing and snapshot, naming every missing field.
-- Pattern to copy for your own checks: read a mart, compute a reason, return the contract columns.

with listings as (
    select * from {{ ref('fct_listings') }}
),

missing as (
    select
        snapshot_date,
        partner,
        listing_id,
        concat_ws(
            ',',
            case when name is null then 'name' end,
            case when latitude is null or longitude is null then 'coordinates' end,
            case when city_raw is null then 'city' end
        ) as missing_fields
    from listings
)

select
    snapshot_date,
    partner,
    listing_id,
    cast(null as varchar) as related_listing_id,
    cast(null as date) as stay_date,
    missing_fields as field,
    cast(null as varchar) as observed_value,
    cast(null as varchar) as expected_value,
    cast(json_object('missing', missing_fields) as varchar) as details
from missing
where missing_fields <> ''
