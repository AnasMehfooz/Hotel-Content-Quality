-- Rheinland Reisen: German CSV. Decimal commas, dd.mm.yyyy dates, Superior written as "4S".
with source as (
    select * from {{ source('rheinland', 'hotels') }}
)

select
    cast(snapshot_date as date) as snapshot_date,
    'rheinland' as partner,
    "HotelID" as listing_id,
    nullif(trim("Hotelname"), '') as name,
    nullif(trim("Strasse"), '') as street,
    nullif(trim("PLZ"), '') as postcode,
    nullif(trim("Ort"), '') as city_raw,
    try_cast(replace("Breitengrad", ',', '.') as double) as latitude,
    try_cast(replace("Laengengrad", ',', '.') as double) as longitude,
    nullif(trim("Sterne"), '') as stars_raw,
    try_cast(regexp_extract(trim("Sterne"), '^(-?\d+)S?$', 1) as integer) as star_class,
    coalesce(regexp_matches(trim("Sterne"), '^\d+S$'), false) as is_superior,
    nullif(trim("Telefon"), '') as phone_raw,
    nullif(trim("Webseite"), '') as website_raw,
    cast(try_strptime("Stand", '%d.%m.%Y') as date) as last_updated
from source
