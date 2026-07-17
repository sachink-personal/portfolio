"""
APScheduler job definitions.

Three jobs:
  daily_digest   — Mon–Fri 8:00 AM IST: update prices, snapshot market, send email
  weekly_monthly — Saturday 9:00 AM IST: weekly analysis OR 1st-Saturday monthly rebalance
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import config

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


# ── Individual job implementations ────────────────────────────────────────────

def _run_daily_job() -> None:
    """Fetch prices, record daily snapshot, check exits, send morning email."""
    from datetime import date

    from core.sheets import SheetsClient
    from core.market_regime import MarketRegime
    from core.signal_processor import SignalProcessor
    from data.equity import get_current_prices
    from data.mf_nav import get_mf_prices
    from notifications.email_sender import EmailSender

    today = date.today().isoformat()
    log.info("Daily job started — %s", today)

    try:
        sheets = SheetsClient()
        holdings = sheets.get_holdings()

        # ── 1. Fetch current prices ──────────────────────────────────────────
        equity_tickers: list[str] = []
        if not holdings.empty and "AssetClass" in holdings.columns:
            equity_tickers = holdings[
                holdings["AssetClass"].str.upper().isin(["EQUITY", "ETF"])
            ]["Ticker"].tolist()

        price_map = get_current_prices(equity_tickers) if equity_tickers else {}
        price_map.update(get_mf_prices(holdings))

        if price_map:
            sheets.update_holdings_prices(price_map)
            holdings = sheets.get_holdings()

        portfolio_value = float(holdings["Value"].sum()) if not holdings.empty else 0.0

        # ── 2. Market regime ─────────────────────────────────────────────────
        regime = MarketRegime().get_full_regime()

        # ── 3. Append to MarketHistory ───────────────────────────────────────
        sheets.append_market_history({
            "Date": today,
            "PortfolioValue": round(portfolio_value, 2),
            "Nifty500Close": regime["trend"]["close"],
            "Nifty500_200DMA": regime["trend"]["dma_200"],
            "PE_Ratio": regime["valuation"]["pe"] if regime["valuation"]["pe"] else "",
            "BreadthPct": regime["breadth"]["breadth_pct"] if regime["breadth"]["breadth_pct"] else "",
        })

        # ── 4. Exit signals ──────────────────────────────────────────────────
        exits = SignalProcessor(sheets.get_signals()).get_exit_signals(holdings)
        sell_alerts = exits.to_dict("records") if not exits.empty else []

        # ── 5. Send email ────────────────────────────────────────────────────
        EmailSender().send_daily_digest(
            portfolio_value=portfolio_value,
            regime=regime,
            sell_alerts=sell_alerts,
            date_str=today,
        )
        log.info("Daily job complete. Value: ₹%s", f"{portfolio_value:,.0f}")

    except Exception as exc:
        log.error("Daily job failed: %s", exc, exc_info=True)


def _run_weekly_job() -> None:
    """Auto-screen candidates, update Signals sheet, send weekly analysis email."""
    from datetime import date
    import pandas as pd

    from core.sheets import SheetsClient
    from core.market_regime import MarketRegime
    from notifications.email_sender import EmailSender

    today = date.today().isoformat()
    log.info("Weekly job started — %s", today)

    try:
        sheets = SheetsClient()
        holdings = sheets.get_holdings()
        regime = MarketRegime().get_full_regime()

        # ── Auto-populate Signals sheet ───────────────────────────────────────
        approved = _run_auto_screen(sheets)

        holdings_perf: list[dict] = []
        if not holdings.empty:
            for _, row in holdings.iterrows():
                avg = float(row.get("AvgBuyPrice", 0))
                curr = float(row.get("CurrentPrice", 0))
                pnl_pct = ((curr - avg) / avg * 100) if avg > 0 else 0.0
                holdings_perf.append({
                    "Ticker": row.get("Ticker", ""),
                    "pnl_pct": round(pnl_pct, 2),
                    "CurrentWeight": row.get("CurrentWeight", 0),
                })

        EmailSender().send_weekly_analysis(
            regime=regime,
            approved_candidates=approved.to_dict("records") if not approved.empty else [],
            holdings_performance=holdings_perf,
            date_str=today,
        )
        log.info("Weekly job complete. Candidates: %d", len(approved))

    except Exception as exc:
        log.error("Weekly job failed: %s", exc, exc_info=True)


def _run_auto_screen(sheets=None):
    """
    Populate the Signals sheet automatically using the configured SCREEN_MODE.

    Modes (set SCREEN_MODE in .env):
        tickertape  — parse latest CSV from downloads/ folder + EPS check via yfinance
        yfinance    — fully automatic Nifty 500 screen (slower, ~3-4 min)

    Falls back from tickertape → yfinance if no CSV is found.
    """
    import pandas as pd
    import config

    mode = config.SCREEN_MODE.lower().strip()
    log.info("Auto-screen mode: '%s'", mode)
    approved = pd.DataFrame()

    if mode == "tickertape":
        try:
            from data.tickertape import get_tickertape_signals
            approved = get_tickertape_signals()
            if approved.empty:
                log.warning("Tickertape CSV returned 0 candidates — falling back to yfinance.")
                mode = "yfinance"
        except FileNotFoundError:
            log.warning("No Tickertape CSV in downloads/ — falling back to yfinance.")
            mode = "yfinance"
        except Exception as exc:
            log.error("Tickertape parse failed (%s) — falling back to yfinance.", exc)
            mode = "yfinance"

    if mode == "yfinance":
        from core.auto_screener import AutoScreener
        approved = AutoScreener().run(write_to_sheets=False)

    if approved.empty:
        return approved

    # Write results to Signals sheet
    if sheets is None:
        from core.sheets import SheetsClient
        sheets = SheetsClient()
    try:
        sheets.clear_signals()
        ws = sheets._ws(config.TAB_SIGNALS)
        headers = ws.row_values(1)
        for _, row in approved.iterrows():
            ws.append_row([row.get(h, "") for h in headers])
        log.info("Signals sheet updated with %d candidates.", len(approved))
    except Exception as exc:
        log.error("Failed to write signals to Signals sheet: %s", exc)

    return approved


def _run_monthly_job() -> None:
    """Generate and email the full monthly rebalance plan."""
    from datetime import date

    from core.sheets import SheetsClient
    from core.market_regime import MarketRegime
    from core.signal_processor import SignalProcessor
    from core.allocation import AllocationEngine
    from core.rebalance import format_plan_as_html
    from notifications.email_sender import EmailSender

    today = date.today().isoformat()
    log.info("Monthly rebalance job started — %s", today)

    try:
        sheets = SheetsClient()
        holdings = sheets.get_holdings()
        regime = MarketRegime().get_full_regime()

        processor = SignalProcessor(sheets.get_signals())
        approved = processor.filter_candidates()
        exits = processor.get_exit_signals(holdings)

        portfolio_value = float(holdings["Value"].sum()) if not holdings.empty else 0.0
        plan = AllocationEngine(holdings, regime, approved, portfolio_value).generate_rebalance_plan(exits)

        html = format_plan_as_html(plan, portfolio_value)
        EmailSender().send_monthly_rebalance(html, today)
        log.info("Monthly rebalance job complete.")

    except Exception as exc:
        log.error("Monthly rebalance job failed: %s", exc, exc_info=True)


# ── Dispatcher ────────────────────────────────────────────────────────────────

def _is_first_saturday() -> bool:
    """Return True if today is the first Saturday of the current month."""
    now = datetime.now(IST)
    return now.weekday() == 5 and now.day <= 7


def _saturday_dispatcher() -> None:
    """Run monthly rebalance on the 1st Saturday, weekly analysis otherwise."""
    if _is_first_saturday():
        log.info("1st Saturday detected — running monthly rebalance job.")
        _run_monthly_job()
    else:
        _run_weekly_job()


# ── Scheduler builder ─────────────────────────────────────────────────────────

def build_scheduler() -> BlockingScheduler:
    """Construct and return the fully configured APScheduler."""
    scheduler = BlockingScheduler()

    # Daily 8:00 AM IST, Mon–Fri
    scheduler.add_job(
        _run_daily_job,
        CronTrigger(
            day_of_week="mon-fri",
            hour=config.DAILY_JOB_HOUR_IST,
            minute=config.DAILY_JOB_MINUTE_IST,
            timezone=IST,
        ),
        id="daily_digest",
        name="Daily Morning Digest",
        replace_existing=True,
        misfire_grace_time=3600,  # Allow up to 1 h late start (e.g., PC was off)
    )

    # Saturday 9:00 AM IST
    scheduler.add_job(
        _saturday_dispatcher,
        CronTrigger(
            day_of_week=config.WEEKLY_JOB_DAY,
            hour=config.WEEKLY_JOB_HOUR_IST,
            minute=config.WEEKLY_JOB_MINUTE_IST,
            timezone=IST,
        ),
        id="weekly_monthly",
        name="Weekly/Monthly Analysis",
        replace_existing=True,
        misfire_grace_time=7200,
    )

    return scheduler
