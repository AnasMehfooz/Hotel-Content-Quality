"""Data-quality dashboard: trends, issue explorer, scorecard and agent tickets.

Start it with ``hcq dashboard``. Reads the DuckDB warehouse read-only, so it can stay open
while the pipeline runs (it retries if dbt holds the write lock).
"""

from __future__ import annotations

import json
import time

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

from hcq.config import get_settings

settings = get_settings()
PARTNER_COLORS = {"northwind": "#3b82c4", "rheinland": "#d9822b", "citybeds": "#2f9e72"}
STATUS_COLORS = {"pass": "#2f9e72", "fail": "#d64545", "todo": "#9aa0a6", "example": "#3b82c4"}

st.set_page_config(page_title="Hotel content quality", layout="wide")


@st.cache_data(ttl=30, show_spinner=False)
def query(sql: str) -> pd.DataFrame:
    for attempt in range(5):
        try:
            with duckdb.connect(str(settings.warehouse_path), read_only=True) as con:
                return con.sql(sql).df()
        except duckdb.IOException:
            if attempt == 4:
                raise
            time.sleep(1.5)  # dbt is writing; try again shortly
    raise RuntimeError("unreachable")


if not settings.warehouse_path.exists():
    st.title("Hotel content quality")
    st.info("No warehouse yet. Run `hcq demo` in the project folder, then reload this page.")
    st.stop()

summary = query("select * from dq.dq_daily_summary")
summary["snapshot_date"] = pd.to_datetime(summary["snapshot_date"])
days = sorted(summary["snapshot_date"].unique())
latest, previous = days[-1], days[-2] if len(days) > 1 else days[-1]
incidents = query("select * from eval.eval_incidents")
scores = query("select * from eval.eval_check_scores")

st.title("Hotel content quality")
st.caption(
    f"{len(days)} daily snapshots, {pd.Timestamp(days[0]):%d %b} to {pd.Timestamp(latest):%d %b %Y} · "
    "partners: northwind, rheinland, citybeds · Köln and Düsseldorf"
)

# ------------------------------------------------------------------------------- headline
per_day = (
    summary.groupby(["snapshot_date", "partner"])
    .agg(listings=("listings", "first"), issues=("issues", "sum"))
    .reset_index()
)
affected = query(
    "select snapshot_date, count(distinct partner || listing_id) as affected from dq.dq_issues group by 1"
)
affected["snapshot_date"] = pd.to_datetime(affected["snapshot_date"])
listings_by_day = per_day.groupby("snapshot_date")["listings"].sum()
issues_by_day = per_day.groupby("snapshot_date")["issues"].sum()
affected_by_day = affected.set_index("snapshot_date")["affected"].reindex(days, fill_value=0)
share_now = affected_by_day[latest] / listings_by_day[latest]
share_prev = affected_by_day[previous] / listings_by_day[previous]

scored = scores[scores["precision"].notna()]
meets = (scored["precision"] >= scored["target_precision"]) & (
    scored["recall"] >= scored["target_recall"]
)

cols = st.columns(4)
cols[0].metric("Listings on latest snapshot", f"{int(listings_by_day[latest]):,}")
cols[1].metric(
    "Listings with an issue",
    f"{share_now:.1%}",
    f"{(share_now - share_prev) * 100:+.1f} pts vs previous day",
    delta_color="inverse",
)
cols[2].metric(
    "Issues detected",
    f"{int(issues_by_day[latest]):,}",
    f"{int(issues_by_day[latest] - issues_by_day[previous]):+,}",
    delta_color="inverse",
)
cols[3].metric("Checks meeting target", f"{int(meets.sum())} of {len(scores)}")

trend_tab, explore_tab, score_tab, ticket_tab = st.tabs(
    ["Trend", "Explore issues", "Scorecard", "Tickets"]
)

