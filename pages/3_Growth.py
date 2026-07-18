"""
Page 3 — Growth
Portfolio NAV chart vs Nifty 500 benchmark, date-range selector, and returns table.
Both series are normalised to 100 on the start date for direct comparison.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Growth", page_icon="📈", layout="wide")
st.title("📈 Portfolio Growth")


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def load_history():
    from core.sheets import SheetsClient
    return SheetsClient().get_market_history()


@st.cache_data(ttl=600)
def load_nifty50(period: str = "5y"):
    from data.equity import get_nifty50_history
    return get_nifty50_history(period=period)


# ── Sidebar controls ──────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("⚙️ Chart Settings")
    period_label = st.radio(
        "Date Range",
        ["1 Month", "3 Months", "6 Months", "1 Year", "All Time"],
        index=3,
    )
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

period_days_map = {
    "1 Month": 30,
    "3 Months": 90,
    "6 Months": 180,
    "1 Year": 365,
    "All Time": None,
}
period_days = period_days_map[period_label]

# ── Load ──────────────────────────────────────────────────────────────────────

try:
    history = load_history()
    nifty50_raw = load_nifty50()
except Exception as exc:
    st.error(f"Data load failed: {exc}")
    st.stop()

if history.empty or "Date" not in history.columns or "PortfolioValue" not in history.columns:
    st.info(
        "No portfolio history yet. The daily scheduler records a snapshot each morning. "
        "Run `python main.py --daily` to record today's snapshot, "
        "or let the scheduler run for a few days.\n\n"
        "Make sure you have holdings in your database first."
    )
    st.stop()

# ── Filter by date range ──────────────────────────────────────────────────────

history = history.dropna(subset=["Date", "PortfolioValue"])
history = history[history["PortfolioValue"] > 0].copy()

if period_days:
    cutoff = pd.Timestamp(date.today() - timedelta(days=period_days))
    history = history[history["Date"] >= cutoff]

if history.empty:
    st.warning(f"No history available for the selected period ({period_label}).")
    st.stop()

# ── Normalise both series to 100 from start ───────────────────────────────────

start_date = history["Date"].min()
end_date = history["Date"].max()

portfolio_series = history.set_index("Date")["PortfolioValue"]
portfolio_norm = portfolio_series / portfolio_series.iloc[0] * 100

# Nifty 50 — align to same date range
nifty_norm = None
if not nifty50_raw.empty:
    nifty50 = nifty50_raw["Close"].copy()
    nifty50.index = pd.to_datetime(nifty50.index)
    nifty50 = nifty50[(nifty50.index >= start_date) & (nifty50.index <= end_date)]
    if not nifty50.empty:
        nifty_norm = nifty50 / nifty50.iloc[0] * 100

# ── Chart ─────────────────────────────────────────────────────────────────────

fig = go.Figure()

fig.add_trace(go.Scatter(
    x=portfolio_norm.index,
    y=portfolio_norm.values,
    mode="lines",
    name="My Portfolio",
    line=dict(color="#4a90e2", width=2.5),
    hovertemplate="%{x|%d %b %Y}<br>Portfolio: %{y:.1f}<extra></extra>",
))

if nifty_norm is not None:
    fig.add_trace(go.Scatter(
        x=nifty_norm.index,
        y=nifty_norm.values,
        mode="lines",
        name="Nifty 50 (benchmark)",
        line=dict(color="#f0a500", width=1.5, dash="dash"),
        hovertemplate="%{x|%d %b %Y}<br>Nifty 50: %{y:.1f}<extra></extra>",
    ))

fig.add_hline(y=100, line_dash="dot", line_color="gray", opacity=0.5)
fig.update_layout(
    title=f"Normalised Growth ({period_label}, base = 100)",
    xaxis_title="Date",
    yaxis_title="Normalised Value",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    margin=dict(t=50, b=20),
)
st.plotly_chart(fig, use_container_width=True)

# ── Returns table ─────────────────────────────────────────────────────────────

st.subheader("📋 Returns Summary")


def calc_return(series: pd.Series, days: int) -> str | float:
    """Return % gain over the last `days` days, or 'N/A'."""
    cutoff = pd.Timestamp(date.today() - timedelta(days=days))
    subset = series[series.index >= cutoff]
    if len(subset) < 2:
        return "N/A"
    return round((subset.iloc[-1] / subset.iloc[0] - 1) * 100, 2)


periods = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}
rows = []
for label, days in periods.items():
    p_ret = calc_return(portfolio_series, days)
    n_ret = calc_return(nifty50_raw["Close"] if not nifty50_raw.empty else pd.Series(dtype=float), days)
    alpha = (
        round(float(p_ret) - float(n_ret), 2)
        if isinstance(p_ret, (int, float)) and isinstance(n_ret, (int, float))
        else "N/A"
    )
    rows.append({
        "Period": label,
        "Portfolio": f"{p_ret}%" if isinstance(p_ret, (int, float)) else p_ret,
        "Nifty 50": f"{n_ret}%" if isinstance(n_ret, (int, float)) else n_ret,
        "Alpha": f"{alpha}%" if isinstance(alpha, (int, float)) else alpha,
    })

returns_df = pd.DataFrame(rows)
st.dataframe(returns_df, use_container_width=True, hide_index=True)

# ── Portfolio value over time (absolute) ──────────────────────────────────────

st.subheader("💰 Portfolio Value Over Time")
fig2 = go.Figure()
fig2.add_trace(go.Scatter(
    x=portfolio_series.index,
    y=portfolio_series.values,
    mode="lines",
    fill="tozeroy",
    line=dict(color="#4a90e2"),
    hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.0f}<extra></extra>",
))
fig2.update_layout(
    xaxis_title="Date",
    yaxis_title="Portfolio Value (₹)",
    yaxis_tickformat=",.0f",
    margin=dict(t=10, b=20),
)
st.plotly_chart(fig2, use_container_width=True)
