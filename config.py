"""
Central configuration — all numeric thresholds live here.
Edit this file to tune the strategy; no changes needed in the engine modules.

Data persistence: SQLite database (no Google Sheets dependency).
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH: str = os.getenv("DB_PATH", "portfolio.db")

# ── Email ─────────────────────────────────────────────────────────────────────
EMAIL_SENDER: str = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT: str = os.getenv("EMAIL_RECIPIENT", os.getenv("EMAIL_SENDER", ""))

# ── Market Tickers ────────────────────────────────────────────────────────────
# Note: ^CNX500 (Nifty 500) is unavailable on yfinance; ^NSEI (Nifty 50) used
NIFTY500_TICKER: str = "^NSEI"    # Nifty 50 — reliable proxy for 200-DMA regime
NIFTY50_TICKER: str = "^NSEI"     # Benchmark for growth chart comparison

# ── 200-DMA Regime ────────────────────────────────────────────────────────────
DMA_WINDOW: int = 200
EQUITY_ALLOC_BULLISH: float = 0.90   # 90% equity allowed in a bull market
EQUITY_ALLOC_BEARISH: float = 0.50   # 50% cap in a bear market

# ── Nifty PE Bands ────────────────────────────────────────────────────────────
PE_OVERVALUED: float = 24.0
PE_FAIR_HIGH: float = 22.0
PE_FAIR_LOW: float = 18.0
PE_UNDERVALUED: float = 16.0

# ── Market Breadth ────────────────────────────────────────────────────────────
# Paste the % of Nifty 500 stocks above 200-DMA from Chartink into the sidebar
BREADTH_WARNING_THRESHOLD: float = 50.0

# ── Signal Filters ────────────────────────────────────────────────────────────
ROC_MIN: float = 20.0        # 6-month Rate of Change minimum (%)
RSI_BUY_LOW: float = 60.0   # Weekly RSI buy zone lower bound
RSI_BUY_HIGH: float = 75.0  # Weekly RSI buy zone upper bound
RSI_SELL: float = 40.0      # Weekly RSI mandatory exit trigger
ROE_MIN: float = 15.0       # Return on Equity minimum (%)
DE_MAX: float = 0.5         # Max Debt-to-Equity (pre-filtered via Screener.in)

# ── Position Sizing ───────────────────────────────────────────────────────────
MAX_POSITION_WEIGHT: float = 0.15   # Max single stock weight (15%)
MIN_POSITION_WEIGHT: float = 0.03   # Min meaningful position (3%)
MAX_HOLDINGS: int = 15              # Max equity holdings at any time

# ── Scheduler Times (runs in IST = UTC+5:30) ─────────────────────────────────
DAILY_JOB_HOUR_IST: int = 8       # 8:00 AM
DAILY_JOB_MINUTE_IST: int = 0
WEEKLY_JOB_DAY: str = "sat"
WEEKLY_JOB_HOUR_IST: int = 9      # 9:00 AM
WEEKLY_JOB_MINUTE_IST: int = 0

# ── NSE India API ─────────────────────────────────────────────────────────────
NSE_ALL_INDICES_URL: str = "https://www.nseindia.com/api/allIndices"
NSE_HEADERS: dict = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "X-Requested-With": "XMLHttpRequest",
}

# ── MF API ────────────────────────────────────────────────────────────────────
MFAPI_BASE: str = "https://api.mfapi.in/mf"

# ── Screening Mode ────────────────────────────────────────────────────────────
# "tickertape" : reads the latest CSV from downloads/ folder (recommended)
# "yfinance"   : fully automatic but fundamentals less reliable for small caps
SCREEN_MODE: str = os.getenv("SCREEN_MODE", "tickertape")

# Folder where Tickertape CSV is dropped
TICKERTAPE_DOWNLOADS_DIR: str = "downloads"

# ── Google Sheets Tab Names ───────────────────────────────────────────────────
TAB_HOLDINGS: str = "Holdings"
TAB_LEDGER: str = "Ledger"
TAB_SIGNALS: str = "Signals"
TAB_MARKET_HISTORY: str = "MarketHistory"


# ── Database Helper Functions ─────────────────────────────────────────────────

def initialize_db() -> None:
    """Initialise the SQLite database (create tables if they don't exist)."""
    from core.database import initialize_database
    initialize_database()