# ------------------------------------------------------------------------------- trend
with trend_tab:
    share = query(
        """
        select l.snapshot_date, l.partner, count(*) as listings,
               count(distinct i.listing_id) as affected
        from marts.fct_listings l
        left join (select distinct snapshot_date, partner, listing_id from dq.dq_issues) i
            using (snapshot_date, partner, listing_id)
        group by all
        """
    )
    share["snapshot_date"] = pd.to_datetime(share["snapshot_date"])
    share["issue_rate"] = share["affected"] / share["listings"]
    windows = incidents.assign(
        start=pd.to_datetime(incidents["start_date"]) - pd.Timedelta(hours=12),
        end=pd.to_datetime(incidents["end_date"]) + pd.Timedelta(hours=12),
    )
    windows["label"] = windows["partner"] + " · " + windows["check_code"].str.lower()
    bands = (
        alt.Chart(windows)
        .mark_rect(opacity=0.10)
        .encode(
            x="start:T",
            x2="end:T",
            color=alt.Color(
                "partner:N",
                scale=alt.Scale(domain=list(PARTNER_COLORS), range=list(PARTNER_COLORS.values())),
                legend=None,
            ),
            tooltip=["incident_id", "description"],
        )
    )
    band_labels = (
        alt.Chart(windows)
        .mark_text(align="left", baseline="top", dx=4, dy=4, fontSize=11, color="#6b7280")
        .encode(x="start:T", y=alt.value(0), text="label:N")
    )
    lines = (
        alt.Chart(share)
        .mark_line(point=True, strokeWidth=2)
        .encode(
            x=alt.X("snapshot_date:T", title=None, axis=alt.Axis(format="%d %b")),
            y=alt.Y(
                "issue_rate:Q", title="Listings with at least one issue", axis=alt.Axis(format="%")
            ),
            color=alt.Color(
                "partner:N",
                scale=alt.Scale(domain=list(PARTNER_COLORS), range=list(PARTNER_COLORS.values())),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=[
                "partner",
                alt.Tooltip("snapshot_date:T", format="%d %b"),
                alt.Tooltip("issue_rate:Q", format=".1%"),
            ],
        )
    )
    st.subheader("Issue rate by partner")
    st.caption(
        "Shaded: the injected systemic incidents. Spikes inside them are what triage should escalate."
    )
    st.altair_chart(bands + band_labels + lines, width="stretch")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Issues per day by check")
        by_check = summary.groupby(["snapshot_date", "check_code"])["issues"].sum().reset_index()
        by_check = by_check[by_check["issues"] > 0]
        bars = (
            alt.Chart(by_check)
            .mark_bar()
            .encode(
                x=alt.X("snapshot_date:T", title=None, axis=alt.Axis(format="%d %b")),
                y=alt.Y("issues:Q", title="Issues", scale=alt.Scale(type="symlog")),
                color=alt.Color(
                    "check_code:N", legend=alt.Legend(orient="bottom", columns=3, title=None)
                ),
                tooltip=["check_code", "issues", alt.Tooltip("snapshot_date:T", format="%d %b")],
            )
        )
        st.altair_chart(bars, width="stretch")
        st.caption("Symmetric log scale: price incidents produce thousands of rate-level issues.")
    with right:
        st.subheader(f"Latest snapshot, {pd.Timestamp(latest):%d %b}")
        heat = summary[summary["snapshot_date"] == latest]
        chart = (
            alt.Chart(heat)
            .mark_rect()
            .encode(
                x=alt.X("partner:N", title=None),
                y=alt.Y(
                    "check_code:N",
                    title=None,
                    sort=list(scores["check_code"]),
                    axis=alt.Axis(labelLimit=220),
                ),
                color=alt.Color(
                    "affected_share:Q",
                    title="Listings affected",
                    scale=alt.Scale(scheme="oranges"),
                    legend=alt.Legend(format="%"),
                ),
                tooltip=[
                    "partner",
                    "check_code",
                    "affected_listings",
                    alt.Tooltip("affected_share:Q", format=".1%"),
                ],
            )
        )
        st.altair_chart(chart, width="stretch")

# ------------------------------------------------------------------------------- explore
with explore_tab:
    f1, f2, f3 = st.columns(3)
    day = f1.selectbox(
        "Snapshot", days[::-1], format_func=lambda d: f"{pd.Timestamp(d):%a %d %b %Y}"
    )
    partner = f2.selectbox("Partner", ["all", *PARTNER_COLORS])
    check = f3.selectbox("Check", ["all", *scores["check_code"]])
    where = [f"snapshot_date = date '{pd.Timestamp(day):%Y-%m-%d}'"]
    if partner != "all":
        where.append(f"partner = '{partner}'")
    if check != "all":
        where.append(f"check_code = '{check}'")
    issues = query(
        "select check_code, severity, partner, listing_id, related_listing_id, stay_date, field, "
        f"observed_value, expected_value, details from dq.dq_issues where {' and '.join(where)} "
        "order by severity, check_code, partner, listing_id limit 2000"
    )
    st.caption(
        f"{len(issues):,} issues (showing up to 2,000). Select a row to compare the partner and master record."
    )
    event = st.dataframe(
        issues,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        height=320,
    )
    rows = event.selection.rows if event and event.selection else []
    if rows:
        picked = issues.iloc[rows[0]]
        listing = query(
            f"select * from marts.fct_listings where snapshot_date = date '{pd.Timestamp(day):%Y-%m-%d}' "
            f"and partner = '{picked.partner}' and listing_id = '{picked.listing_id}'"
        )
        if not listing.empty:
            rec = listing.iloc[0]
            a, b = st.columns(2)
            a.markdown(f"**Partner record** · {picked.partner} `{picked.listing_id}`")
            a.dataframe(
                pd.DataFrame(
                    {
                        "value": rec[
                            [
                                "name",
                                "street",
                                "postcode",
                                "city_raw",
                                "latitude",
                                "longitude",
                                "stars_raw",
                                "phone_raw",
                                "website_raw",
                                "last_updated",
                            ]
                        ].astype(str)
                    }
                ),
                width="stretch",
            )
            b.markdown(f"**Master record** · `{rec.hotel_id or 'unmapped'}`")
            b.dataframe(
                pd.DataFrame(
                    {
                        "value": rec[
                            [
                                "master_name",
                                "master_street",
                                "master_postcode",
                                "master_city",
                                "master_latitude",
                                "master_longitude",
                                "master_stars",
                                "master_phone",
                                "master_website",
                            ]
                        ].astype(str)
                    }
                ),
                width="stretch",
            )
            points = pd.DataFrame(
                [
                    {"lat": rec.latitude, "lon": rec.longitude, "color": "#d9822b", "size": 40},
                    {
                        "lat": rec.master_latitude,
                        "lon": rec.master_longitude,
                        "color": "#3b82c4",
                        "size": 40,
                    },
                ]
            ).dropna()
            points = points[points["lat"].between(-90, 90) & points["lon"].between(-180, 180)]
            if not points.empty:
                st.map(points, latitude="lat", longitude="lon", color="color", size="size")
                st.caption("Orange: where the partner puts the hotel. Blue: the master record.")
        if isinstance(picked.details, str) and picked.details.startswith("{"):
            st.json(json.loads(picked.details))

# ------------------------------------------------------------------------------- scorecard
with score_tab:
    st.subheader("Checks against the injected ground truth")
    st.caption(
        "Precision: share of flagged issues that are real defects. Recall: share of injected defects found. "
        "Possible only because the feeds are simulated with labels."
    )
    table = scores.copy()
    table["status"] = "todo"
    table.loc[table["precision"].notna(), "status"] = "fail"
    table.loc[
        table["precision"].notna() & meets.reindex(table.index, fill_value=False), "status"
    ] = "pass"
    st.dataframe(
        table[
            [
                "check_code",
                "dimension",
                "status",
                "precision",
                "recall",
                "target_precision",
                "target_recall",
                "true_positives",
                "false_positives",
                "false_negatives",
            ]
        ],
        width="stretch",
        height=(len(table) + 1) * 35 + 3,  # every check visible without scrolling
        hide_index=True,
        column_config={
            "check_code": st.column_config.TextColumn("Check"),
            "dimension": st.column_config.TextColumn("Dimension"),
            "status": st.column_config.TextColumn("Status"),
            "true_positives": st.column_config.NumberColumn("TP"),
            "false_positives": st.column_config.NumberColumn("FP"),
            "false_negatives": st.column_config.NumberColumn("FN"),
            "precision": st.column_config.ProgressColumn(
                "Precision", min_value=0, max_value=1, format="%.3f"
            ),
            "recall": st.column_config.ProgressColumn(
                "Recall", min_value=0, max_value=1, format="%.3f"
            ),
            "target_precision": st.column_config.NumberColumn("Target P", format="%.2f"),
            "target_recall": st.column_config.NumberColumn("Target R", format="%.2f"),
        },
    )
    st.caption(
        "`hcq progress` shows the same table in the terminal, including which checks are still stubs."
    )

# ------------------------------------------------------------------------------- tickets
with ticket_tab:
    if not settings.tickets_path.exists():
        st.info("No tickets yet. Implement Milestone 6, then run `hcq triage` with Ollama running.")
    else:
        tickets = pd.read_parquet(settings.tickets_path)
        st.caption(f"{len(tickets)} tickets from the latest triage run")
        for t in tickets.sort_values(
            ["severity", "issue_count"], ascending=[True, False]
        ).itertuples():
            with st.expander(f"{t.severity} · {t.kind.replace('_', ' ')} · {t.title}"):
                st.markdown(t.summary)
                st.markdown("\n".join(f"- {e}" for e in t.evidence))
                st.markdown(f"**Suggested fix:** {t.suggested_fix}")
                st.caption(
                    f"{t.partner} · {t.check_code} · route to {t.route_to} · confidence {t.confidence:.0%}"
                )
