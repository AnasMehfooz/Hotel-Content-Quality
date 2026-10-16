-- Feed completeness: every partner must deliver a snapshot every day.
-- A missing feed is an ingestion incident, not a content issue, so it fails the build.
with days as (select distinct snapshot_date from {{ ref('fct_listings') }}),
     partners as (select distinct partner from {{ ref('fct_listings') }}),
     delivered as (select distinct snapshot_date, partner from {{ ref('fct_listings') }})

select days.snapshot_date, partners.partner
from days
cross join partners
anti join delivered using (snapshot_date, partner)
