# Partner feeds

Three simulated partners deliver a full snapshot every day. Each has its own format, written
the way such feeds usually look; one staging model per partner turns it into the common
listing shape. Files land in Hive-style folders, so DuckDB reads the snapshot date from the path:

```
data/raw/<partner>/snapshot_date=YYYY-MM-DD/<files>
```

| | Northwind Stays | Rheinland Reisen | CityBeds |
|---|---|---|---|
| Type | Large online travel agency | Regional tour operator | Booking API |
| Coverage of the catalog | ~80% | ~62% | ~55% |
| Files | `listings.jsonl`, `rates.jsonl` | `hotels.csv`, `preise.csv` | `properties.json` |
| Format | JSON lines | CSV, `;` separator, German headers | One nested JSON document |
| Coordinates | floats | decimal comma, `Breitengrad` / `Laengengrad` | `geo.lat` / `geo.lng` |
| Stars | integer, no Superior | `4`, Superior as `4S` | float, Superior as `4.5` |
| Phone | `+492211234567` | `0221 / 1234567` | `+49 (0)221 1234567` |
| Website | `https://www.host.de` | `www.host.de/path` | `http://www.host.de` |
| City | `Köln` | `KOELN` | `Cologne` |
| Updated | ISO timestamp, refreshed daily | `dd.mm.yyyy`, within 7 days | Unix epoch, within 3 days |
| Prices | `price_eur` | `Preis` as `1.290,00` | `amount_cents` integer |
| Name style | as in the catalog | sometimes appends the city | sometimes drops `Hotel ` |

## Northwind Stays

`listings.jsonl`, one listing per line:

```json
{"listing_id": "NW-394740", "name": "CityStay Köln Altstadt",
 "address": {"street": "Neusser Straße 125", "postal_code": "50667", "city": "Köln", "country": "DE"},
 "geo": {"lat": 50.9385, "lon": 6.958517}, "stars": 3, "phone": "+492219500568",
 "website": "https://www.citystay.de/koeln-altstadt", "updated_at": "2026-10-15T08:02:00Z"}
```

`rates.jsonl`: `{"listing_id": "NW-394740", "stay_date": "2026-10-16", "price_eur": 82.69, "currency": "EUR"}`

## Rheinland Reisen

`hotels.csv`, UTF-8, `;`-separated, CRLF line endings, empty string for missing values:

```
HotelID;Hotelname;Strasse;PLZ;Ort;Breitengrad;Laengengrad;Sterne;Telefon;Webseite;Stand
0269804;CityStay Köln Altstadt;Neusser Straße 125;50667;KOELN;50,938208;6,957777;3;;www.citystay.de/koeln-altstadt;11.10.2026
```

`preise.csv`: `HotelID;Anreise;Preis` with `20.10.2026;1.290,00`. The thousands separator is a
dot, so replacing the comma alone would turn 1.290,00 into 1.29.

Ids are 7-digit strings with leading zeros: read them as text.

## CityBeds

`properties.json`, one document per snapshot, rates nested inside each property:

```json
{"generated_at": 1792027800,
 "properties": [{"id": "cb_a9be270a91", "title": "CityStay Köln Altstadt",
   "location": {"address": {"line1": "Neusser Straße 125", "zip": "50667", "city": "Cologne"},
                "geo": {"lat": 50.939179, "lng": 6.958197}},
   "rating": {"stars": 3.0}, "contact": {"phone": null, "url": null},
   "last_modified": 1791549120,
   "rates": [{"date": "2026-10-16", "amount_cents": 8406, "currency": "EUR"}]}]}
```

## Mapping table

`data/raw/mapping/snapshot_date=.../mapping.csv` links partner listings to master hotels:
`partner, listing_id, hotel_id, method (auto | manual), confidence`. A listing without a row is
unmapped, either because it is new and waiting for mapping or because nobody noticed it.

## Ground truth

`data/raw/_manifest/` holds what a real pipeline never has:

- `defects.parquet`: one row per injected defect per day (`defect_code`, `field`,
  `clean_value`, `dirty_value`, `incident_id`, and `stay_date` / `related_listing_id` where
  relevant).
- `incidents.json`: the three systemic incidents with their start and end dates.
- `scenario.json`: seed, window, trade-fair nights and label counts.

Checks must never read these. The `eval` models do, to score the checks.
