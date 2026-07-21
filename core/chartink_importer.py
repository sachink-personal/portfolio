#!/usr/bin/env python3
"""
Chartink CSV Importer
Parses Chartink CSV exports and stores technical analysis data in Signals table.
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import logging
import json

import pandas as pd

# Setup paths
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import get_session

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def validate_chartink_file(file_path):
    """Validate Chartink CSV file exists and is readable."""
    if not Path(file_path).exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if not file_path.endswith('.csv'):
        raise ValueError(f"Expected CSV file (.csv), got: {file_path}")
    
    return True


def get_holdings_tickers():
    """Get list of tickers from Holdings table for matching."""
    session = get_session()
    try:
        from sqlalchemy import text
        result = session.execute(text("SELECT Ticker FROM Holdings")).fetchall()
        return {row[0].upper() for row in result if row[0]}
    finally:
        session.close()


def normalize_ticker(ticker_str):
    """
    Normalize ticker symbol for matching.
    - Remove .NS, .BO suffixes
    - Convert to uppercase
    """
    if not ticker_str:
        return None
    
    ticker = str(ticker_str).strip().upper()
    
    # Remove NSE/BSE suffixes
    for suffix in ['.NS', '.BO', '.BSE', '.MCX']:
        if ticker.endswith(suffix):
            ticker = ticker[:-len(suffix)]
    
    return ticker


def parse_chartink_csv(file_path, holdings_tickers=None):
    """
    Parse Chartink CSV file.
    
    Expected columns (Flexible matching):
    - Name: Company name
    - Ticker: Stock ticker symbol
    - RSI – 14D: 14-day RSI value (Required)
    - 6M Return: 6-month return %
    - Market Cap: Market capitalization
    - Return on Equity: ROE %
    - Debt to Equity: D/E ratio
    - Sub-Sector: Industry classification
    
    Returns:
        list of dict: Parsed data with validation
    """
    
    logger.info(f"Parsing Chartink CSV: {file_path}")
    
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        raise ValueError(f"Failed to read CSV file: {e}")
    
    # Expected required columns
    required_cols = ['Name', 'Ticker', 'RSI – 14D']
    
    # Check required columns exist
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing columns: {missing_cols}\nFound: {df.columns.tolist()}")
    
    logger.info(f"Found {len(df)} stocks in Chartink export")
    
    parsed_data = []
    errors = []
    
    if holdings_tickers is None:
        holdings_tickers = get_holdings_tickers()
    
    for idx, row in df.iterrows():
        try:
            company_name = str(row['Name']).strip()
            ticker_raw = str(row['Ticker']).strip()
            
            if not company_name or company_name == 'nan':
                errors.append(f"Row {idx + 2}: Missing company name")
                continue
            
            if not ticker_raw or ticker_raw == 'nan':
                errors.append(f"Row {idx + 2}: {company_name} - Missing ticker")
                continue
            
            # Normalize ticker
            ticker = normalize_ticker(ticker_raw)
            
            if not ticker:
                errors.append(f"Row {idx + 2}: {company_name} - Invalid ticker format: {ticker_raw}")
                continue
            
            # Check if ticker exists in holdings
            in_holdings = ticker in holdings_tickers
            
            if not in_holdings:
                logger.warning(f"Row {idx + 2}: Ticker {ticker} not in current holdings")
            
            # Extract indicators with dynamic keyword matching
            try:
                # Mandatory
                rsi = float(row['RSI – 14D']) if pd.notna(row['RSI – 14D']) else None
                
                # Optional indicators with keyword matching
                return_6m = None
                rsi_weekly = None  # Weekly RSI from Chartink
                market_cap = None
                roe = None
                de_ratio = None
                sub_sector = None
                sector = None  # Sector from Chartink
                
                for col in df.columns:
                    col_lower = col.lower()
                    if '6m return' in col_lower:
                        return_6m = float(row[col]) if pd.notna(row[col]) else None
                    elif 'rsi' in col_lower and 'weekly' in col_lower:
                        rsi_weekly = float(row[col]) if pd.notna(row[col]) else None
                    elif 'market cap' in col_lower:
                        market_cap = float(row[col]) if pd.notna(row[col]) else None
                    elif 'return on equity' in col_lower:
                        roe = float(row[col]) if pd.notna(row[col]) else None
                    elif 'debt to equity' in col_lower:
                        de_ratio = float(row[col]) if pd.notna(row[col]) else None
                    elif 'sub-sector' in col_lower:
                        sub_sector = str(row[col]).strip() if pd.notna(row[col]) else None
                    elif col_lower in ('sector', 'industry'):
                        sector = str(row[col]).strip() if pd.notna(row[col]) else None
                
            except (ValueError, TypeError) as e:
                errors.append(f"Row {idx + 2}: {company_name} ({ticker}) - Invalid numeric values: {e}")
                continue
            
            # Validate RSI (must be 0-100)
            if rsi is not None and not (0 <= rsi <= 100):
                errors.append(f"Row {idx + 2}: {company_name} ({ticker}) - Invalid RSI value: {rsi}")
                continue
            
            if rsi is None:
                errors.append(f"Row {idx + 2}: {company_name} ({ticker}) - Missing RSI value")
                continue
            
            parsed_data.append({
                'ticker': ticker,
                'company_name': company_name,
                'rsi_14d': rsi,
                'rsi_weekly': rsi_weekly,  # Weekly RSI (now captured from CSV)
                'return_6m': return_6m,
                'market_cap': market_cap,
                'roe': roe,
                'debt_to_equity': de_ratio,
                'sub_sector': sub_sector,
                'sector': sector,  # Sector (now captured from CSV)
                'source': 'Chartink',
                'import_date': datetime.now().strftime('%Y-%m-%d'),
                'in_holdings': in_holdings
            })
            
            logger.info(f"✓ {company_name} ({ticker}) - RSI: {rsi:.2f}")
        
        except Exception as e:
            logger.error(f"Row {idx + 2}: Unexpected error: {e}")
            errors.append(f"Row {idx + 2}: {e}")
    
    return parsed_data, errors


def store_signals_in_db(parsed_data):
    """
    Store parsed Chartink data as Signals in database.
    These signals contain technical analysis data for buy/sell decisions.
    """
    
    session = get_session()
    inserted = 0
    errors = []
    not_in_holdings = 0
    
    try:
        from sqlalchemy import text
        
        for data in parsed_data:
            try:
                # Generate action based on RSI
                rsi = data['rsi_14d']
                if rsi < 30:
                    action = 'OVERSOLD'  # Potential buy
                elif rsi > 70:
                    action = 'OVERBOUGHT'  # Potential sell
                else:
                    action = 'NEUTRAL'
                
                # Create metadata JSON
                metadata = json.dumps({
                    'company_name': data['company_name'],
                    'sub_sector': data['sub_sector'],
                    'rsi_14d': data['rsi_14d'],
                    'return_6m': data['return_6m'],
                    'market_cap': data['market_cap'],
                    'roe': data['roe'],
                    'debt_to_equity': data['debt_to_equity']
                })
                
                # Insert signal record
                session.execute(
                    text("""
                        INSERT INTO Signals 
                        (Date, Ticker, AssetClass, Action, Source, CompanyName, RSI_14D, 
                         ROC_6M, RSI_Weekly, ROE, MarketCap, DebtToEquity, SubSector, Sector, 
                         Metadata, Strategy)
                        VALUES (:date, :ticker, :asset_class, :action, :source, :company_name,
                                :rsi, :return_6m, :rsi_weekly, :roe, :market_cap, :de, :sub_sector, 
                                :sector, :metadata, :strategy)
                    """),
                    {
                        'date': data['import_date'],
                        'ticker': data['ticker'],
                        'asset_class': 'EQUITY',
                        'action': action,
                        'source': data['source'],
                        'company_name': data['company_name'],
                        'rsi': data['rsi_14d'],
                        'return_6m': data['return_6m'],
                        'rsi_weekly': data.get('rsi_weekly'),
                        'roe': data['roe'],
                        'market_cap': data['market_cap'],
                        'de': data['debt_to_equity'],
                        'sub_sector': data['sub_sector'],
                        'sector': data.get('sector'),
                        'metadata': metadata,
                        'strategy': 'CHARTINK_TECHNICALS'
                    }
                )
                inserted += 1
                
                if not data['in_holdings']:
                    not_in_holdings += 1
                
            except Exception as e:
                errors.append(f"{data['ticker']}: {e}")
                logger.error(f"Failed to insert signal for {data['ticker']}: {e}")
        
        session.commit()
        logger.info(f"[OK] Stored {inserted} signals in database")
        
        if not_in_holdings > 0:
            logger.warning(f"[WARN] {not_in_holdings} stocks not in current holdings (stored as reference)")
        
    except Exception as e:
        session.rollback()
        raise RuntimeError(f"Database commit failed: {e}")
    finally:
        session.close()
    
    return inserted, errors, not_in_holdings


def import_chartink_csv(file_path):
    """
    Main function: Parse Chartink CSV and store in database.
    
    Args:
        file_path (str): Path to Chartink CSV file
    
    Returns:
        dict: Summary with inserted count, error count, and error messages
    """
    
    logger.info("=" * 80)
    logger.info("CHARTINK IMPORT")
    logger.info("=" * 80)
    
    # Validate file
    validate_chartink_file(file_path)
    
    # Parse file
    parsed_data, parse_errors = parse_chartink_csv(file_path)
    
    if not parsed_data:
        logger.error(f"No valid stocks found in {file_path}")
        return {
            'status': 'FAILED',
            'inserted': 0,
            'failed': len(parse_errors),
            'errors': parse_errors
        }
    
    logger.info(f"Successfully parsed {len(parsed_data)} stocks")
    
    # Store in database
    inserted, db_errors, not_in_holdings = store_signals_in_db(parsed_data)
    
    all_errors = parse_errors + db_errors
    
    result = {
        'status': 'SUCCESS' if inserted > 0 else 'FAILED',
        'inserted': inserted,
        'not_in_holdings': not_in_holdings,
        'failed': len(all_errors),
        'errors': all_errors,
        'total_processed': len(parsed_data) + len(parse_errors)
    }
    
    logger.info("=" * 80)
    logger.info(f"RESULT: {inserted} signals stored, {not_in_holdings} not in holdings, {len(all_errors)} errors")
    logger.info("=" * 80)
    
    return result