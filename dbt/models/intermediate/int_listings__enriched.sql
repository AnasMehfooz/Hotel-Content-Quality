-- Partner listings joined to the mapping table and, through it, to the master catalog.
-- master_* columns are null for unmapped listings.
select
    listings.snapshot_date,
    listings.partner,
    listings.listing_id,
    mapping.hotel_id,
    mapping.mapping_method,
    mapping.mapping_confidence,
    listings.name,
    listings.street,
    listings.postcode,
    listings.city_raw,
    listings.city,
    listings.latitude,
    listings.longitude,
    listings.stars_raw,
    listings.star_class,
    listings.is_superior,
    listings.phone_raw,
    listings.website_raw,
    listings.last_updated,
    master.name as master_name,
    master.kind as master_kind,
    master.brand as master_brand,
    master.stars as master_stars,
    master.is_superior as master_is_superior,
    master.street as master_street,
    master.housenumber as master_housenumber,
    master.postcode as master_postcode,
    master.city as master_city,
    master.latitude as master_latitude,
    master.longitude as master_longitude,
    master.phone as master_phone,
    master.website as master_website
from {{ ref('int_listings__unioned') }} as listings
left join {{ ref('stg_mapping__listings') }} as mapping
    on listings.snapshot_date = mapping.snapshot_date
    and listings.partner = mapping.partner
    and listings.listing_id = mapping.listing_id
left join {{ ref('stg_master__hotels') }} as master
    on mapping.hotel_id = master.hotel_id
