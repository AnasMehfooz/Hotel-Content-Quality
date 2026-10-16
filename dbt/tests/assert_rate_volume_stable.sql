-- Volume monitor: a partner's daily rate count should stay within 40% of its median.
{{ config(severity='warn') }}
with daily as (
    select partner, snapshot_date, count(*) as rates
    from {{ ref('fct_rates') }}
    group by all
),

baseline as (
    select partner, median(rates) as median_rates from daily group by partner
)

select daily.*, baseline.median_rates
from daily
join baseline using (partner)
where abs(daily.rates - baseline.median_rates) > 0.4 * baseline.median_rates
