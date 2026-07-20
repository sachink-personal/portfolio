"""
Buy/Sell Recommendation Engine
Based on Quantitative Portfolio Management Engine Roadmap

Dual-Engine Architecture:
1. Defensive Shield - Determines max risk allowed (Market Regime)
2. Offensive Engine - Selects best assets when shield is clear

Recommendation Rules:
- Buy: ROC > 20%, RSI 60-75, ROE > 15%, D/E < 0.5
- Sell: ROC < 20%, RSI < 40, ROE < 15%, D/E > 0.5
"""

from __future__ import annotations

import io
import logging
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import config

log = logging.getLogger(__name__)


class BuySellRecommendation:
    """
    Generates buy/sell recommendations based on:
    - Market Regime (Defensive Shield)
    - Asset Technicals (Offensive Engine)
    - Asset Fundamentals (Quality)
    """
    
    def __init__(self):
        self.regime = None
        self.chartink_data = None
        self.screener_data = None
        self.holdings = None
    
    def set_regime(self, regime: Dict):
        """Set market regime from MarketRegime.get_full_regime()"""
        self.regime = regime
        return self
    
    def set_chartink_data(self, df: pd.DataFrame):
        """Set Chartink data (technical indicators)"""
        self.chartink_data = df
        return self
    
    def set_screener_data(self, df: pd.DataFrame):
        """Set Screener data (fundamentals)"""
        self.screener_data = df
        return self
    
    def set_holdings(self, holdings: pd.DataFrame):
        """Set current holdings"""
        self.holdings = holdings
        return self
    
    def _get_chartink_row(self, ticker: str) -> Optional[Dict]:
        """Get Chartink row for a ticker"""
        if self.chartink_data is None:
            return None
        
        # Try to find the ticker in the data
        ticker_upper = ticker.upper()
        df = self.chartink_data.copy()
        
        # Normalize column names for comparison
        def get_column(col_names):
            for col in col_names:
                if col in df.columns:
                    return col
            return None
        
        # Check for symbol column (various formats)
        symbol_col = get_column(['Symbol', 'Symbol Name', 'symbol', 'SYMBOL', 'symbol_name'])
        if symbol_col:
            df[symbol_col] = df[symbol_col].astype(str).str.upper()
            row = df[df[symbol_col] == ticker_upper]
            if not row.empty:
                return row.iloc[0].to_dict()
        
        return None
    
    def _get_screener_row(self, ticker: str) -> Optional[Dict]:
        """Get Screener row for a ticker"""
        if self.screener_data is None:
            return None
        
        ticker_upper = ticker.upper()
        df = self.screener_data.copy()
        
        # Normalize column names for comparison
        def get_column(col_names):
            for col in col_names:
                if col in df.columns:
                    return col
            return None
        
        # Check for symbol column (various formats)
        symbol_col = get_column(['Symbol', 'Symbol Name', 'symbol', 'SYMBOL', 'symbol_name'])
        if symbol_col:
            df[symbol_col] = df[symbol_col].astype(str).str.upper()
            row = df[df[symbol_col] == ticker_upper]
            if not row.empty:
                return row.iloc[0].to_dict()
        
        return None
    
    def _get_current_holdings_row(self, ticker: str) -> Optional[Dict]:
        """Get holdings row for a ticker"""
        if self.holdings is None:
            return None
        
        ticker_upper = ticker.upper()
        df = self.holdings.copy()
        
        # Check for 'Ticker' column
        if 'Ticker' in df.columns:
            df['Ticker'] = df['Ticker'].astype(str).str.upper()
            row = df[df['Ticker'] == ticker_upper]
            if not row.empty:
                return row.iloc[0].to_dict()
        
        # Check for 'symbol' column
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str).str.upper()
            row = df[df['symbol'] == ticker_upper]
            if not row.empty:
                return row.iloc[0].to_dict()
        
        return None
    
    def _check_defensive_shield(self) -> Tuple[bool, str]:
        """
        Defensive Shield Check
        Returns (is_safe, reason)
        """
        if self.regime is None:
            return True, "No regime data available"
        
        trend = self.regime.get('trend', {}).get('trend', 'UNKNOWN')
        valuation = self.regime.get('valuation', {}).get('valuation', 'UNKNOWN')
        breadth = self.regime.get('breadth', {}).get('status', 'UNKNOWN')
        
        # 1. Check 200-DMA Trend
        if trend == 'BEARISH':
            return False, "Market is BEARISH - 200-DMA filter failed"
        
        # 2. Check PE Ratio
        if valuation == 'OVERVALUED':
            return False, "Market is OVERVALUED - PE filter failed"
        
        # 3. Check Market Breadth
        breadth_pct = self.regime.get('breadth', {}).get('breadth_pct', 100)
        if breadth_pct < config.BREADTH_WARNING_THRESHOLD:
            return False, f"Market Breadth ({breadth_pct:.1f}%) below threshold ({config.BREADTH_WARNING_THRESHOLD}%)"
        
        return True, "Defensive Shield: CLEAR"
    
    def _check_buy_conditions(self, chartink_row: Dict, screener_row: Dict) -> Tuple[bool, List[str]]:
        """
        Check all buy conditions
        Returns (is_buy, reasons_list)
        """
        reasons = []
        
        # ROC Filter (> 20%)
        roc = chartink_row.get('ROC', chartink_row.get('roc', chartink_row.get('ROC_6M', 0)))
        if roc is not None and roc > 0:
            roc_pct = float(roc)
            if roc_pct >= config.ROC_MIN:
                reasons.append(f"ROC {roc_pct:.1f}% > {config.ROC_MIN}% ✓")
            else:
                return False, [f"ROC {roc_pct:.1f}% < {config.ROC_MIN}% ✗"]
        else:
            reasons.append("ROC N/A")
        
        # RSI Filter (60-75)
        rsi = chartink_row.get('rsi', chartink_row.get('RSI', chartink_row.get('RSI_Weekly', 0)))
        if rsi is not None:
            rsi_val = float(rsi)
            if config.RSI_BUY_LOW <= rsi_val <= config.RSI_BUY_HIGH:
                reasons.append(f"RSI {rsi_val:.1f} in buy zone ({config.RSI_BUY_LOW}-{config.RSI_BUY_HIGH}) ✓")
            else:
                return False, [f"RSI {rsi_val:.1f} outside buy zone ({config.RSI_BUY_LOW}-{config.RSI_BUY_HIGH}) ✗"]
        else:
            reasons.append("RSI N/A")
        
        # ROE Filter (> 15%)
        if screener_row:
            roe = screener_row.get('ROE', screener_row.get('roe', screener_row.get('ROE %', 0)))
            if roe is not None:
                roe_val = float(roe)
                if roe_val >= config.ROE_MIN:
                    reasons.append(f"ROE {roe_val:.1f}% > {config.ROE_MIN}% ✓")
                else:
                    return False, [f"ROE {roe_val:.1f}% < {config.ROE_MIN}% ✗"]
            else:
                reasons.append("ROE N/A")
        
        # Debt/Equity Filter (< 0.5)
        if screener_row:
            de = screener_row.get('Debt / Eq', screener_row.get('debt_to_equity', screener_row.get('D/E', 10)))
            if de is not None:
                de_val = float(de)
                if de_val <= config.DE_MAX:
                    reasons.append(f"D/E {de_val:.2f} < {config.DE_MAX} ✓")
                else:
                    return False, [f"D/E {de_val:.2f} > {config.DE_MAX} ✗"]
            else:
                reasons.append("D/E N/A")
        
        return True, reasons
    
    def _check_sell_conditions(self, holdings_row: Dict, chartink_row: Dict, screener_row: Dict) -> Tuple[bool, List[str]]:
        """
        Check sell conditions for existing holdings
        Returns (should_sell, reasons_list)
        """
        reasons = []
        
        # Check if current holding has weak momentum
        rsi = chartink_row.get('rsi', chartink_row.get('RSI', chartink_row.get('RSI_Weekly', 0)))
        if rsi is not None:
            rsi_val = float(rsi)
            if rsi_val < config.RSI_SELL:
                reasons.append(f"RSI {rsi_val:.1f} < {config.RSI_SELL} (SELL trigger) ✗")
                return True, reasons
        
        return False, reasons
    
    def generate_recommendations(self) -> Dict:
        """
        Generate comprehensive buy/sell recommendations
        """
        recommendations = {
            'buy_suggestions': [],
            'sell_recommendations': [],
            'hold_recommendations': [],
            'defensive_shield_status': 'UNKNOWN',
            'defensive_shield_reason': '',
            'market_regime': self.regime
        }
        
        # Check defensive shield first
        is_safe, shield_reason = self._check_defensive_shield()
        recommendations['defensive_shield_status'] = 'CLEAR' if is_safe else 'TRIGGERED'
        recommendations['defensive_shield_reason'] = shield_reason
        
        # Get all tickers from chartink and holdings
        all_tickers = set()
        
        if self.chartink_data is not None:
            if 'Symbol' in self.chartink_data.columns:
                all_tickers.update(self.chartink_data['Symbol'].dropna().astype(str).str.upper())
            if 'Symbol Name' in self.chartink_data.columns:
                all_tickers.update(self.chartink_data['Symbol Name'].dropna().astype(str).str.upper())
            if 'symbol' in self.chartink_data.columns:
                all_tickers.update(self.chartink_data['symbol'].dropna().astype(str).str.upper())
        
        if self.holdings is not None:
            if 'Ticker' in self.holdings.columns:
                all_tickers.update(self.holdings['Ticker'].dropna().astype(str).str.upper())
            if 'symbol' in self.holdings.columns:
                all_tickers.update(self.holdings['symbol'].dropna().astype(str).str.upper())
        
        # Process each ticker
        for ticker in all_tickers:
            ticker_upper = ticker.upper()
            
            chartink_row = self._get_chartink_row(ticker_upper)
            screener_row = self._get_screener_row(ticker_upper)
            holdings_row = self._get_current_holdings_row(ticker_upper)
            
            if chartink_row is None:
                continue
            
            # Get current price
            price = chartink_row.get('close', chartink_row.get('Close', chartink_row.get('price', 0)))
            if price is None:
                price = chartink_row.get('CMP', chartink_row.get('cmp', 0))
            
            is_buyable, buy_reasons = self._check_buy_conditions(chartink_row, screener_row)
            
            # Check if it's a new buy candidate
            if holdings_row is None:
                # Not a holding - check if it should be bought
                if is_buyable:
                    recommendations['buy_suggestions'].append({
                        'ticker': ticker_upper,
                        'price': price,
                        'reasons': buy_reasons,
                        'chartink_data': chartink_row,
                        'screener_data': screener_row
                    })
            else:
                # It's a holding - check if it should be sold
                is_sellable, sell_reasons = self._check_sell_conditions(holdings_row, chartink_row, screener_row)
                
                if is_sellable:
                    recommendations['sell_recommendations'].append({
                        'ticker': ticker_upper,
                        'price': price,
                        'reasons': sell_reasons,
                        'chartink_data': chartink_row,
                        'screener_data': screener_row,
                        'holdings_data': holdings_row
                    })
                else:
                    # Check if it should be held or upgraded
                    recommendations['hold_recommendations'].append({
                        'ticker': ticker_upper,
                        'price': price,
                        'reasons': buy_reasons if is_buyable else ['Holding maintained'],
                        'chartink_data': chartink_row,
                        'screener_data': screener_row,
                        'holdings_data': holdings_row
                    })
        
        # Sort buy suggestions by ROC (best first)
        recommendations['buy_suggestions'].sort(
            key=lambda x: x.get('chartink_data', {}).get('ROC', 0),
            reverse=True
        )
        
        # Sort sell recommendations by RSI (worst first)
        recommendations['sell_recommendations'].sort(
            key=lambda x: x.get('chartink_data', {}).get('rsi', 100)
        )
        
        return recommendations
    
    def get_summary(self, recommendations: Dict) -> str:
        """Generate a human-readable summary of recommendations"""
        lines = []
        lines.append("=" * 60)
        lines.append("QUANTITATIVE BUY/SELL RECOMMENDATIONS")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Defensive Shield: {recommendations['defensive_shield_status']}")
        lines.append(f"Reason: {recommendations['defensive_shield_reason']}")
        lines.append("")
        
        if recommendations['defensive_shield_status'] == 'TRIGGERED':
            lines.append("⚠️  MARKET REGIME IS DEFENSIVE - NO NEW BUYINGS")
            lines.append("")
        
        lines.append(f"BUY SUGGESTIONS: {len(recommendations['buy_suggestions'])}")
        lines.append("-" * 40)
        
        for item in recommendations['buy_suggestions'][:10]:  # Top 10
            ticker = item['ticker']
            price = item.get('price', 'N/A')
            reasons = item.get('reasons', [])
            roc = item.get('chartink_data', {}).get('ROC', item.get('chartink_data', {}).get('roc', 'N/A'))
            rsi = item.get('chartink_data', {}).get('rsi', item.get('chartink_data', {}).get('RSI', 'N/A'))
            roe = item.get('screener_data', {}).get('ROE', item.get('screener_data', {}).get('ROE %', 'N/A'))
            de = item.get('screener_data', {}).get('Debt / Eq', item.get('screener_data', {}).get('D/E', 'N/A'))
            
            lines.append(f"  {ticker}: ₹{price}")
            lines.append(f"    ROC: {roc}%, RSI: {rsi}, ROE: {roe}%, D/E: {de}")
            for reason in reasons:
                lines.append(f"    {reason}")
            lines.append("")
        
        lines.append(f"SELL RECOMMENDATIONS: {len(recommendations['sell_recommendations'])}")
        lines.append("-" * 40)
        
        for item in recommendations['sell_recommendations']:
            ticker = item['ticker']
            price = item.get('price', 'N/A')
            reasons = item.get('reasons', [])
            rsi = item.get('chartink_data', {}).get('rsi', item.get('chartink_data', {}).get('RSI', 'N/A'))
            roe = item.get('screener_data', {}).get('ROE', item.get('screener_data', {}).get('ROE %', 'N/A'))
            
            lines.append(f"  {ticker}: ₹{price}")
            lines.append(f"    RSI: {rsi}, ROE: {roe}")
            for reason in reasons:
                lines.append(f"    {reason}")
            lines.append("")
        
        lines.append(f"HOLD RECOMMENDATIONS: {len(recommendations['hold_recommendations'])}")
        lines.append("-" * 40)
        
        for item in recommendations['hold_recommendations'][:10]:
            ticker = item['ticker']
            price = item.get('price', 'N/A')
            reasons = item.get('reasons', [])
            lines.append(f"  {ticker}: ₹{price}")
            for reason in reasons:
                lines.append(f"    {reason}")
            lines.append("")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)


