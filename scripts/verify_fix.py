"""Verify AssetClass fix in Ledger table."""
import sqlite3
import json

conn = sqlite3.connect('portfolio.db')
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM Ledger')
print(f'Total transactions: {cursor.fetchone()[0]}')

cursor.execute('SELECT COUNT(*) FROM Ledger WHERE AssetClass IS NULL OR AssetClass = ""')
print(f'Empty AssetClass: {cursor.fetchone()[0]}')

# Check Holdings schema
cursor.execute("PRAGMA table_info(Holdings)")
print('\nHoldings table schema:')
for row in cursor.fetchall():
    print(f'  {row}')

# Check Holdings data
cursor.execute('SELECT * FROM Holdings LIMIT 5')
print('\nHoldings data (first 5 rows):')
for row in cursor.fetchall():
    print(f'  {row}')

# Check Ledger schema  
cursor.execute("PRAGMA table_info(Ledger)")
print('\nLedger table schema:')
for row in cursor.fetchall():
    print(f'  {row}')

# Check Ledger data
cursor.execute('SELECT * FROM Ledger LIMIT 5')
print('\nLedger data (first 5 rows):')
for row in cursor.fetchall():
    print(f'  {row}')

conn.close()

# Check JSON data
with open('portfolio-backup-2026-01-14.json') as f:
    data = json.load(f)
print('\nJSON assets (first 5):')
for a in data.get('assets', [])[:5]:
    print(f'  id={a.get("id")}, symbol={a.get("symbol")}, type={a.get("type")}, name={a.get("name")}')

# Check assets with specific IDs
print('\nAssets with IDs 31-62:')
assets = data.get('assets', [])
for a in assets:
    aid = a.get('id')
    if aid and aid in list(range(31, 63)):
        print(f'  id={a.get("id")}, symbol={a.get("symbol")}, type={a.get("type")}, name={a.get("name")}')