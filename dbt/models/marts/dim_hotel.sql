-- Master hotels plus how many partners list each one on the latest snapshot.
with latest as (
    select max(snapshot_date) as snapshot_date from {{ ref('fct_listings') }}
),

coverage as (
    select hotel_id, count(distinct partner) as partners_listing
    from {{ ref('fct_listings') }}
    where snapshot_date = (select snapshot_date from latest) and hotel_id is not null
    group by hotel_id
)

select
    hotels.*,
    coalesce(coverage.partners_listing, 0) as partners_listing
from {{ ref('stg_master__hotels') }} as hotels
left join coverage using (hotel_id)
