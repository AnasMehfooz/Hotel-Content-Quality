-- CityBeds: one nested JSON document per snapshot. Superior is encoded as a half star (4.5),
-- timestamps are Unix epoch seconds.
with properties as (
    select snapshot_date, unnest(properties) as p
    from {{ source('citybeds', 'properties') }}
)

select
    cast(snapshot_date as date) as snapshot_date,
    'citybeds' as partner,
    p.id as listing_id,
    nullif(trim(p.title), '') as name,
    nullif(trim(p.location.address.line1), '') as street,
    nullif(trim(p.location.address.zip), '') as postcode,
    nullif(trim(p.location.address.city), '') as city_raw,
    p.location.geo.lat as latitude,
    p.location.geo.lng as longitude,
    nullif(trim(p.rating.stars), '') as stars_raw,
    cast(floor(try_cast(p.rating.stars as double)) as integer) as star_class,
    coalesce(try_cast(p.rating.stars as double) % 1 = 0.5, false) as is_superior,
    nullif(trim(p.contact.phone), '') as phone_raw,
    nullif(trim(p.contact.url), '') as website_raw,
    cast(epoch_ms(p.last_modified * 1000) as date) as last_updated
from properties
