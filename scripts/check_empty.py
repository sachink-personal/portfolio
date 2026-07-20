import sqlite3
conn = sqlite3.connect('portfolio.db')
cur = conn.cursor()

# Get transactions with empty AssetClass
cur.execute('SELECT Date, Ticker, AssetClass, Action FROM Ledger WHERE AssetClass = "" ORDER BY id LIMIT 18')
print('Transactions with empty AssetClass:')
for row in cur.fetchall():
    print(f'  {row}')

conn.close()