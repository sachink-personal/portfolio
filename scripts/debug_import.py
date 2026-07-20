import json

data = json.load(open("portfolio-backup-2026-01-14.json"))
tx = data.get("transactions", [])
assets = data.get("assets", [])

# Build asset lookup
asset_lookup = {}
for a in assets:
    aid = a.get("id")
    asset_lookup[aid] = a

# Check first 5 transactions
for t in tx[:5]:
    aid = t.get("assetId")
    print(f"Transaction assetId={aid}")
    a = asset_lookup.get(aid)
    if a:
        print(f"  Found asset: {a.get('name')}")
        print(f"  Type: {a.get('type')}")
        print(f"  Symbol: {a.get('symbol')}")
        print(f"  schemeCode: {a.get('schemeCode')}")
    else:
        print(f"  Asset NOT FOUND!")

# Now let's check what the import script is producing
print("\n--- Testing the parse_transactions function ---")

def classify_stock(symbol):
    EQUITY_SYMBOLS = {"APLAPOLLO", "HINDALCO", "BSE", "JINDALSTEL"}
    sym = symbol.upper().replace(".NS", "").strip()
    if sym in EQUITY_SYMBOLS:
        return "EQUITY"
    return "ETF"

def _parse_date(raw):
    from datetime import datetime
    raw = str(raw).strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw

def parse_transactions(data, id_to_asset):
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
        
        ledger.append({
            "Date": _parse_date(tx.get("date", "")),
            "Ticker": ticker,
            "AssetClass": aclass,
            "Action": str(tx.get("type", "BUY")).upper(),
            "Qty": round(float(tx.get("units", 0) or 0), 4),
            "ExecPrice": round(float(tx.get("price", 0) or 0), 4),
            "TotalValue": round(float(tx.get("units", 0)) * float(tx.get("price", 0)), 2),
            "Charges": 0,
        })
    return ledger

# Build id_to_asset dict
id_to_asset = {}
for a in assets:
    id_to_asset[a.get("id")] = a

ledger = parse_transactions(data, id_to_asset)
print(f"Total transactions: {len(ledger)}")
print(f"First 5 transactions:")
for t in ledger[:5]:
    print(f"  Date: {t['Date']}, Ticker: '{t['Ticker']}', AssetClass: '{t['AssetClass']}'")