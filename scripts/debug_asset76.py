import json
data = json.load(open('portfolio-backup-2026-01-14.json'))

# Get asset 76
for a in data.get('assets', []):
    if a.get('id') == 76:
        print(f"Asset 76: {a}")
        break

# Check transactions for asset 76
print("\nTransactions for asset 76:")
for tx in data.get('transactions', []):
    if tx.get('assetId') == 76:
        print(f"  {tx}")