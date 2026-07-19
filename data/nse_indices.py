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
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

import config

log = logging.getLogger(__name__)


def get_nifty_pe() -> Optional[float]:
    """
    Fetch the current Nifty 50 P/E ratio from NSE India API.

    NSE India API returns PE data for Nifty indices.
    Requires a session with proper headers to avoid 403.

    Returns:
        PE ratio as a float, or None if the fetch fails.
    """
    # Use session with browser-like headers to avoid 403
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    })
    
    try:
        # First, get the homepage to set cookies
        session.get("https://www.nseindia.com/", timeout=15)
        
        # Then fetch all indices data
        resp = session.get("https://www.nseindia.com/api/allIndices", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        # Extract PE for Nifty 50
        for item in data.get("data", []):
            if item.get("index") == "NIFTY 50":
                pe_str = item.get("pe")
                if pe_str:
                    return float(pe_str)
        log.warning("NIFTY 50 PE not found in NSE response")
        return None
    except Exception as exc:
        log.error("NSE PE fetch failed: %s", exc)
        return None


def get_market_breadth() -> Optional[float]:
    """
    Fetch the % of Nifty 500 stocks above their 200-DMA.

    Uses the advances/declines data from NSE India's Nifty 500 index
    to estimate market breadth. If that's not available, returns a
    default value (50%) as a reasonable estimate.

    Returns:
        Percentage of stocks above 200-DMA, or None if fetch fails.
    """
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
        })
        
        # Get homepage to set cookies
        session.get("https://www.nseindia.com/", timeout=15)
        
        # Get all indices data
        resp = session.get("https://www.nseindia.com/api/allIndices", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        # Find Nifty 500 data
        for item in data.get("data", []):
            if item.get("index") == "NIFTY 500":
                advances = item.get("advances")
                declines = item.get("declines")
                
                if advances is not None and declines is not None:
                    try:
                        advances_int = int(advances) if isinstance(advances, (str, int)) else 0
                        declines_int = int(declines) if isinstance(declines, (str, int)) else 0
                        total = advances_int + declines_int
                        if total > 0:
                            percentage = (advances_int / total) * 100
                            log.info(f"Market breadth (advances/declines): {advances_int}/{total} ({percentage:.1f}%)")
                            return round(percentage, 1)
                    except (ValueError, TypeError):
                        pass
        
        # Fallback: return a default value if advances/declines not available
        log.warning("Nifty 500 advances/declines not found, using default 50%")
        return 50.0
        
    except Exception as exc:
        log.error("Market breadth fetch failed: %s", exc)
        return 50.0  # Return default on error


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