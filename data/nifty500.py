"""
Nifty 500 constituent list from NSE India.
Downloads the official CSV, caches it locally for 7 days.
Returns list of {ticker, sector} dicts ready for yfinance (.NS suffix added).
"""
from __future__ import annotations

import io
import json
import logging
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

log = logging.getLogger(__name__)

_CACHE_FILE = Path("cache/nifty500.json")
_CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days

_NSE_CSV_URL = (
    "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
)
_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nseindia.com/",
    "Accept": "text/html,application/xhtml+xml,*/*",
}


def get_nifty500_universe() -> list[dict]:
    """
    Return the Nifty 500 universe as a list of dicts:
        [{"ticker": "RELIANCE", "sector": "Energy"}, ...]

    Tries the NSE CSV first. Raises exception if download fails—caller
    must handle and display error to user.
    """
    # ── Serve from cache if fresh ────────────────────────────────────────────
    if _CACHE_FILE.exists():
        age = time.time() - _CACHE_FILE.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            try:
                with open(_CACHE_FILE, encoding="utf-8") as fh:
                    data = json.load(fh)
                log.info("Nifty 500 list loaded from cache (%d stocks).", len(data))
                return data
            except Exception:
                pass  # Cache corrupt — re-download

    # ── Download from NSE ─────────────────────────────────────────────────────
    try:
        resp = requests.get(_NSE_CSV_URL, headers=_NSE_HEADERS, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))

        # NSE CSV column names vary slightly — normalise
        df.columns = [c.strip() for c in df.columns]
        symbol_col = next(
            (c for c in df.columns if "symbol" in c.lower()), None
        )
        sector_col = next(
            (c for c in df.columns if "industry" in c.lower() or "sector" in c.lower()), None
        )
        series_col = next(
            (c for c in df.columns if "series" in c.lower()), None
        )
        company_col = next(
            (c for c in df.columns if "company" in c.lower() or "name" in c.lower()), None
        )

        if symbol_col is None:
            raise ValueError(f"Symbol column not found. Columns: {df.columns.tolist()}")

        # Keep only EQ series (exclude derivatives, ETFs in index)
        if series_col:
            df = df[df[series_col].astype(str).str.strip() == "EQ"]

        result = []
        for _, row in df.iterrows():
            ticker = str(row[symbol_col]).strip().upper()
            sector = str(row[sector_col]).strip() if sector_col else ""
            company_name = str(row[company_col]).strip() if company_col else ""
            if ticker:
                result.append({
                    "ticker": ticker,
                    "sector": sector,
                    "company_name": company_name
                })

        log.info("Nifty 500 downloaded from NSE: %d stocks.", len(result))
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(result, fh)
        return result

    except Exception as exc:
        # ⚠️ NO FALLBACK — raise exception so caller can handle properly
        log.error("Nifty 500 download failed: %s", exc)
        raise RuntimeError(
            f"Unable to download Nifty 500 list from NSE. "
            f"Error: {exc}. "
            f"Please check your internet connection and try again."
        )


def get_nifty500_tickers() -> list[str]:
    """Return just the ticker symbols (without .NS suffix)."""
    return [item["ticker"] for item in get_nifty500_universe()]


def get_sector_map() -> dict[str, str]:
    """Return {ticker: sector} mapping."""
    return {item["ticker"]: item["sector"] for item in get_nifty500_universe()}