def load_chartink_data(file_path: str = None, excel_bytes: bytes = None) -> pd.DataFrame:
    """Load Chartink data from file or bytes"""
    import os
    import io
    from pathlib import Path
    
    # Handle Excel files (from upload)
    if excel_bytes is not None:
        df = pd.read_excel(io.BytesIO(excel_bytes), engine='openpyxl')
        return _normalize_chartink_columns(df)
    
    # Handle file path
    if file_path is None:
        downloads_dir = Path(config.TICKERTAPE_DOWNLOADS_DIR)
        csv_files = [f for f in downloads_dir.glob("*.csv") if not f.name.startswith("~$")]
        excel_files = [f for f in downloads_dir.glob("*.xlsx") if not f.name.startswith("~$")]
        
        # Prefer Excel files over CSV
        if excel_files:
            file_path = str(excel_files[0])
        elif csv_files:
            file_path = str(csv_files[0])
    
    if file_path:
        # Determine file type and load appropriately
        if file_path.endswith('.xlsx'):
            df = pd.read_excel(file_path, engine='openpyxl')
            return _normalize_chartink_columns(df)
        else:
            df = pd.read_csv(file_path)
            return _normalize_chartink_columns(df)
    
    return pd.DataFrame()


def _normalize_chartink_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize Chartink column names to standard format"""
    if df.empty:
        return df
    
    # Create a copy to avoid modifying original
    df = df.copy()
    
    # Common column name variations
    column_mapping = {
        # Ticker/stock identifier columns
        'symbol': 'Symbol', 'SYMBOL': 'Symbol', 'Symbol Name': 'Symbol', 'SYMBOL NAME': 'Symbol',
        'symbol_name': 'Symbol', 'instrument': 'Symbol', 'instrument_name': 'Symbol',
        
        # ROC columns
        'roc_6m': 'ROC_6M', 'ROC 6M': 'ROC_6M', 'ROC': 'ROC_6M', 'roc': 'ROC_6M',
        '6 month roc': 'ROC_6M', 'roc_6m_percent': 'ROC_6M',
        
        # RSI columns
        'rsi_weekly': 'RSI_Weekly', 'rsi': 'RSI_Weekly', 'RSI': 'RSI_Weekly',
        'rsi_14': 'RSI_Weekly', 'rsi_14w': 'RSI_Weekly', 'weekly_rsi': 'RSI_Weekly',
        'rsi_14_weekly': 'RSI_Weekly',
    }
    
    # Apply column mapping
    new_columns = {}
    for col in df.columns:
        col_lower = str(col).lower().strip()
        if col_lower in column_mapping:
            new_columns[col] = column_mapping[col_lower]
        else:
            new_columns[col] = col
    
    df = df.rename(columns=new_columns)
    
    return df


def load_screener_data(file_path: str = None, excel_bytes: bytes = None) -> pd.DataFrame:
    """Load Screener data from file or bytes"""
    import os
    import io
    from pathlib import Path
    
    # Handle Excel files (from upload)
    if excel_bytes is not None:
        df = pd.read_excel(io.BytesIO(excel_bytes), engine='openpyxl')
        return _normalize_screener_columns(df)
    
    # Handle file path
    if file_path is None:
        downloads_dir = Path(config.TICKERTAPE_DOWNLOADS_DIR)
        excel_files = [f for f in downloads_dir.glob("*.xlsx") if not f.name.startswith("~$")]
        
        if excel_files:
            file_path = str(excel_files[0])
    
    if file_path:
        df = pd.read_excel(file_path, engine='openpyxl')
        return _normalize_screener_columns(df)
    
    return pd.DataFrame()


def _normalize_screener_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize Screener column names to standard format"""
    if df.empty:
        return df
    
    # Create a copy to avoid modifying original
    df = df.copy()
    
    # Common column name variations
    column_mapping = {
        # Ticker/stock identifier columns
        'symbol': 'Symbol', 'SYMBOL': 'Symbol', 'Symbol Name': 'Symbol', 'SYMBOL NAME': 'Symbol',
        'symbol_name': 'Symbol', 'instrument': 'Symbol', 'instrument_name': 'Symbol',
        
        # ROE columns
        'roe %': 'ROE %', 'ROE': 'ROE %', 'ROE%': 'ROE %', 'roe': 'ROE %',
        'return_on_equity': 'ROE %', 'return_on_equity_%': 'ROE %',
        
        # Debt/Equity columns
        'debt / eq': 'Debt / Eq', 'debt_to_equity': 'Debt / Eq', 'debt / equity': 'Debt / Eq',
        'debt/equity': 'Debt / Eq', 'de': 'Debt / Eq', 'd/e': 'Debt / Eq',
        'debt_to_eq': 'Debt / Eq', 'debt / equity_ratio': 'Debt / Eq',
    }
    
    # Apply column mapping
    new_columns = {}
    for col in df.columns:
        col_lower = str(col).lower().strip()
        if col_lower in column_mapping:
            new_columns[col] = column_mapping[col_lower]
        else:
            new_columns[col] = col
    
    df = df.rename(columns=new_columns)
    
    return df


def load_tickertape_data(file_path: str = None, excel_bytes: bytes = None) -> pd.DataFrame:
    """Load Tickertape data from file or bytes"""
    import os
    import io
    from pathlib import Path
    
    if excel_bytes is not None:
        return pd.read_excel(io.BytesIO(excel_bytes), engine='openpyxl')
    
    if file_path is None:
        downloads_dir = Path(config.TICKERTAPE_DOWNLOADS_DIR)
        excel_files = [f for f in downloads_dir.glob("*.xlsx") if not f.name.startswith("~$")]
        if excel_files:
            file_path = str(excel_files[0])
    
    if file_path:
        return pd.read_excel(file_path, engine='openpyxl')
    
    return pd.DataFrame()


def load_holdings_data() -> pd.DataFrame:
    """Load current holdings from database"""
    from core.sheets import SheetsClient
    sheets = SheetsClient()
    return sheets.get_holdings()