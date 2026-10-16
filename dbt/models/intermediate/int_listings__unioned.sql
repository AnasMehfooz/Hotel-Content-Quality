-- All partner listings in one shape, with the city name normalised through the alias seed
-- (Köln / Koeln / KOELN / Cologne -> Köln).
{%- set partners = ['northwind', 'rheinland', 'citybeds'] %}

with unioned as (
    {%- for partner in partners %}
    select * from {{ ref('stg_' ~ partner ~ '__listings') }}
    {%- if not loop.last %}
    union all by name
    {%- endif %}
    {%- endfor %}
)

select
    unioned.*,
    cities.city
from unioned
left join {{ ref('city_reference') }} as cities
    on list_contains(string_split(cities.aliases, '|'), lower(trim(unioned.city_raw)))
