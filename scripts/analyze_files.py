#!/usr/bin/env python
"""Analyze Screener and Chartink files to understand structure."""

import sys
sys.path.insert(0, '.')

import pandas as pd

# Load Screener.xlsx
print("=" * 80)
print("SCREENER.IN EXCEL ANALYSIS")
print("=" * 80)
try:
    df_screener = pd.read_excel('downloads/screener.xlsx')
    print(f"\nColumns: {df_screener.columns.tolist()}")
    print(f"Shape: {df_screener.shape}")
    print(f"\nFirst 3 rows:")
    print(df_screener.head(3).to_string())
    print(f"\nData types:")
    print(df_screener.dtypes)
except Exception as e:
    print(f"Error reading screener.xlsx: {e}")

# Load Chartink CSV
print("\n" + "=" * 80)
print("CHARTINK CSV ANALYSIS")
print("=" * 80)
try:
    df_chartink = pd.read_csv('downloads/for_Portfolio_7_13_2026.csv')
    print(f"\nColumns: {df_chartink.columns.tolist()}")
    print(f"Shape: {df_chartink.shape}")
    print(f"\nFirst 3 rows:")
    print(df_chartink.head(3).to_string())
    print(f"\nData types:")
    print(df_chartink.dtypes)
except Exception as e:
    print(f"Error reading CSV: {e}")
