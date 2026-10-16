{%- set partners = ['northwind', 'rheinland', 'citybeds'] %}
{%- for partner in partners %}
select * from {{ ref('stg_' ~ partner ~ '__rates') }}
{%- if not loop.last %}
union all by name
{%- endif %}
{%- endfor %}
