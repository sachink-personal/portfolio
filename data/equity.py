"""
Equity and ETF price data via yfinance.
NSE stocks use the .NS suffix (e.g. RELIANCE → RELIANCE.NS).
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)


def _nse_ticker(ticker: str) -> str:
    """Ensure .NS suffix for NSE-listed instruments."""
    t = ticker.strip().upper()
    if not t.endswith(".NS") and not t.endswith(".BO") and not t.startswith("^"):
        t += ".NS"
    return t


def get_current_prices(tickers: list[str]) -> dict[str, float]:
    """
    Fetch the latest close price for a list of NSE tickers.
    Returns {original_ticker: price}. Missing tickers map to 0.0.
    """
    if not tickers:
        return {}

    nse_map: dict[str, str] = {_nse_ticker(t): t for t in tickers}
    nse_tickers = list(nse_map.keys())

    try:
        raw = yf.download(
            nse_tickers,
            period="2d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        # Normalise multi/single-ticker structure
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"]
        else:
            close = raw[["Close"]].rename(columns={"Close": nse_tickers[0]})

        result: dict[str, float] = {}
        for nse_t, orig_t in nse_map.items():
            try:
                price = float(close[nse_t].dropna().iloc[-1])
            except Exception:
                price = 0.0
                log.warning("Price not available for %s", nse_t)
            result[orig_t] = price
        return result

    except Exception as exc:
        log.error("yfinance batch download failed: %s", exc)
        return {t: 0.0 for t in tickers}


def get_historical_ohlcv(ticker: str, period: str = "1y") -> pd.DataFrame:
    """
    Download full OHLCV history for a single NSE ticker.

    Args:
        ticker: NSE ticker (with or without .NS suffix).
        period: yfinance period string — '3mo', '6mo', '1y', '2y', etc.

    Returns:
        DataFrame with DatetimeIndex and columns [Open, High, Low, Close, Volume].
    """
    t = _nse_ticker(ticker)
    try:
        df = yf.download(t, period=period, auto_adjust=True, progress=False)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as exc:
        log.error("Historical fetch failed for %s: %s", ticker, exc)
        return pd.DataFrame()


def get_nifty500_history(period: str = "1y") -> pd.DataFrame:
    """Download Nifty 50 index history (^NSEI) used for 200-DMA regime calculation.
    Note: ^CNX500 (Nifty 500) is not available on yfinance; Nifty 50 is used as proxy."""
    import config
    return get_historical_ohlcv(config.NIFTY500_TICKER, period=period)


def get_nifty50_history(period: str = "2y") -> pd.DataFrame:
    """Download Nifty 50 index history (^NSEI) — used as benchmark."""
    try:
        df = yf.download("^NSEI", period=period, auto_adjust=True, progress=False)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as exc:
        log.error("Nifty 50 fetch failed: %s", exc)
        return pd.DataFrame()
