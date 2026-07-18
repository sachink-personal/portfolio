"""
Page 1 — Dashboard
Portfolio command centre: total value, P&L, XIRR, market regime, and asset breakdown.
"""
from __future__ import annotations

from datetime import date

import plotly.express as px
import streamlit as st

import config

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
st.title("📊 Dashboard")
st.caption(f"Data as of {date.today().strftime('%d %B %Y')}")


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_portfolio_data():
    from core.sheets import SheetsClient
    sheets = SheetsClient()
    return sheets.get_holdings(), sheets.get_market_history(), sheets.get_ledger()


@st.cache_data(ttl=300)
def load_regime(manual_pe: float, manual_breadth: float):
    from core.market_regime import MarketRegime
    return MarketRegime(
        manual_pe=manual_pe if manual_pe > 0 else None,
        manual_breadth=manual_breadth if manual_breadth > 0 else None,
    ).get_full_regime()


def compute_xirr(ledger, portfolio_value: float):
    """Compute XIRR from the Ledger using pyxirr."""
    try:
        from pyxirr import xirr as _xirr
        import pandas as pd

        if ledger.empty or "Date" not in ledger.columns:
            return None

        cash_flows: list[tuple] = []
        for _, row in ledger.iterrows():
            action = str(row.get("Action", "")).upper()
            val = float(row.get("TotalValue", 0))
            dt = row["Date"]
            if hasattr(dt, "date"):
                dt = dt.date()
            if not dt or val == 0:
                continue
            # Buys are cash out (negative), sells are cash in (positive)
            cf = -val if action == "BUY" else val
            cash_flows.append((dt, cf))

        if not cash_flows or portfolio_value == 0:
            return None

        # Final cash-flow = current portfolio value (terminal value)
        cash_flows.append((date.today(), portfolio_value))
        dates = [cf[0] for cf in cash_flows]
        amounts = [cf[1] for cf in cash_flows]
        result = _xirr(dates, amounts)
        return result if result is not None and abs(result) < 10 else None  # Sanity cap
    except Exception:
        return None


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("⚙️ Manual Overrides")
    st.caption("Use when NSE API is blocked or Chartink breadth is ready.")
    manual_pe = st.number_input(
        "Nifty 50 PE (0 = auto-fetch)", min_value=0.0, max_value=60.0, value=0.0, step=0.1
    )
    manual_breadth = st.number_input(
        "Market Breadth % (0 = skip)", min_value=0.0, max_value=100.0, value=0.0, step=0.5
    )
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Load data ─────────────────────────────────────────────────────────────────

try:
    holdings, market_history, ledger = load_portfolio_data()
    regime = load_regime(manual_pe, manual_breadth)
except Exception as exc:
    st.error(f"Failed to load data: {exc}")
    st.info(
        "Check that the database file exists. "
        "Run `python main.py --init` to create the database structure."
    )
    st.stop()

# ── Portfolio metrics ─────────────────────────────────────────────────────────

portfolio_value = float(holdings["Value"].sum()) if not holdings.empty else 0.0
prev_value = portfolio_value
if not market_history.empty and len(market_history) >= 2:
    prev_value = float(market_history.iloc[-2]["PortfolioValue"])

daily_pnl = portfolio_value - prev_value
daily_pnl_pct = (daily_pnl / prev_value * 100) if prev_value > 0 else 0.0
xirr_val = compute_xirr(ledger, portfolio_value)

# ── Metric cards ──────────────────────────────────────────────────────────────

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric(
        "💰 Portfolio Value",
        f"₹{portfolio_value:,.0f}",
        f"₹{daily_pnl:+,.0f} ({daily_pnl_pct:+.2f}%) vs yesterday",
    )
with c2:
    n_holdings = len(holdings) if not holdings.empty else 0
    st.metric("📦 Total Holdings", str(n_holdings))
with c3:
    if xirr_val is not None:
        st.metric("📈 XIRR (Since Inception)", f"{xirr_val * 100:.1f}%")
    else:
        st.metric("📈 XIRR", "Add trades to Ledger")
