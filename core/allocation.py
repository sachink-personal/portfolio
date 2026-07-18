"""
Allocation Engine — Inverse Volatility Weighting and Rebalance Plan Generation.

The Inverse Volatility method sizes positions so that each asset contributes
equally to overall portfolio risk:
    weight_i = (1/σ_i) / Σ(1/σ_j)

Individual positions are then capped at MAX_POSITION_WEIGHT (15%) and
floored at MIN_POSITION_WEIGHT (3%) to avoid extreme concentration.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

import config
from data.equity import get_historical_ohlcv

log = logging.getLogger(__name__)


def compute_inverse_volatility_weights(
    tickers: list[str],
    lookback_days: int = 20,
) -> dict[str, float]:
    """
    Compute portfolio weights using Inverse Volatility.

    Args:
        tickers      : List of NSE tickers to size.
        lookback_days: Rolling window for daily-return standard deviation.

    Returns:
        Dict {ticker: weight} where weights sum to 1.0.
        Falls back to equal weights if volatility data is unavailable.
    """
    if not tickers:
        return {}
    if len(tickers) == 1:
        return {tickers[0]: 1.0}

    vol_map: dict[str, float] = {}
    for ticker in tickers:
        try:
            hist = get_historical_ohlcv(ticker, period="3mo")
            if hist.empty or len(hist) < lookback_days:
                vol_map[ticker] = np.inf
                continue
            # Handle yfinance MultiIndex columns
            if isinstance(hist.columns, pd.MultiIndex):
                close_s = hist["Close"].iloc[:, 0]
            else:
                close_s = hist["Close"]
            returns = close_s.pct_change().dropna().tail(lookback_days)
            vol = float(returns.std())
            vol_map[ticker] = vol if vol > 1e-9 else np.inf
        except Exception as exc:
            log.error("Volatility fetch failed for %s: %s", ticker, exc)
            vol_map[ticker] = np.inf

    finite_vols = {t: v for t, v in vol_map.items() if np.isfinite(v)}
    if not finite_vols:
        n = len(tickers)
        return {t: round(1.0 / n, 4) for t in tickers}

    inv_vol = {t: 1.0 / v for t, v in finite_vols.items()}
    total_inv = sum(inv_vol.values())
    raw_weights = {t: v / total_inv for t, v in inv_vol.items()}

    # Tickers with no volatility data get equal share of remaining weight
    no_data = [t for t in tickers if t not in finite_vols]
    if no_data:
        used = sum(raw_weights.values())
        per_no_data = (1.0 - used) / len(no_data)
        for t in no_data:
            raw_weights[t] = per_no_data

    return _apply_weight_bounds(raw_weights)


def _apply_weight_bounds(weights: dict[str, float]) -> dict[str, float]:
    """
    Iteratively cap weights at MAX_POSITION_WEIGHT and redistribute excess.
    Then remove positions below MIN_POSITION_WEIGHT and renormalise.
    """
    w = dict(weights)
    max_w = config.MAX_POSITION_WEIGHT
    min_w = config.MIN_POSITION_WEIGHT

    for _ in range(20):  # Converges quickly
        capped = {t: min(v, max_w) for t, v in w.items()}
        surplus = sum(w.values()) - sum(capped.values())
        if abs(surplus) < 1e-9:
            w = capped
            break
        uncapped = [t for t, v in capped.items() if v < max_w]
        if not uncapped:
            w = capped
            break
        extra = surplus / len(uncapped)
        for t in uncapped:
            capped[t] = min(capped[t] + extra, max_w)
        w = capped

    # Remove tiny positions
    w = {t: v for t, v in w.items() if v >= min_w}
    total = sum(w.values())
    if total == 0:
        return weights  # Safety fallback
    return {t: round(v / total, 4) for t, v in w.items()}


class AllocationEngine:
    """
    Generates the monthly rebalance plan given the current portfolio state,
    market regime, and approved signal candidates.
    """

    def __init__(
        self,
        holdings_df: pd.DataFrame,
        regime: dict,
        approved_signals: pd.DataFrame,
        portfolio_value: Optional[float] = None,
    ) -> None:
        self.holdings = holdings_df
        self.regime = regime
        self.approved = approved_signals
        self.portfolio_value = portfolio_value or (
            float(holdings_df["Value"].sum()) if "Value" in holdings_df.columns else 0.0
        )

    def generate_rebalance_plan(self, exit_signals: pd.DataFrame) -> dict:
        """
        Build a complete rebalance plan.

        Returns:
            {
                sells           : list of {ticker, reason, current_value}
                buys            : list of {ticker, sector, roc_6m, rsi, roe, weight, target_value}
                fd_action       : str | None — defensive reallocation instruction
                deployment_note : str | None — PE-based deployment guidance
                equity_cap      : float
                regime_summary  : str
            }
        """
        plan: dict = {
            "sells": [],
            "buys": [],
            "fd_action": None,
            "deployment_note": None,
            "equity_cap": self.regime.get("equity_cap", 0.9),
            "regime_summary": self.regime.get("regime_label", ""),
        }

        trend = self.regime["trend"]["trend"]
        valuation = self.regime["valuation"]["valuation"]
        equity_cap = plan["equity_cap"]

        # ── Sell: Exit-triggered holdings ────────────────────────────────────
        exit_set = set(exit_signals["Ticker"].tolist()) if not exit_signals.empty else set()
        for _, row in self.holdings.iterrows():
            ticker = str(row.get("Ticker", ""))
            asset_class = str(row.get("AssetClass", "")).upper()
            if asset_class not in ("EQUITY", "ETF"):
                continue
            if ticker in exit_set:
                reason = exit_signals.loc[
                    exit_signals["Ticker"] == ticker, "ExitReason"
                ].values[0]
                plan["sells"].append({
                    "ticker": ticker,
                    "reason": reason,
                    "current_value": float(row.get("Value", 0)),
                })

        # ── Bearish defensive reallocation ───────────────────────────────────
        if trend == "BEARISH" and "AssetClass" in self.holdings.columns:
            equity_value = float(
                self.holdings[
                    self.holdings["AssetClass"].str.upper().isin(["EQUITY", "ETF"])
                ]["Value"].sum()
            )
            target_equity = self.portfolio_value * equity_cap
            excess = equity_value - target_equity
            if excess > 1000:
                plan["fd_action"] = (
                    f"BEARISH REGIME ACTIVE — Move ₹{excess:,.0f} from equities to "
                    f"FD / Overnight MF (target equity: {equity_cap*100:.0f}% of portfolio)"
                )

        # ── PE-based deployment guidance ──────────────────────────────────────
        if valuation == "OVERVALUED":
            plan["deployment_note"] = (
                f"Nifty PE is OVERVALUED (>{config.PE_OVERVALUED}). "
                "Pause new equity deployments. Route this month's SIP into FD or Debt MF."
            )
        elif valuation == "UNDERVALUED":
            plan["deployment_note"] = (
                f"Nifty PE is UNDERVALUED (<{config.PE_UNDERVALUED}). "
                "AGGRESSIVE DEPLOY ZONE: Consider moving FD maturity proceeds into equities."
            )

        # ── Buy: Top approved candidates ─────────────────────────────────────
        if not self.approved.empty and trend == "BULLISH" and valuation != "OVERVALUED":
            held = set(self.holdings["Ticker"].tolist()) if "Ticker" in self.holdings.columns else set()
            new_candidates = (
                self.approved[~self.approved["Ticker"].isin(held)]
                .head(config.MAX_HOLDINGS)
            )

            if not new_candidates.empty:
                buy_tickers = new_candidates["Ticker"].tolist()
                weights = compute_inverse_volatility_weights(buy_tickers)

                sell_proceeds = sum(s["current_value"] for s in plan["sells"])
                # Note: user adds SIP amount on top of sell proceeds when executing

                for ticker, weight in weights.items():
                    row_mask = new_candidates["Ticker"] == ticker
                    if not row_mask.any():
                        continue
                    cand_row = new_candidates[row_mask].iloc[0]
                    plan["buys"].append({
                        "ticker": ticker,
                        "sector": str(cand_row.get("Sector", "")),
                        "roc_6m": float(cand_row.get("ROC_6M", 0)),
                        "rsi": float(cand_row.get("RSI_Weekly", 0)),
                        "roe": float(cand_row.get("ROE", 0)),
                        "weight": round(weight * 100, 2),
                        "target_value": round(sell_proceeds * weight, 0),
                    })

        return plan
