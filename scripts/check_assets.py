import json
data = json.load(open('portfolio-backup-2026-01-14.json'))
for a in data.get('assets', []):
    if a.get('id', 0) >= 76:
        print(f"ID={a['id']}, name={a.get('name')}, symbol={a.get('symbol')}, units={a.get('units')}, value={a.get('value')}")