import sqlite3
conn = sqlite3.connect('portfolio.db')
cur = conn.cursor()

# Count total transactions
cur.execute('SELECT COUNT(*) FROM Ledger')
total = cur.fetchone()[0]
print(f'Total transactions: {total}')

# Count empty AssetClass
cur.execute('SELECT COUNT(*) FROM Ledger WHERE AssetClass = ""')
empty = cur.fetchone()[0]
print(f'Empty AssetClass: {empty}')

# Count by AssetClass
cur.execute('SELECT AssetClass, COUNT(*) FROM Ledger GROUP BY AssetClass')
print('\nBy AssetClass:')
for row in cur.fetchall():
    print(f'  {row}')

# First 10 transactions
cur.execute('SELECT Date, Ticker, AssetClass, Action FROM Ledger ORDER BY id LIMIT 10')
print('\nFirst 10 transactions:')
for row in cur.fetchall():
    print(f'  {row}')

conn.close()