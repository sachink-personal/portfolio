"""
Fundamental data fetcher via yfinance.
Fetches ROE, Debt-to-Equity, and EPS acceleration for a list of NSE tickers.
Only called for the technical shortlist (~20-50 stocks) not the full 500.
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import yfinance as yf

import config

log = logging.getLogger(__name__)


def _nse(ticker: str) -> str:
    t = ticker.strip().upper()
    return t if t.endswith(".NS") else t + ".NS"


def get_fundamentals(tickers: list[str]) -> pd.DataFrame:
    """
    Fetch ROE, D/E ratio and EPS acceleration flag for each ticker.

    Returns DataFrame with columns:
        Ticker, ROE, DE, EPSAccelerating
    Rows where data is completely unavailable are still included
    (with NaN values) so the caller can decide how to handle them.
    """
    rows = []
    for ticker in tickers:
        row = {
            "Ticker": ticker,
            "ROE": None,
            "DE": None,
            "EPSAccelerating": None,
        }
        try:
            t = yf.Ticker(_nse(ticker))
            info = t.info or {}

            # ── ROE ──────────────────────────────────────────────────────────
            roe_raw = info.get("returnOnEquity")
            if roe_raw is not None:
                # yfinance returns as decimal (0.15 = 15%)
                row["ROE"] = round(float(roe_raw) * 100, 2)

            # ── Debt-to-Equity ────────────────────────────────────────────────
            de_raw = info.get("debtToEquity")
            if de_raw is not None:
                # yfinance returns D/E as a percentage in some versions (150 = 1.5x)
                # Normalise to ratio
                de_val = float(de_raw)
                row["DE"] = round(de_val / 100 if de_val > 10 else de_val, 3)

            # ── EPS Acceleration ──────────────────────────────────────────────
            row["EPSAccelerating"] = _check_eps_acceleration(t)

        except Exception as exc:
            log.warning("Fundamentals fetch failed for %s: %s", ticker, exc)

        rows.append(row)

    df = pd.DataFrame(rows)
    return df


def _check_eps_acceleration(ticker_obj: yf.Ticker) -> Optional[bool]:
    """
    Check if EPS is accelerating over two consecutive quarters.

    Logic:
        Q_n > Q_{n-1}  (latest quarter beat the one before)
        Q_{n-1} > Q_{n-2}  (the one before also beat the one before that)

    Returns True/False, or None if data is unavailable.
    """
    try:
        qf = ticker_obj.quarterly_income_stmt
        if qf is None or qf.empty:
            return None

        # Look for EPS row (label varies by data source)
        eps_labels = [
            "Basic EPS", "Diluted EPS", "EPS", "Earnings Per Share",
            "Basic Earnings Per Share", "Diluted Earnings Per Share",
        ]
        eps_row = None
        for label in eps_labels:
            if label in qf.index:
                eps_row = qf.loc[label]
                break

        if eps_row is None:
            # Compute from Net Income / Shares
            if "Net Income" in qf.index:
                ni = qf.loc["Net Income"]
                info = ticker_obj.info or {}
                shares = info.get("sharesOutstanding")
                if shares and shares > 0:
                    eps_row = ni / shares
            if eps_row is None:
                return None

        # Sort columns by date descending (most recent first)
        eps_sorted = eps_row.sort_index(ascending=False).dropna()
        if len(eps_sorted) < 3:
            return None

        q0 = float(eps_sorted.iloc[0])  # Most recent
        q1 = float(eps_sorted.iloc[1])  # One quarter back
        q2 = float(eps_sorted.iloc[2])  # Two quarters back

        return bool(q0 > q1 > q2)

    except Exception as exc:
        log.debug("EPS acceleration check failed: %s", exc)
        return None


def apply_quality_filter(
    df: pd.DataFrame,
    roe_min: float = None,
    de_max: float = None,
    require_eps_acceleration: bool = True,
) -> pd.DataFrame:
    """
    Filter a fundamentals DataFrame against quality thresholds.
    NaN values in ROE or DE are treated as failing the filter.

    Args:
        df: Output of get_fundamentals()
        roe_min: Minimum ROE %. Defaults to config.ROE_MIN.
        de_max: Maximum D/E ratio. Defaults to config.DE_MAX.
        require_eps_acceleration: If True, filter out non-accelerating EPS.
                                   If EPSAccelerating is None (data unavailable),
                                   the stock is kept (benefit of the doubt).
    """
    roe_min = roe_min if roe_min is not None else config.ROE_MIN
    de_max = de_max if de_max is not None else config.DE_MAX

    mask = pd.Series([True] * len(df), index=df.index)

    # ROE filter — skip row if NaN (no data = fail)
    if "ROE" in df.columns:
        mask &= df["ROE"].notna() & (df["ROE"] > roe_min)

    # D/E filter — skip row if NaN
    if "DE" in df.columns:
        mask &= df["DE"].notna() & (df["DE"] < de_max)

    # EPS acceleration — None (no data) is treated as passing
    if require_eps_acceleration and "EPSAccelerating" in df.columns:
        mask &= df["EPSAccelerating"].isna() | (df["EPSAccelerating"] == True)

    return df[mask].reset_index(drop=True)
