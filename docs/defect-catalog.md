# Defect catalog

Every check returns rows with the same nine columns (the contract in
`dbt/models/dq/checks/_checks.yml`, empty template in `dq_empty()`):

| Column | Meaning |
|---|---|
| `snapshot_date`, `partner`, `listing_id` | the listing the issue is about |
| `related_listing_id` | the other listing of a pair (`DUPLICATE_LISTING` only) |
| `stay_date` | the night the rate is for (`PRICE_OUTLIER` only) |
| `field` | the field or fields concerned, e.g. `phone` or `latitude,longitude` |
| `observed_value` / `expected_value` | what was sent, and what it should probably be |
| `details` | JSON with your evidence: distances, scores, thresholds |

Scoring matches your rows with the injected labels on `(snapshot_date, partner, listing_id)`,
plus `stay_date` for prices and the unordered pair for duplicates. One issue per key: the
`unique` test on `dq_issues.issue_id` fails if a check returns the same issue twice.

Read the raw columns (`*_raw`, `name`, `street`) in `marts.fct_listings`; the master record sits
next to them as `master_*` columns, and the mapping as `hotel_id`. City reference data
(aliases, postcode ranges, dialling codes, bounding boxes) is the seed `ref.city_reference`.

Rates in this catalog are per partner, as a share of the listings that could carry the defect,
over the whole window. Defects persist for some days, so one defective listing produces
several labelled rows.

---

## MISSING_REQUIRED

Completeness · listing grain · **example check, already implemented**

A listing needs a name, coordinates and a city to be shown. The generator nulls one of them on
3% of listings (name 40%, coordinates 40%, city 20%). Read `dq_missing_required.sql` as the
pattern for your own checks.

## ENCODING_MOJIBAKE

Validity · listing grain · target 0.95 / 0.95

**What it looks like:** `Köln` arrives as `KÃ¶ln`, `Straße` as `StraÃŸe`.
**Real cause:** UTF-8 bytes decoded as Windows-1252, usually in a CSV export or an old ETL step.
**Injected:** 5% of the listings whose name or street contains a non-ASCII character get their
name and/or street garbled. On top of that, Northwind's export breaks for a few days near the
end of the window and garbles every name and street with an umlaut (a systemic incident).

**Hints**
- Each German special character becomes `Ã` followed by one more character.
- Report which field is affected (`name`, `street` or both) in `field`.
- Think about what a regex could match by accident in real data (Portuguese `ã` is lower case,
  for example) and keep the pattern tight.

## STAR_INVALID

Validity · listing grain · target 0.95 / 0.95

**What it looks like:** a star rating of 0, 6, 7 or 9.
**Injected:** 3% of listings, rendered in the partner's own format: Northwind `7`,
Rheinland `7` or `7S`, CityBeds `7.0` or `7.5`.

**Traps**
- Superior is legitimate and encoded differently per partner: Rheinland `4S`, CityBeds `4.5`.
  Staging already parses this into `star_class` and `is_superior`.
- An empty rating is not invalid: unclassified hotels and hostels have none.
- A value that does not parse at all would also be invalid (`stars_raw` set, `star_class` null).

## PHONE_INVALID

Validity · listing grain · target 0.95 / 0.95

**Injected:** 4% of listings that have a phone number, in three variants: truncated
(`0221 / 12`), letters (`+4922147HOTEL`), too long (eight extra digits).

**Valid formats you must accept** (see [partner-feeds.md](partner-feeds.md)):
`+492211234567` (Northwind), `0221 / 1234567` (Rheinland), `+49 (0)221 1234567` (CityBeds),
plus mobile numbers (`+49151...`) and central reservation lines (`+4969...`).

**Hints**
- Normalise first (strip separators, drop the `(0)` trunk prefix, turn a leading `0` into
  `+49`), then validate. Put the normalisation in a macro: `ADDRESS_CITY_MISMATCH` needs it too.
- German numbers have between 6 and 13 digits after `+49`.

## URL_INVALID

Validity · listing grain · target 0.95 / 0.95

**Injected:** 4% of listings with a website: `htp://host`, `https//host`,
`https://www .host.de` (space), `https://www..host.de`, `http://example.com`, `n/a`.

**Traps:** Rheinland sends bare hosts with paths (`www.citystay.de/koeln-messe`) and CityBeds
uses `http://`. Both are fine. A missing website is not invalid.

## ADDRESS_CITY_MISMATCH

Consistency · listing grain · target 0.95 / 0.95

**What it looks like:** a Köln hotel with a Düsseldorf postcode, or with the Düsseldorf area
code `0211` instead of Köln's `0221`. One wrong digit moves a hotel to the other city.
**Injected:** 3% of listings; either the postcode is replaced with one from the other city, or
the phone's area code is switched to the other city's.

**Traps**
- The city arrives as `Köln`, `KOELN` or `Cologne`. Use the normalised `city` column (or the
  master city when it is missing).
- Mobile numbers and central reservation lines are not mismatches. Flag only the *other*
  city's area code, not every number that is not local.
- Postcode ranges and dialling codes are in `ref.city_reference`.

## STAR_CONFLICT

Consistency · listing grain · target 0.95 / 0.95

