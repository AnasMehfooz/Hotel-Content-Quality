{#-
  Every check model returns rows with exactly these columns (enforced by the model contract in
  models/dq/checks/_checks.yml). One row = one issue at the check's grain:
    listing grain: snapshot_date + partner + listing_id
    rate grain:    ... + stay_date            (PRICE_OUTLIER)
    pair grain:    ... + related_listing_id   (DUPLICATE_LISTING)
-#}
{% macro dq_empty() -%}
select
    cast(null as date) as snapshot_date,
    cast(null as varchar) as partner,
    cast(null as varchar) as listing_id,
    cast(null as varchar) as related_listing_id,
    cast(null as date) as stay_date,
    cast(null as varchar) as field,
    cast(null as varchar) as observed_value,
    cast(null as varchar) as expected_value,
    cast(null as varchar) as details
where false
{%- endmacro %}

{% macro dq_check_code(model_name) -%}
    {{ model_name | upper | replace('DQ_', '', 1) }}
{%- endmacro %}

{#- Match key used by the eval models. Listing checks match on (snapshot, partner, listing);
    PRICE_OUTLIER also on stay_date; DUPLICATE_LISTING on the unordered pair of ids. -#}
{% macro dq_match_key(relation) -%}
    select distinct
        check_code,
        snapshot_date,
        partner,
        case when check_code = 'DUPLICATE_LISTING'
            then least(listing_id, coalesce(related_listing_id, '')) else listing_id end as key_a,
        case when check_code = 'DUPLICATE_LISTING'
            then greatest(listing_id, coalesce(related_listing_id, '')) else '' end as key_b,
        case when check_code = 'PRICE_OUTLIER' then coalesce(stay_date, date '1900-01-01')
            else date '1900-01-01' end as key_c
    from {{ relation }}
{%- endmacro %}
