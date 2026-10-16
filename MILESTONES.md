# Milestones

The scaffold runs end to end: feeds are generated, dbt builds every layer, two example checks
pass, and the dashboard and Dagster graph work. What is left is the part you have to be able to
defend in an interview: 11 checks, duplicate detection, and the triage agent.

Progress is measured, not guessed:

```powershell
uv run hcq build          # rebuild after every change (or: hcq build -s dq_star_invalid+)
uv run hcq progress       # precision / recall of every check vs its target
uv run pytest             # acceptance tests switch on as you finish each piece
```

A check counts as yours once you delete `{{ config(tags=['stub']) }}` from its model. From that
moment `pytest` holds it to the targets in `dbt/seeds/dq_checks.csv`. Inspect misses with:

```powershell
uv run hcq sql "select * from eval.eval_matches where check_code = 'STAR_CONFLICT' and is_predicted <> is_labelled"
```

`eval_matches` lists every false positive (`is_predicted` only) and false negative
(`is_labelled` only); join it to `marts.fct_listings` or `eval.eval_labels` to see the values.

Hours are rough estimates for someone who knows Python and SQL but is new to dbt.

---

## M0 · Run it and read it (2-3 h)

1. `uv sync`, `uv run hcq doctor`, `uv run hcq demo`, `uv run hcq dashboard`.
2. `uv run hcq orchestrate`, open http://localhost:3000, look at the asset graph, materialise
   `daily_pipeline` once.
3. Read [docs/architecture.md](docs/architecture.md) and [docs/partner-feeds.md](docs/partner-feeds.md).
4. Open the raw files in `data/raw/` for one day and find the same hotel in all three formats.
5. Answer with SQL (`uv run hcq sql "..."`, read-only):
   - How many listings does each partner send on the last snapshot, and how many are unmapped?
   - Which master hotels are listed by all three partners?
   - Which stay dates are trade-fair nights? (Look at the median Köln rate per `stay_date`.)
   - On which days did Rheinland's coordinates break, and how can you tell from `fct_listings`?

**Explain it:** why does every partner get its own staging model instead of one generic
parser? What is the grain of `fct_listings`, `fct_rates` and `dq_issues`?

## M1 · Real hotels (1-2 h)

1. `uv run hcq reference --source osm`, then `uv run hcq generate` and `uv run hcq build`.
2. Read `data/reference/quarantine.csv`: what did validation drop or null, and why?
3. Compare `hcq progress` before and after. The two example checks should still pass.

If the Overpass API is slow or rate-limits you, wait a few minutes; the client retries with
backoff. The query is in `src/hcq/reference/osm.py`.

**Explain it:** why validate the master catalog on ingest? Why are generated data and the OSM
extract kept out of git?

## M2 · Validity checks (4-6 h)

Implement in `dbt/models/dq/checks/`:

- `dq_encoding_mojibake.sql`
- `dq_star_invalid.sql`
- `dq_phone_invalid.sql` (you will want a phone-normalisation macro in `dbt/macros/`)
- `dq_url_invalid.sql`

**Done when** `pytest tests/acceptance/test_checks.py` passes for these four.

**Explain it:** what does `Ã¶` tell you about how a file was decoded? Why is `0221 / 123456`
valid but `+49 221 12` not? Why does the check read the raw value and not a cleaned one?

## M3 · Consistency, accuracy, timeliness (6-10 h)

- `dq_address_city_mismatch.sql`
- `dq_wrong_mapping.sql`, then `dq_geo_offset.sql` and `dq_star_conflict.sql`
- `dq_stale_listing.sql`

Order matters. A listing mapped to the wrong hotel also looks like it has wrong coordinates and
a wrong star rating. Build `WRONG_MAPPING` first and let the other two defer to it (one root
cause, one issue). The catalog explains the traps: same-brand sibling hotels, the geocoder's
city-centre fallback, legitimate one-star disagreements.

**Done when** all five pass their targets.

**Explain it:** how do you tell a wrong mapping from wrong coordinates with only the data you
have? What does "root-cause precedence" mean for an issue table?

## M4 · Price outliers (3-5 h)

`dq_price_outlier.sql`, at rate grain (set `stay_date`).

A naive rule (compare each price with the listing's own median, or a z-score) flags every
trade-fair night in Köln. Measure that first: it is a good story. Then compare prices with the
market for the same city and stay date, using robust statistics (median, MAD or log-ratios).

**Done when** precision and recall reach 0.95.

**Explain it:** why median and MAD instead of mean and standard deviation? What changes if you
compare within the city and stay date? What would you do with currency mixes?

## M5 · Duplicate listings in Python (5-8 h)

Implement `find_duplicate_pairs` in `src/hcq/dedup/matcher.py` (delete the `@todo` decorator).
The dbt Python model `dq_duplicate_listing.py` already calls it.

1. Blocking: only compare listings of the same partner and day, and only nearby ones.
2. Name normalisation: case, umlauts, the city in three languages, `Hotel` / `Garni` / `Hbf`.
3. Similarity: `rapidfuzz` token scores plus distance; pick thresholds from the data.
4. Optional: `HCQ_EMBEDDINGS=ollama` with `bge-m3` for names that differ in language. Report
   F1 with and without embeddings.

**Done when** `pytest tests/acceptance/test_dedup.py` passes (0.90 precision and recall).

**Explain it:** why blocking? What are the hard negatives here (same chain, same street)? How
does a pair key need to look so you report each pair once?

## M6 · Triage agent (8-12 h)

Spec: [docs/agent.md](docs/agent.md). Pull a model first: `ollama pull qwen3:14b`.

- **6a** `build_incidents` in `src/hcq/agent/triage.py`: group issues per partner and check,
  and split sudden spikes (systemic episodes) from the chronic background. No LLM.
- **6b** `investigate`: the tool-calling loop, then a schema-validated ticket.
- Tools in `src/hcq/agent/tools.py`: `issue_timeline`, `nearby_master_hotels`,
  `market_price_index`.

**Done when** `pytest tests/acceptance/test_agent.py` passes, and with Ollama running:

```powershell
uv run hcq triage
uv run hcq eval-agent        # aim for systemic recall 100%, kind accuracy >= 80%
$env:HCQ_LIVE_LLM=1; uv run pytest -m live_llm
```

**Explain it:** why group deterministically before the LLM? How do you stop the model from
inventing evidence? What does your eval measure and what does it not?

## M7 · Ship it (3-5 h)

1. Push to GitHub, get CI green (lint, tests, demo run, Docker build).
2. Replace the Results table in README with your `hcq progress` output and a dashboard screenshot.
3. Run `docker compose up --build` once.
4. Write your CV bullet with real numbers, for example: *"Built a hotel-content data-quality
   pipeline (dbt, DuckDB, Dagster): 13 checks scored against injected ground truth (mean F1
   0.97), fuzzy + embedding duplicate detection, and a local-LLM triage agent that isolates
   3/3 systemic feed incidents."* Use your numbers, not these.
5. Rehearse [docs/interview-prep.md](docs/interview-prep.md).

## Stretch

- Make `fct_listings` and `fct_rates` incremental on `snapshot_date`.
- Onboard a fourth partner: a Latin-1 CSV with a different id scheme (generator profile,
  writer, staging model, tests).
- Publish `dbt docs generate` to GitHub Pages.
- Daily-partition the Dagster feed asset and add a sensor for new files.
- Send P1 tickets to a webhook (Slack, Teams) from the triage asset.
- Re-implement three checks in Great Expectations or Soda and compare the experience.
