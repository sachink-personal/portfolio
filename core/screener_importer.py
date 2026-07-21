#!/usr/bin/env python3
"""
Screener.in Excel Importer
Parses Screener.in Excel exports and stores fundamental data in Signals table.
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
from core.recommendations import fuzzy_match_ticker

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def validate_screener_file(file_path):
    """Validate Screener Excel file exists and is readable."""
    if not Path(file_path).exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if not file_path.endswith('.xlsx'):
        raise ValueError(f"Expected Excel file (.xlsx), got: {file_path}")
    
    return True


def parse_screener_excel(file_path):
    """
    Parse Screener.in Excel file.
    
    Expected columns:
    - Name: Company name (will be fuzzy matched to ticker)
    - CMP Rs.: Current market price
    - ROE %: Return on Equity percentage
    - Mar Cap Rs.Cr.: Market Cap in Crores
    - Debt / Eq: Debt to Equity ratio
    - Sales Var 3Yrs %: 3-year sales growth
    - ROCE %: Return on Capital Employed
    - EPS Qtr Rs.: EPS for quarter
    - EPS Prev Qtr Rs.: EPS for previous quarter
    
    Returns:
        list of dict: Parsed data with ticker matched
    """
    
    logger.info(f"Parsing Screener Excel: {file_path}")
    
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        raise ValueError(f"Failed to read Excel file: {e}")
    
    # Normalize column names (remove non-breaking spaces and extra whitespace)
    df.columns = [col.replace('\xa0', ' ').strip() for col in df.columns]
    
    # Expected columns (using normalized names)
    required_cols = ['Name', 'CMP Rs.', 'ROE %', 'Debt / Eq']
    
    # Check required columns exist
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing columns: {missing_cols}\nFound: {df.columns.tolist()}")
    
    logger.info(f"Found {len(df)} stocks in Screener export")
    
    parsed_data = []
    errors = []
    
    for idx, row in df.iterrows():
        try:
            company_name = str(row['Name']).strip()
            
            if not company_name or company_name == 'nan':
                errors.append(f"Row {idx + 2}: Missing company name")
                continue
            
            # Fuzzy match name to ticker
            ticker, confidence = fuzzy_match_ticker(company_name)
            
            if not ticker:
                logger.warning(f"Row {idx + 2}: Could not match '{company_name}' to any Nifty 500 stock")
                errors.append(f"Row {idx + 2}: '{company_name}' - not found in Nifty 500")
                continue
            
            # Extract fundamentals
            try:
                roe = float(row['ROE %']) if pd.notna(row['ROE %']) else None
                de_ratio = float(row['Debt / Eq']) if pd.notna(row['Debt / Eq']) else None
                cmp = float(row['CMP Rs.']) if pd.notna(row['CMP Rs.']) else None
                market_cap = float(row['Mar Cap Rs.Cr.']) if pd.notna(row['Mar Cap Rs.Cr.']) else None
                
                # Optional columns - dynamic keyword matching
                sales_var = None
                roce = None
                eps_qtr = None
                sales_growth_3y = None  # alias for compatibility
                roce_3y = None  # alias for compatibility
                
                for col in df.columns:
                    col_lower = col.lower()
                    if 'sales' in col_lower and '3yr' in col_lower:
                        sales_var = float(row[col]) if pd.notna(row[col]) else None
                    elif 'roce' in col_lower:
                        roce = float(row[col]) if pd.notna(row[col]) else None
                    elif 'eps' in col_lower and 'prev' not in col_lower and 'qtr' in col_lower:
                        eps_qtr = float(row[col]) if pd.notna(row[col]) else None
                
            except (ValueError, TypeError) as e:
                errors.append(f"Row {idx + 2}: {company_name} - Invalid numeric values: {e}")
                continue
            
            # Validate key data
            if roe is None or de_ratio is None:
                errors.append(f"Row {idx + 2}: {company_name} - Missing ROE or D/E ratio")
                continue
            
            parsed_data.append({
                'ticker': ticker,
                'company_name': company_name,
                'confidence': confidence,
                'price': cmp,
                'roe': roe,
                'debt_to_equity': de_ratio,
                'market_cap': market_cap,
                'sales_growth_3y': sales_var,
                'roce': roce,
                'eps_qtr': eps_qtr,
                'source': 'Screener.in',
                'import_date': datetime.now().strftime('%Y-%m-%d')
            })
            
            logger.info(f"[OK] {company_name} -> {ticker} (confidence: {confidence:.2f})")
        
        except Exception as e:
            logger.error(f"Row {idx + 2}: Unexpected error: {e}")
            errors.append(f"Row {idx + 2}: {e}")
    
    return parsed_data, errors


def store_signals_in_db(parsed_data):
    """
    Store parsed Screener data as Signals in database.
    These signals can be used to generate buy/sell recommendations.
    """
    
    session = get_session()
    inserted = 0
    errors = []
    
    try:
        from sqlalchemy import text
        
        for data in parsed_data:
            try:
                # Create metadata JSON
                metadata = json.dumps({
                    'company_name': data['company_name'],
                    'confidence': data['confidence'],
                    'price': data['price'],
                    'sales_growth_3y': data['sales_growth_3y'],
                    'roce': data['roce'],
                    'eps_qtr': data['eps_qtr']
                })
                
                # Insert signal record (16 columns matching Signals table schema)
                # Note: Screener.in provides only fundamental data, technical columns (RSI_14D, 
                # ROC_6M, RSI_Weekly) will be NULL. Chartink handles technical data.
                session.execute(
                    text("""
                        INSERT INTO Signals 
                        (Date, Ticker, Strategy, AssetClass, Action, Source, CompanyName, 
                         ROC_6M, RSI_14D, RSI_Weekly, ROE, MarketCap, DebtToEquity, 
                         Sector, SubSector, Metadata)
                        VALUES (:date, :ticker, :strategy, :asset_class, :action, :source, 
                                :company_name, :return_6m, :rsi, :rsi_weekly, :roe, :market_cap, 
                                :de, :sector, :sub_sector, :metadata)
                    """),
                    {
                        'date': data['import_date'],
                        'ticker': data['ticker'],
                        'asset_class': 'EQUITY',
                        'action': 'ANALYZE',
                        'source': data['source'],
                        'company_name': data['company_name'],
                        'rsi': None,  # Screener doesn't provide RSI
                        'return_6m': None,  # Screener doesn't provide 6M return
                        'rsi_weekly': None,  # Screener doesn't provide weekly RSI
                        'roe': data['roe'],
                        'market_cap': data['market_cap'],
                        'de': data['debt_to_equity'],
                        'sub_sector': None,  # Screener doesn't provide sub-sector
                        'sector': None,  # Screener doesn't provide sector
                        'metadata': metadata,
                        'strategy': 'SCREENER_FUNDAMENTALS'
                    }
                )
                inserted += 1
                
            except Exception as e:
                errors.append(f"{data['ticker']}: {e}")
                logger.error(f"Failed to insert signal for {data['ticker']}: {e}")
        
        session.commit()
        logger.info(f"[OK] Stored {inserted} signals in database")
        
    except Exception as e:
        session.rollback()
        raise RuntimeError(f"Database commit failed: {e}")
    finally:
        session.close()
    
    return inserted, errors


def import_screener_excel(file_path):
    """
    Main function: Parse Screener Excel and store in database.
    
    Args:
        file_path (str): Path to Screener.xlsx file
    
    Returns:
        dict: Summary with inserted count, error count, and error messages
    """
    
    logger.info("=" * 80)
    logger.info("SCREENER.IN IMPORT")
    logger.info("=" * 80)
    
    # Validate file
    validate_screener_file(file_path)
    
    # Parse file
    parsed_data, parse_errors = parse_screener_excel(file_path)
    
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
    inserted, db_errors = store_signals_in_db(parsed_data)
    
    all_errors = parse_errors + db_errors
    
    result = {
        'status': 'SUCCESS' if inserted > 0 else 'FAILED',
        'inserted': inserted,
        'failed': len(all_errors),
        'errors': all_errors,
        'total_processed': len(parsed_data) + len(parse_errors)
    }
    
    logger.info("=" * 80)
    logger.info(f"RESULT: {inserted} signals stored, {len(all_errors)} errors")
    logger.info("=" * 80)
    
    return result