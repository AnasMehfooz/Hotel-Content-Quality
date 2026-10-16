# Milestone 6: the triage agent

A content-quality service desk does not read 4,000 issue rows. It looks at incidents: "Rheinland
coordinates broke on the 8th", "a few dozen stale CityBeds listings, as usual". The agent does
that job in two stages, and only the second one uses an LLM.

```
dq_issues ──> build_incidents (pandas, deterministic) ──> Incident ──> investigate (LLM + tools) ──> Ticket
```

**Why deterministic first:** grouping and spike detection are counting problems, and SQL or
pandas get them right every time, cheaply. The LLM gets a small, well-defined job: look at the
evidence, decide what kind of incident this is, and write a ticket a human can act on. That
keeps the model's context small, its output checkable, and the failure modes visible.

Files: `src/hcq/agent/triage.py` (your two functions), `tools.py` (three tools to add),
`prompts.py` (a starting prompt to improve). Run: `hcq triage`, then `hcq eval-agent`.

## 6a · `build_incidents(issues, volumes) -> list[Incident]`

Inputs (from `load_issue_frames`):

- `issues`: one row per issue: `issue_id, check_code, severity, snapshot_date, partner,
  listing_id, related_listing_id, stay_date, field, observed_value, hotel_id, city`
- `volumes`: listings per `snapshot_date` and `partner`

Contract (tested in `tests/acceptance/test_agent.py`):

- one incident = one partner and one check;
- every issue in at most one incident, and at least 95% of issues in one;
- a sudden spike is its own incident, separate from the chronic background of the same partner
  and check, and its `first_seen` / `last_seen` are within one day of the real episode;
- at most three incidents per partner and check (no per-day incidents);
- deterministic `incident_id`, e.g. `rheinland-GEO_SWAPPED-2026-10-08`.

A workable approach: for each partner and check, compute the share of the partner's listings
affected on every snapshot day (fill days without issues with zero), take a robust baseline
(the median), mark days far above it, and turn consecutive marked days into episodes.
Everything else for that partner and check is the chronic incident.

## 6b · `investigate(incident, llm, toolbox, max_steps=6) -> Ticket`

The loop, with Ollama's message format:

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": incident.model_dump_json(exclude={"issue_ids"})},
]

reply = llm.chat(messages, tools=toolbox.specs())
# reply == {"role": "assistant", "content": "",
#           "tool_calls": [{"function": {"name": "issue_timeline",
#                                        "arguments": {"partner": "rheinland", "check_code": "GEO_SWAPPED"}}}]}
messages.append(reply)
messages.append(
    {
        "role": "tool",
        "tool_name": "issue_timeline",
        "content": toolbox.call("issue_timeline", {...}),
    }
)  # always a JSON string
# ...repeat until the reply has no tool_calls, or max_steps rounds

reply = llm.chat(messages, schema=TicketDraft.model_json_schema())  # structured output
draft = TicketDraft.model_validate_json(reply["content"])  # retry once on failure
```

Then build the `Ticket` from the draft plus the incident's own fields. The model writes
`title, kind, route_to, severity, onset_date, summary, evidence, suggested_fix, confidence`;
your code sets `incident_id, partner, check_code, affected_listings, issue_count, model, steps`.
Facts the code already knows are never left to the model.

## Tools to implement

| Tool | Returns | Why the agent needs it |
|---|---|---|
| `issue_timeline(partner, check_code)` | one row per snapshot day: issues, affected listings, listings, share | find the onset and tell a spike from background |
| `nearby_master_hotels(latitude, longitude, radius_km)` | master hotels within the radius, nearest first | decide wrong mapping vs wrong coordinates |
| `market_price_index(city, stay_date_from, stay_date_to)` | median rate per stay date for the city | tell a real market move (trade fair) from broken prices |

Keep results small (the `ToolBox` caps rows), return plain JSON-safe values, and never let a
tool raise into the loop: `ToolBox.call` turns errors into `{"error": ...}` so the model can
correct its arguments. A tool appears in `toolbox.specs()` as soon as you delete its `@todo`.

## Classification and routing

| Kind | Typical evidence | Route |
|---|---|---|
| `systemic` | issue share jumps from ~2% to most of the feed on one day, one field | `partner` |
| `record_level` | steady low share, scattered listings, no onset | `content_team` |
| `false_positive` | the data is plausible; e.g. every Köln hotel at every partner is "expensive" on the same nights | `none` |

`false_positive` only shows up when a check is too naive. Try it: temporarily replace your price
check with a per-listing z-score and see whether the agent notices the trade fair through
`market_price_index`.

## Model choice on a 16 GB GPU

| Model | VRAM at Q4 | Notes |
|---|---|---|
| `qwen3:14b` (default) | ~9-10 GB + context | good tool calling; fits with a 16k context |
| `qwen3:8b` | ~5-6 GB | faster iteration while you build the loop |
| `bge-m3` | ~1.2 GB | embeddings for Milestone 5, can stay loaded next to the chat model |

- Temperature 0 (the client default) keeps runs comparable.
- `HCQ_LLM_THINK=false` skips qwen3's reasoning phase: faster, and usually enough for this task.
  Compare both with `hcq eval-agent`.
- The client sends `keep_alive=30m`, so the model stays in VRAM between incidents instead of
  being reloaded over the Thunderbolt link each time.

## Evaluation

`hcq eval-agent` grades the latest tickets against the simulation's ground truth:

- **systemic recall:** injected incidents that got a `systemic` ticket for the right partner
  and check, with `onset_date` within one day;
- **systemic precision:** `systemic` tickets that match an injected incident;
- **kind accuracy:** ticket `kind` vs the majority truth of its issues (part of an injected
  incident, a background defect, or a false positive);
- **route accuracy:** `route_to` vs the route that truth implies.

Things the eval does not measure, and you should check by reading tickets: whether the evidence
is true (compare it with the tool results in your transcript), and whether the suggested fix
would actually help.

## Testing without a GPU

`ScriptedLLM` replays fixed replies and records every request. The acceptance tests use it to
check the loop mechanics (tools offered, tool results sent back, schema requested, one retry on
invalid JSON). The live test runs against Ollama:

```powershell
$env:HCQ_LIVE_LLM=1; uv run pytest -m live_llm
```