with c4:
    equity_cap = regime.get("equity_cap", 0.9)
    st.metric("🎯 Equity Allocation Cap", f"{equity_cap * 100:.0f}%")

st.divider()

# ── Market Regime ─────────────────────────────────────────────────────────────

st.subheader("📡 Market Regime")
trend_d = regime.get("trend", {})
val_d = regime.get("valuation", {})
breadth_d = regime.get("breadth", {})

rc1, rc2, rc3 = st.columns(3)

with rc1:
    t = trend_d.get("trend", "UNKNOWN")
    icon = "🟢" if t == "BULLISH" else ("🔴" if t == "BEARISH" else "⚪")
    st.markdown(f"#### {icon} {t}")
    st.caption("Nifty 500 vs 200-Day Moving Average")
    st.write(
        f"Close: **{trend_d.get('close', 0):,.0f}** &nbsp;|&nbsp; "
        f"200-DMA: **{trend_d.get('dma_200', 0):,.0f}**"
    )
    dist = trend_d.get("distance_pct", 0)
    color_str = "green" if dist >= 0 else "red"
    st.markdown(
        f"Distance from 200-DMA: <span style='color:{color_str}'><b>{dist:+.1f}%</b></span>",
        unsafe_allow_html=True,
    )

with rc2:
    v = val_d.get("valuation", "UNKNOWN")
    v_icon = {"OVERVALUED": "🔴", "UNDERVALUED": "🟢", "FAIR": "🟡"}.get(v, "⚪")
    pe = val_d.get("pe")
    pe_str = f"{pe:.1f}" if pe else "N/A (auto-fetch failed — enter manually)"
    st.markdown(f"#### {v_icon} {v}")
    st.caption("Nifty 50 P/E Ratio")
    st.write(f"PE: **{pe_str}**")
    st.write(
        f"Overvalued > {config.PE_OVERVALUED} &nbsp;|&nbsp; "
        f"Undervalued < {config.PE_UNDERVALUED}"
    )

with rc3:
    bpct = breadth_d.get("breadth_pct")
    bstatus = breadth_d.get("status", "UNKNOWN")
    b_icon = "🔴" if breadth_d.get("warning") else ("🟢" if bpct is not None else "⚪")
    st.markdown(f"#### {b_icon} {bstatus}")
    st.caption("Market Breadth (paste from Chartink)")
    bstr = f"{bpct:.1f}%" if bpct is not None else "Not set"
    st.write(f"**{bstr}** of Nifty 500 stocks above 200-DMA")
    if breadth_d.get("warning"):
        st.warning(f"Breadth divergence: below {config.BREADTH_WARNING_THRESHOLD}% threshold")
    elif bpct is None:
        st.caption("Enter breadth % in the sidebar to enable this signal.")

st.divider()

# ── Asset class breakdown ─────────────────────────────────────────────────────

st.subheader("🥧 Asset Class Breakdown")
if (
    not holdings.empty
    and "AssetClass" in holdings.columns
    and "Value" in holdings.columns
):
    breakdown = (
        holdings.groupby("AssetClass")["Value"]
        .sum()
        .reset_index()
        .rename(columns={"AssetClass": "Asset Class"})
    )
    total = breakdown["Value"].sum()
    breakdown["Weight %"] = (breakdown["Value"] / total * 100).round(1)

    chart_col, table_col = st.columns([2, 1])
    with chart_col:
        fig = px.pie(
            breakdown,
            values="Value",
            names="Asset Class",
            color_discrete_sequence=px.colors.qualitative.Set3,
            hole=0.4,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(margin=dict(t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)
    with table_col:
        display = breakdown.copy()
        display["Value"] = display["Value"].apply(lambda x: f"₹{x:,.0f}")
        st.dataframe(display, use_container_width=True, hide_index=True)
else:
    st.info(
        "No holdings found. Use the Portfolio page to add your first position, "
        "or run `python scripts/import_portfolio.py` to import from a backup file."
    )
