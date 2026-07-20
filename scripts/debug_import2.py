import sys
sys.path.insert(0, 'scripts')
from import_portfolio import parse_transactions, parse_assets, classify_stock
import json

data = json.load(open('portfolio-backup-2026-01-14.json'))
rows = parse_assets(data)

print('Parsed assets:', len(rows))
print('First 3 assets:')
for r in rows[:3]:
    print(f'  id={r["id"]}, Ticker={r["Ticker"]}, AssetClass={r["AssetClass"]}')

# Build id_to_asset
id_to_asset = {r['id']: r for r in rows}

# Test first 5 transactions
print('\nTesting first 5 transactions:')
for tx in data.get('transactions', [])[:5]:
    asset_id = tx.get('assetId')
    asset_data = id_to_asset.get(asset_id)
    print(f'  assetId={asset_id}, asset_data={asset_data}')

# Now test parse_transactions
print('\nTesting parse_transactions:')
ledger = parse_transactions(data, id_to_asset)
print(f'  Total: {len(ledger)}')
for t in ledger[:5]:
    print(f'  {t}')