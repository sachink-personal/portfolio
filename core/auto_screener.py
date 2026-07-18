"""
Fully automated screening pipeline.
Replaces the manual Screener.in + Chartink CSV workflow entirely.

Pipeline (runs in ~3-4 minutes):
  1. Load Nifty 500 universe from NSE (cached 7 days)
  2. Batch-download 1-year OHLCV for all ~500 stocks via yfinance
  3. Compute daily ROC(125) → keep stocks with ROC > 20%   (~50-100 remain)
  4. Compute weekly RSI(14) → keep stocks with RSI 60-75   (~15-40 remain)
  5. Fetch fundamentals for shortlist: ROE, D/E, EPS       (~5-15 remain)
  6. Write approved candidates to the signals database
  7. Return the final approved DataFrame

Usage:
    from core.auto_screener import AutoScreener
    result = AutoScreener().run(progress_callback=print)
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Callable, Optional

import numpy as np
import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator

import config
from data.nifty500 import get_nifty500_universe, get_sector_map
from data.fundamentals import get_fundamentals, apply_quality_filter

log = logging.getLogger(__name__)

# Batch size for yfinance downloads (avoids timeout on very large lists)
_DOWNLOAD_BATCH = 100


class AutoScreener:
    """
    Runs the full quantitative screen automatically.
    Accepts an optional progress_callback(message: str) for UI feedback.
    Writes results to the signals database by default.
    """

    def __init__(self, progress_callback: Optional[Callable[[str], None]] = None):
        self._cb = progress_callback or log.info

    def _log(self, msg: str) -> None:
        self._cb(msg)
        log.info(msg)

    # ── Step 1: Universe ──────────────────────────────────────────────────────

    def _load_universe(self) -> tuple[list[str], dict[str, str]]:
        self._log("Step 1/5 — Loading Nifty 500 universe…")
        universe = get_nifty500_universe()
        tickers = [u["ticker"] for u in universe]
        sector_map = {u["ticker"]: u["sector"] for u in universe}
        self._log(f"  Universe: {len(tickers)} stocks")
        return tickers, sector_map

    # ── Step 2: Batch OHLCV download ─────────────────────────────────────────

    def _download_ohlcv(self, tickers: list[str]) -> pd.DataFrame:
        """
        Batch-download 1-year close prices for all tickers.
        Returns a DataFrame where each column is a ticker (NSE symbol).
        """
        self._log(f"Step 2/5 — Downloading 1-year price history for {len(tickers)} stocks…")
        self._log("  This takes ~60-90 seconds. Please wait…")

        nse_tickers = [t + ".NS" for t in tickers]
        all_close = pd.DataFrame()

        for i in range(0, len(nse_tickers), _DOWNLOAD_BATCH):
            batch = nse_tickers[i: i + _DOWNLOAD_BATCH]
            batch_num = i // _DOWNLOAD_BATCH + 1
            total_batches = (len(nse_tickers) + _DOWNLOAD_BATCH - 1) // _DOWNLOAD_BATCH
            self._log(f"  Batch {batch_num}/{total_batches} ({len(batch)} stocks)…")

            try:
                raw = yf.download(
                    batch,
                    period="1y",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                    timeout=60,
                )
                if raw.empty:
                    continue

                if isinstance(raw.columns, pd.MultiIndex):
                    close = raw["Close"]
                else:
                    # Single ticker
                    close = raw[["Close"]].rename(columns={"Close": batch[0]})

                # Strip .NS suffix from column names
                close.columns = [c.replace(".NS", "") for c in close.columns]
                all_close = pd.concat([all_close, close], axis=1)

            except Exception as exc:
                log.error("Batch %d download failed: %s", batch_num, exc)

        self._log(f"  Downloaded data for {all_close.shape[1]} stocks.")
        return all_close

    # ── Step 3: ROC filter ────────────────────────────────────────────────────

    def _filter_by_roc(
        self, close_df: pd.DataFrame, min_roc: float = None
    ) -> tuple[list[str], dict[str, float]]:
        """
        Compute 125-day Rate of Change for all tickers.
        Returns (passing_tickers, {ticker: roc_value}).
        """
        min_roc = min_roc if min_roc is not None else config.ROC_MIN
        self._log(f"Step 3/5 — Computing ROC(125) for {close_df.shape[1]} stocks…")

        roc_map: dict[str, float] = {}
        for ticker in close_df.columns:
            series = close_df[ticker].dropna()
            if len(series) < 126:
                continue
            past_price = float(series.iloc[-126])
            curr_price = float(series.iloc[-1])
            if past_price > 0:
                roc = (curr_price - past_price) / past_price * 100
                roc_map[ticker] = round(roc, 2)

        passing = [t for t, roc in roc_map.items() if roc >= min_roc]
        self._log(
            f"  ROC filter (>{min_roc}%): {len(close_df.columns)} → {len(passing)} stocks"
        )
        return passing, roc_map

    # ── Step 4: Weekly RSI filter ─────────────────────────────────────────────

    def _filter_by_rsi(
        self,
        tickers: list[str],
        close_df: pd.DataFrame,
        rsi_low: float = None,
        rsi_high: float = None,
    ) -> tuple[list[str], dict[str, float]]:
        """
        Compute Weekly RSI(14) for tickers that passed the ROC filter.
        Returns (passing_tickers, {ticker: rsi_value}).
        """
        rsi_low = rsi_low if rsi_low is not None else config.RSI_BUY_LOW
        rsi_high = rsi_high if rsi_high is not None else config.RSI_BUY_HIGH
        self._log(f"Step 4/5 — Computing Weekly RSI(14) for {len(tickers)} stocks…")

        rsi_map: dict[str, float] = {}
        for ticker in tickers:
            if ticker not in close_df.columns:
                continue
            try:
                daily = close_df[ticker].dropna()
                weekly = daily.resample("W").last().dropna()
                if len(weekly) < 15:
                    continue
                rsi_series = RSIIndicator(close=weekly, window=14).rsi().dropna()
                if rsi_series.empty:
                    continue
                rsi_map[ticker] = round(float(rsi_series.iloc[-1]), 2)
            except Exception as exc:
                log.debug("RSI failed for %s: %s", ticker, exc)

        passing = [t for t, rsi in rsi_map.items() if rsi_low <= rsi <= rsi_high]
        self._log(
            f"  RSI filter ({rsi_low}–{rsi_high}): {len(tickers)} → {len(passing)} stocks"
        )
        return passing, rsi_map

    # ── Step 5: Quality (fundamentals) ───────────────────────────────────────

    def _filter_by_fundamentals(
        self, tickers: list[str]
    ) -> pd.DataFrame:
        """
        Fetch ROE, D/E and EPS acceleration for the shortlist.
        Returns a filtered DataFrame of stocks that pass all quality checks.
        """
        self._log(
            f"Step 5/5 — Fetching fundamentals for {len(tickers)} stocks "
            f"(ROE>{config.ROE_MIN}%, D/E<{config.DE_MAX})…"
        )
        fund_df = get_fundamentals(tickers)
        approved = apply_quality_filter(fund_df, require_eps_acceleration=True)
        self._log(
            f"  Quality filter: {len(tickers)} → {len(approved)} stocks approved"
        )
        return approved

    # ── Full pipeline ─────────────────────────────────────────────────────────

    def run(self, write_to_sheets: bool = True) -> pd.DataFrame:
        """
        Execute the full automated screen.

        Args:
            write_to_sheets: If True, clears the signals database and writes results.

        Returns:
            DataFrame with columns matching the signals database schema:
            [Date, Ticker, Strategy, ROC_6M, RSI_Weekly, ROE, Sector]
        """
        self._log("=" * 55)
        self._log("AUTO-SCREENER STARTED")
        self._log("=" * 55)

        # ── 1. Universe ──────────────────────────────────────────────────────
        tickers, sector_map = self._load_universe()

        # ── 2. Download ──────────────────────────────────────────────────────
        close_df = self._download_ohlcv(tickers)
        if close_df.empty:
            self._log("ERROR: No price data downloaded. Check internet connection.")
            return pd.DataFrame()

        close_df.index = pd.to_datetime(close_df.index)

        # ── 3. ROC filter ────────────────────────────────────────────────────
        roc_pass, roc_map = self._filter_by_roc(close_df)
        if not roc_pass:
            self._log("No stocks passed ROC filter. Market may be in a downturn.")
            return pd.DataFrame()

        # ── 4. RSI filter ────────────────────────────────────────────────────
        rsi_pass, rsi_map = self._filter_by_rsi(roc_pass, close_df)
        if not rsi_pass:
            self._log("No stocks passed RSI filter (60–75 zone).")
            return pd.DataFrame()

        # ── 5. Fundamentals ──────────────────────────────────────────────────
        approved_fund = self._filter_by_fundamentals(rsi_pass)

        if approved_fund.empty:
            self._log("No stocks passed quality filter. Try relaxing ROE/D/E thresholds.")
            return pd.DataFrame()

        # ── Build final Signals DataFrame ────────────────────────────────────
        today = date.today().isoformat()
        rows = []
        for _, fund_row in approved_fund.iterrows():
            ticker = fund_row["Ticker"]
            rows.append({
                "Date": today,
                "Ticker": ticker,
                "Strategy": "AUTO",
                "ROC_6M": roc_map.get(ticker, 0),
                "RSI_Weekly": rsi_map.get(ticker, 0),
                "ROE": fund_row.get("ROE") or 0,
                "Sector": sector_map.get(ticker, ""),
            })

        result_df = pd.DataFrame(rows).sort_values("ROC_6M", ascending=False).reset_index(drop=True)

        self._log(f"\n✅ SCREEN COMPLETE — {len(result_df)} candidates approved:")
        for _, r in result_df.iterrows():
            self._log(
                f"  {r['Ticker']:15s}  ROC:{r['ROC_6M']:6.1f}%  "
                f"RSI:{r['RSI_Weekly']:5.1f}  ROE:{r['ROE']:5.1f}%  {r['Sector']}"
            )

        # ── Write to Signals database ────────────────────────────────────────
        if write_to_sheets:
            try:
                from core.database import clear_signals, bulk_insert_signals
                clear_signals()
                signal_rows = []
                for _, row in result_df.iterrows():
                    signal_rows.append({
                        "Date": row.get("Date", ""),
                        "Ticker": row.get("Ticker", ""),
                        "Strategy": row.get("Strategy", ""),
                        "ROC_6M": float(row.get("ROC_6M", 0)),
                        "RSI_Weekly": float(row.get("RSI_Weekly", 0)),
                        "ROE": float(row.get("ROE", 0)),
                        "Sector": row.get("Sector", ""),
                    })
                bulk_insert_signals(signal_rows)
                self._log(f"✅ Signals database updated with {len(result_df)} candidates.")
            except Exception as exc:
                log.error("Failed to write to Signals database: %s", exc)
                self._log(f"⚠️  Signals database write failed: {exc}")

        return result_df
