# Interview prep

Questions you should be able to answer about this project, with the points a strong answer
covers. Practise them out loud, with the code open, until you can answer without it.

## Telling the story (2 minutes)

1. **Problem:** platforms that compare hotels merge the same hotel from many partner feeds;
   each feed has its own format and its own failure modes, and bad content reaches travellers.
2. **What you built:** ingestion of three formats, a dbt model with contracts and tests, 13
   checks across six quality dimensions, measured against injected ground truth, and an agent
   that turns thousands of issues into a handful of tickets.
3. **One hard problem you solved:** pick one (the trade fair in price checks, wrong mapping vs
   wrong coordinates, duplicate hard negatives) and tell it as before / after with numbers.
4. **Result:** your `hcq progress` numbers and agent eval.

**Be precise about authorship.** The scaffold (generator, staging models, framework,
orchestration, dashboard) was set up with AI assistance; the checks, duplicate detection and
the agent are yours, test-driven against fixed targets. Say so plainly if asked. Then show that
you understand the scaffold as well as your own code. Interviewers care far more about that than
about who typed the boilerplate.

## Data modelling and dbt

- **What is the grain of `fct_listings`, `fct_rates`, `dq_issues`?** Snapshot × partner ×
  listing; plus stay date; one row per issue at the check's own grain.
- **Why staging, intermediate, marts?** Separation of concerns: format adapters, business
  logic, consumer-facing tables. Changes stay local; tests sit where the assumption is made.
- **What does a model contract do?** Enforces column names and types at build time, so the
  union in `dq_issues` cannot drift.
- **External sources: why read files in place?** No load step to maintain; explicit types make
  schema drift fail in staging.
- **How would you make this incremental?** `is_incremental()` on `snapshot_date`, a unique key,
  and a lookback for late-arriving files.
- **Generic vs singular tests?** Reusable assertions on columns (`unique_combination`) vs one-off
  business assertions (every partner delivers every day).

## Checks and statistics

- **Precision vs recall here:** precision = share of flagged issues that are real (analyst time
  wasted); recall = share of real defects found (bad content shown). Which one matters more
  depends on the check: a false geo alarm is cheap, a missed price bug is not.
- **Why median and MAD?** Robust to the outliers you are hunting; a few x100 prices shift a mean
  and standard deviation enough to hide themselves.
- **The trade fair:** naive per-listing outlier detection flags every Köln hotel on fair nights.
  Comparing against the market for the same city and stay date removes the shared shock.
- **Root-cause precedence:** one wrong mapping also looks like wrong coordinates and a wrong
  star rating. Report it once, as the most specific cause.
- **How did you choose thresholds?** From the data's legitimate variation (jitter up to ~90 m,
  one-star disagreements, refresh cadences) with a margin, then validated on the scores.
- **What if you had no ground truth?** Sample and label issues by hand, track issue rates over
  time, compare partners, alert on change rather than on absolute levels.

## Python and duplicate detection

- **Why blocking?** All-pairs is O(n²) per partner and day; blocking by location (and partner,
  day) cuts candidates to a handful and removes most hard negatives for free.
- **Which similarity and why?** Token-based scores handle reordering and extra words; distance
  separates chain siblings; normalisation handles case, umlauts, languages and abbreviations.
- **Did embeddings help?** Answer with your measured F1 with and without them, and the cost.
- **Why a dbt Python model?** It stays in the DAG and the lineage, while the logic lives in a
  unit-tested module.

## Orchestration, testing, delivery

- **Why Dagster assets instead of tasks?** The graph is about data products; every dbt model is
  an asset and every dbt test an asset check, so you can see what is stale and what failed.
- **What does CI run?** Lint, unit tests, the full pipeline on a 7-day window, acceptance tests
  for every implemented check, and a Docker build.
- **How do the acceptance tests switch on?** A check is skipped while its model has the `stub`
  tag; removing the tag makes the target binding.
- **DuckDB locking:** one writer per file; dbt runs as a subprocess; the dashboard uses short
  read-only connections and retries.

## The agent

- **Why not give the LLM all the issues?** Too much context, no reproducibility, and counting is
  not what LLMs are good at. Deterministic grouping first, LLM for judgement and writing.
- **How do you stop hallucinated evidence?** Read-only tools with small, typed results; facts
  the code knows are set by the code; JSON-schema output validated by Pydantic; and reading
  tickets against the tool transcript.
- **How do you evaluate it?** Systemic recall and precision against injected incidents, kind and
  route accuracy against the truth of each incident's issues. Mention what it does not
  measure (truth of evidence, usefulness of the fix).
- **Why a local model?** Partner data stays on the machine, no per-token cost, and a 14B model
  on a 16 GB GPU is enough for structured triage.
- **What would you do next?** Human feedback on tickets as labels, deduplicating tickets across
  days, and alerting.

## Questions to ask them

- How do partner feeds reach you today, and what breaks most often?
- How do you measure whether a data-quality rule is worth keeping?
- Where do AI tools already sit in the team's workflow?
