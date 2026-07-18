from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from app_data import empty_state, load_normalized_csv, load_processed_csv, load_report_csv, render_data_diagnostics
from alt_asset_explorer.custom_index_storage import (
    CombinedCustomIndexRegistry,
    CustomIndexStorageError,
    DuplicateCustomIndexError,
    JsonDirectoryCustomIndexStorage,
    custom_index_storage_is_read_only,
)
from alt_asset_explorer.custom_indices import build_custom_index, calculate_index_metrics, new_custom_index_definition
from alt_asset_explorer.indices import build_index_from_selection, prepare_quarterly_observations, summarize_contributions
from alt_asset_explorer.market_table import build_market_table, filter_market_table
from alt_asset_explorer.research import calculate_sector_performance, completed_categories


st.set_page_config(page_title="Rally Terminal", layout="wide")
render_data_diagnostics()

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; max-width: 1500px;}
    [data-testid="stMetric"] {background: rgba(20, 28, 40, .55); border: 1px solid rgba(128, 145, 170, .18); border-radius: 10px; padding: .8rem 1rem;}
    [data-testid="stMetricLabel"] {letter-spacing: .02em;}
    div[data-testid="stVerticalBlockBorderWrapper"] {border-color: rgba(128, 145, 170, .24); border-radius: 12px;}
    .research-kicker {font-size: .72rem; text-transform: uppercase; letter-spacing: .12em; opacity: .62; margin-bottom: .2rem;}
    .coverage-list {line-height: 1.8; font-size: .9rem; opacity: .9;}
    .custom-badge {display:inline-block; padding:.15rem .48rem; border-radius:999px; background:rgba(88,166,255,.15); color:#58a6ff; font-size:.72rem; font-weight:700; letter-spacing:.04em;}
    </style>
    """,
    unsafe_allow_html=True,
)


def format_money(value: object) -> str:
    number = pd.to_numeric(value, errors="coerce")
    return "Unavailable" if pd.isna(number) else f"${number:,.0f}"


def format_pct(value: object) -> str:
    number = pd.to_numeric(value, errors="coerce")
    return "Unavailable" if pd.isna(number) else f"{number:.1%}"


canonical = load_processed_csv("canonical_asset_master", required=True)
decision = load_processed_csv("rally_asset_decision_universe", required=True)
prices = load_processed_csv("price_history", required=True)
manual_price_observations = load_normalized_csv("price_observations")
liquidity = load_processed_csv("liquidity_metrics")
coverage = load_report_csv("research_coverage")
index_portfolio = load_processed_csv("index_portfolio_history")
exit_analytics = load_processed_csv("exit_analytics")
exchange_market_cap = load_processed_csv("exchange_market_cap_history")
current_universe_artifact = load_processed_csv("current_asset_universe")
current_universe_summary = load_processed_csv("current_universe_summary")

st.title("Rally Terminal")
st.caption("Market intelligence for Rally collectibles. Research only, not financial advice.")

with st.expander("Data caveats", expanded=True):
    st.write(
        "Current tradable assets use the shared canonical universe: production Rally assets with active-tradable status, shares, and a non-stale secondary valuation. "
        "Experimental estimated fair value uses secondary comparable-sales logic and should not be read as a precise appraisal. "
        "Legacy interactive index diagnostics may differ from exit-aware total-return indexes when constituent, rebalance, or price-fill rules differ."
    )

if canonical.empty or decision.empty:
    empty_state()
    st.stop()

market = build_market_table(canonical, decision, prices, liquidity)
current = current_universe_artifact.copy() if not current_universe_artifact.empty else market[market["is_current_listed"].fillna(False)]
summary_row = current_universe_summary.iloc[0].to_dict() if not current_universe_summary.empty else {}
current_as_of = summary_row.get("as_of_date") or (pd.to_datetime(current["date"], errors="coerce").max().date().isoformat() if "date" in current and not current.empty else "Unavailable")

metric_cols = st.columns(4)
metric_cols[0].metric("Current Tradable Assets", f"{int(summary_row.get('tradable_asset_count', len(current))):,}", help=f"Canonical production Rally assets with active-tradable status and a non-stale current valuation as of {current_as_of}.")
metric_cols[1].metric("Research Universe Rows", f"{len(market):,}", help="Rows in the broader research table, including historical/SEC-context rows; this is not a unique current-asset count.")
metric_cols[2].metric("Tradable Exchange Market Cap", format_money(summary_row.get("tradable_market_cap", current.get("canonical_market_cap", current.get("current_market_cap_usd", pd.Series(dtype=float))).sum() if not current.empty else None)), help=f"Canonical current price × shares for current tradable assets as of {current_as_of}; stale carried-forward and offering-only values are excluded.")
metric_cols[3].metric("Assets With Experimental FV", f"{int(current.get('experimental_estimated_fair_value_usd', pd.Series(dtype=float)).notna().sum()):,}")

st.subheader("Market Size and Exit-Aware Total Return")
if not exchange_market_cap.empty:
    exchange_market_cap["date"] = pd.to_datetime(exchange_market_cap["date"], errors="coerce")
    latest_exchange = exchange_market_cap.sort_values("date").iloc[-1]
    size_cols = st.columns(6)
    size_cols[0].metric("Represented Exchange Value", format_money(latest_exchange.get("total_market_cap")), help="Broader reconstructed exchange-history value, including stale carried-forward observations; not the canonical tradable market cap.")
    size_cols[1].metric("Represented Assets", f"{int(latest_exchange.get('active_asset_count', 0)):,}")
    size_cols[2].metric("Active Categories", f"{int(exchange_market_cap.get('active_category_count', pd.Series([0])).iloc[-1] if 'active_category_count' in exchange_market_cap else current['category'].nunique()):,}")
    size_cols[3].metric("Pending Settlement Value", format_money(index_portfolio['pending_settlement_value'].max() if not index_portfolio.empty and 'pending_settlement_value' in index_portfolio else 0))
    size_cols[4].metric("New Issuance YTD", format_money(exchange_market_cap.loc[exchange_market_cap['date'].dt.year.eq(latest_exchange['date'].year), 'new_issuance'].sum() if 'new_issuance' in exchange_market_cap else 0))
    size_cols[5].metric("Capital Removed Through Exits YTD", format_money(exchange_market_cap.loc[exchange_market_cap['date'].dt.year.eq(latest_exchange['date'].year), 'removed_capital'].sum() if 'removed_capital' in exchange_market_cap else 0))
if not index_portfolio.empty:
    index_portfolio["date"] = pd.to_datetime(index_portfolio["date"], errors="coerce")
    tr_categories = ["all"] + sorted([c for c in index_portfolio["category"].dropna().astype(str).unique() if c != "all"])
    tr_cols = st.columns([1.8, 1.2, 1.2])
    tr_category = tr_cols[0].selectbox("Total-return universe", tr_categories, format_func=lambda v: "Full market" if v == "all" else v.replace("_", " ").title(), key="home_tr_category")
    tr_rebal = tr_cols[1].selectbox("Rebalance frequency", sorted(index_portfolio["rebalance_frequency"].dropna().unique()), key="home_tr_rebalance")
    tr_range = tr_cols[2].selectbox("Total-return date range", ["Entire history", "Last 3 years", "Last year"], key="home_tr_range")
    tr = index_portfolio[index_portfolio["category"].astype(str).eq(tr_category) & index_portfolio["rebalance_frequency"].astype(str).eq(tr_rebal)].copy()
    if tr_range != "Entire history" and not tr.empty:
        years = 3 if tr_range == "Last 3 years" else 1
        tr = tr[tr["date"] >= tr["date"].max() - pd.DateOffset(years=years)]
    tr_plot = tr.pivot_table(index="date", columns="weighting_method", values="index_level", aggfunc="last").reset_index().rename(columns={"equal_weight":"Equal-Weighted Total Return Index", "market_cap_weight":"Market-Cap-Weighted Total Return Index"})
    st.plotly_chart(px.line(tr_plot, x="date", y=[c for c in tr_plot.columns if c != "date"], title="What $100 Became (realized exits reinvested on schedule)"), use_container_width=True)
    latest_tr = tr.sort_values("date").groupby("weighting_method").tail(1)
    ret_cols = st.columns(6)
    for idx, method in enumerate(["equal_weight", "market_cap_weight"]):
        row = latest_tr[latest_tr["weighting_method"].eq(method)]
        if not row.empty:
            r = row.iloc[0]; label = "Equal-weighted" if method == "equal_weight" else "Cap-weighted"
            ret_cols[idx*3].metric(label + " return", format_pct(r.get("cumulative_return")))
            ret_cols[idx*3+1].metric(label + " CAGR", format_pct((float(r.get("index_level", 100))/100) ** (365.25 / max((tr["date"].max()-tr["date"].min()).days, 1)) - 1))
            ret_cols[idx*3+2].metric(label + " max drawdown", format_pct(tr[tr["weighting_method"].eq(method)]["drawdown"].min()))
if not exit_analytics.empty:
    ex_cols = st.columns(6)
    ex_cols[0].metric("Total Exited Assets", f"{exit_analytics['asset_id'].nunique():,}")
    ex_cols[1].metric("Total Realized Exit Proceeds", format_money(exit_analytics.get("exit_market_cap", pd.Series(dtype=float)).sum()))
    ex_cols[2].metric("Realized Exit P/L", format_money(exit_analytics.get("realized_pl", pd.Series(dtype=float)).sum()))
    ex_cols[3].metric("Median Exit Return", format_pct(exit_analytics.get("total_return", pd.Series(dtype=float)).median()))
    ex_cols[4].metric("Median Holding Period", f"{pd.to_numeric(exit_analytics.get('holding_period_days'), errors='coerce').median():,.0f} days")
    ex_cols[5].metric("Premium vs Last Trade", format_pct(exit_analytics.get("premium_vs_last_trade", pd.Series(dtype=float)).median()))

quarterly_observations = prepare_quarterly_observations(prices, canonical)
complete_categories = completed_categories(coverage, canonical)
custom_index_read_only = custom_index_storage_is_read_only()
custom_index_registry = CombinedCustomIndexRegistry(
    JsonDirectoryCustomIndexStorage(ROOT / "data" / "custom_indices" / "curated", read_only=True),
    JsonDirectoryCustomIndexStorage(ROOT / "data" / "custom_indices" / "local", read_only=custom_index_read_only),
)
saved_custom_indices = custom_index_registry.list()

overview_col, coverage_col = st.columns([3.4, 1.2], gap="large")
with coverage_col:
    with st.container(border=True):
        st.markdown('<div class="research-kicker">Research Coverage</div>', unsafe_allow_html=True)
        researched_count = int(pd.to_numeric(coverage.get("observation_count"), errors="coerce").fillna(0).gt(0).sum()) if not coverage.empty else 0
        observation_count = int(pd.to_numeric(coverage.get("observation_count"), errors="coerce").fillna(0).sum()) if not coverage.empty else 0
        coverage_metrics = st.columns(3)
        coverage_metrics[0].metric("Assets", researched_count)
        coverage_metrics[1].metric("Complete", len(complete_categories))
        coverage_metrics[2].metric("Observations", observation_count)
        completed_html = "<br>".join(f"✅ {category.replace('_', ' ').title()}" for category in complete_categories) or "No categories complete"
        all_categories = sorted(canonical["category"].dropna().astype(str).unique())
        remaining = [category for category in all_categories if category not in complete_categories]
        remaining_html = " · ".join(category.replace("_", " ").title() for category in remaining[:5])
        if len(remaining) > 5:
            remaining_html += " · …"
        st.markdown(f'<div class="coverage-list"><b>Completed</b><br>{completed_html}</div>', unsafe_allow_html=True)
        if remaining_html:
            st.caption(f"Remaining · {remaining_html}")

with overview_col:
    st.subheader("Sector Performance")
    sector_categories = sorted(quarterly_observations["category"].dropna().astype(str).unique()) if not quarterly_observations.empty else []
    if not sector_categories:
        st.info("Sector statistics appear as categories gain at least two comparable observations.")
    else:
        # Keep this call compatible with already-running Streamlit processes that
        # may still have the previous research module cached during hot reload.
        sector_performance = calculate_sector_performance(quarterly_observations, canonical, sector_categories)
        coverage_by_category: dict[str, dict[str, int]] = {}
        if not coverage.empty and {"asset_id", "category", "observation_count"}.issubset(coverage.columns):
            coverage_targets = coverage.copy()
            if {"asset_id", "status"}.issubset(canonical.columns):
                coverage_targets = coverage_targets.merge(
                    canonical[["asset_id", "status"]].drop_duplicates("asset_id"),
                    on="asset_id",
                    how="left",
                )
                coverage_targets = coverage_targets[coverage_targets["status"].astype(str).str.lower().eq("trading")]
            coverage_targets["_researched"] = pd.to_numeric(
                coverage_targets["observation_count"], errors="coerce"
            ).fillna(0).gt(0)
            coverage_summary = coverage_targets.groupby("category").agg(
                target_asset_count=("asset_id", "nunique"),
                researched_asset_count=("_researched", "sum"),
            )
            coverage_by_category = coverage_summary.astype(int).to_dict("index")
        for row_index, row in sector_performance.iterrows():
            category_coverage = coverage_by_category.get(str(row["category"]))
            if category_coverage:
                researched = category_coverage["researched_asset_count"]
                target = category_coverage["target_asset_count"]
                sector_performance.loc[row_index, "researched_asset_count"] = researched
                sector_performance.loc[row_index, "target_asset_count"] = target
                sector_performance.loc[row_index, "coverage_pct"] = researched / target if target else None
                sector_performance.loc[row_index, "coverage_status"] = "Complete" if target and researched >= target else "Building"
        sector_display = sector_performance.copy()
        sector_display["category"] = sector_display["category"].str.replace("_", " ").str.title()
        for percentage_column in ["since_inception", "last_year", "annualized_volatility"]:
            sector_display[percentage_column] = pd.to_numeric(sector_display[percentage_column], errors="coerce") * 100
        sector_display["coverage"] = (
            sector_display["researched_asset_count"].astype("Int64").astype(str)
            + " / "
            + sector_display["target_asset_count"].astype("Int64").astype(str)
        )
        sector_display["coverage_status"] = sector_display["coverage_status"].map({"Complete": "✅ Complete", "Building": "🟡 Building"})
        sector_display = sector_display.rename(
            columns={
                "category": "Category",
                "since_inception": "Since inception",
                "last_year": "Last year",
                "annualized_volatility": "Volatility",
                "volatility_band": "Risk band",
                "constituent_count": "Assets",
                "coverage": "Coverage",
                "coverage_status": "Research status",
            }
        )
        st.dataframe(
            sector_display[["Category", "Since inception", "Last year", "Volatility", "Risk band", "Coverage", "Research status"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Since inception": st.column_config.NumberColumn(format="%+.1f%%"),
                "Last year": st.column_config.NumberColumn(format="%+.1f%%"),
                "Volatility": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
        st.caption(
            "Sectors appear as soon as a return can be calculated. Returns use equal-weight quarterly indices; "
            "coverage shows researched assets versus the current trading universe, and volatility is annualized."
        )

st.subheader("Index Explorer")
if quarterly_observations.empty:
    st.info("No quarterly observations are available. Run `python3 scripts/build_dataset.py`.")
else:
    saved_options = {"Built-in market and category indexes": None}
    saved_options.update({f"🧰 {item.name} · Custom · {len(item.constituents)} assets": item for item in saved_custom_indices})
    selected_saved_label = st.selectbox(
        "Explore index",
        list(saved_options),
        key="explorer_saved_index",
        help="Saved workshop indexes appear here alongside the built-in market and category indexes.",
    )
    selected_saved_index = saved_options[selected_saved_label]
    observation_categories = set(quarterly_observations["category"].dropna().astype(str).unique())
    canonical_categories = set(canonical["category"].dropna().astype(str).unique()) if "category" in canonical else set()
    available_categories = sorted(observation_categories | canonical_categories)
    control_cols = st.columns([2.2, 1.5, 1.5, 1.4], gap="medium")
    selected_index_categories = control_cols[0].multiselect(
        "Categories",
        available_categories,
        default=available_categories,
        format_func=lambda value: value.replace("_", " ").title(),
        key="index_categories",
    )
    weighting_labels = control_cols[1].multiselect(
        "Weighting",
        ["Equal Weight", "Market-Cap Weight"],
        default=["Equal Weight"],
        key="index_weightings",
    )
    universe_label = control_cols[2].radio(
        "Universe",
        ["Currently Trading Only", "Include Exited Assets"],
        horizontal=False,
        key="index_universe",
    )
    range_label = control_cols[3].selectbox(
        "Date range",
        ["Entire history", "Last 3 years", "Last year", "Custom"],
        key="index_range",
    )

    observation_dates = pd.to_datetime(quarterly_observations["date"], errors="coerce").dropna()
    max_observation_date = observation_dates.max().date()
    min_observation_date = observation_dates.min().date()
    start_date = None
    end_date = max_observation_date
    if range_label == "Last 3 years":
        start_date = (pd.Timestamp(max_observation_date) - pd.DateOffset(years=3)).date()
    elif range_label == "Last year":
        start_date = (pd.Timestamp(max_observation_date) - pd.DateOffset(years=1)).date()
    elif range_label == "Custom":
        custom_dates = st.date_input(
            "Custom window",
            value=(min_observation_date, max_observation_date),
            min_value=min_observation_date,
            max_value=max_observation_date,
        )
        if isinstance(custom_dates, (tuple, list)) and len(custom_dates) == 2:
            start_date, end_date = custom_dates

    weighting_map = {"Equal Weight": "equal", "Market-Cap Weight": "market_cap"}
    selected_weightings = [weighting_map[label] for label in weighting_labels]
    universe_assets = canonical.copy()
    if universe_label == "Currently Trading Only":
        universe_assets = universe_assets[universe_assets["status"].astype(str).str.lower().eq("trading")]
    universe_assets = universe_assets[universe_assets["category"].astype(str).isin(selected_index_categories)]
    selected_asset_ids = universe_assets["asset_id"].astype(str).unique().tolist()

    explorer_series: list[pd.DataFrame] = []
    primary_result = None
    selected_saved_result = None
    for weighting in selected_weightings:
        weighting_name = "Equal Weight" if weighting == "equal" else "Market Cap"
        combined = build_index_from_selection(
            quarterly_observations,
            asset_ids=selected_asset_ids,
            weighting_method=weighting,
            index_id=f"explorer_all_{weighting}",
            index_name=f"Selected Market · {weighting_name}",
            category="selected",
            start_date=start_date,
            end_date=end_date,
        )
        if primary_result is None:
            primary_result = combined
        explorer_series.append(combined.series)
        for category in selected_index_categories:
            category_ids = universe_assets.loc[universe_assets["category"].astype(str).eq(category), "asset_id"].astype(str).tolist()
            category_result = build_index_from_selection(
                quarterly_observations,
                asset_ids=category_ids,
                weighting_method=weighting,
                index_id=f"explorer_{category}_{weighting}",
                index_name=f"{category.replace('_', ' ').title()} · {weighting_name}",
                category=category,
                start_date=start_date,
                end_date=end_date,
            )
            explorer_series.append(category_result.series)

    if selected_saved_index is not None:
        saved_ids = [item.asset_id for item in selected_saved_index.constituents]
        saved_weights = {item.asset_id: item.weight for item in selected_saved_index.constituents}
        selected_saved_result = build_custom_index(
            quarterly_observations,
            asset_ids=saved_ids,
            weights=saved_weights,
            base_value=selected_saved_index.base_value,
            start_date=start_date or selected_saved_index.start_date,
            end_date=end_date or selected_saved_index.end_date,
        )
        st.markdown('<span class="custom-badge">CUSTOM INDEX</span>', unsafe_allow_html=True)
        st.markdown(f"### {selected_saved_index.name}")
        if selected_saved_index.description:
            st.write(selected_saved_index.description)
        st.caption(
            f"Created by {selected_saved_index.creator} · {selected_saved_index.created_at.date().isoformat()} · "
            f"{len(saved_ids)} constituents · {selected_saved_index.weighting_method.replace('_', ' ').title()}"
        )
        saved_composition = pd.DataFrame(
            [
                {
                    "Ticker": item.ticker or item.asset_id,
                    "Asset": item.display_name or item.asset_id,
                    "Asset ID": item.asset_id,
                    "Weight": item.weight,
                }
                for item in selected_saved_index.constituents
            ]
        )
        saved_composition["Weight"] = saved_composition["Weight"] * 100
        st.dataframe(
            saved_composition,
            use_container_width=True,
            hide_index=True,
            column_config={"Weight": st.column_config.NumberColumn(format="%.1f%%")},
        )
        st.download_button(
            "Download index definition (JSON)",
            selected_saved_index.model_dump_json(indent=2),
            file_name=f"{selected_saved_index.id}.json",
            mime="application/json",
            key="explorer_download_custom_json",
        )
        if selected_saved_result.series.empty:
            st.warning("This saved index cannot be calculated from the current local observations.")
        else:
            saved_chart = selected_saved_result.series.rename(columns={"return_period": "return_1d"}).copy()
            saved_chart["index_id"] = selected_saved_index.id
            saved_chart["index_name"] = f"{selected_saved_index.name} · Custom"
            saved_chart["category"] = "custom"
            explorer_series.insert(0, saved_chart)
            saved_metrics = calculate_index_metrics(selected_saved_result.series)
            custom_metric_cols = st.columns(5)
            custom_metric_cols[0].metric("Total Return", format_pct(saved_metrics["total_return"]))
            custom_metric_cols[1].metric("CAGR", format_pct(saved_metrics["cagr"]))
            custom_metric_cols[2].metric("Volatility", format_pct(saved_metrics["annualized_volatility"]))
            custom_metric_cols[3].metric("Sharpe", "N/A" if saved_metrics["sharpe_ratio"] is None else f"{saved_metrics['sharpe_ratio']:.2f}")
            custom_metric_cols[4].metric("Max Drawdown", format_pct(saved_metrics["maximum_drawdown"]))
            st.caption(
                f"Effective history: {selected_saved_result.effective_start_date} through {selected_saved_result.effective_end_date}. "
                "Constant-weight normalized composite; common observed quarter-ends only; no price imputation."
            )

    chart_data = pd.concat(explorer_series, ignore_index=True) if explorer_series else pd.DataFrame()
    if chart_data.empty:
        st.warning("No observations match this selection. Add categories, weightings, or broaden the universe/date range.")
    else:
        latest_combined = chart_data[chart_data["category"].eq("selected")].sort_values("date").groupby("index_id", as_index=False).tail(1)
        metric_columns = st.columns(max(1, len(latest_combined)))
        for metric_column, (_, row) in zip(metric_columns, latest_combined.iterrows()):
            metric_column.metric(row["index_name"], f"{float(row['index_level']):,.2f}", format_pct(row.get("return_1d")))
            metric_column.caption(f"{int(row['constituent_count'])} constituents · through {row['date']}")

        explorer_figure = go.Figure()
        palette = ["#58a6ff", "#3fb950", "#d29922", "#f778ba", "#a371f7", "#ff7b72", "#79c0ff", "#56d4dd"]
        for color_index, (series_name, frame) in enumerate(chart_data.groupby("index_name", sort=False)):
            explorer_figure.add_trace(
                go.Scatter(
                    x=frame["date"],
                    y=frame["index_level"],
                    name=series_name,
                    mode="lines+markers",
                    line={"width": 3 if str(series_name).startswith("Selected Market") else 1.8, "color": palette[color_index % len(palette)]},
                    marker={"size": 5},
                    customdata=frame[["constituent_count", "return_1d"]],
                    hovertemplate="%{x}<br><b>%{y:.2f}</b><br>%{customdata[0]} constituents<br>Period return %{customdata[1]:+.1%}<extra>%{fullData.name}</extra>",
                )
            )
        explorer_figure.update_layout(
            height=510,
            hovermode="x unified",
            dragmode="zoom",
            legend={"orientation": "h", "yanchor": "bottom", "y": 1.03, "x": 0},
            margin={"t": 76, "r": 24, "b": 48, "l": 52},
            xaxis={"title": "Quarter end", "rangeslider": {"visible": True}},
            yaxis={"title": "Index level", "fixedrange": False},
        )
        st.plotly_chart(
            explorer_figure,
            use_container_width=True,
            config={"scrollZoom": True, "displaylogo": False, "modeBarButtonsToAdd": ["drawline", "eraseshape"]},
        )
        st.caption("Click legend entries to isolate series. Drag to zoom, scroll to zoom, double-click to reset, and use the range slider to pan.")

        if selected_saved_result is not None and not selected_saved_result.contributions.empty:
            st.markdown("#### Saved Custom Index Contribution Analysis")
            saved_contributions = selected_saved_result.contributions.merge(
                canonical[["asset_id", "ticker", "name", "category"]].drop_duplicates("asset_id"),
                on="asset_id",
                how="left",
            )
            for percentage_column in ["starting_weight", "asset_return", "contribution_return", "share_of_total_move"]:
                saved_contributions[percentage_column] = pd.to_numeric(saved_contributions[percentage_column], errors="coerce") * 100
            st.dataframe(
                saved_contributions.rename(
                    columns={
                        "ticker": "Ticker", "name": "Asset", "category": "Category",
                        "starting_weight": "Starting weight", "asset_return": "Asset return",
                        "contribution_return": "Weighted contribution", "contribution_points": "Contribution points",
                        "share_of_total_move": "Share of total move",
                    }
                )[["Ticker", "Asset", "Category", "Starting weight", "Asset return", "Weighted contribution", "Contribution points", "Share of total move"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Starting weight": st.column_config.NumberColumn(format="%.1f%%"),
                    "Asset return": st.column_config.NumberColumn(format="%+.1f%%"),
                    "Weighted contribution": st.column_config.NumberColumn(format="%+.1f%%"),
                    "Contribution points": st.column_config.NumberColumn(format="%+.2f"),
                    "Share of total move": st.column_config.NumberColumn(format="%+.1f%%"),
                },
            )

        st.subheader("Contribution Analysis")
        if primary_result is None or primary_result.contributions.empty:
            st.info("Attribution appears after the selection contains at least two comparable observations.")
        else:
            contribution_summary = summarize_contributions(primary_result.contributions, canonical)
            positive = contribution_summary[contribution_summary["contribution_points"] > 0].head(5)
            negative = contribution_summary[contribution_summary["contribution_points"] < 0].sort_values("contribution_points").head(5)
            positive_col, negative_col = st.columns(2, gap="large")

            def render_contributors(container: object, title: str, frame: pd.DataFrame) -> None:
                with container:
                    st.markdown(f"**{title}**")
                    if frame.empty:
                        st.caption("No contributors in this direction.")
                    for _, contributor in frame.iterrows():
                        label = contributor.get("ticker") if pd.notna(contributor.get("ticker")) else contributor.get("name")
                        if pd.isna(label):
                            label = contributor["asset_id"]
                        st.metric(str(label), f"{float(contributor['contribution_points']):+.2f} pts")

            render_contributors(positive_col, "Largest Positive Contributors", positive)
            render_contributors(negative_col, "Largest Negative Contributors", negative)
            primary_series = primary_result.series.sort_values("date")
            total_move = float(primary_series.iloc[-1]["index_level"] - primary_series.iloc[0]["index_level"])
            leaders = positive.head(2)
            laggards = negative.head(1)
            leader_names = [str(row["ticker"] if pd.notna(row["ticker"]) else row["name"]) for _, row in leaders.iterrows()]
            laggard_names = [str(row["ticker"] if pd.notna(row["ticker"]) else row["name"]) for _, row in laggards.iterrows()]
            direction = "rose" if total_move >= 0 else "fell"
            commentary = f"The selected index {direction} {abs(total_move):.1f} points over this window"
            if leader_names:
                commentary += f", led by {' and '.join(leader_names)}"
            if laggard_names:
                commentary += f", while weakness in {' and '.join(laggard_names)} offset part of the move"
            st.info(commentary + ".")

st.subheader("Asset Price History")
if prices.empty:
    st.info("No asset price observations are available yet.")
else:
    price_assets = prices.dropna(subset=["asset_id", "last"]).copy()
    price_assets["date"] = pd.to_datetime(price_assets["date"], errors="coerce").dt.tz_localize(None)
    price_assets = price_assets.dropna(subset=["date"])
    if not manual_price_observations.empty:
        offering_rows = manual_price_observations[
            manual_price_observations["event_type"].astype(str).eq("offering_price")
            & manual_price_observations["price_per_share"].notna()
        ].copy()
        if not offering_rows.empty:
            offering_rows["date"] = pd.to_datetime(offering_rows["observed_at"], errors="coerce", utc=True).dt.tz_localize(None)
            offering_rows["last"] = pd.to_numeric(offering_rows["price_per_share"], errors="coerce")
            offering_rows["market_cap_usd"] = pd.to_numeric(offering_rows["market_cap"], errors="coerce")
            offering_rows["source"] = "manual:" + offering_rows["event_type"].astype(str) + ":" + offering_rows["precision_status"].astype(str)
            offering_display = offering_rows[
                ["date", "asset_id", "last", "market_cap_usd", "source", "event_type", "precision_status", "period_end"]
            ].dropna(subset=["asset_id", "date", "last"])
            price_assets = pd.concat([price_assets, offering_display], ignore_index=True)
            price_assets = price_assets.sort_values(["asset_id", "date", "event_type"]).drop_duplicates(
                subset=["asset_id", "date", "last", "event_type"], keep="last"
            )
    asset_names = market[["asset_id", "ticker", "name", "category", "subcategory"]].drop_duplicates("asset_id")
    price_assets = price_assets.merge(asset_names, on="asset_id", how="left")
    price_assets["ticker"] = price_assets["ticker"].fillna(price_assets["asset_id"]).astype(str)
    price_assets["name"] = price_assets["name"].fillna(price_assets["asset_id"]).astype(str)
    price_assets["asset_label"] = price_assets["ticker"] + " | " + price_assets["name"]
    options = price_assets[["asset_id", "asset_label"]].drop_duplicates().sort_values("asset_label").reset_index(drop=True)

    history_mode = st.radio(
        "Mode",
        ["Single Asset", "Custom Index Workshop"],
        horizontal=True,
        key="asset_history_mode",
    )
    if options.empty:
        st.info("No asset price observations are available yet.")
    elif history_mode == "Single Asset":
        default_idx = 0
        mosasaur_match = options.index[options["asset_id"].eq("rally-mosasaur")].tolist()
        if mosasaur_match:
            default_idx = mosasaur_match[0]
        selected_label = st.selectbox("Asset", options["asset_label"].tolist(), index=default_idx, key="single_asset")
        selected_asset_id = options.loc[options["asset_label"].eq(selected_label), "asset_id"].iloc[0]
        asset_prices = price_assets[price_assets["asset_id"].eq(selected_asset_id)].sort_values("date").copy()
        hover_columns = [column for column in ["period_end", "market_cap_usd", "event_type", "source", "precision_status"] if column in asset_prices.columns]
        asset_fig = px.line(asset_prices, x="date", y="last", markers=True, hover_data=hover_columns, labels={"date": "Observed date", "last": "Price per share"})
        asset_fig.update_layout(height=320)
        st.plotly_chart(asset_fig, use_container_width=True)
        detail_columns = [column for column in ["date", "period_end", "last", "market_cap_usd", "event_type", "source", "precision_status"] if column in asset_prices.columns]
        st.dataframe(
            asset_prices[detail_columns].rename(columns={"date": "Observed date", "period_end": "Period end", "last": "Price per share", "market_cap_usd": "Market cap", "event_type": "Event type", "source": "Source", "precision_status": "Precision"}),
            use_container_width=True,
            hide_index=True,
            column_config={"Price per share": st.column_config.NumberColumn(format="$%.2f"), "Market cap": st.column_config.NumberColumn(format="$%.0f")},
        )
    else:
        st.markdown("### Custom Index Workshop")
        st.caption("Build a basket, tune its allocation, and save it for comparison in Index Explorer.")
        workshop_metadata = canonical[["asset_id", "ticker", "name", "category", "subcategory"]].drop_duplicates("asset_id")
        workshop_metadata = workshop_metadata[workshop_metadata["asset_id"].astype(str).isin(quarterly_observations["asset_id"].astype(str).unique())].copy()
        workshop_metadata["label"] = (
            workshop_metadata["ticker"].fillna(workshop_metadata["asset_id"]).astype(str)
            + " | " + workshop_metadata["name"].fillna(workshop_metadata["asset_id"]).astype(str)
            + " · " + workshop_metadata["category"].fillna("other").astype(str).str.replace("_", " ").str.title()
        )
        label_to_id = dict(zip(workshop_metadata["label"], workshop_metadata["asset_id"].astype(str)))
        id_to_label = {value: key for key, value in label_to_id.items()}
        prior_ids = st.session_state.get("workshop_constituent_ids", [])
        default_labels = [id_to_label[item] for item in prior_ids if item in id_to_label]
        selected_labels = st.multiselect(
            "Build a Basket",
            sorted(label_to_id),
            default=default_labels,
            placeholder="Search by ticker, asset, or category",
            key="workshop_asset_labels",
        )
        selected_ids = [label_to_id[label] for label in selected_labels]
        if selected_ids != prior_ids:
            st.session_state["workshop_constituent_ids"] = selected_ids
            equal_pct = 100.0 / len(selected_ids) if selected_ids else 0.0
            st.session_state["workshop_weights"] = {asset_id: equal_pct for asset_id in selected_ids}
        workshop_weights = st.session_state.setdefault("workshop_weights", {})

        def reset_workshop() -> None:
            for key in ["workshop_asset_labels", "workshop_constituent_ids", "workshop_weights", "workshop_name", "workshop_description", "workshop_saved"]:
                st.session_state.pop(key, None)

        st.button("Reset Workshop", key="workshop_reset", on_click=reset_workshop)

        if not selected_ids:
            st.info("Choose at least one asset to start your custom index at 100.")
        else:
            allocation_mode = st.radio("Allocation", ["Equal Weight", "Custom Weight"], horizontal=True, key="workshop_allocation_mode")
            if allocation_mode == "Equal Weight":
                workshop_weights = {asset_id: 100.0 / len(selected_ids) for asset_id in selected_ids}
                st.session_state["workshop_weights"] = workshop_weights
            else:
                weight_columns = st.columns(min(4, len(selected_ids)))
                for position, asset_id in enumerate(selected_ids):
                    meta = workshop_metadata[workshop_metadata["asset_id"].astype(str).eq(asset_id)].iloc[0]
                    workshop_weights[asset_id] = weight_columns[position % len(weight_columns)].number_input(
                        str(meta["ticker"]),
                        min_value=0.01,
                        max_value=100.0,
                        value=float(workshop_weights.get(asset_id, 100.0 / len(selected_ids))),
                        step=0.5,
                        format="%.2f",
                        key=f"workshop_weight_{asset_id}",
                    )
                def normalize_workshop_weights() -> None:
                    total_raw = sum(workshop_weights.values())
                    if total_raw > 0:
                        st.session_state["workshop_weights"] = {key: value / total_raw * 100 for key, value in workshop_weights.items()}
                        for asset_id, value in st.session_state["workshop_weights"].items():
                            st.session_state[f"workshop_weight_{asset_id}"] = value

                def equalize_workshop_weights() -> None:
                    equal_pct = 100.0 / len(selected_ids)
                    st.session_state["workshop_weights"] = {asset_id: equal_pct for asset_id in selected_ids}
                    for asset_id in selected_ids:
                        st.session_state[f"workshop_weight_{asset_id}"] = equal_pct

                normalize_col, equal_col = st.columns(2)
                normalize_col.button("Normalize to 100%", key="workshop_normalize", on_click=normalize_workshop_weights)
                equal_col.button("Reset to Equal Weight", key="workshop_equal", on_click=equalize_workshop_weights)

            total_weight = sum(workshop_weights.get(asset_id, 0) for asset_id in selected_ids)
            weight_valid = abs(total_weight - 100.0) <= 0.01
            (st.success if weight_valid else st.warning)(f"Total allocation: {total_weight:.2f}%" + ("" if weight_valid else " · Normalize or edit weights to continue."))
            normalized_workshop_weights = {asset_id: workshop_weights[asset_id] / 100 for asset_id in selected_ids}
            workshop_result = build_custom_index(quarterly_observations, asset_ids=selected_ids, weights=normalized_workshop_weights)
            for warning in workshop_result.warnings:
                st.warning(warning)
            if workshop_result.series.empty:
                st.error("These assets do not have enough overlapping valid price history to form an index.")
            elif weight_valid:
                workshop_metrics = calculate_index_metrics(workshop_result.series)
                workshop_figure = px.line(workshop_result.series, x="date", y="index_level", markers=True, labels={"date": "Quarter end", "index_level": "Custom index level"})
                workshop_figure.update_traces(line={"width": 3, "color": "#58a6ff"})
                workshop_figure.update_layout(height=390, hovermode="x unified")
                st.plotly_chart(workshop_figure, use_container_width=True, config={"scrollZoom": True, "displaylogo": False})
                scorecard = st.columns(5)
                scorecard[0].metric("Total Return", format_pct(workshop_metrics["total_return"]))
                scorecard[1].metric("CAGR", format_pct(workshop_metrics["cagr"]))
                scorecard[2].metric("Volatility", format_pct(workshop_metrics["annualized_volatility"]))
                scorecard[3].metric("Sharpe", "N/A" if workshop_metrics["sharpe_ratio"] is None else f"{workshop_metrics['sharpe_ratio']:.2f}")
                scorecard[4].metric("Max Drawdown", format_pct(workshop_metrics["maximum_drawdown"]))
                st.caption(f"{len(selected_ids)} constituents · effective history {workshop_result.effective_start_date} through {workshop_result.effective_end_date} · risk band {workshop_metrics['risk_band']}")

                composition = workshop_metadata[workshop_metadata["asset_id"].astype(str).isin(selected_ids)].copy()
                composition["Weight"] = composition["asset_id"].map(normalized_workshop_weights)
                first_dates = workshop_result.aligned_prices.apply(lambda column: column.first_valid_index().date().isoformat() if column.first_valid_index() is not None else None)
                last_dates = workshop_result.aligned_prices.apply(lambda column: column.last_valid_index().date().isoformat() if column.last_valid_index() is not None else None)
                composition["Available start"] = composition["asset_id"].map(first_dates)
                composition["Available end"] = composition["asset_id"].map(last_dates)
                composition = composition.merge(workshop_result.contributions, on="asset_id", how="left")
                composition_display = composition.rename(columns={"ticker": "Ticker", "name": "Asset", "category": "Category", "asset_return": "Asset return", "contribution_points": "Contribution points"})
                composition_display["Weight"] *= 100
                composition_display["Asset return"] = pd.to_numeric(composition_display["Asset return"], errors="coerce") * 100
                st.markdown("#### Constituents & Contribution Analysis")
                st.dataframe(
                    composition_display[["Ticker", "Asset", "Category", "Weight", "Available start", "Available end", "Asset return", "Contribution points"]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={"Weight": st.column_config.NumberColumn(format="%.2f%%"), "Asset return": st.column_config.NumberColumn(format="%+.1f%%"), "Contribution points": st.column_config.NumberColumn(format="%+.2f pts")},
                )

                st.markdown("#### Name & Save")
                if custom_index_read_only:
                    st.info("Saving is disabled in this cloud deployment because its filesystem is not durable. You can still export the definition as JSON.")
                name_col, description_col = st.columns([1, 2])
                index_name = name_col.text_input("Index name", max_chars=100, key="workshop_name", placeholder="e.g. Jurassic Index")
                index_description = description_col.text_area("Description (optional)", max_chars=1000, key="workshop_description", height=90)
                pending_definition = None
                if index_name.strip():
                    constituents = []
                    for asset_id in selected_ids:
                        meta = workshop_metadata[workshop_metadata["asset_id"].astype(str).eq(asset_id)].iloc[0]
                        constituents.append({"asset_id": asset_id, "display_name": str(meta["name"]), "ticker": str(meta["ticker"]), "weight": normalized_workshop_weights[asset_id]})
                    pending_definition = new_custom_index_definition(
                        name=index_name,
                        description=index_description,
                        constituents=constituents,
                        weighting_method="equal" if allocation_mode == "Equal Weight" else "custom",
                        start_date=workshop_result.effective_start_date,
                        end_date=workshop_result.effective_end_date,
                        analytics_snapshot=workshop_metrics,
                    )
                if st.button("Save Custom Index", type="primary", key="workshop_save", disabled=pending_definition is None or custom_index_read_only):
                    try:
                        saved = custom_index_registry.save(pending_definition)
                        st.session_state["workshop_saved"] = saved.model_dump(mode="json")
                        st.success(f"Saved {saved.name}. Index ID: {saved.id}. It is now available in Index Explorer.")
                    except (DuplicateCustomIndexError, CustomIndexStorageError, ValueError) as exc:
                        st.error(str(exc))
                export_definition = st.session_state.get("workshop_saved")
                if pending_definition is not None and (custom_index_read_only or export_definition is None):
                    export_definition = pending_definition.model_dump(mode="json")
                if export_definition:
                    st.download_button("Export definition (JSON)", json.dumps(export_definition, indent=2), file_name=f"{export_definition['id']}.json", mime="application/json", key="workshop_export_json")

st.subheader("Rally Market Table")

with st.sidebar:
    st.subheader("Market filters")
    current_only = st.toggle("Current listed assets only", value=True)
    search = st.text_input("Search name or ticker", value="")
    category_options = sorted(market["category"].dropna().astype(str).unique().tolist())
    selected_categories = st.multiselect("Category", category_options, default=category_options)
    subcategory_base = market[market["category"].astype(str).isin(selected_categories)] if selected_categories else market
    subcategory_options = sorted(subcategory_base["subcategory"].dropna().astype(str).unique().tolist())
    selected_subcategories = st.multiselect("Subcategory", subcategory_options, default=subcategory_options)
    quality_options = sorted(market["data_quality_status"].dropna().astype(str).unique().tolist())
    selected_quality = st.multiselect("Data quality", quality_options, default=quality_options)
    valuation_filter = st.selectbox("Fair value position", ["All", "Below estimated fair value", "Above estimated fair value"])
    min_confidence = st.slider("Minimum FV confidence", 0.0, 1.0, 0.0, 0.05)

filtered = filter_market_table(
    market,
    search=search,
    categories=selected_categories,
    subcategories=selected_subcategories,
    data_quality=selected_quality,
    valuation_filter=valuation_filter,
    min_confidence=min_confidence,
    current_listed_only=current_only,
)

if filtered.empty:
    st.info("No assets match the current filters.")
else:
    display = filtered.rename(
        columns={
            "name": "Asset name",
            "ticker": "Ticker",
            "asset_id": "Asset ID",
            "category": "Category",
            "subcategory": "Subcategory",
            "last_price": "Last price",
            "best_bid": "Best bid",
            "best_ask": "Best ask",
            "bid_ask_spread_pct": "Bid-ask spread",
            "shares_outstanding": "Shares outstanding",
            "current_market_cap_usd": "Market cap",
            "offering_price_usd": "Offering price",
            "offering_valuation_usd": "Offering valuation",
            "experimental_estimated_fair_value_usd": "Experimental estimated fair value",
            "premium_discount_to_fair_value": "Premium / discount to FV",
            "nav_confidence": "FV confidence",
            "last_quote_observed_at": "Last quote update",
            "data_quality_status": "Data quality",
            "data_quality_warnings": "Data warnings",
        }
    )
    columns = [
        "Ticker",
        "Asset name",
        "Asset ID",
        "Category",
        "Subcategory",
        "Last price",
        "Best bid",
        "Best ask",
        "Bid-ask spread",
        "Shares outstanding",
        "Market cap",
        "Offering price",
        "Offering valuation",
        "Experimental estimated fair value",
        "Premium / discount to FV",
        "FV confidence",
        "Last quote update",
        "Data quality",
        "Data warnings",
    ]
    for percent_col in ("Bid-ask spread", "Premium / discount to FV", "FV confidence"):
        if percent_col in display:
            display[percent_col] = pd.to_numeric(display[percent_col], errors="coerce") * 100
    st.dataframe(
        display[[col for col in columns if col in display.columns]].sort_values("Ticker"),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Last price": st.column_config.NumberColumn(format="$%.2f"),
            "Best bid": st.column_config.NumberColumn(format="$%.2f"),
            "Best ask": st.column_config.NumberColumn(format="$%.2f"),
            "Bid-ask spread": st.column_config.NumberColumn(format="%.1f%%"),
            "Shares outstanding": st.column_config.NumberColumn(format="%.0f"),
            "Market cap": st.column_config.NumberColumn(format="$%.0f"),
            "Offering price": st.column_config.NumberColumn(format="$%.2f"),
            "Offering valuation": st.column_config.NumberColumn(format="$%.0f"),
            "Experimental estimated fair value": st.column_config.NumberColumn(format="$%.0f"),
            "Premium / discount to FV": st.column_config.NumberColumn(format="%.1f%%"),
            "FV confidence": st.column_config.NumberColumn(format="%.0f%%"),
        },
    )

    st.caption(
        "Unavailable values are intentionally left blank. SEC-synthesized rows remain research context and are hidden by default unless current-listing filtering is turned off."
    )
