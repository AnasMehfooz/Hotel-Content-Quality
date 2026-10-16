-- One row per partner listing, snapshot day and stay date, with the listing's city and mapping
-- so prices can be compared within a market.
select
    rates.snapshot_date,
    rates.partner,
    rates.listing_id,
    rates.stay_date,
    rates.price_eur,
    rates.currency,
    listings.hotel_id,
    coalesce(listings.city, listings.master_city) as city,
    listings.star_class,
    listings.master_stars
from {{ ref('int_rates__unioned') }} as rates
left join {{ ref('fct_listings') }} as listings
    on rates.snapshot_date = listings.snapshot_date
    and rates.partner = listings.partner
    and rates.listing_id = listings.listing_id
