"""
Equity and ETF price data via yfinance.
NSE stocks use the .NS suffix (e.g. RELIANCE → RELIANCE.NS).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

# Retry settings for rate limiting
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 10


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
    
    Implements retry logic for rate limiting errors from yfinance/NSE APIs.
    """
    if not tickers:
        return {}

    nse_map: dict[str, str] = {_nse_ticker(t): t for t in tickers}
    nse_tickers = list(nse_map.keys())

    retry_count = 0
    raw = None
    
    while retry_count <= _MAX_RETRIES:
        try:
            raw = yf.download(
                nse_tickers,
                period="2d",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            break  # Success, exit retry loop
            
        except Exception as exc:
            err_str = str(exc).lower()
            is_rate_limit = any(
                keyword in err_str 
                for keyword in ["rate limit", "too many requests", "429", "throttle"]
            )
            
            if is_rate_limit and retry_count < _MAX_RETRIES:
                retry_count += 1
                wait_time = _RETRY_DELAY_SECONDS * retry_count
                log.warning(
                    "Rate limit hit fetching prices for %d tickers. "
                    "Waiting %ds before retry (attempt %d/%d)",
                    len(nse_tickers), wait_time, retry_count, _MAX_RETRIES
                )
                time.sleep(wait_time)
            else:
                log.error("yfinance batch download failed: %s", exc)
                return {t: 0.0 for t in tickers}

    if raw is None or (isinstance(raw, pd.DataFrame) and raw.empty):
        log.error("No price data downloaded")
        return {t: 0.0 for t in tickers}

    try:
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
        
        # Validate that we have the expected columns
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in required_cols:
            if col not in df.columns:
                log.warning("Missing column '%s' for %s", col, ticker)
        
        # Handle yfinance MultiIndex structure - extract single column DataFrames
        if isinstance(df.columns, pd.MultiIndex):
            # For MultiIndex, columns look like [('Open', 'TICKER'), ('Close', 'TICKER'), ...]
            # We need to extract the actual column value
            new_df = pd.DataFrame(index=df.index)
            for col in required_cols:
                if col in df.columns.get_level_values(0):
                    new_df[col] = df[col].iloc[:, 0] if col in df else None
            df = new_df
        
        return df
    except Exception as exc:
        log.error("Historical fetch failed for %s: %s", ticker, exc)
        return pd.DataFrame()


def get_nifty500_history(period: str = "1y") -> pd.DataFrame:
    """Download Nifty 50 index history (^NSEI) used for 200-DMA regime calculation.
    Note: ^CNX500 (Nifty 500) is not available on yfinance; Nifty 50 is used as proxy.
    
    Returns DataFrame with columns: [Open, High, Low, Close, Volume]
    """
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
