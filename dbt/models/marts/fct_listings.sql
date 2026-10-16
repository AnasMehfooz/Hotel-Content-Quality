-- One row per partner listing per snapshot day. The table every listing-level check reads.
select * from {{ ref('int_listings__enriched') }}
