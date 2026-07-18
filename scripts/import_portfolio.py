"""
One-time import script: reads portfolio-backup-2026-01-14.json and
writes all holdings AND transactions to the SQLite database.

Run: python scripts/import_portfolio.py
     python scripts/import_portfolio.py --preview
     python scripts/import_portfolio.py --ledger-only
     python scripts/import_portfolio.py --holdings-only
"""
import json
import re
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.sheets import SheetsClient

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
    return raw  # Return as-is if unknown format


def parse_assets(data: dict) -> list[dict]:
    rows = []
    for a in data.get("assets", []):
        atype = str(a.get("type", "")).upper()
        units = float(a.get("units", 0) or 0)
        avg   = float(a.get("avgPrice", 0) or 0)
        curr  = float(a.get("currentPrice", 0) or 0)
        value = float(a.get("value", 0) or 0)

        # Skip zero-unit watchlist / placeholder entries
        if units == 0 and value == 0:
            continue

        if atype == "STOCK":
            symbol = a.get("symbol", "").replace(".NS", "").strip().upper()
            rows.append({
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
                "Ticker":       scheme,
                "Name":         a.get("name", ""),
                "AssetClass":   "MF",
                "Qty":          round(units, 4),
                "AvgBuyPrice":  round(avg, 4),
                "CurrentPrice": round(curr, 4),
                "Value":        round(value, 2),
                "TargetWeight": 0,
                "CurrentWeight": 0,
            })

        elif atype == "FD":
            rows.append({
                "Ticker":       f"FD-{a.get('id', '')}",
                "Name":         a.get("name", ""),
                "AssetClass":   "FD",
                "Qty":          1,
                "AvgBuyPrice":  round(value, 2),
                "CurrentPrice": round(value, 2),
                "Value":        round(value, 2),
                "TargetWeight": 0,
                "CurrentWeight": 0,
            })

    return rows


def main(preview: bool = False, ledger_only: bool = False, holdings_only: bool = False):
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

    # Parse transactions if not just holdings
    if not holdings_only:
        id_to_ticker  = {r["Ticker"]: r["AssetClass"] for r in rows}
        
        def parse_transactions(data: dict) -> list[dict]:
            """Map transactions to Ledger schema."""
            ledger = []
            for tx in data.get("transactions", []):
                asset_id = tx.get("assetId")
                ticker   = id_to_ticker.get(asset_id, f"ASSET-{asset_id}")
                aclass   = id_to_ticker.get(asset_id, "")
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
        
        tx_counts = Counter(r["Action"] for r in parse_transactions(data))
        print(f"\nTransactions ({len(parse_transactions(data))} total):")
        for action, n in sorted(tx_counts.items()):
            print(f"  {action:6s}  {n:4d} transactions")
    else:
        print("\nTransactions skipped (--holdings-only)")

    if preview:
        print("\n--- Holdings preview (first 10) ---")
        for r in rows[:10]:
            print(f"  {r['AssetClass']:8s}  {str(r['Ticker']):30s}  "
                  f"Qty:{r['Qty']:<10}  Value:{r['Value']:>12,.2f}  {r['Name'][:40]}")
        return

    sheets = SheetsClient()

    # Write holdings
    if not holdings_only:
        print(f"\nWriting {len(rows)} holdings to Holdings table...")
        for r in rows:
            sheets.upsert_holding(r)
        print(f"  Written {len(rows)} holdings successfully.")

    # Write transactions
    if not ledger_only:
        id_to_ticker  = {r["Ticker"]: r["AssetClass"] for r in rows}
        
        def parse_transactions(data: dict) -> list[dict]:
            """Map transactions to Ledger schema."""
            ledger = []
            for tx in data.get("transactions", []):
                asset_id = tx.get("assetId")
                ticker   = id_to_ticker.get(asset_id, f"ASSET-{asset_id}")
                aclass   = id_to_ticker.get(asset_id, "")
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

        ledger_rows = parse_transactions(data)
        print(f"\nWriting {len(ledger_rows)} transactions to Ledger table...")
        from core.database import bulk_insert_ledger
        bulk_insert_ledger(ledger_rows)
        print(f"  Written {len(ledger_rows)} transactions successfully.")

    print("\nImport complete. Go to Portfolio page → Refresh Prices to update current values.")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--preview",      action="store_true")
    p.add_argument("--ledger-only",  action="store_true")
    p.add_argument("--holdings-only",action="store_true")
    args = p.parse_args()
    main(preview=args.preview, ledger_only=args.ledger_only, holdings_only=args.holdings_only)