"""
Sector Relative Rotation Graph (RRG) computation using NSE sectoral indices.
Downloads weekly price history for each sector index, computes RS-Ratio and
RS-Momentum against the Nifty 500 benchmark, and classifies into the four
RRG quadrants: Leading, Weakening, Lagging, Improving.

No manual input needed — runs fully automatically via yfinance.
"""
from __future__ import annotations

import logging

import pandas as pd
import numpy as np
import yfinance as yf

log = logging.getLogger(__name__)

# ── NSE Sectoral ETF tickers (yfinance-verified working symbols) ─────────────
# Using NSE-listed sectoral ETFs as proxies for sector indices.
# Benchmark: NIFTYBEES.NS (Nifty 50 ETF)
SECTOR_TICKERS: dict[str, str] = {
    "Banking":   "BANKBEES.NS",
    "IT":        "ITBEES.NS",
    "Pharma":    "PHARMABEES.NS",
    "PSU Bank":  "PSUBNKBEES.NS",
    "Auto":      "AUTOBEES.NS",
    "FMCG":      "FMCGIETF.NS",
    "Metal":     "METALIETF.NS",
    "Energy":    "CPSEETF.NS",
    "Infra":     "INFRABEES.NS",
    "Finance":   "FINIETF.NS",
}

BENCHMARK_TICKER = "NIFTYBEES.NS"   # Nifty 50 ETF — reliable on yfinance

# RRG smoothing parameters
_RS_RATIO_WINDOW  = 10   # weeks — smoothing window for RS-Ratio
_RS_MOM_WINDOW    = 4    # weeks — lookback for momentum calculation


def _close_series(ticker: str, period: str) -> pd.Series:
    """Download weekly close prices for a single ticker as a clean Series."""
    raw = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if raw.empty:
        return pd.Series(dtype=float)
    close = raw["Close"]
    # yfinance >=0.2 sometimes returns a single-column DataFrame — squeeze to Series
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index)
    return close.resample("W").last().dropna()


def compute_sector_rrg(period: str = "1y") -> pd.DataFrame:
    """
    Compute RRG values for all NSE sectors.

    Returns DataFrame with columns:
        Sector, RS_Ratio, RS_Momentum, Quadrant, Ticker
    Rows are sorted by quadrant priority: Leading → Improving → Weakening → Lagging.
    """
    # ── Download benchmark ────────────────────────────────────────────────────
    try:
        bench_weekly = _close_series(BENCHMARK_TICKER, period)
        if bench_weekly.empty:
            log.error("Benchmark data unavailable.")
            return pd.DataFrame()
    except Exception as exc:
        log.error("Benchmark download failed: %s", exc)
        return pd.DataFrame()

    rows = []
    for sector_name, ticker in SECTOR_TICKERS.items():
        try:
            sector_weekly = _close_series(ticker, period)

            # Align both series to common dates
            common = bench_weekly.index.intersection(sector_weekly.index)
            if len(common) < 20:
                continue

            bench  = bench_weekly.loc[common]
            sector = sector_weekly.loc[common]

            # ── RS (relative strength) = sector / benchmark, normalised to 100 ──
            rs = (sector / bench) * 100
            rs_norm = rs / rs.mean() * 100  # centre around 100

            # ── RS-Ratio: smoothed RS (EMA) ───────────────────────────────────
            rs_ratio = rs_norm.ewm(span=_RS_RATIO_WINDOW, adjust=False).mean()
            current_ratio = float(rs_ratio.iloc[-1])

            # ── RS-Momentum: recent change in RS-Ratio ────────────────────────
            if len(rs_ratio) < _RS_MOM_WINDOW + 1:
                continue
            rs_momentum_raw = (rs_ratio - rs_ratio.shift(_RS_MOM_WINDOW)) + 100
            current_momentum = float(rs_momentum_raw.iloc[-1])

            # ── Quadrant classification ────────────────────────────────────────
            if current_ratio >= 100 and current_momentum >= 100:
                quadrant = "Leading"
            elif current_ratio >= 100 and current_momentum < 100:
                quadrant = "Weakening"
            elif current_ratio < 100 and current_momentum >= 100:
                quadrant = "Improving"
            else:
                quadrant = "Lagging"

            rows.append({
                "Sector":      sector_name,
                "RS_Ratio":    round(current_ratio, 2),
                "RS_Momentum": round(current_momentum, 2),
                "Quadrant":    quadrant,
                "Ticker":      ticker,
            })

        except Exception as exc:
            log.warning("RRG failed for %s (%s): %s", sector_name, ticker, exc)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    order = {"Leading": 0, "Improving": 1, "Weakening": 2, "Lagging": 3}
    df["_order"] = df["Quadrant"].map(order)
    df = df.sort_values("_order").drop(columns="_order").reset_index(drop=True)
    return df


QUADRANT_META: dict[str, dict] = {
    "Leading":   {"emoji": "🟢", "color": "#d4edda", "desc": "Strong & accelerating — preferred"},
    "Improving": {"emoji": "🔵", "color": "#cce5ff", "desc": "Weak but accelerating — watch closely"},
    "Weakening": {"emoji": "🟡", "color": "#fff3cd", "desc": "Strong but decelerating — reduce exposure"},
    "Lagging":   {"emoji": "🔴", "color": "#f8d7da", "desc": "Weak & decelerating — avoid"},
}


def get_buy_eligible_sectors(rrg_df: pd.DataFrame) -> set[str]:
    """Return sector names in Leading or Improving quadrant (eligible for new buys)."""
    if rrg_df.empty:
        return set()
    return set(
        rrg_df[rrg_df["Quadrant"].isin(["Leading", "Improving"])]["Sector"].tolist()
    )
