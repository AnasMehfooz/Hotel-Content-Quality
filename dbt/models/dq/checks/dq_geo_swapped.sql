-- GEO_SWAPPED · accuracy · example check (already implemented)
--
-- Köln and Düsseldorf sit around latitude 51, longitude 7. A swapped pair therefore lands near
-- latitude 7, longitude 51, in the Horn of Africa. Flag a listing when its coordinates fall
-- outside every city's bounding box as given, but inside one once you swap them.

with listings as (
    select * from {{ ref('fct_listings') }}
    where latitude is not null and longitude is not null
),

cities as (
    select * from {{ ref('city_reference') }}
),

located as (
    select
        listings.*,
        exists (
            select 1 from cities
            where listings.latitude between cities.min_lat and cities.max_lat
              and listings.longitude between cities.min_lon and cities.max_lon
        ) as inside_as_given,
        exists (
            select 1 from cities
            where listings.longitude between cities.min_lat and cities.max_lat
              and listings.latitude between cities.min_lon and cities.max_lon
        ) as inside_when_swapped
    from listings
)

select
    snapshot_date,
    partner,
    listing_id,
    cast(null as varchar) as related_listing_id,
    cast(null as date) as stay_date,
    'latitude,longitude' as field,
    concat(latitude, ',', longitude) as observed_value,
    concat(longitude, ',', latitude) as expected_value,
    cast(json_object('rule', 'inside a city bbox only after swapping') as varchar) as details
from located
where inside_when_swapped and not inside_as_given
