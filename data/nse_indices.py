"""
NSE India data: Nifty 50 PE ratio and market breadth.

PE ratio: fetched from NSE's public allIndices JSON endpoint.
          NSE blocks direct API calls without a session cookie — the module
          primes a session by visiting the homepage first.
          If the fetch fails, the caller receives None and the UI shows
          a manual-input fallback.

Market breadth (% of Nifty 500 stocks above 200-DMA): sourced from a
          Chartink scanner result.  The user pastes the number once a week
          via the sidebar — this module only classifies the stored value.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

import config

log = logging.getLogger(__name__)


def _build_nse_session() -> requests.Session:
    """
    Create a requests Session that mimics a browser visit to NSE India.
    NSE requires cookies set by the homepage before any API call succeeds.
    """
    session = requests.Session()
    session.headers.update(config.NSE_HEADERS)
    try:
        session.get("https://www.nseindia.com", timeout=10)
    except Exception:
        pass  # Proceed anyway; cookies may still be empty
    return session


def get_nifty_pe() -> Optional[float]:
    """
    Fetch the current Nifty 50 P/E ratio from NSE India's allIndices API.

    Returns:
        PE ratio as a float, or None if the request fails.
    """
    try:
        session = _build_nse_session()
        resp = session.get(config.NSE_ALL_INDICES_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for index in data.get("data", []):
            if index.get("indexSymbol") == "NIFTY 50":
                raw_pe = index.get("pe")
                if raw_pe:
                    return float(raw_pe)
        log.warning("NIFTY 50 entry not found in NSE allIndices response.")
        return None
    except Exception as exc:
        log.error("NSE PE fetch failed: %s", exc)
        return None


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
