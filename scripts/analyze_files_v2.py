#!/usr/bin/env python3
"""Analyze Screener and Chartink files."""

import sys
import os

# Change to the correct directory
os.chdir('d:/delete/portfolio_g')
sys.path.insert(0, '.')

try:
    import pandas as pd
    
    # Load Screener.xlsx
    print("=" * 80)
    print("SCREENER.IN EXCEL ANALYSIS")
    print("=" * 80)
    try:
        df_screener = pd.read_excel('downloads/screener.xlsx')
        print(f"\nShape: {df_screener.shape} rows x columns")
        print(f"\nColumns ({len(df_screener.columns)}):")
        for i, col in enumerate(df_screener.columns, 1):
            print(f"  {i}. {col}")
        print(f"\nFirst 2 rows:")
        print(df_screener.head(2).to_string())
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

    # Load Chartink file (try both xlsx and csv)
    print("\n" + "=" * 80)
    print("CHARTINK FILE ANALYSIS")
    print("=" * 80)
    
    # Try CSV first
    try:
        df_chartink = pd.read_csv('downloads/for_Portfolio_7_13_2026.csv')
        print(f"\nFile: for_Portfolio_7_13_2026.csv")
        print(f"Shape: {df_chartink.shape} rows x columns")
        print(f"\nColumns ({len(df_chartink.columns)}):")
        for i, col in enumerate(df_chartink.columns, 1):
            print(f"  {i}. {col}")
        print(f"\nFirst 2 rows:")
        print(df_chartink.head(2).to_string())
    except Exception as e:
        print(f"CSV Error: {e}")
    
    # Try xlsx
    try:
        df_chartink_xlsx = pd.read_excel('downloads/chartink.xlsx')
        print(f"\n\nFile: chartink.xlsx")
        print(f"Shape: {df_chartink_xlsx.shape} rows x columns")
        print(f"\nColumns ({len(df_chartink_xlsx.columns)}):")
        for i, col in enumerate(df_chartink_xlsx.columns, 1):
            print(f"  {i}. {col}")
        print(f"\nFirst 2 rows:")
        print(df_chartink_xlsx.head(2).to_string())
    except Exception as e:
        print(f"XLSX Error: {e}")

except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)
