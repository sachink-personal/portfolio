"""
SQLite database client — replaces Google Sheets for portfolio data persistence.
Uses SQLAlchemy ORM for clean, portable access to all four tables:
  Holdings, Ledger, Signals, MarketHistory
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import config

log = logging.getLogger(__name__)

# ── Engine & Session ───────────────────────────────────────────────────────────

def get_engine(db_path: Optional[str] = None) -> object:
    """Return a SQLAlchemy engine for the SQLite database."""
    path = db_path or config.DB_PATH
    url = f"sqlite:///{path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    return engine

def get_session(db_path: Optional[str] = None):
    """Return a new SQLAlchemy session bound to the portfolio database."""
    engine = get_engine(db_path)
    Session = sessionmaker(bind=engine)
    return Session()

# ── Schema Initialisation ──────────────────────────────────────────────────────

def initialize_database(db_path: Optional[str] = None) -> None:
    """
    Create all required tables with correct columns if they do not already exist.
    Safe to call multiple times — existing tables are left untouched.
    """
    session = get_session(db_path)
    try:
        create_tables(session)
        log.info("Database initialised at %s", config.DB_PATH)
    finally:
        session.close()

def create_tables(session):
    """Execute CREATE TABLE IF NOT EXISTS for all four tables."""
    statements = [
        # Holdings
        text("""
            CREATE TABLE IF NOT EXISTS Holdings (
                Ticker TEXT PRIMARY KEY,
                Name TEXT,
                AssetClass TEXT,
                Qty REAL DEFAULT 0,
                AvgBuyPrice REAL DEFAULT 0,
                CurrentPrice REAL DEFAULT 0,
                Value REAL DEFAULT 0,
                TargetWeight REAL DEFAULT 0,
                CurrentWeight REAL DEFAULT 0
            )
        """),
        # Ledger
        text("""
            CREATE TABLE IF NOT EXISTS Ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Date TEXT,
                Ticker TEXT,
                AssetClass TEXT,
                Action TEXT,
                Qty REAL DEFAULT 0,
                ExecPrice REAL DEFAULT 0,
                TotalValue REAL DEFAULT 0,
                Charges REAL DEFAULT 0
            )
        """),
        # Signals
        text("""
            CREATE TABLE IF NOT EXISTS Signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Date TEXT,
                Ticker TEXT,
                Strategy TEXT,
                ROC_6M REAL DEFAULT 0,
                RSI_Weekly REAL DEFAULT 0,
                ROE REAL DEFAULT 0,
                Sector TEXT
            )
        """),
        # MarketHistory
        text("""
            CREATE TABLE IF NOT EXISTS MarketHistory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Date TEXT,
                PortfolioValue REAL DEFAULT 0,
                Nifty500Close REAL DEFAULT 0,
                Nifty500_200DMA REAL DEFAULT 0,
                PE_Ratio REAL,
                BreadthPct REAL
            )
        """),
    ]
    for stmt in statements:
        session.execute(stmt)
    session.commit()

# ── Holdings ───────────────────────────────────────────────────────────────────

def get_holdings(db_path: Optional[str] = None) -> pd.DataFrame:
    """Return the Holdings table as a DataFrame."""
    session = get_session(db_path)
    try:
        df = pd.read_sql_table("Holdings", session.bind)
        return df if not df.empty else pd.DataFrame(columns=[
            "Ticker", "Name", "AssetClass", "Qty", "AvgBuyPrice",
            "CurrentPrice", "Value", "TargetWeight", "CurrentWeight"
        ])
    finally:
        session.close()

def update_holdings_prices(price_map: dict[str, float], db_path: Optional[str] = None) -> None:
    """
    Update CurrentPrice for matching tickers and recalculate Value and CurrentWeight.
    """
    session = get_session(db_path)
    try:
        # Update prices
        for ticker, price in price_map.items():
            if price == 0.0:
                continue
            session.execute(
                text("UPDATE Holdings SET CurrentPrice = :price WHERE Ticker = :ticker"),
                {"price": price, "ticker": ticker},
            )

        # Recalculate Value = Qty * CurrentPrice
        session.execute(text("UPDATE Holdings SET Value = Qty * CurrentPrice"))

        # Recalculate CurrentWeight
        result = session.execute(text("SELECT SUM(Value) FROM Holdings")).scalar()
        total = float(result or 0.0)
        if total > 0:
            session.execute(
                text("UPDATE Holdings SET CurrentWeight = ROUND((Value / :total) * 100, 2)"),
                {"total": total},
            )

        session.commit()
    finally:
        session.close()

def upsert_holding(holding: dict, db_path: Optional[str] = None) -> None:
    """Add a new holding row, or update an existing one matched by Ticker."""
    session = get_session(db_path)
    try:
        existing = session.execute(
            text("SELECT 1 FROM Holdings WHERE Ticker = :ticker"),
            {"ticker": holding.get("Ticker", "")},
        ).scalar()

        if existing:
            # Update
            cols = []
            vals = {}
            for col in ("Name", "AssetClass", "Qty", "AvgBuyPrice", "CurrentPrice", "Value", "TargetWeight", "CurrentWeight"):
                if col in holding:
                    cols.append(f"{col} = :{col}")
                    vals[col] = holding[col]
            if cols:
                vals["ticker"] = holding["Ticker"]
                session.execute(
                    text(f"UPDATE Holdings SET {', '.join(cols)} WHERE Ticker = :ticker"),
                    vals,
                )
        else:
            # Insert
            session.execute(
                text("""INSERT INTO Holdings (Ticker, Name, AssetClass, Qty, AvgBuyPrice, CurrentPrice, Value, TargetWeight, CurrentWeight)
                        VALUES (:Ticker, :Name, :AssetClass, :Qty, :AvgBuyPrice, :CurrentPrice, :Value, :TargetWeight, :CurrentWeight)"""),
                {
                    "Ticker": holding.get("Ticker", ""),
                    "Name": holding.get("Name", ""),
                    "AssetClass": holding.get("AssetClass", ""),
                    "Qty": float(holding.get("Qty", 0)),
                    "AvgBuyPrice": float(holding.get("AvgBuyPrice", 0)),
                    "CurrentPrice": float(holding.get("CurrentPrice", 0)),
                    "Value": float(holding.get("Value", 0)),
                    "TargetWeight": float(holding.get("TargetWeight", 0)),
                    "CurrentWeight": float(holding.get("CurrentWeight", 0)),
                },
            )

        session.commit()
    finally:
        session.close()

def delete_holding(ticker: str, db_path: Optional[str] = None) -> None:
    """Remove a holding row by Ticker."""
    session = get_session(db_path)
    try:
        session.execute(
            text("DELETE FROM Holdings WHERE Ticker = :ticker"),
            {"ticker": ticker},
        )
        session.commit()
    finally:
        session.close()

# ── Ledger ─────────────────────────────────────────────────────────────────────

def get_ledger(db_path: Optional[str] = None) -> pd.DataFrame:
    """Return the Ledger table as a DataFrame with Date parsed."""
    session = get_session(db_path)
    try:
        df = pd.read_sql_table("Ledger", session.bind)
        if not df.empty and "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        return df
    finally:
        session.close()

def append_ledger(row: dict, db_path: Optional[str] = None) -> None:
    """Append a single transaction row to the Ledger table."""
    session = get_session(db_path)
    try:
        session.execute(
            text("""INSERT INTO Ledger (Date, Ticker, AssetClass, Action, Qty, ExecPrice, TotalValue, Charges)
                    VALUES (:Date, :Ticker, :AssetClass, :Action, :Qty, :ExecPrice, :TotalValue, :Charges)"""),
            {
                "Date": row.get("Date", ""),
                "Ticker": row.get("Ticker", ""),
                "AssetClass": row.get("AssetClass", ""),
                "Action": row.get("Action", ""),
                "Qty": float(row.get("Qty", 0)),
                "ExecPrice": float(row.get("ExecPrice", 0)),
                "TotalValue": float(row.get("TotalValue", 0)),
                "Charges": float(row.get("Charges", 0)),
            },
        )
        session.commit()
    finally:
        session.close()

def bulk_insert_ledger(rows: list[dict], db_path: Optional[str] = None) -> None:
    """Bulk-insert multiple ledger rows efficiently."""
    if not rows:
        return
    session = get_session(db_path)
    try:
        for row in rows:
            session.execute(
                text("""INSERT INTO Ledger (Date, Ticker, AssetClass, Action, Qty, ExecPrice, TotalValue, Charges)
                        VALUES (:Date, :Ticker, :AssetClass, :Action, :Qty, :ExecPrice, :TotalValue, :Charges)"""),
                {
                    "Date": row.get("Date", ""),
                    "Ticker": row.get("Ticker", ""),
                    "AssetClass": row.get("AssetClass", ""),
                    "Action": row.get("Action", ""),
                    "Qty": float(row.get("Qty", 0)),
                    "ExecPrice": float(row.get("ExecPrice", 0)),
                    "TotalValue": float(row.get("TotalValue", 0)),
                    "Charges": float(row.get("Charges", 0)),
                },
            )
        session.commit()
    finally:
        session.close()

# ── Signals ────────────────────────────────────────────────────────────────────

def get_signals(db_path: Optional[str] = None) -> pd.DataFrame:
    """Return the Signals table as a DataFrame."""
    session = get_session(db_path)
    try:
        df = pd.read_sql_table("Signals", session.bind)
        return df
    finally:
        session.close()

def clear_signals(db_path: Optional[str] = None) -> None:
    """Clear all signal rows."""
    session = get_session(db_path)
    try:
        session.execute(text("DELETE FROM Signals"))
        session.commit()
    finally:
        session.close()

def append_signal(row: dict, db_path: Optional[str] = None) -> None:
    """Append a single signal row."""
    session = get_session(db_path)
    try:
        session.execute(
            text("""INSERT INTO Signals (Date, Ticker, Strategy, ROC_6M, RSI_Weekly, ROE, Sector)
                    VALUES (:Date, :Ticker, :Strategy, :ROC_6M, :RSI_Weekly, :ROE, :Sector)"""),
            {
                "Date": row.get("Date", ""),
                "Ticker": row.get("Ticker", ""),
                "Strategy": row.get("Strategy", ""),
                "ROC_6M": float(row.get("ROC_6M", 0)),
                "RSI_Weekly": float(row.get("RSI_Weekly", 0)),
                "ROE": float(row.get("ROE", 0)),
                "Sector": row.get("Sector", ""),
            },
        )
        session.commit()
    finally:
        session.close()

def bulk_insert_signals(rows: list[dict], db_path: Optional[str] = None) -> None:
    """Bulk-insert multiple signal rows efficiently."""
    if not rows:
        return
    session = get_session(db_path)
    try:
        for row in rows:
            session.execute(
                text("""INSERT INTO Signals (Date, Ticker, Strategy, ROC_6M, RSI_Weekly, ROE, Sector)
                        VALUES (:Date, :Ticker, :Strategy, :ROC_6M, :RSI_Weekly, :ROE, :Sector)"""),
                {
                    "Date": row.get("Date", ""),
                    "Ticker": row.get("Ticker", ""),
                    "Strategy": row.get("Strategy", ""),
                    "ROC_6M": float(row.get("ROC_6M", 0)),
                    "RSI_Weekly": float(row.get("RSI_Weekly", 0)),
                    "ROE": float(row.get("ROE", 0)),
                    "Sector": row.get("Sector", ""),
                },
            )
        session.commit()
    finally:
        session.close()

# ── Market History ─────────────────────────────────────────────────────────────

def get_market_history(db_path: Optional[str] = None) -> pd.DataFrame:
    """Return the MarketHistory table sorted by date ascending."""
    session = get_session(db_path)
    try:
        df = pd.read_sql_table("MarketHistory", session.bind)
        if not df.empty and "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        return df
    finally:
        session.close()

def append_market_history(snapshot: dict, db_path: Optional[str] = None) -> None:
    """Append one daily snapshot row to the MarketHistory table."""
    session = get_session(db_path)
    try:
        session.execute(
            text("""INSERT INTO MarketHistory (Date, PortfolioValue, Nifty500Close, Nifty500_200DMA, PE_Ratio, BreadthPct)
                    VALUES (:Date, :PortfolioValue, :Nifty500Close, :Nifty500_200DMA, :PE_Ratio, :BreadthPct)"""),
            {
                "Date": snapshot.get("Date", ""),
                "PortfolioValue": float(snapshot.get("PortfolioValue", 0)),
                "Nifty500Close": float(snapshot.get("Nifty500Close", 0)),
                "Nifty500_200DMA": float(snapshot.get("Nifty500_200DMA", 0)),
                "PE_Ratio": float(snapshot["PE_Ratio"]) if snapshot.get("PE_Ratio") else None,
                "BreadthPct": float(snapshot["BreadthPct"]) if snapshot.get("BreadthPct") else None,
            },
        )
        session.commit()
    finally:
        session.close()

# ── Backward-compatible SheetsClient wrapper ───────────────────────────────────
# This class mirrors the old SheetsClient API so all existing imports continue to work.

class SheetsClient:
    """
    Drop-in replacement for the Google Sheets client.
    All methods have the same signature as before but operate on SQLite instead.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or config.DB_PATH

    # ── Sheet Initialisation ──────────────────────────────────────────────────

    def initialize_sheet_structure(self) -> None:
        """Create all required tables with correct columns if they do not already exist."""
        initialize_database(self._db_path)

    # ── Holdings ──────────────────────────────────────────────────────────────

    def get_holdings(self) -> pd.DataFrame:
        return get_holdings(self._db_path)

    def update_holdings_prices(self, price_map: dict[str, float]) -> None:
        update_holdings_prices(price_map, self._db_path)

    def upsert_holding(self, holding: dict) -> None:
        upsert_holding(holding, self._db_path)

    def delete_holding(self, ticker: str) -> None:
        delete_holding(ticker, self._db_path)

    # ── Ledger ────────────────────────────────────────────────────────────────

    def get_ledger(self) -> pd.DataFrame:
        return get_ledger(self._db_path)

    def append_ledger(self, row: dict) -> None:
        append_ledger(row, self._db_path)

    # ── Signals ───────────────────────────────────────────────────────────────

    def get_signals(self) -> pd.DataFrame:
        return get_signals(self._db_path)

    def clear_signals(self) -> None:
        clear_signals(self._db_path)

    # ── Market History ────────────────────────────────────────────────────────

    def get_market_history(self) -> pd.DataFrame:
        return get_market_history(self._db_path)

    def append_market_history(self, snapshot: dict) -> None:
        append_market_history(snapshot, self._db_path)