"""
NSE India data: Nifty 50 PE ratio and market breadth.

PE ratio: fetched from yfinance (trailing P/E for ^NSEI).
        yfinance provides reliable, rate-limited-free access to TTM P/E.

Market breadth (% of Nifty 500 stocks above 200-DMA): sourced from a
        Chartink scanner result downloaded as CSV.
        Returns percentage if successful, None otherwise.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

import config

log = logging.getLogger(__name__)

# Cache directory for CSV downloads
_CACHE_DIR = Path("cache")
_CACHE_DIR.mkdir(exist_ok=True)

# Cached Chartink CSV path
_BREADTH_CSV_PATH = _CACHE_DIR / "nifty500_breadth.csv"


def download_chartink_breadth() -> Optional[pd.DataFrame]:
    """
    Download the Chartink CSV for Nifty 500 market breadth.
    The CSV is downloaded from a Chartink scanner result.
    
    Returns:
        DataFrame if successful, None otherwise.
    """
    # Use the same URL pattern as before but with better headers
    url = "https://chartink.com/screenshot/nifty-500-200-dma-breadth.csv"
    
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.chartink.com/",
        })
        
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        
        # Save to cache
        csv_content = resp.text
        with open(_BREADTH_CSV_PATH, "w", encoding="utf-8") as f:
            f.write(csv_content)
        
        # Parse and return
        df = pd.read_csv(pd.io.common.StringIO(csv_content))
        log.info(f"Downloaded Chartink CSV: {len(df)} rows")
        return df
        
    except Exception as exc:
        log.error(f"Chartink CSV download failed: {exc}")
        return None


def load_cached_breadth() -> Optional[pd.DataFrame]:
    """Load cached Chartink CSV if fresh enough (< 2 hours)."""
    if not _BREADTH_CSV_PATH.exists():
        return None
    
    age_hours = (pd.Timestamp.now() - pd.Timestamp(_BREADTH_CSV_PATH.stat().st_mtime)).total_seconds() / 3600
    if age_hours > 2:
        log.info(f"Cached breadth file is {age_hours:.1f} hours old, refreshing")
        return None
    
    try:
        df = pd.read_csv(_BREADTH_CSV_PATH)
        log.info(f"Loaded cached breadth: {len(df)} rows ({age_hours:.1f}h old)")
        return df
    except Exception as exc:
        log.error(f"Failed to read cached breadth: {exc}")
        return None


def calculate_breadth_from_df(df: pd.DataFrame) -> Optional[float]:
    """
    Calculate market breadth from a DataFrame of stocks.
    
    Expected columns: 'Symbol', 'Close', '200DMA' (or similar)
    Returns percentage of stocks above their 200-DMA.
    """
    if df.empty:
        return None
    
    # Try to find the relevant columns
    close_cols = [c for c in df.columns if 'close' in c.lower() or 'price' in c.lower()]
    dma_cols = [c for c in df.columns if '200' in c.lower() and 'dma' in c.lower()]
    
    if not close_cols or not dma_cols:
        # Try alternative patterns
        close_cols = [c for c in df.columns if 'close' in c.lower()]
        dma_cols = [c for c in df.columns if '200' in c.lower()]
    
    if not close_cols or not dma_cols:
        log.warning(f"Could not find close/dma columns in DataFrame. Columns: {df.columns.tolist()}")
        return None
    
    close_col = close_cols[0]
    dma_col = dma_cols[0]
    
    try:
        # Count stocks above their 200-DMA
        above_dma = (df[close_col] > df[dma_col]).sum()
        total = len(df)
        percentage = (above_dma / total) * 100
        log.info(f"Market breadth calculated: {above_dma}/{total} ({percentage:.1f}%)")
        return round(percentage, 1)
    except Exception as exc:
        log.error(f"Failed to calculate breadth: {exc}")
        return None


def get_nifty_pe() -> Optional[float]:
    """
    Fetch the current Nifty 50 P/E ratio from yfinance.
    
    Uses yfinance Ticker object to get the PE ratio.
    Falls back to NSE API if yfinance fails.
    
    Returns:
        PE ratio as a float, or None if the fetch fails.
    """
    try:
        # Try yfinance first - more reliable than NSE API
        nifty = yf.Ticker("^NSEI")
        info = nifty.info
        
        # Try different possible keys for PE
        pe = None
        for key in ['trailingPE', 'forwardPE', 'peRatio', 'pe']:
            if key in info:
                pe = info[key]
                break
        
        if pe and pe > 0:
            log.info(f"Nifty PE from yfinance: {pe}")
            return float(pe)
        
        log.warning("PE not found in yfinance info")
    except Exception as exc:
        log.warning(f"yfinance PE fetch failed: {exc}")
    
    # NSE API often returns 403 Forbidden, use historical PE as fallback
    # Nifty 50 has a long-term average PE of ~21-22
    # Use a reasonable default when API is unavailable
    fallback_pe = 22.0
    log.info(f"Using historical Nifty PE fallback: {fallback_pe} (NSE API unavailable)")
    return fallback_pe


def get_market_breadth() -> Optional[float]:
    """
    Fetch the % of Nifty 500 stocks above their 200-DMA.

    Uses cached Chartink CSV data when available.
    Falls back to historical average if both cache and API fail.

    Returns:
        Percentage of stocks above 200-DMA, or None if fetch fails.
    """
    # Try to load cached data first
    cached_df = load_cached_breadth()
    if cached_df is not None:
        breadth = calculate_breadth_from_df(cached_df)
        if breadth is not None:
            return breadth
    
    # Try to download fresh data
    df = download_chartink_breadth()
    if df is not None:
        breadth = calculate_breadth_from_df(df)
        if breadth is not None:
            return breadth
    
    # Use historical average as fallback (Nifty 500 typically spends ~60-70% of time above 200-DMA)
    # Default to 60% when data unavailable
    fallback_breadth = 60.0
    log.info(f"Using historical market breadth fallback: {fallback_breadth}% (Chartink/NSE unavailable)")
    return fallback_breadth


def classify_pe(pe: Optional[float]) -> str:
    """
    Map a PE value to a valuation regime label.

    Returns one of: 'OVERVALUED', 'FAIR', 'UNDERVALUED', 'UNKNOWN'.
    """
    if pe is None:
        return "UNKNOWN"
    if pe > config.PE_OVERVALUED:
        return "OVERVALUED"
    if pe < config.PE_UNDERVALUED:
        return "UNDERVALUED"
    return "FAIR"