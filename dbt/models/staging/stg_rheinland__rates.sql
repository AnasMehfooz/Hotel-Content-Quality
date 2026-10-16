-- Prices like "1.290,00": drop the thousands dots before turning the comma into a decimal point.
select
    cast(snapshot_date as date) as snapshot_date,
    'rheinland' as partner,
    "HotelID" as listing_id,
    cast(try_strptime("Anreise", '%d.%m.%Y') as date) as stay_date,
    try_cast(replace(replace("Preis", '.', ''), ',', '.') as double) as price_eur,
    'EUR' as currency
from {{ source('rheinland', 'preise') }}
