import json
data = json.load(open('portfolio-backup-2026-01-14.json'))

# Get asset 81
for a in data.get('assets', []):
    if a.get('id') == 81:
        print(f"Asset 81: {a}")
        break

# Check transactions for asset 81
print("\nTransactions for asset 81:")
for tx in data.get('transactions', []):
    if tx.get('assetId') == 81:
        print(f"  {tx}")