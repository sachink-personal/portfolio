"""
Google Sheets client — DEPRECATED.
This module now delegates all operations to core/database.py (SQLite).
Kept for backward compatibility so existing imports continue to work without changes.

All data is stored in a local SQLite database instead of Google Sheets,
eliminating the need for credentials.json and Google API configuration.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Re-export everything from the new database module so existing imports work unchanged.
from core.database import (
    SheetsClient,
    get_holdings,
    update_holdings_prices,
    upsert_holding,
    delete_holding,
    get_ledger,
    append_ledger,
    bulk_insert_ledger,
    get_signals,
    clear_signals,
    append_signal,
    bulk_insert_signals,
    get_market_history,
    append_market_history,
    initialize_database,
)

log.info("core.sheets loaded — delegating to SQLite (Google Sheets replaced)")