**What it looks like:** a partner says 5 stars, the master catalog says 3.
**Injected:** 3% of mapped listings whose master hotel has a rating; the partner value differs
from the master by two or more stars.

**Traps**
- Partners legitimately disagree by one star on about 5% of listings.
- Superior (`4S`, `4.5`) is still four stars.
- Out-of-range values belong to `STAR_INVALID`.
- A **wrong mapping** compares the partner's stars with a different hotel's rating. Those rows
  are `WRONG_MAPPING` issues, not star conflicts. Precision above 0.95 requires excluding them.

## GEO_SWAPPED

Accuracy · listing grain · **example check, already implemented**

Latitude and longitude swapped: 2% of listings in the background, and Rheinland's whole feed
for a few days in the middle of the window (a column-order change in their export).

## GEO_OFFSET

Accuracy · listing grain · target 0.90 / 0.90

**What it looks like:** the listing's coordinates are kilometres away from the mapped hotel.
**Injected:** 3% of mapped listings. Half are snapped to the exact city centre (a geocoder that
falls back to the city when it cannot resolve the street; only hotels at least 2 km from the
centre get this); the other half are moved 2-15 km in a random direction.

**Traps**
- Legitimate partner coordinates differ from the master by up to about 90 m.
- Swapped coordinates are `GEO_SWAPPED`, not offsets.
- A wrong mapping also produces a large distance, because the master record is the wrong
  hotel. Decide which root cause the row has, and report only that one.
- Many listings sharing exactly the same coordinates is a strong signal on its own.

## WRONG_MAPPING

Accuracy · listing grain · target 0.90 / 0.90

**What it looks like:** the mapping table links a partner listing to a different master hotel
in the same city. The listing's own content (name, coordinates) is correct.
**Injected:** 3% of mapped listings, linked to another hotel 0.3-6 km away. Usually one of the
three nearest candidates, with hotels of the same brand first, which makes it hard.

**Traps**
- Same-brand siblings: `CityStay Köln Altstadt` vs `CityStay Köln Messe`.
- Partner name variants: Rheinland may append the city, CityBeds may drop `Hotel`. Normalise
  names before comparing. Jaro-Winkler gives a big bonus to shared prefixes, which is exactly
  what chain names have.
- Useful questions: how far is the listing from its mapped hotel? Is there another master hotel
  right where the listing says it is, with a better-matching name?

## STALE_LISTING

Timeliness · listing grain · target 0.95 / 0.95

**Injected:** 3% of listings stop being refreshed: `last_updated` is fixed 120-500 days before
the window.
**Legitimate cadence:** Northwind refreshes daily, CityBeds within 3 days, Rheinland within 7.
Staging already turns the three timestamp formats (ISO, `dd.mm.yyyy`, Unix epoch) into a date.
Choose a threshold with a margin over the slowest legitimate cadence and say why.

## DUPLICATE_LISTING

Uniqueness · pair grain · target 0.90 / 0.90 · **Python** (`src/hcq/dedup/matcher.py`)

**What it looks like:** one partner lists the same hotel twice under two ids.
**Injected:** for 4% of each partner's listings a second listing appears on some day and stays.
It has a name variant (one or two of: upper case, umlauts transliterated, the city translated
to English, `Hotel` added or removed, `X Hotel` word order, `Hbf` / `St.` / `Str.`
abbreviations, ` Garni`, ` - City Centre`), coordinates 5-60 m from the original, and is
unmapped 70% of the time (otherwise mapped to the same hotel).

**Traps**
- Two partners listing the same hotel is expected. Only pairs within one partner count.
- Hard negatives: chain hotels with near-identical names, and reused names in other districts
  (`Hotel Königshof` vs `Hotel Königshof Köln-Porz`). Distance separates most of them.
- Some listings are unmapped legitimately, so "unmapped" alone is not a duplicate signal.
- Output contract: one row per unordered pair and snapshot day, with
  `snapshot_date, partner, listing_id, related_listing_id, score, reason`.

**Hints:** block by partner, day and location before comparing names; `rapidfuzz` gives
`token_set_ratio` and friends. Embeddings (`HCQ_EMBEDDINGS=ollama`, `bge-m3`) help with
`Köln` vs `Cologne`; measure whether they help enough to justify the dependency.

## PRICE_OUTLIER

Plausibility · rate grain (set `stay_date`) · target 0.95 / 0.95

**What it looks like:** a nightly rate 100 times too high or too low, or zero.
**Injected:** 0.2% of rate rows (x100, /100 or 0). CityBeds also has a systemic incident in
the first half of the window: it sends euro amounts in its `amount_cents` field for about two days, so every
CityBeds rate is 100 times too low.

**Legitimate patterns you must not flag**
- A trade fair in Köln for four stay nights late in the window: every Köln hotel costs
  2.8-4.5 times its usual rate, at every partner.
- Weekday effects (Saturday up, Sunday down), partners differing by a few percent for the same
  hotel, and daily noise of a few percent.

**Hint:** compare a rate with the market (same city, same stay date, all partners) before
comparing it with the listing's own history. Medians and log-ratios are robust to the very
outliers you are looking for; means and standard deviations are not.
