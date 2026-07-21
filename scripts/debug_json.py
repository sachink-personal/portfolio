import json
data = json.load(open('portfolio-backup-2026-01-14.json', encoding='utf-8'))
print(f"Total assets: {len(data.get('assets', []))}")
types = {}
for i, a in enumerate(data.get('assets', [])):
    typ = a.get('type')
    types[typ] = types.get(typ, 0) + 1
    sym = a.get('symbol')
    scheme = a.get('schemeCode')
    if not sym and not scheme:
        print(f"No symbol/scheme for index {i}: {a.get('name')}")
print("Type distribution:", types)

mfs_with_no_symbol = [a for a in data.get('assets', []) if a.get('type') == 'MF' and not a.get('symbol')]
print(f"MFs with no symbol: {len(mfs_with_no_symbol)}")
if mfs_with_no_symbol:
    print("Sample MF details:", mfs_with_no_symbol[0])
