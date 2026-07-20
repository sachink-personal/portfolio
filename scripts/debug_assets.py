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

        # Skip zero-unit watchlist / placeholder entries
        if units == 0 and value == 0:
            print(f"  SKIPPED (zero units/value): {a.get('name')}")
            continue

        if atype == "STOCK":
            symbol = a.get("symbol", "").replace(".NS", "").strip().upper()
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
            })

    return rows


def parse_transactions(data: dict, id_to_asset: dict) -> list[dict]:
    ledger = []
    for tx in data.get("transactions", []):
        asset_id = tx.get("assetId")
        asset_data = id_to_asset.get(asset_id)
        if asset_data:
            symbol = asset_data.get("symbol", "")
            if symbol and symbol.strip():
                ticker = symbol.replace(".NS", "").strip().upper()
            else:
                ticker = str(asset_data.get("schemeCode", "")).strip()
            aclass = asset_data.get("type", "")
            if aclass == "STOCK":
                aclass = classify_stock(ticker)
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


# Main
data = json.load(open(JSON_FILE))
rows = parse_assets(data)

print(f"Assets parsed: {len(rows)}")
print(f"\nFirst 5 assets:")
for r in rows[:5]:
    print(f"  id={r['id']}, Ticker={r['Ticker']}, AssetClass={r['AssetClass']}")

# Build id_to_asset
id_to_asset = {r["id"]: r for r in rows}

print(f"\nid_to_asset keys (first 10): {list(id_to_asset.keys())[:10]}")

# Check what's in id_to_asset for id=1
print(f"\nid_to_asset.get(1): {id_to_asset.get(1)}")

# Check first transaction
tx = data.get("transactions", [])[0]
asset_id = tx.get("assetId")
print(f"\nFirst transaction assetId: {asset_id}")
print(f"id_to_asset.get({asset_id}): {id_to_asset.get(asset_id)}")