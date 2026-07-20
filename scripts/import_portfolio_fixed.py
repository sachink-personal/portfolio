"""
One-time import script: reads portfolio-backup-2026-01-14.json and
writes all holdings AND transactions to the SQLite database.

Run: python scripts/import_portfolio_fixed.py
"""
import json
import re
import sys
import os
from datetime import datetime
from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.sheets import SheetsClient
from core.database import get_engine, bulk_insert_ledger

JSON_FILE = "portfolio-backup-2026-01-14.json"

ETF_KEYWORDS = re.compile(
    r"(BEES|IETF|ETFGSC|ETF(?!$)|NIFTY|MOM30|NEXT50|MOMENTUM50|MASPTOP50|"
    r"MONQ50|MIDCAPETF|HNGSNG|SILVER|MAHKTECH|OIL|MOGSEC|LICNET|ALPHA|"
    r"HDFCSML|MAFANG|MOHEALTH|BFSI|CONS$|PSUBNK|CONSUMIETF|GOLDBEES)",
    re.IGNORECASE,
)
EQUITY_SYMBOLS = {"APLAPOLLO", "HINDALCO", "BSE", "JINDALSTEL"}


def classify_stock(symbol: str) -> str:
    sym = symbol.upper().replace(".NS", "").strip()
    if sym in EQUITY_SYMBOLS:
        return "EQUITY"
    return "ETF"


def _parse_date(raw: str) -> str:
    """Normalise date to YYYY-MM-DD. Handles DD-MM-YYYY and ISO formats."""
    raw = str(raw).strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def parse_assets(data: dict) -> list[dict]:
    rows = []
    for a in data.get("assets", []):
        atype = str(a.get("type", "")).upper()
        units = float(a.get("units", 0) or 0)
        avg   = float(a.get("avgPrice", 0) or 0)
        curr  = float(a.get("currentPrice", 0) or 0)
        value = float(a.get("value", 0) or 0)

        # Always include assets in id_to_asset for transaction lookup,
        # even if they have 0 units (sold holdings). The skip check below
        # is only for display purposes in the Holdings table.
        is_watchlist = units == 0 and value == 0

        if atype == "STOCK":
            raw_symbol = a.get("symbol")
            if raw_symbol is None:
                symbol = ""
            else:
                symbol = str(raw_symbol).replace(".NS", "").strip().upper()
            rows.append({
                "id":           a.get("id"),
                "Ticker":       symbol,
                "Name":         a.get("name", ""),
                "AssetClass":   classify_stock(symbol),
                "Qty":          round(units, 4),
                "AvgBuyPrice":  round(avg, 4),
                "CurrentPrice": round(curr, 4),
                "Value":        round(value, 2),
                "TargetWeight": 0,
                "CurrentWeight": 0,
            })

        elif atype == "MF":
            scheme = str(a.get("schemeCode", "")).strip()
            rows.append({
                "id":           a.get("id"),
                "Ticker":       scheme,
                "Name":         a.get("name", ""),
                "AssetClass":   "MF",
                "Qty":          round(units, 4),
                "AvgBuyPrice":  round(avg, 4),
                "CurrentPrice": round(curr, 4),
                "Value":        round(value, 2),
                "TargetWeight": 0,
                "CurrentWeight": 0,
                "is_watchlist": is_watchlist,
            })

        elif atype == "FD":
            rows.append({
                "id":           a.get("id"),
                "Ticker":       f"FD-{a.get('id', '')}",
                "Name":         a.get("name", ""),
                "AssetClass":   "FD",
                "Qty":          1,
                "AvgBuyPrice":  round(value, 2),
                "CurrentPrice": round(value, 2),
                "Value":        round(value, 2),
                "TargetWeight": 0,
                "CurrentWeight": 0,
                "is_watchlist": is_watchlist,
            })

        elif atype == "SAVINGS":
            # Savings accounts use name as Ticker (e.g., "ICICI", "HDFC")
            ticker = a.get("name", "").strip().upper() or f"Savings-{a.get('id', '')}"
            rows.append({
                "id":           a.get("id"),
                "Ticker":       ticker,
                "Name":         a.get("name", ""),
                "AssetClass":   "SAVINGS",
                "Qty":          round(units, 2),
                "AvgBuyPrice":  round(avg, 2),
                "CurrentPrice": round(curr, 2),
                "Value":        round(value, 2),
                "TargetWeight": 0,
                "CurrentWeight": 0,
                "is_watchlist": is_watchlist,
            })

        elif atype == "CASH":
            # Cash accounts use "Cash" as Ticker
            ticker = "CASH"
            rows.append({
                "id":           a.get("id"),
                "Ticker":       ticker,
                "Name":         a.get("name", ""),
                "AssetClass":   "CASH",
                "Qty":          round(units, 2),
                "AvgBuyPrice":  round(avg, 2),
                "CurrentPrice": round(curr, 2),
                "Value":        round(value, 2),
                "TargetWeight": 0,
                "CurrentWeight": 0,
                "is_watchlist": is_watchlist,
            })

    return rows


