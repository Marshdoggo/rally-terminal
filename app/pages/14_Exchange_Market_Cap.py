from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from app_data import load_processed_csv, render_data_diagnostics
from alt_asset_explorer.exchange_history import performance_summary, rebuild_exchange_history

st.set_page_config(page_title="Exchange Market Cap & Performance", layout="wide")
render_data_diagnostics()
st.title("Exchange Market Cap & Performance")
st.caption("Historical represented Rally exchange capitalization, flow-adjusted performance, category mix, and coverage diagnostics from committed processed artifacts.")

@st.cache_data(show_spinner=False)
def load_exchange_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        load_processed_csv("exchange_market_cap_history"),
        load_processed_csv("exchange_category_history"),
        load_processed_csv("exchange_asset_history"),
        load_processed_csv("exchange_data_quality_report"),
        load_processed_csv("exchange_reconciliation_report"),
    )

market, category, asset, quality, recon = load_exchange_data()
if market.empty:
    st.warning("Exchange history has not been generated yet. Run `python3 scripts/rebuild_exchange_history.py --frequency native` or rebuild the full dataset.")
    if st.button("Build exchange history now from committed processed inputs"):
        result = rebuild_exchange_history(frequency="native", force=True)
        st.success(f"Built {len(result.market_cap_history):,} market-cap rows. Refresh the page to load the cached artifact.")
    st.stop()

for frame in [market, category, asset, quality, recon]:
    if not frame.empty and "date" in frame:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")

with st.sidebar:
    st.header("Controls")
    frequency_label = st.selectbox("Reporting frequency label", ["native", "weekly", "monthly", "quarterly"], index=0)
    min_date, max_date = market["date"].min().date(), market["date"].max().date()
    date_range = st.date_input("Date range", (min_date, max_date), min_value=min_date, max_value=max_date)
    categories = sorted(category["category"].dropna().astype(str).unique()) if not category.empty else []
    selected_categories = st.multiselect("Categories", categories, default=categories)
    composition_view = st.radio("Category chart", ["Absolute market capitalization", "Percentage composition", "Indexed category performance"])
    direct_only = st.checkbox("Direct observations only", value=False)
    with st.expander("Advanced controls"):
        max_staleness = st.slider("Maximum displayed price age (days)", 0, 730, 120)
        group_small = st.checkbox("Group small categories as Other", value=False)
        small_threshold = st.slider("Other threshold", 0.0, 0.10, 0.02, 0.005)
        include_exited = st.checkbox("Include exited assets when present", value=True)
        weighting = st.radio("Performance index", ["Market-cap weighted", "Equal weighted"], horizontal=True)

start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[-1])
market_f = market[(market["date"] >= start) & (market["date"] <= end)].copy()
category_f = category[(category["date"] >= start) & (category["date"] <= end) & (category["category"].astype(str).isin(selected_categories))].copy()
asset_f = asset[(asset["date"] >= start) & (asset["date"] <= end)].copy() if not asset.empty else asset
if direct_only and not asset_f.empty:
    eligible_assets = asset_f[asset_f["is_direct_observation"].fillna(False)][["date", "asset_id"]]
    asset_f = asset_f.merge(eligible_assets, on=["date", "asset_id"], how="inner")
if not asset_f.empty:
    asset_f = asset_f[pd.to_numeric(asset_f["observation_age_days"], errors="coerce").fillna(0) <= max_staleness]

latest = market_f.iloc[-1]
summary = performance_summary(market_f, frequency=frequency_label)
cols = st.columns(6)
cols[0].metric("Exchange market cap", f"${latest['total_market_cap']:,.0f}")
cols[1].metric("Issued capital", f"${latest['cumulative_invested_capital']:,.0f}")
cols[2].metric("Flow-adjusted P/L", f"${latest['cumulative_flow_adjusted_pl']:,.0f}")
cols[3].metric("Since inception", f"{summary.get('since_inception_return', 0):.1%}")
cols[4].metric("Max drawdown", f"{summary.get('max_drawdown', 0):.1%}")
cols[5].metric("Direct coverage", f"{latest['direct_coverage_pct']:.1%}")
cols2 = st.columns(5)
cols2[0].metric("Active assets", f"{int(latest['active_asset_count']):,}")
cols2[1].metric("Categories", f"{len(selected_categories):,}")
cols2[2].metric("Latest observation", latest["date"].date().isoformat())
cols2[3].metric("Annualized return", "n/a" if summary.get("annualized_return") is None else f"{summary['annualized_return']:.1%}")
cols2[4].metric("Carried coverage", f"{latest['carried_forward_coverage_pct']:.1%}")

