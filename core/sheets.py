"""
Google Sheets client — reads and writes all four portfolio tabs via gspread.
Uses a Service Account credential file (credentials.json) for authentication.

How to set up:
1. Go to console.cloud.google.com → New Project → Enable Google Sheets API.
2. IAM & Admin → Service Accounts → Create → Download JSON key → save as credentials.json.
3. Open your Google Sheet → Share → paste the service account email → Editor role.
4. Copy the Sheet ID from the URL and set GOOGLE_SHEET_ID in .env.
"""
from __future__ import annotations

import logging
from typing import Optional

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

import config

log = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


class SheetsClient:
    """
    Thread-safe wrapper around gspread for all portfolio sheet operations.
    Connection is established lazily on the first call.
    """

    def __init__(
        self,
        sheet_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ) -> None:
        self._sheet_id = sheet_id or config.SHEET_ID
        self._creds_path = credentials_path or config.CREDENTIALS_PATH
        self._spreadsheet: Optional[gspread.Spreadsheet] = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _connect(self) -> gspread.Spreadsheet:
        if self._spreadsheet is None:
            creds = Credentials.from_service_account_file(self._creds_path, scopes=_SCOPES)
            gc = gspread.authorize(creds)
            self._spreadsheet = gc.open_by_key(self._sheet_id)
            log.info("Connected to Google Sheet: %s", self._sheet_id)
        return self._spreadsheet

    def _ws(self, name: str) -> gspread.Worksheet:
        return self._connect().worksheet(name)

    @staticmethod
    def _to_df(records: list[dict], numeric_cols: list[str]) -> pd.DataFrame:
        df = pd.DataFrame(records)
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        return df

    # ── Sheet Initialisation ──────────────────────────────────────────────────

    def initialize_sheet_structure(self) -> None:
        """
        Create all required tabs with header rows if they do not already exist.
        Safe to call multiple times — existing tabs are left untouched.
        """
        sheet = self._connect()
        existing_titles = [ws.title for ws in sheet.worksheets()]
        tabs = {
            config.TAB_HOLDINGS: [
                "Ticker", "Name", "AssetClass", "Qty",
                "AvgBuyPrice", "CurrentPrice", "Value",
                "TargetWeight", "CurrentWeight",
            ],
            config.TAB_LEDGER: [
                "Date", "Ticker", "AssetClass", "Action",
                "Qty", "ExecPrice", "TotalValue", "Charges",
            ],
            config.TAB_SIGNALS: [
                "Date", "Ticker", "Strategy",
                "ROC_6M", "RSI_Weekly", "ROE", "Sector",
            ],
            config.TAB_MARKET_HISTORY: [
                "Date", "PortfolioValue", "Nifty500Close",
                "Nifty500_200DMA", "PE_Ratio", "BreadthPct",
            ],
        }
        for tab_name, headers in tabs.items():
            if tab_name not in existing_titles:
                ws = sheet.add_worksheet(title=tab_name, rows=1000, cols=len(headers))
                ws.append_row(headers)
                log.info("Created tab: %s", tab_name)
            else:
                log.info("Tab already exists, skipped: %s", tab_name)

    # ── Holdings ──────────────────────────────────────────────────────────────

    def get_holdings(self) -> pd.DataFrame:
        """Return the Holdings tab as a DataFrame."""
        ws = self._ws(config.TAB_HOLDINGS)
        return self._to_df(
            ws.get_all_records(),
            ["Qty", "AvgBuyPrice", "CurrentPrice", "Value", "TargetWeight", "CurrentWeight"],
        )

    def update_holdings_prices(self, price_map: dict[str, float]) -> None:
        """
        Write fetched prices into the Holdings sheet and recalculate
        Value and CurrentWeight columns in-place.
        """
        ws = self._ws(config.TAB_HOLDINGS)
        df = self.get_holdings()
        if df.empty:
            return

        headers = ws.row_values(1)
        col_idx = {name: i + 1 for i, name in enumerate(headers)}

        for idx, row in df.iterrows():
            ticker = str(row.get("Ticker", "")).strip()
            if ticker not in price_map or price_map[ticker] == 0.0:
                continue
            df.at[idx, "CurrentPrice"] = price_map[ticker]

        df["Value"] = df["Qty"] * df["CurrentPrice"]
        total = df["Value"].sum()
        df["CurrentWeight"] = (df["Value"] / total * 100).round(2) if total > 0 else 0.0

        updates = []
        for idx, row in df.iterrows():
            row_num = idx + 2  # +1 for header, +1 for 1-indexing
            for col_name in ("CurrentPrice", "Value", "CurrentWeight"):
                if col_name in col_idx:
                    updates.append({
                        "range": gspread.utils.rowcol_to_a1(row_num, col_idx[col_name]),
                        "values": [[row[col_name]]],
                    })

        if updates:
            ws.batch_update(updates)

    def upsert_holding(self, holding: dict) -> None:
        """Add a new holding row, or update an existing one matched by Ticker."""
        ws = self._ws(config.TAB_HOLDINGS)
        headers = ws.row_values(1)
        df = self.get_holdings()
        tickers = df["Ticker"].tolist() if "Ticker" in df.columns else []

        if holding.get("Ticker") in tickers:
            row_num = tickers.index(holding["Ticker"]) + 2
            for i, header in enumerate(headers):
                if header in holding:
                    ws.update_cell(row_num, i + 1, holding[header])
        else:
            ws.append_row([holding.get(h, "") for h in headers])

    def delete_holding(self, ticker: str) -> None:
        """Remove a holding row by Ticker."""
        ws = self._ws(config.TAB_HOLDINGS)
        df = self.get_holdings()
        if "Ticker" not in df.columns:
            return
        tickers = df["Ticker"].tolist()
        if ticker in tickers:
            ws.delete_rows(tickers.index(ticker) + 2)

    # ── Ledger ────────────────────────────────────────────────────────────────

    def get_ledger(self) -> pd.DataFrame:
        """Return the Ledger tab as a DataFrame with Date parsed."""
        ws = self._ws(config.TAB_LEDGER)
        df = self._to_df(
            ws.get_all_records(),
            ["Qty", "ExecPrice", "TotalValue", "Charges"],
        )
        if not df.empty and "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        return df

    def append_ledger(self, row: dict) -> None:
        """Append a single transaction row to the Ledger tab."""
        ws = self._ws(config.TAB_LEDGER)
        headers = ws.row_values(1)
        ws.append_row([row.get(h, "") for h in headers])

    # ── Signals ───────────────────────────────────────────────────────────────

    def get_signals(self) -> pd.DataFrame:
        """Return the Signals tab as a DataFrame."""
        ws = self._ws(config.TAB_SIGNALS)
        return self._to_df(
            ws.get_all_records(),
            ["ROC_6M", "RSI_Weekly", "ROE"],
        )

    def clear_signals(self) -> None:
        """Clear all signal rows while preserving the header row."""
        ws = self._ws(config.TAB_SIGNALS)
        headers = ws.row_values(1)
        ws.clear()
        ws.append_row(headers)

    # ── Market History ────────────────────────────────────────────────────────

    def get_market_history(self) -> pd.DataFrame:
        """Return the MarketHistory tab sorted by date ascending."""
        ws = self._ws(config.TAB_MARKET_HISTORY)
        df = self._to_df(
            ws.get_all_records(),
            ["PortfolioValue", "Nifty500Close", "Nifty500_200DMA", "PE_Ratio", "BreadthPct"],
        )
        if not df.empty and "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        return df

    def append_market_history(self, snapshot: dict) -> None:
        """Append one daily snapshot row to the MarketHistory tab."""
        ws = self._ws(config.TAB_MARKET_HISTORY)
        headers = ws.row_values(1)
        ws.append_row([snapshot.get(h, "") for h in headers])
