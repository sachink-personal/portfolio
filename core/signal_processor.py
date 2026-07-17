"""
Signal Processor — filters raw screener candidates from the Signals sheet
and scans current holdings for mandatory exit triggers.

Inputs come from two external platforms:
  - Chartink.com  : RSI, 6-month ROC, volume breakouts
  - Screener.in   : ROE, Debt-to-Equity (pre-screened before pasting)

The user pastes CSV output from these platforms into the Signals tab monthly.
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from ta.momentum import RSIIndicator

import config
from data.equity import get_historical_ohlcv

log = logging.getLogger(__name__)


class SignalProcessor:
    """
    Applies the three-filter quantitative screen to candidate signals
    and identifies exit triggers in current holdings.
    """

    def __init__(self, signals_df: pd.DataFrame) -> None:
        self.signals = signals_df.copy()

    # ── Entry filters ─────────────────────────────────────────────────────────

    def filter_candidates(self) -> pd.DataFrame:
        """
        Apply entry rules from the spec:
          1. 6-Month ROC > ROC_MIN (20%)
          2. Weekly RSI in [RSI_BUY_LOW, RSI_BUY_HIGH] (60–75)
          3. ROE > ROE_MIN (15%)

        Returns approved candidates sorted by ROC_6M descending.
        Returns an empty DataFrame if no candidates qualify.
        """
        df = self.signals.copy()
        if df.empty:
            log.warning("Signals sheet is empty — paste candidates from Chartink/Screener.in first.")
            return pd.DataFrame()

        required = {"ROC_6M", "RSI_Weekly", "ROE"}
        missing = required - set(df.columns)
        if missing:
            log.error("Signals sheet is missing required columns: %s", missing)
            return pd.DataFrame()

        mask = (
            (df["ROC_6M"] > config.ROC_MIN)
            & (df["RSI_Weekly"] >= config.RSI_BUY_LOW)
            & (df["RSI_Weekly"] <= config.RSI_BUY_HIGH)
            & (df["ROE"] > config.ROE_MIN)
        )
        approved = df[mask].sort_values("ROC_6M", ascending=False).reset_index(drop=True)
        log.info(
            "Signal filter: %d/%d candidates approved.",
            len(approved), len(df),
        )
        return approved

    # ── Exit triggers ─────────────────────────────────────────────────────────

    def get_exit_signals(self, holdings_df: pd.DataFrame) -> pd.DataFrame:
        """
        Scan Equity and ETF holdings for mandatory sell triggers:
          - Weekly RSI < RSI_SELL (40)
          - Current price below the stock's own 200-DMA

        MF and FD rows are skipped (they use different exit logic).

        Returns a DataFrame with columns ['Ticker', 'ExitReason'].
        """
        exits = []

        if holdings_df.empty or "Ticker" not in holdings_df.columns:
            return pd.DataFrame(columns=["Ticker", "ExitReason"])

        if "AssetClass" in holdings_df.columns:
            candidates = holdings_df[
                holdings_df["AssetClass"].str.upper().isin(["EQUITY", "ETF"])
            ]
        else:
            candidates = holdings_df

        for _, row in candidates.iterrows():
            ticker = str(row.get("Ticker", "")).strip()
            if not ticker:
                continue

            try:
                hist = get_historical_ohlcv(ticker, period="1y")
                if hist.empty or len(hist) < 15:
                    log.warning("Skipping exit check for %s — insufficient history.", ticker)
                    continue

                reasons = []

                # Weekly RSI check
                weekly_close_raw = hist["Close"]
                if isinstance(weekly_close_raw, pd.DataFrame):
                    weekly_close_raw = weekly_close_raw.iloc[:, 0]
                weekly_close_raw.index = pd.to_datetime(weekly_close_raw.index)
                weekly_close = weekly_close_raw.resample("W").last().dropna()
                rsi_series = RSIIndicator(close=weekly_close, window=14).rsi()
                if rsi_series is not None and not rsi_series.dropna().empty:
                    current_rsi = float(rsi_series.dropna().iloc[-1])
                    if current_rsi < config.RSI_SELL:
                        reasons.append(f"RSI {current_rsi:.1f} < {config.RSI_SELL}")

                # 200-DMA check (daily data)
                if len(hist) >= config.DMA_WINDOW:
                    dma_200 = float(hist["Close"].rolling(config.DMA_WINDOW).mean().iloc[-1])
                    current_price = float(hist["Close"].iloc[-1])
                    if current_price < dma_200:
                        reasons.append(
                            f"Price {current_price:,.0f} < 200-DMA {dma_200:,.0f}"
                        )

                if reasons:
                    exits.append({
                        "Ticker": ticker,
                        "ExitReason": "; ".join(reasons),
                    })

            except Exception as exc:
                log.error("Exit signal check failed for %s: %s", ticker, exc)

        return pd.DataFrame(exits) if exits else pd.DataFrame(columns=["Ticker", "ExitReason"])
