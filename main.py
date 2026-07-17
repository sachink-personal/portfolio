"""
Quantitative Portfolio Manager — Entry Point

Usage:
  python main.py              Start the scheduler (runs indefinitely)
  python main.py --init       Create all Google Sheet tabs with correct headers
  python main.py --test       Fire all three notification jobs once; check inbox
  python main.py --daily      Run only the daily digest job once and exit
  python main.py --weekly     Run only the weekly analysis job once and exit
  python main.py --monthly    Run only the monthly rebalance job once and exit

For automated daily execution on Windows, set up a Task Scheduler task that runs:
  python main.py --daily
at 08:00 every weekday — this is more reliable than keeping main.py running 24/7.
"""
from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("portfolio.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("main")


def cmd_init() -> None:
    log.info("Initialising Google Sheets structure…")
    from core.sheets import SheetsClient
    SheetsClient().initialize_sheet_structure()
    log.info("Done. Open your Google Sheet to verify the four tabs.")


def cmd_test() -> None:
    log.info("=== TEST MODE — firing all jobs once ===")
    from notifications.email_sender import EmailSender
    from notifications.scheduler import _run_daily_job, _run_weekly_job, _run_monthly_job

    log.info("[1/4] Email configuration test…")
    ok = EmailSender().send_test()
    log.info("Email test: %s", "PASSED" if ok else "FAILED — check .env credentials")

    log.info("[2/4] Daily digest job…")
    _run_daily_job()

    log.info("[3/4] Weekly analysis job…")
    _run_weekly_job()

    log.info("[4/4] Monthly rebalance job…")
    _run_monthly_job()

    log.info("=== TEST COMPLETE — check your inbox ===")


def cmd_start_scheduler() -> None:
    log.info("Starting Quantitative Portfolio Manager scheduler…")
    log.info("  Daily digest    : 8:00 AM IST (Mon–Fri)")
    log.info("  Weekly analysis : Saturday 9:00 AM IST")
    log.info("  Monthly rebalance: 1st Saturday 9:00 AM IST")
    log.info("Press Ctrl+C to stop.\n")
    from notifications.scheduler import build_scheduler
    scheduler = build_scheduler()
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quantitative Portfolio Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--init", action="store_true", help="Initialise Google Sheets tabs")
    parser.add_argument("--test", action="store_true", help="Fire all jobs once (check email)")
    parser.add_argument("--daily", action="store_true", help="Run daily job once")
    parser.add_argument("--weekly", action="store_true", help="Run weekly job once")
    parser.add_argument("--monthly", action="store_true", help="Run monthly rebalance job once")
    args = parser.parse_args()

    if args.init:
        cmd_init()
    elif args.test:
        cmd_test()
    elif args.daily:
        from notifications.scheduler import _run_daily_job
        _run_daily_job()
    elif args.weekly:
        from notifications.scheduler import _run_weekly_job
        _run_weekly_job()
    elif args.monthly:
        from notifications.scheduler import _run_monthly_job
        _run_monthly_job()
    else:
        cmd_start_scheduler()


if __name__ == "__main__":
    main()
