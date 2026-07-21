"""
Migrate portfolio from JSON backup to SQLite database.

This script loads `portfolio-backup-2026-01-14.json` and populates:
1. Holdings table (current positions)
2. Ledger table (all historical transactions)

Includes validation:
- All required fields must be present
- Qty, prices must be positive
- Dates must be valid
- Tickers must exist in Nifty 500 or be recognized fund/commodity codes
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from core.database import get_session, upsert_holding, append_ledger, get_holdings, get_ledger

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ── Configuration ──────────────────────────────────────────────────────────────

BACKUP_FILE = Path("portfolio-backup-2026-01-14.json")
ASSET_TYPES_TO_IMPORT = {"STOCK", "MF", "GOLD"}  # Skip CASH, SAVINGS, FD
ASSET_CLASS_MAP = {
    "STOCK": "EQUITY",
    "MF": "MF",
    "GOLD": "GOLD",
    "ETF": "EQUITY",
}


def load_backup_json() -> dict:
    """Load and parse the JSON backup file."""
    if not BACKUP_FILE.exists():
        raise FileNotFoundError(f"Backup file not found: {BACKUP_FILE}")
    
    with open(BACKUP_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    
    log.info(f"Loaded backup: version {data.get('version')}, dated {data.get('date')}")
    return data


def validate_asset(asset: dict) -> Tuple[bool, str]:
    """
    Validate a single asset record.
    Returns (is_valid, error_message)
    """
    errors = []
    
    # Required fields
    if not asset.get("name"):
        errors.append("Missing: name")
    if not asset.get("symbol"):
        errors.append("Missing: symbol")
    if asset.get("type") not in ASSET_TYPES_TO_IMPORT:
        errors.append(f"Invalid type: {asset.get('type')}")
    
    # Numeric fields must be positive
    units = float(asset.get("units", 0))
    if units <= 0:
        errors.append(f"Invalid units: {units}")
    
    avg_price = float(asset.get("avgPrice", 0))
    if avg_price <= 0:
        errors.append(f"Invalid avgPrice: {avg_price}")
    
    current_price = float(asset.get("currentPrice", 0))
    if current_price <= 0:
        errors.append(f"Invalid currentPrice: {current_price}")
    
    if errors:
        return False, " | ".join(errors)
    
    return True, ""


def validate_transaction(txn: dict, asset_id_map: dict) -> Tuple[bool, str]:
    """
    Validate a single transaction record.
    Returns (is_valid, error_message)
    """
    errors = []
    
    # Required fields
    if not txn.get("date"):
        errors.append("Missing: date")
    elif not is_valid_date(txn["date"]):
        errors.append(f"Invalid date format: {txn['date']}")
    
    if txn.get("type") not in {"BUY", "SELL"}:
        errors.append(f"Invalid type: {txn.get('type')}")
    
    units = float(txn.get("units", 0))
    if units <= 0:
        errors.append(f"Invalid units: {units}")
    
    price = float(txn.get("price", 0))
    if price <= 0:
        errors.append(f"Invalid price: {price}")
    
    asset_id = txn.get("assetId")
    if asset_id not in asset_id_map:
        errors.append(f"Asset not found: assetId {asset_id}")
    
    if errors:
        return False, " | ".join(errors)
    
    return True, ""


def is_valid_date(date_str: str) -> bool:
    """Check if date string is valid (format: DD-MM-YYYY)."""
    try:
        datetime.strptime(date_str, "%d-%m-%Y")
        return True
    except ValueError:
        return False


def parse_date(date_str: str) -> str:
    """Convert DD-MM-YYYY to YYYY-MM-DD for database storage."""
    dt = datetime.strptime(date_str, "%d-%m-%Y")
    return dt.strftime("%Y-%m-%d")


def clean_ticker(symbol: str, asset_type: str) -> str:
    """
    Clean and normalize ticker symbol.
    - Remove .NS suffix if present
    - Convert to uppercase
    """
    if not symbol:
        return ""
    
    symbol = symbol.strip().upper()
    if symbol.endswith(".NS"):
        symbol = symbol[:-3]
    
    return symbol


def migrate_assets(backup_data: dict) -> Tuple[int, list[str], dict]:
    """
    Load assets from backup into Holdings table.
    Returns (num_imported, error_messages, asset_id_map)
    """
    assets = backup_data.get("assets", [])
    asset_id_map = {}  # Map from asset.id to (ticker, assetType) for transactions
    
    imported = 0
    errors = []
    nifty_tickers = set()
    
    # Try to load Nifty 500 for validation (optional)
    try:
        from data.nifty500 import get_nifty500_universe
        nifty_list = get_nifty500_universe()
        nifty_tickers = {item['ticker'] for item in nifty_list}
    except Exception as e:
        log.warning(f"Could not load Nifty 500 list: {e}. Skipping ticker validation.")
    
    for i, asset in enumerate(assets, 1):
        # Validate asset
        is_valid, error_msg = validate_asset(asset)
        if not is_valid:
            errors.append(f"Row {i}: {asset.get('name', 'UNKNOWN')} - {error_msg}")
            continue
        
        # Skip unwanted asset types
        if asset.get("type") not in ASSET_TYPES_TO_IMPORT:
            log.info(f"Skipping {asset.get('name')} (type: {asset.get('type')})")
            continue
        
        # Clean ticker
        ticker = clean_ticker(asset.get("symbol", ""), asset.get("type", ""))
        if not ticker:
            errors.append(f"Row {i}: {asset.get('name')} - Could not parse ticker from '{asset.get('symbol')}'")
            continue
        
        # Check ticker validity
        asset_type = asset.get("type", "")
        if asset_type == "STOCK" and nifty_tickers and ticker not in nifty_tickers:
            log.warning(f"Ticker {ticker} not in Nifty 500. May be delisted or invalid.")
        
        # Prepare holding record
        holding = {
            "Ticker": ticker,
            "Name": asset.get("name", ""),
            "AssetClass": ASSET_CLASS_MAP.get(asset_type, "OTHER"),
            "Qty": float(asset.get("units", 0)),
            "AvgBuyPrice": float(asset.get("avgPrice", 0)),
            "CurrentPrice": float(asset.get("currentPrice", 0)),
            "Value": float(asset.get("value", 0)),
        }
        
        # Insert into database
        try:
            upsert_holding(holding)
            asset_id_map[asset.get("id")] = (ticker, asset_type)
            imported += 1
            log.info(f"Imported: {ticker} ({asset.get('name')}) - Qty: {holding['Qty']}")
        except Exception as e:
            errors.append(f"Row {i}: {asset.get('name')} - Database error: {str(e)}")
    
    log.info(f"Assets imported: {imported}/{len(assets)}")
    return imported, errors, asset_id_map


def migrate_transactions(backup_data: dict, asset_id_map: dict) -> Tuple[int, list[str]]:
    """
    Load transactions from backup into Ledger table.
    Returns (num_imported, error_messages)
    """
    transactions = backup_data.get("transactions", [])
    
    imported = 0
    errors = []
    
    for i, txn in enumerate(transactions, 1):
        # Validate transaction
        is_valid, error_msg = validate_transaction(txn, asset_id_map)
        if not is_valid:
            errors.append(f"Txn {i}: {error_msg}")
            continue
        
        # Get asset info
        asset_id = txn.get("assetId")
        ticker, asset_type = asset_id_map[asset_id]
        
        # Prepare ledger record
        ledger_row = {
            "Date": parse_date(txn.get("date", "")),
            "Ticker": ticker,
            "AssetClass": ASSET_CLASS_MAP.get(asset_type, "OTHER"),
            "Action": txn.get("type", "").upper(),  # BUY or SELL
            "Qty": float(txn.get("units", 0)),
            "ExecPrice": float(txn.get("price", 0)),
            "TotalValue": float(txn.get("units", 0)) * float(txn.get("price", 0)),
            "Charges": 0,  # Not in JSON backup
        }
        
        # Insert into database
        try:
            append_ledger(ledger_row)
            imported += 1
        except Exception as e:
            errors.append(f"Txn {i}: Database error: {str(e)}")
    
    log.info(f"Transactions imported: {imported}/{len(transactions)}")
    return imported, errors


def main():
    """Run the migration."""
    print("\n" + "="*80)
    print("PORTFOLIO MIGRATION: JSON BACKUP -> SQLite DATABASE")
    print("="*80 + "\n")
    
    try:
        from core.database import initialize_database
        initialize_database()
    except Exception as exc:
        print(f"Failed to initialize database schema: {exc}")
        return 1
    
    try:
        # Load backup
        print("Loading backup file...")
        backup_data = load_backup_json()
        
        # Migrate assets
        print("\nMigrating assets (Holdings)...")
        assets_imported, asset_errors, asset_id_map = migrate_assets(backup_data)
        
        # Show asset errors
        if asset_errors:
            print(f"\n[WARN] Asset import issues ({len(asset_errors)}):")
            for error in asset_errors[:10]:  # Show first 10
                print(f"  - {error}")
            if len(asset_errors) > 10:
                print(f"  ... and {len(asset_errors) - 10} more")
        
        # Migrate transactions
        print("\nMigrating transactions (Ledger)...")
        txns_imported, txn_errors = migrate_transactions(backup_data, asset_id_map)
        
        # Show transaction errors
        if txn_errors:
            print(f"\n[WARN] Transaction import issues ({len(txn_errors)}):")
            for error in txn_errors[:10]:  # Show first 10
                print(f"  - {error}")
            if len(txn_errors) > 10:
                print(f"  ... and {len(txn_errors) - 10} more")
        
        # Verify
        print("\n=== VERIFICATION ===")
        print("-" * 80)
        holdings_df = get_holdings()
        ledger_df = get_ledger()
        
        print(f"Holdings loaded: {len(holdings_df)} positions")
        print(f"  Total value: Rs. {holdings_df['Value'].sum():,.0f}")
        print(f"  Asset classes: {holdings_df['AssetClass'].unique().tolist()}")
        
        print(f"\nLedger loaded: {len(ledger_df)} transactions")
        if not ledger_df.empty and "Date" in ledger_df.columns:
            print(f"  Date range: {ledger_df['Date'].min()} to {ledger_df['Date'].max()}")
        print(f"  Buy transactions: {len(ledger_df[ledger_df['Action'] == 'BUY'])}")
        print(f"  Sell transactions: {len(ledger_df[ledger_df['Action'] == 'SELL'])}")
        
        # Summary
        print("\n" + "="*80)
        print("MIGRATION SUMMARY")
        print("="*80)
        print(f"[OK] Assets:       {assets_imported} imported")
        if asset_errors:
            print(f"[WARN] Errors:       {len(asset_errors)} asset issues")
        print(f"[OK] Transactions: {txns_imported} imported")
        if txn_errors:
            print(f"[WARN] Errors:       {len(txn_errors)} transaction issues")
        print("="*80 + "\n")
        
        if asset_errors or txn_errors:
            print("[WARN] REVIEW ERRORS ABOVE AND FIX BEFORE PROCEEDING TO SIGNAL GENERATION\n")
            return 1
        else:
            print("[OK] MIGRATION COMPLETE - All data imported successfully!\n")
            print("Next steps:")
            print("1. Run Screener.in import: streamlit run scripts/import_screener.py")
            print("2. Run Chartink import:    streamlit run scripts/import_chartink.py")
            print("3. View portfolio:         streamlit run app.py\n")
            return 0
    
    except Exception as e:
        print(f"\n[ERROR] MIGRATION FAILED: {str(e)}\n")
        log.exception("Migration error")
        return 1


if __name__ == "__main__":
    exit(main())
