-- Every issue from every check, one row per issue, with check metadata attached.
-- The checks to union come from var('dq_checks') in dbt_project.yml.
{%- set checks = var('dq_checks') %}

with unioned as (
    {%- for check in checks %}
    select
        '{{ dq_check_code(check) }}' as check_code,
        cast(snapshot_date as date) as snapshot_date,
        cast(partner as varchar) as partner,
        cast(listing_id as varchar) as listing_id,
        cast(related_listing_id as varchar) as related_listing_id,
        cast(stay_date as date) as stay_date,
        cast(field as varchar) as field,
        cast(observed_value as varchar) as observed_value,
        cast(expected_value as varchar) as expected_value,
        cast(details as varchar) as details
    from {{ ref(check) }}
    {%- if not loop.last %}
    union all
    {%- endif %}
    {%- endfor %}
)

select
    md5(concat_ws(
        '|', unioned.check_code, unioned.snapshot_date, unioned.partner, unioned.listing_id,
        coalesce(unioned.related_listing_id, ''), coalesce(cast(unioned.stay_date as varchar), '')
    )) as issue_id,
    unioned.*,
    checks.dimension,
    checks.severity,
    listings.hotel_id,
    coalesce(listings.city, listings.master_city) as city
from unioned
left join {{ ref('dq_checks') }} as checks
    on unioned.check_code = checks.check_code
left join {{ ref('fct_listings') }} as listings
    on unioned.snapshot_date = listings.snapshot_date
    and unioned.partner = listings.partner
    and unioned.listing_id = listings.listing_id
