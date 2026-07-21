#!/usr/bin/env python
"""Check database contents after migration."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import get_holdings, get_ledger
import pandas as pd

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 150)

holdings = get_holdings()
ledger = get_ledger()

print(f"\n[OK] Holdings loaded: {len(holdings)} positions")
if len(holdings) > 0:
    print(f"  Total value: Rs. {holdings['Value'].sum():,.0f}")
    print(f"  Asset classes: {holdings['AssetClass'].unique().tolist()}")
    print("\nSample holdings (first 5):")
    print(holdings[['Ticker', 'Name', 'Qty', 'CurrentPrice', 'Value']].head())

print(f"\n[OK] Ledger loaded: {len(ledger)} transactions")
if len(ledger) > 0:
    print(f"  Buy transactions: {len(ledger[ledger['Action'] == 'BUY'])}")
    print(f"  Sell transactions: {len(ledger[ledger['Action'] == 'SELL'])}")
    if "Date" in ledger.columns:
        print(f"  Date range: {ledger['Date'].min()} to {ledger['Date'].max()}")
    print("\nSample transactions (first 3):")
    print(ledger[['Date', 'Ticker', 'Action', 'Qty', 'ExecPrice']].head())

print("\n" + "="*80)
