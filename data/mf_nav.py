"""
Mutual Fund NAV fetcher via mfapi.in — free, no authentication required.
AMFI scheme codes can be looked up at: https://api.mfapi.in/mf
"""
from __future__ import annotations

import logging

import pandas as pd
import requests

import config

log = logging.getLogger(__name__)


def get_mf_nav(scheme_code: str | int) -> float:
    """
    Fetch the latest NAV for a mutual fund scheme.

    Args:
        scheme_code: AMFI numeric scheme code (e.g. 120503 for SBI Blue Chip Fund).
                     Store this as the 'Ticker' value in the Holdings sheet for MF rows.

    Returns:
        Latest NAV as a float, or 0.0 on failure.
    """
    try:
        url = f"{config.MFAPI_BASE}/{scheme_code}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        nav = float(data["data"][0]["nav"])
        return nav
    except Exception as exc:
        log.error("MF NAV fetch failed for scheme %s: %s", scheme_code, exc)
        return 0.0


def get_mf_nav_history(scheme_code: str | int) -> pd.DataFrame:
    """
    Fetch full NAV history for an MF scheme.

    Returns:
        DataFrame with columns ['date', 'nav'] sorted oldest → newest.
    """
    try:
        url = f"{config.MFAPI_BASE}/{scheme_code}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rows = list(reversed(data.get("data", [])))
        df = pd.DataFrame(rows)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
            df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
            df = df.dropna().sort_values("date").reset_index(drop=True)
        return df
    except Exception as exc:
        log.error("MF history fetch failed for scheme %s: %s", scheme_code, exc)
        return pd.DataFrame()


def get_mf_prices(holdings_df: pd.DataFrame) -> dict[str, float]:
    """
    Fetch current NAV for all MF rows in a holdings DataFrame.

    The 'Ticker' column for MF rows must contain the AMFI scheme code.
    Returns {ticker_value: nav_float}.
    """
    result: dict[str, float] = {}
    if holdings_df.empty or "AssetClass" not in holdings_df.columns:
        return result

    mf_rows = holdings_df[holdings_df["AssetClass"].str.upper() == "MF"]
    for _, row in mf_rows.iterrows():
        scheme_code = str(row.get("Ticker", "")).strip()
        if scheme_code:
            result[row["Ticker"]] = get_mf_nav(scheme_code)

    return result
