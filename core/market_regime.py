"""
Market Regime Analysis — evaluates three macro health signals to determine
how much equity exposure the portfolio is allowed to carry.

Signal 1 — 200-DMA Trend   : Is Nifty 500 above or below its 200-day average?
Signal 2 — PE Valuation     : Is the Nifty 50 cheap, fair, or expensive?
Signal 3 — Market Breadth   : What % of Nifty 500 stocks are in an uptrend?
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

import config
from data.equity import get_nifty500_history
from data.nse_indices import get_nifty_pe, classify_pe, get_market_breadth

log = logging.getLogger(__name__)


class MarketRegime:
    """
    Computes all three macro signals and derives the current equity allocation cap.

    Args:
        manual_pe      : Override PE value when NSE API is unavailable.
        manual_breadth : % of Nifty 500 stocks above their 200-DMA (from Chartink).
    """

    def __init__(
        self,
        manual_pe: Optional[float] = None,
        manual_breadth: Optional[float] = None,
    ) -> None:
        self._manual_pe = manual_pe
        self._manual_breadth = manual_breadth

    # ── Signal 1: Trend ───────────────────────────────────────────────────────

    def get_trend(self) -> dict:
        """
        Returns 200-DMA trend for Nifty 500.

        Returns dict with keys:
            trend         : 'BULLISH' | 'BEARISH' | 'UNKNOWN'
            close         : latest close price
            dma_200       : 200-day moving average
            distance_pct  : % distance of close from 200-DMA
        """
        df = get_nifty500_history(period="1y")
        if df.empty or len(df) < config.DMA_WINDOW:
            log.warning("Insufficient Nifty 500 data for 200-DMA calculation.")
            return {"trend": "UNKNOWN", "close": 0.0, "dma_200": 0.0, "distance_pct": 0.0}

        # Ensure we have the Close column
        if "Close" not in df.columns:
            log.warning("Close column not found in Nifty 500 history.")
            return {"trend": "UNKNOWN", "close": 0.0, "dma_200": 0.0, "distance_pct": 0.0}

        # Extract Close column as a Series
        close_series = df["Close"]
        
        # Get latest close value
        try:
            close_val = close_series.iloc[-1]
            # Ensure we have a scalar value
            if isinstance(close_val, (pd.Series, pd.DataFrame)):
                close_val = float(close_val.values[0]) if hasattr(close_val, 'values') else float(close_val.iloc[0])
            else:
                close_val = float(close_val)
        except (ValueError, TypeError, IndexError) as e:
            log.warning(f"Failed to extract close value: {e}")
            return {"trend": "UNKNOWN", "close": 0.0, "dma_200": 0.0, "distance_pct": 0.0}
        
        close = close_val
        
        # Compute rolling mean
        try:
            dma_series = close_series.rolling(config.DMA_WINDOW).mean()
            dma_val = dma_series.iloc[-1]
            # Ensure we have a scalar value
            if isinstance(dma_val, (pd.Series, pd.DataFrame)):
                dma_val = float(dma_val.values[0]) if hasattr(dma_val, 'values') else float(dma_val.iloc[0])
            else:
                dma_val = float(dma_val)
        except (ValueError, TypeError, IndexError) as e:
            log.warning(f"Failed to extract DMA value: {e}")
            dma_val = 0.0
        dma_200 = dma_val
        
        distance_pct = ((close - dma_200) / dma_200 * 100) if dma_200 > 0 else 0.0

        return {
            "trend": "BULLISH" if close > dma_200 else "BEARISH",
            "close": round(close, 2),
            "dma_200": round(dma_200, 2),
            "distance_pct": round(distance_pct, 2),
        }

    # ── Signal 2: Valuation ───────────────────────────────────────────────────

    def get_valuation(self) -> dict:
        """
        Returns PE-based valuation regime.

        Returns dict with keys:
            valuation : 'OVERVALUED' | 'FAIR' | 'UNDERVALUED' | 'UNKNOWN'
            pe        : current PE ratio (float or None)
        """
        pe = self._manual_pe if self._manual_pe is not None else get_nifty_pe()
        return {
            "valuation": classify_pe(pe),
            "pe": pe,
        }

    # ── Signal 3: Breadth ─────────────────────────────────────────────────────

    def get_breadth(self) -> dict:
        """
        Returns market breadth classification.

        Breadth is the % of Nifty 500 stocks trading above their 200-DMA.
        Source: Chartink scanner CSV export (automated).

        Returns dict with keys:
            breadth_pct : float or None
            warning     : True when breadth < BREADTH_WARNING_THRESHOLD while Nifty is rising
            status      : 'HEALTHY' | 'WEAK' | 'UNKNOWN'
        """
        pct = self._manual_breadth if self._manual_breadth is not None else get_market_breadth()
        if pct is None:
            return {"breadth_pct": None, "warning": False, "status": "UNKNOWN"}

        warning = pct < config.BREADTH_WARNING_THRESHOLD
        return {
            "breadth_pct": round(pct, 1),
            "warning": warning,
            "status": "WEAK" if warning else "HEALTHY",
        }

    # ── Combined regime ───────────────────────────────────────────────────────

    def get_full_regime(self) -> dict:
        """
        Run all three signals and compute the equity allocation cap.

        Returns dict with keys:
            trend          : result of get_trend()
            valuation      : result of get_valuation()
            breadth        : result of get_breadth()
            equity_cap     : float — max fraction of portfolio to hold in equities
            regime_label   : human-readable summary string
        """
        trend_data = self.get_trend()
        val_data = self.get_valuation()
        breadth_data = self.get_breadth()

        trend = trend_data["trend"]
        valuation = val_data["valuation"]

        if trend == "BULLISH":
            if valuation == "OVERVALUED":
                equity_cap = 0.70   # Reduce new deployments but hold existing
            elif valuation == "UNDERVALUED":
                equity_cap = 1.00   # Aggressive — draw from FD too
            else:
                equity_cap = config.EQUITY_ALLOC_BULLISH
        elif trend == "BEARISH":
            equity_cap = config.EQUITY_ALLOC_BEARISH
        else:
            equity_cap = 0.60

        regime_label = f"{trend} / {valuation}"
        if breadth_data["warning"]:
            regime_label += " ⚠️ LOW BREADTH"

        return {
            "trend": trend_data,
            "valuation": val_data,
            "breadth": breadth_data,
            "equity_cap": round(equity_cap, 2),
            "regime_label": regime_label,
        }
