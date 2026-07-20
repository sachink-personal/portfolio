import json
data = json.load(open('portfolio-backup-2026-01-14.json'))

# Get asset IDs from transactions
tx_assets = set(tx['assetId'] for tx in data.get('transactions', []))
# Get asset IDs from assets
holdings_assets = set(a['id'] for a in data.get('assets', []))

print(f'Transaction asset IDs: {sorted(tx_assets)[:20]}...')
print(f'Holding asset IDs: {sorted(holdings_assets)}')

# Check assetId 20
print('\nAsset 20 from holdings:')
for a in data.get('assets', []):
    if a['id'] == 20:
        print(f"  {a}")
        break

# Check assetId 19
print('\nAsset 19 from holdings:')
for a in data.get('assets', []):
    if a['id'] == 19:
        print(f"  {a}")
        break

# Find transactions with assetId 20
print('\nTransactions with assetId 20:')
for tx in data.get('transactions', []):
    if tx['assetId'] == 20:
        print(f"  {tx}")