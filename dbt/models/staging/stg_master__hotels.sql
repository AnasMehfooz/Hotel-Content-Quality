select
    hotel_id,
    name,
    kind,
    brand,
    cast(stars as integer) as stars,
    superior as is_superior,
    street,
    housenumber,
    postcode,
    city,
    latitude,
    longitude,
    phone,
    website,
    source
from {{ source('master', 'hotels') }}