def parse_transactions(data: dict, id_to_asset: dict) -> list[dict]:
    """Map transactions to Ledger schema.
    
    Note: id_to_asset should be created from parse_assets() output.
    The lookup dict has keys: id, Ticker, Name, AssetClass, Qty, AvgBuyPrice, 
    CurrentPrice, Value, TargetWeight, CurrentWeight
    """
    ledger = []
    for tx in data.get("transactions", []):
        asset_id = tx.get("assetId")
        asset_data = id_to_asset.get(asset_id)
        if asset_data:
            # asset_data has 'Ticker' (already cleaned), not 'symbol'
            ticker = asset_data.get("Ticker", "")
            if ticker and ticker.strip():
                # For stocks, re-classify based on ticker
                aclass = classify_stock(ticker)
            else:
                # For MF/FD, use the AssetClass from parse_assets
                aclass = asset_data.get("AssetClass", "")
        else:
            ticker = f"ASSET-{asset_id}"
            aclass = ""
        
        units    = float(tx.get("units", 0) or 0)
        price    = float(tx.get("price", 0) or 0)
        total    = round(units * price, 2)
        action   = str(tx.get("type", "BUY")).upper()
        date_str = _parse_date(tx.get("date", ""))
        
        ledger.append({
            "Date":       date_str,
            "Ticker":     ticker,
            "AssetClass": aclass,
            "Action":     action,
            "Qty":        round(units, 4),
            "ExecPrice":  round(price, 4),
            "TotalValue": total,
            "Charges":    0,
        })
    
    ledger.sort(key=lambda x: x["Date"])
    return ledger


def main():
    with open(JSON_FILE, encoding="utf-8") as f:
        data = json.load(f)

    rows = parse_assets(data)
    print(f"\n{'='*50}")
    print(f"Portfolio backup: {data.get('date','')}")
    print(f"{'='*50}")

    # Summary by asset class
    from collections import Counter
    counts = Counter(r["AssetClass"] for r in rows)
    print(f"\nHoldings ({len(rows)} total):")
    for cls, n in sorted(counts.items()):
        total = sum(r["Value"] for r in rows if r["AssetClass"] == cls)
        print(f"  {cls:8s}  {n:3d}  ₹{total:>15,.2f}")
    print(f"  {'TOTAL':8s}  {len(rows):3d}  ₹{sum(r['Value'] for r in rows):>15,.2f}")

    # Build id_to_asset
    id_to_asset = {r["id"]: r for r in rows}
    
    # Parse transactions
    ledger_rows = parse_transactions(data, id_to_asset)
    print(f"\nTransactions ({len(ledger_rows)} total):")
    tx_counts = Counter(r["Action"] for r in ledger_rows)
    for action, n in sorted(tx_counts.items()):
        print(f"  {action:6s}  {n:4d} transactions")
    
    # Print first 5 transactions for debugging
    print("\nFirst 5 transactions (for debugging):")
    for t in ledger_rows[:5]:
        print(f"  {t}")
    
    # Write holdings
    print(f"\nWriting {len(rows)} holdings to Holdings table...")
    for r in rows:
        SheetsClient().upsert_holding(r)
    print(f"  Written {len(rows)} holdings successfully.")

    # Write transactions
    print(f"\nClearing existing transactions from Ledger table...")
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM Ledger"))
        conn.commit()
    print("  Ledger table cleared.")

    print(f"\nWriting {len(ledger_rows)} transactions to Ledger table...")
    bulk_insert_ledger(ledger_rows)
    print(f"  Written {len(ledger_rows)} transactions successfully.")

    print("\nImport complete. Go to Portfolio page → Refresh Prices to update current values.")


if __name__ == "__main__":
    main()