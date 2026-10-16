-- Northwind Stays: JSON lines. Stars are plain integers (no Superior flag), timestamps ISO-8601 UTC.
select
    cast(snapshot_date as date) as snapshot_date,
    'northwind' as partner,
    listing_id,
    nullif(trim(name), '') as name,
    nullif(trim(address.street), '') as street,
    nullif(trim(address.postal_code), '') as postcode,
    nullif(trim(address.city), '') as city_raw,
    geo.lat as latitude,
    geo.lon as longitude,
    nullif(trim(stars), '') as stars_raw,
    try_cast(stars as integer) as star_class,
    false as is_superior,
    nullif(trim(phone), '') as phone_raw,
    nullif(trim(website), '') as website_raw,
    cast(try_strptime(updated_at, '%Y-%m-%dT%H:%M:%SZ') as date) as last_updated
from {{ source('northwind', 'listings') }}
