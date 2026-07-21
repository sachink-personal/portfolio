"""
Page 2 — Portfolio
Live holdings table, current vs target weights, per-holding P&L, and add/edit/delete forms.
"""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Portfolio", page_icon="📦", layout="wide")
st.title("📦 Portfolio Holdings")


# ── Data loader ───────────────────────────────────────────────────────────────
# NOTE: Caching removed to comply with "ALL LIVE values" requirement

def load_holdings():
    """Load holdings directly from database (LIVE — no caching)."""
    from core.sheets import SheetsClient
    return SheetsClient().get_holdings()


def refresh_prices(holdings):
    """Fetch latest prices and write them back to the database."""
    from data.equity import get_current_prices
    from data.mf_nav import get_mf_prices
    from core.sheets import SheetsClient

    equity_tickers = []
    if "AssetClass" in holdings.columns:
        equity_tickers = holdings[
            holdings["AssetClass"].str.upper().isin(["EQUITY", "ETF"])
        ]["Ticker"].tolist()

    price_map = get_current_prices(equity_tickers) if equity_tickers else {}
    price_map.update(get_mf_prices(holdings))

    if price_map:
        SheetsClient().update_holdings_prices(price_map)
    st.cache_data.clear()


# ── Sidebar actions ───────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("⚙️ Actions")
    if st.button("🔄 Refresh Prices", width="stretch"):
        with st.spinner("Fetching latest prices…"):
            try:
                h = load_holdings()
                refresh_prices(h)
                st.success("Prices updated.")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed: {exc}")

    if st.button("🔃 Reload Data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

# ── Load ──────────────────────────────────────────────────────────────────────

try:
    holdings = load_holdings()
except Exception as exc:
    st.error(f"Could not load holdings: {exc}")
    st.stop()

if holdings.empty:
    st.info(
        "No holdings yet. Use the form below to add your first position, "
        "or run `python scripts/import_portfolio.py` to import from a backup file."
    )
else:
    # ── Computed columns ──────────────────────────────────────────────────────
    import pandas as pd

    h = holdings.copy()
    h["P&L ₹"] = (h["CurrentPrice"] - h["AvgBuyPrice"]) * h["Qty"]
    h["P&L %"] = ((h["CurrentPrice"] - h["AvgBuyPrice"]) / h["AvgBuyPrice"] * 100).where(
        h["AvgBuyPrice"] > 0, 0
    ).round(2)

    # ── Summary metrics ───────────────────────────────────────────────────────
    total_value = h["Value"].sum()
    total_invested = (h["AvgBuyPrice"] * h["Qty"]).sum()
    total_pnl = total_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Current Value", f"₹{total_value:,.0f}")
    with c2:
        st.metric("Total Invested", f"₹{total_invested:,.0f}")
    with c3:
        st.metric(
            "Unrealised P&L",
            f"₹{total_pnl:,.0f}",
            f"{total_pnl_pct:+.2f}%",
        )

    st.divider()

    # ── Holdings table ────────────────────────────────────────────────────────
    st.subheader("Holdings Table")

    display_cols = [
        "Ticker", "Name", "AssetClass", "Qty",
        "AvgBuyPrice", "CurrentPrice", "Value",
        "P&L ₹", "P&L %", "TargetWeight", "CurrentWeight",
    ]
    display_cols = [c for c in display_cols if c in h.columns]

    # Keep columns numeric so Streamlit's built-in column sorting works.
    # Use column_config for ₹ / % formatting.
    col_cfg = {}
    for col in ("AvgBuyPrice", "CurrentPrice"):
        if col in display_cols:
            col_cfg[col] = st.column_config.NumberColumn(col, format="₹%.2f")
    for col in ("Value", "P&L ₹"):
        if col in display_cols:
            col_cfg[col] = st.column_config.NumberColumn(col, format="₹%d")
    for col in ("P&L %", "TargetWeight", "CurrentWeight"):
        if col in display_cols:
            col_cfg[col] = st.column_config.NumberColumn(col, format="%.1f%%")

    st.dataframe(
        h[display_cols],
        width="stretch",
        hide_index=True,
        column_config=col_cfg,
    )

    st.divider()

    # ── Current vs Target weights bar chart ───────────────────────────────────
    st.subheader("📊 Current vs Target Weight")
    if "TargetWeight" in h.columns and "CurrentWeight" in h.columns:
        fig = go.Figure()
        tickers = h["Ticker"].tolist()
        fig.add_trace(go.Bar(
            name="Current %",
            x=tickers,
            y=h["CurrentWeight"].tolist(),
            marker_color="#4a90e2",
        ))
        fig.add_trace(go.Bar(
            name="Target %",
            x=tickers,
            y=h["TargetWeight"].tolist(),
            marker_color="#f0a500",
        ))
        fig.update_layout(
            barmode="group",
            xaxis_title="Ticker",
            yaxis_title="Weight (%)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(t=20),
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Add TargetWeight values for your holdings to see this chart.")

st.divider()

# ── Add / Edit holding form ───────────────────────────────────────────────────

st.subheader("➕ Add / Update Holding")
with st.expander("Open form", expanded=False):
    with st.form("add_holding_form"):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            ticker = st.text_input("Ticker *", placeholder="e.g. RELIANCE or 120503 for MF")
            name = st.text_input("Name", placeholder="e.g. Reliance Industries")
        with fc2:
            asset_class = st.selectbox("Asset Class *", ["EQUITY", "ETF", "MF", "FD"])
            qty = st.number_input("Quantity *", min_value=0.0, step=1.0)
        with fc3:
            avg_buy_price = st.number_input("Avg Buy Price ₹ *", min_value=0.0, step=0.01)
            target_weight = st.number_input("Target Weight %", min_value=0.0, max_value=100.0, step=0.1)

        submitted = st.form_submit_button("Save Holding", width="stretch")
        if submitted:
            if not ticker or qty == 0 or avg_buy_price == 0:
                st.error("Ticker, Quantity, and Avg Buy Price are required.")
            else:
                try:
                    from core.sheets import SheetsClient
                    current_price = avg_buy_price  # Will be updated on next price refresh
                    value = qty * current_price
                    SheetsClient().upsert_holding({
                        "Ticker": ticker.strip().upper(),
                        "Name": name,
                        "AssetClass": asset_class,
                        "Qty": qty,
                        "AvgBuyPrice": avg_buy_price,
                        "CurrentPrice": current_price,
                        "Value": round(value, 2),
                        "TargetWeight": target_weight,
                        "CurrentWeight": 0,
                    })
                    st.success(f"Saved {ticker.upper()}. Click Refresh Prices to update current value.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Save failed: {exc}")

# ── Delete holding ────────────────────────────────────────────────────────────

if not holdings.empty:
    st.subheader("🗑️ Remove Holding")
    with st.expander("Open form", expanded=False):
        tickers_list = holdings["Ticker"].tolist()
        del_ticker = st.selectbox("Select ticker to remove", tickers_list)
        if st.button("Remove Holding", type="secondary"):
            try:
                from core.sheets import SheetsClient
                SheetsClient().delete_holding(del_ticker)
                st.success(f"Removed {del_ticker}.")
                st.cache_data.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"Delete failed: {exc}")