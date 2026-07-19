"""
Tickertape CSV parser — reads the exported screener CSV and maps columns
to the Signals sheet schema.

Tickertape screen to create (save it for reuse):
  1. ROE            > 15%
  2. Debt to Equity < 0.5
  3. RSI (14, Weekly) between 60 and 75
  4. 6 Month Return > 20%

Export → place the file anywhere → tool auto-detects it in downloads/ folder.

Column names vary slightly by export version — this parser handles all known variants.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import io

log = logging.getLogger(__name__)

# Folder where the user drops the Tickertape CSV download
DOWNLOADS_FOLDER = Path("downloads")

# ── Column name aliases (Tickertape changes these occasionally) ──────────────

_TICKER_ALIASES = [
    "Ticker", "Symbol", "NSE Symbol", "Stock Symbol", "NSE Code",
    "Scrip", "Script", "Nse Symbol",
]
_NAME_ALIASES = ["Name", "Company", "Company Name", "Stock", "Stock Name"]
_ROE_ALIASES = [
    "Return on Equity", "ROE %", "ROE", "Return On Equity %", "ROE (%)",
]
_DE_ALIASES = [
    "Debt to Equity", "Debt / Equity", "Debt/Equity", "D/E",
    "Debt To Equity", "D/E Ratio",
]
_RSI_ALIASES = [
    "RSI \u2013 14D",   # Tickertape uses en-dash: RSI – 14D
    "RSI - 14D",        # regular hyphen variant
    "RSI (14)", "RSI(14)", "RSI", "Weekly RSI", "RSI 14",
    "RSI (14, Weekly)", "Rsi(14)",
]
_RETURN_ALIASES = [
    "6M Return",                   # Tickertape exact name
    "6M Return %", "6 Month Return", "6 Month Return %",
    "Price Return (6M)", "6M Price Return", "6 Month Price Return %",
    "Return 6M", "6mo Return",
]
_SECTOR_ALIASES = [
    "Sub-Sector", "Sector", "Industry",   # Tickertape uses Sub-Sector
    "Sector Name", "Industry Name",
]


def _norm(s: str) -> str:
    """Normalise a column name: lowercase, collapse whitespace, unify dashes."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s)   # decompose unicode (en/em dash → -)
    s = s.lower().strip()
    s = re.sub(r"[-\u2013\u2014\u2212]", "-", s)  # all dash variants → -
    s = re.sub(r"\s+", " ", s)
    return s


def _find_col(df: pd.DataFrame, aliases: list[str]) -> Optional[str]:
    """Return the first alias that matches a column in the DataFrame.
    Tries exact match first, then normalised match."""
    # Exact match
    for alias in aliases:
        if alias in df.columns:
            return alias
    # Normalised match
    norm_map = {_norm(c): c for c in df.columns}
    for alias in aliases:
        if _norm(alias) in norm_map:
            return norm_map[_norm(alias)]
    return None


