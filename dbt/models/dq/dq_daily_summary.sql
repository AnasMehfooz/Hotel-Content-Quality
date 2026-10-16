-- Issues per snapshot day, partner and check, zero-filled so charts show quiet days too.
with listings as (
    select snapshot_date, partner, count(*) as listings
    from {{ ref('fct_listings') }}
    group by all
),

issues as (
    select
        snapshot_date,
        partner,
        check_code,
        count(*) as issues,
        count(distinct listing_id) as affected_listings
    from {{ ref('dq_issues') }}
    group by all
),

grid as (
    select listings.snapshot_date, listings.partner, listings.listings, checks.check_code, checks.dimension, checks.severity
    from listings
    cross join {{ ref('dq_checks') }} as checks
)

select
    grid.snapshot_date,
    grid.partner,
    grid.check_code,
    grid.dimension,
    grid.severity,
    grid.listings,
    coalesce(issues.issues, 0) as issues,
    coalesce(issues.affected_listings, 0) as affected_listings,
    round(coalesce(issues.affected_listings, 0) / grid.listings, 4) as affected_share
from grid
left join issues
    on grid.snapshot_date = issues.snapshot_date
    and grid.partner = issues.partner
    and grid.check_code = issues.check_code
