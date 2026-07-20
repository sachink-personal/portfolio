import json
data = json.load(open('portfolio-backup-2026-01-14.json'))

# Get asset IDs from transactions
tx_assets = set(tx['assetId'] for tx in data.get('transactions', []))
# Get asset IDs from assets
holdings_assets = set(a['id'] for a in data.get('assets', []))

# Find transactions that reference non-existent assets
missing = tx_assets - holdings_assets
print(f'Transaction asset IDs not in holdings: {sorted(missing)}')

# Show some transactions with those asset IDs
print('\nSample transactions with missing assets:')
for tx in data.get('transactions', []):
    if tx['assetId'] in missing:
        print(f"  assetId={tx['assetId']}, date={tx['date']}, type={tx['type']}, units={tx['units']}, price={tx['price']}")
        break