def _latest_csv(folder: Path) -> Optional[Path]:
    """Return the most recently modified CSV in the downloads folder."""
    csvs = sorted(folder.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return csvs[0] if csvs else None


def parse_tickertape_csv_from_bytes(csv_bytes: bytes) -> pd.DataFrame:
    """
    Parse a Tickertape screener CSV export from bytes (e.g., uploaded file).
    
    Args:
        csv_bytes: Raw CSV content bytes from file upload.
    
    Returns:
        DataFrame with columns: [Ticker, Name, ROE, DE, RSI_Weekly, ROC_6M, Sector]
    """
    # Read from bytes
    df = pd.read_csv(io.BytesIO(csv_bytes), thousands=",")
    
    if df.empty:
        raise ValueError("CSV is empty.")
    
    df.columns = [c.strip() for c in df.columns]
    
    # Map columns (same as parse_tickertape_csv)
    ticker_col  = _find_col(df, _TICKER_ALIASES)
    name_col    = _find_col(df, _NAME_ALIASES)
    roe_col     = _find_col(df, _ROE_ALIASES)
    de_col      = _find_col(df, _DE_ALIASES)
    rsi_col     = _find_col(df, _RSI_ALIASES)
    return_col  = _find_col(df, _RETURN_ALIASES)
    sector_col  = _find_col(df, _SECTOR_ALIASES)
    
    if ticker_col is None:
        raise ValueError(
            f"Ticker column not found. Available columns: {df.columns.tolist()}\n"
            "Expected one of: " + ", ".join(_TICKER_ALIASES)
        )
    
    log.info(
        "Column mapping — Ticker:%s Name:%s ROE:%s D/E:%s RSI:%s 6MReturn:%s Sector:%s",
        ticker_col, name_col, roe_col, de_col, rsi_col, return_col, sector_col,
    )
    
    # Build result (same as parse_tickertape_csv)
    result = pd.DataFrame()
    result["Ticker"] = df[ticker_col].astype(str).str.strip().str.upper()
    result["Name"]   = df[name_col].astype(str).str.strip() if name_col else ""
    result["Sector"] = df[sector_col].astype(str).str.strip() if sector_col else ""
    
    def _to_float(series: Optional[pd.Series]) -> pd.Series:
        if series is None:
            return pd.Series([None] * len(result))
        # Strip %, commas, spaces
        cleaned = series.astype(str).str.replace(r"[%,\s]", "", regex=True)
        return pd.to_numeric(cleaned, errors="coerce")
    
    result["ROE"]        = _to_float(df[roe_col] if roe_col else None)
    result["DE"]         = _to_float(df[de_col] if de_col else None)
    result["RSI_Weekly"] = _to_float(df[rsi_col] if rsi_col else None)
    result["ROC_6M"]     = _to_float(df[return_col] if return_col else None)
    
    # Drop rows without a valid ticker
    result = result[result["Ticker"].str.len() > 0].reset_index(drop=True)
    
    log.info(
        "Tickertape CSV parsed (from upload): %d stocks. "
        "ROE available: %d, RSI: %d, ROC: %d",
        len(result),
        result["ROE"].notna().sum(),
        result["RSI_Weekly"].notna().sum(),
        result["ROC_6M"].notna().sum(),
    )
    return result


def get_tickertape_signals_from_bytes(csv_bytes: bytes) -> pd.DataFrame:
    """
    Full pipeline from uploaded bytes:
      1. Parse Tickertape CSV from bytes
      2. Check EPS acceleration via yfinance
      3. Return final approved DataFrame
    
    Args:
        csv_bytes: Raw CSV content bytes from file upload.
    
    Returns:
        DataFrame in Signals sheet format with Date, Ticker, Strategy, ROC_6M, RSI_Weekly, ROE, Sector
    """
    from datetime import date
    from data.fundamentals import get_fundamentals
    
    df = parse_tickertape_csv_from_bytes(csv_bytes)
    if df.empty:
        return pd.DataFrame()
    
    tickers = df["Ticker"].tolist()
    log.info("Checking EPS acceleration for %d Tickertape candidates (from upload)...", len(tickers))
    
    fund_df = get_fundamentals(tickers)[["Ticker", "EPSAccelerating"]]
    df = df.merge(fund_df, on="Ticker", how="left")
    
    # Keep stocks where EPS is accelerating OR data unavailable (benefit of doubt)
    approved = df[
        df["EPSAccelerating"].isna() | (df["EPSAccelerating"] == True)
    ].copy()
    
    today = date.today().isoformat()
    approved.insert(0, "Date", today)
    approved.insert(2, "Strategy", "TICKERTAPE_UPLOAD")
    
    # Final column order matching Signals sheet
    signal_cols = ["Date", "Ticker", "Strategy", "ROC_6M", "RSI_Weekly", "ROE", "Sector"]
    approved = approved[[c for c in signal_cols if c in approved.columns]]
    approved = approved.sort_values("ROC_6M", ascending=False).reset_index(drop=True)
    
    log.info(
        "Tickertape upload pipeline complete: %d -> %d approved after EPS check.",
        len(df), len(approved),
    )
    return approved


def parse_tickertape_csv(csv_path: Optional[Path] = None) -> pd.DataFrame:
    """
    Parse a Tickertape screener CSV export.

    Args:
        csv_path: Path to the CSV file. If None, auto-detects the latest
                  CSV in the downloads/ folder.

    Returns:
        DataFrame with columns: [Ticker, Name, ROE, DE, RSI_Weekly, ROC_6M, Sector]
        Ready to be passed to EPS-acceleration check and then written to Signals sheet.
    """
    # ── Locate file ───────────────────────────────────────────────────────────
    if csv_path is None:
        DOWNLOADS_FOLDER.mkdir(exist_ok=True)
        csv_path = _latest_csv(DOWNLOADS_FOLDER)
        if csv_path is None:
            raise FileNotFoundError(
                f"No CSV found in '{DOWNLOADS_FOLDER}/'. "
                "Export your Tickertape screen and drop the file there."
            )
    log.info("Parsing Tickertape CSV: %s", csv_path)

    # ── Read ──────────────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(csv_path, thousands=",")
    except Exception as exc:
        raise ValueError(f"Could not read CSV: {exc}") from exc

    if df.empty:
        raise ValueError("CSV is empty.")

    df.columns = [c.strip() for c in df.columns]

    # ── Map columns ───────────────────────────────────────────────────────────
    ticker_col  = _find_col(df, _TICKER_ALIASES)
    name_col    = _find_col(df, _NAME_ALIASES)
    roe_col     = _find_col(df, _ROE_ALIASES)
    de_col      = _find_col(df, _DE_ALIASES)
    rsi_col     = _find_col(df, _RSI_ALIASES)
    return_col  = _find_col(df, _RETURN_ALIASES)
    sector_col  = _find_col(df, _SECTOR_ALIASES)

    if ticker_col is None:
        raise ValueError(
            f"Ticker column not found. Available columns: {df.columns.tolist()}\n"
            "Expected one of: " + ", ".join(_TICKER_ALIASES)
        )

    log.info(
        "Column mapping — Ticker:%s Name:%s ROE:%s D/E:%s RSI:%s 6MReturn:%s Sector:%s",
        ticker_col, name_col, roe_col, de_col, rsi_col, return_col, sector_col,
    )

    # ── Build result ──────────────────────────────────────────────────────────
    result = pd.DataFrame()
    result["Ticker"] = df[ticker_col].astype(str).str.strip().str.upper()
    result["Name"]   = df[name_col].astype(str).str.strip() if name_col else ""
    result["Sector"] = df[sector_col].astype(str).str.strip() if sector_col else ""

    def _to_float(series: Optional[pd.Series]) -> pd.Series:
        if series is None:
            return pd.Series([None] * len(result))
        # Strip %, commas, spaces
        cleaned = series.astype(str).str.replace(r"[%,\s]", "", regex=True)
        return pd.to_numeric(cleaned, errors="coerce")

    result["ROE"]        = _to_float(df[roe_col] if roe_col else None)
    result["DE"]         = _to_float(df[de_col] if de_col else None)
    result["RSI_Weekly"] = _to_float(df[rsi_col] if rsi_col else None)
    result["ROC_6M"]     = _to_float(df[return_col] if return_col else None)

    # Drop rows without a valid ticker
    result = result[result["Ticker"].str.len() > 0].reset_index(drop=True)

    log.info(
        "Tickertape CSV parsed: %d stocks. "
        "ROE available: %d, RSI: %d, ROC: %d",
        len(result),
        result["ROE"].notna().sum(),
        result["RSI_Weekly"].notna().sum(),
        result["ROC_6M"].notna().sum(),
    )
    return result


def get_tickertape_signals(csv_path: Optional[Path] = None, csv_bytes: Optional[bytes] = None) -> pd.DataFrame:
    """
    Full pipeline:
      1. Parse Tickertape CSV (ROE, D/E, RSI, 6M Return already filtered by screen)
      2. Check EPS acceleration via yfinance for the remaining stocks
      3. Return final approved DataFrame in Signals sheet format

    The Tickertape screen should already have applied:
      ROE > 15%, D/E < 0.5, RSI 60–75, 6M Return > 20%
    So this function only adds the EPS acceleration check on top.
    """
    from datetime import date
    from data.fundamentals import get_fundamentals

    # Handle uploaded file (csv_bytes takes precedence)
    if csv_bytes is not None:
        return get_tickertape_signals_from_bytes(csv_bytes)
    
    # Legacy: read from file path
    df = parse_tickertape_csv(csv_path)
    if df.empty:
        return pd.DataFrame()

    tickers = df["Ticker"].tolist()
    log.info("Checking EPS acceleration for %d Tickertape candidates…", len(tickers))

    fund_df = get_fundamentals(tickers)[["Ticker", "EPSAccelerating"]]
    df = df.merge(fund_df, on="Ticker", how="left")

    # Keep stocks where EPS is accelerating OR data unavailable (benefit of doubt)
    approved = df[
        df["EPSAccelerating"].isna() | (df["EPSAccelerating"] == True)
    ].copy()

    today = date.today().isoformat()
    approved.insert(0, "Date", today)
    approved.insert(2, "Strategy", "TICKERTAPE")

    # Final column order matching Signals sheet
    signal_cols = ["Date", "Ticker", "Strategy", "ROC_6M", "RSI_Weekly", "ROE", "Sector"]
    approved = approved[[c for c in signal_cols if c in approved.columns]]
    approved = approved.sort_values("ROC_6M", ascending=False).reset_index(drop=True)

    log.info(
        "Tickertape pipeline complete: %d → %d approved after EPS check.",
        len(df), len(approved),
    )
    return approved