st.subheader("Total Exchange Market Cap")
fig = px.line(market_f, x="date", y="total_market_cap", hover_data=["active_asset_count", "direct_observation_asset_count", "carried_forward_asset_count", "direct_coverage_pct", "carried_forward_coverage_pct"], markers=True)
fig.update_yaxes(tickprefix="$", title="Represented market cap")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Market Cap vs Flow-Adjusted Performance")
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=market_f["date"], y=market_f["total_market_cap"], name="Market cap", yaxis="y1"))
index_col = "return_index" if weighting == "Market-cap weighted" else "equal_weighted_index"
fig2.add_trace(go.Scatter(x=market_f["date"], y=market_f[index_col], name=weighting + " index", yaxis="y2"))
fig2.update_layout(yaxis=dict(title="Market cap", tickprefix="$"), yaxis2=dict(title="Index level", overlaying="y", side="right"), legend=dict(orientation="h"))
st.plotly_chart(fig2, use_container_width=True)

st.subheader("Category Decomposition")
plot_cat = category_f.copy()
if group_small and not plot_cat.empty:
    small = plot_cat["category_weight"].fillna(0) < small_threshold
    plot_cat.loc[small, "category"] = "Other"
    plot_cat = plot_cat.groupby(["date", "category"], as_index=False).agg(category_market_cap=("category_market_cap", "sum"), category_weight=("category_weight", "sum"), active_asset_count=("active_asset_count", "sum"), return_index=("return_index", "mean"))
y_col = {"Absolute market capitalization": "category_market_cap", "Percentage composition": "category_weight", "Indexed category performance": "return_index"}[composition_view]
fig3 = px.area(plot_cat, x="date", y=y_col, color="category", hover_data=["category_market_cap", "category_weight", "active_asset_count"])
if y_col == "category_market_cap": fig3.update_yaxes(tickprefix="$")
if y_col == "category_weight": fig3.update_yaxes(tickformat=".0%")
st.plotly_chart(fig3, use_container_width=True)

left, right = st.columns(2)
with left:
    st.subheader("Latest Market-Cap Change Decomposition")
    period = market_f.iloc[-1]
    waterfall = pd.DataFrame({"component": ["Beginning", "Price effect", "New issuance", "Removed", "Adjustments", "Ending"], "value": [period["prior_market_cap"], period["price_effect"], period["new_issuance"], -period["removed_capital"], period["other_adjustments"], period["total_market_cap"]]})
    st.plotly_chart(px.bar(waterfall, x="component", y="value", text_auto=".2s"), use_container_width=True)
with right:
    st.subheader("Category Contributions")
    contrib = category_f.groupby("category", as_index=False).agg(price_effect=("price_effect", "sum"), new_issuance=("new_issuance", "sum"), market_cap_change=("category_market_cap", "last"))
    st.plotly_chart(px.bar(contrib.sort_values("price_effect"), x="price_effect", y="category", orientation="h", hover_data=["new_issuance", "market_cap_change"]), use_container_width=True)

with st.expander("Data quality and coverage", expanded=False):
    st.dataframe(quality[(quality["date"] >= start) & (quality["date"] <= end)], use_container_width=True)
    st.plotly_chart(px.bar(market_f, x="date", y=["direct_observation_market_cap", "carried_forward_market_cap"], title="Direct vs carried-forward market cap"), use_container_width=True)

with st.expander("Methodology", expanded=False):
    st.markdown("""
* **Market cap** is price × shares outstanding for assets active on each reporting date.
* **Price selection** uses same-date observations first, then prior observations only; offering price is used on the offering date when no secondary observation exists. Future observations are never used.
* **Staleness** is flagged when the carried observation age exceeds the configured threshold.
* **New issuance** is the first reconstructed market cap for assets entering the series.
* **Price effect** is the period price change for assets already present, multiplied by shares outstanding.
* **Removed capital** is reserved for terminal-event removals; current committed exit linkage is sparse.
* **Flow-adjusted return** removes net external flows from ending market value before comparing with prior market cap and chains the result from 100.
* **Equal-weighted index** averages active asset returns; **market-cap-weighted index** uses the flow-adjusted exchange return.
* **Category decomposition** dynamically groups by the canonical category field and reconciles back to total market cap.
""")

with st.expander("Exports", expanded=False):
    st.download_button("Download total exchange history", market_f.to_csv(index=False), "exchange_market_cap_history_filtered.csv")
    st.download_button("Download category history", category_f.to_csv(index=False), "exchange_category_history_filtered.csv")
    st.download_button("Download asset history", asset_f.to_csv(index=False), "exchange_asset_history_filtered.csv")
    st.download_button("Download data-quality report", quality.to_csv(index=False), "exchange_data_quality_report.csv")
    st.download_button("Download reconciliation report", recon.to_csv(index=False), "exchange_reconciliation_report.csv")
