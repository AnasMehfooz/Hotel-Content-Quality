
-- STAR_INVALID · validity · Milestone 2 · YOUR CHECK
--
-- Star ratings outside the 1-5 scale, or a raw value that does not parse.
-- Spec, gotchas and hints: docs/defect-catalog.md#star_invalid
-- Contract: return the columns of dq_empty() (enforced in _checks.yml). See dq_missing_required.sql.
-- Workflow: delete the config line above, replace the select below, then run
--   hcq build --select dq_star_invalid+    and    hcq progress
-- until the check meets its precision and recall targets.
with listings as (
    select * from {{ ref('fct_listings') }}
)

select
    snapshot_date,
    partner,
    listing_id,
    cast(null as varchar) as related_listing_id,
    cast(null as date) as stay_date,
    'stars' as field,
    stars_raw as observed_value,
    '1-5' as expected_value,
    cast(null as varchar) as details
from listings
where
    star_class not between 1 and 5
    or (stars_raw is not null and star_class is null)





