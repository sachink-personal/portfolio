"""
Script to fix empty AssetClass values in the Ledger table.
Populates AssetClass by looking up tickers from the Holdings table.
"""
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "portfolio.db"

def get_holdings_map(db_path):
    """Get a dictionary mapping Ticker to AssetClass from Holdings table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT Ticker, AssetClass FROM Holdings WHERE AssetClass IS NOT NULL AND AssetClass != ''")
    holdings_map = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    logger.info(f"Found {len(holdings_map)} tickers with AssetClass in Holdings")
    return holdings_map

def fix_asset_class_in_ledger(db_path, holdings_map):
    """Update AssetClass in Ledger table based on Holdings mapping."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Find all ledger entries with empty AssetClass
    cursor.execute("SELECT id, Ticker FROM Ledger WHERE AssetClass IS NULL OR AssetClass = ''")
    rows_to_fix = cursor.fetchall()
    logger.info(f"Found {len(rows_to_fix)} ledger entries with empty AssetClass")
    
    updated = 0
    skipped = []
    
    for ledger_id, ticker in rows_to_fix:
        if ticker in holdings_map:
            asset_class = holdings_map[ticker]
            cursor.execute(
                "UPDATE Ledger SET AssetClass = ? WHERE id = ?",
                (asset_class, ledger_id)
            )
            updated += 1
        else:
            skipped.append((ledger_id, ticker))
    
    conn.commit()
    conn.close()
    
    logger.info(f"Updated {updated} ledger entries with AssetClass")
    if skipped:
        logger.warning(f"Skipped {len(skipped)} entries - ticker not found in Holdings")
        for ledger_id, ticker in skipped[:10]:
            logger.warning(f"  - id={ledger_id}, ticker={ticker}")
        if len(skipped) > 10:
            logger.warning(f"  ... and {len(skipped) - 10} more")
    
    return updated, skipped

def main():
    logger.info("Starting AssetClass fix...")
    holdings_map = get_holdings_map(DB_PATH)
    updated, skipped = fix_asset_class_in_ledger(DB_PATH, holdings_map)
    logger.info(f"Fix complete. Updated {updated} entries.")
    if skipped:
        logger.info(f"Note: {len(skipped)} tickers not found in Holdings - these need manual AssetClass assignment")

if __name__ == "__main__":
    main()