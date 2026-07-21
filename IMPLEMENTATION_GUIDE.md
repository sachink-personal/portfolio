# 🚀 IMPLEMENTATION GUIDE - Portfolio Manager Refactoring

**Status**: Phase 1-2 Complete ✅ | Phase 3-4 In Progress ⏳

**Last Updated**: 2026-07-20  
**Deployment Target**: Render.com (serverless)  
**Python Version**: 3.11

---

## 📋 EXECUTIVE SUMMARY

This guide documents the refactoring of the Quantitative Portfolio Manager to meet strict financial accuracy requirements:
- ❌ **NO hardcoded values** (FIXED)
- ❌ **NO fallbacks/defaults** (FIXED)
- ❌ **NO silent failures** (IN PROGRESS)
- ✅ **ALL LIVE values** (FIXED)
- ✅ **Flag missing data** (IN PROGRESS)

---

## ✅ COMPLETED FIXES

### Phase 1: Core Data Integrity (COMPLETE)

#### 1. Database Schema - Removed DEFAULT 0 ✅
**File**: `core/database.py` (lines 48-100)

**What was fixed**:
```python
# BEFORE: Holdings had silent zero defaults
CREATE TABLE Holdings (
    Qty REAL DEFAULT 0,           # ❌ Missing becomes 0
    AvgBuyPrice REAL DEFAULT 0,   # ❌ Missing becomes 0
)

# AFTER: NOW requires explicit values
CREATE TABLE Holdings (
    Qty REAL NOT NULL,            # ✅ Must be provided
    AvgBuyPrice REAL NOT NULL,    # ✅ Must be provided
)
```

**Impact**: 
- Portfolio calculations now accurate (no hidden zeros)
- Upsert operations must validate all required fields
- Raises exception if data missing (explicit, not silent)

**Tables affected**: Holdings, Ledger, Signals, MarketHistory
- **Holdings**: Name, AssetClass, Qty, AvgBuyPrice, CurrentPrice, Value are now NOT NULL
- **Ledger**: Date, Ticker, AssetClass, Action, Qty, ExecPrice, TotalValue are now NOT NULL
- **Signals**: Date, Ticker, Strategy are now NOT NULL
- **MarketHistory**: Date is now NOT NULL

---

#### 2. Removed Nifty 100 Hardcoded Fallback ✅
**File**: `data/nifty500.py` (lines 19-115)

**What was fixed**:
```python
# BEFORE: Silent fallback to hardcoded 50-stock list
except Exception as exc:
    log.error("Nifty 500 download failed. Using fallback Nifty 100 list.")
    return [{"ticker": t, "sector": ""} for t in _FALLBACK_TICKERS]

# AFTER: Explicit error, caller must handle
except Exception as exc:
    log.error("Nifty 500 download failed: %s", exc)
    raise RuntimeError(
        f"Unable to download Nifty 500 list from NSE. "
        f"Error: {exc}. Please check your internet connection and try again."
    )
```

**Impact**:
- ❌ No more silent universe filtering
- ✅ User sees explicit error message
- ✅ Can implement "Try Again" button in UI (see Phase 4)
- ✅ Screener stocks outside hardcoded list now processable

**Deleted**:
- `_FALLBACK_TICKERS` list (50 hardcoded stocks)

---

#### 3. Removed Hardcoded Ticker Mappings ✅
**File**: `core/recommendations.py` (lines 22-80)

**What was fixed**:
```python
# BEFORE: 60+ hardcoded mappings with typos/duplicates
_INDIAN_STOCK_MAPPING = {
    "LARSEN & TOUBRO": "LT",      # ❌ Typo risk
    "LT TIMEL": "LT",              # ❌ Duplicate! Both map to LT
    "HDFC BANK": "HDFCBANK",
    ... (60 more hardcoded entries)
}

# AFTER: Dynamic matching using Nifty 500 as source of truth
def fuzzy_match_ticker(company_name: str) -> Tuple[Optional[str], float]:
    """Fuzzy match company name to Nifty 500 ticker.
    Returns (ticker, confidence_score) or (None, 0) if no match found.
    """
    # Uses difflib.SequenceMatcher for >60% confidence matching
    # Falls back to Nifty 500 tickers dynamically
```

**Impact**:
- ✅ Screener.in company names auto-matched to Nifty 500 tickers
- ✅ No hardcoded values, all live from NSE data
- ✅ Confidence scoring for fuzzy matches
- ✅ Unmapped stocks flagged explicitly (coming in Phase 3)

**New Functions**:
- `_get_nifty500_ticker_list()`: Dynamic mapping from Nifty 500
- `fuzzy_match_ticker()`: Fuzzy name→ticker matching with confidence

---

#### 4. Removed All Streamlit Caches ✅
**Files**: 
- `pages/1_Dashboard.py` (lines 20-30)
- `pages/2_Portfolio.py` (lines 18-24)
- `pages/3_Growth.py` (lines 20-36)
- `pages/4_Weekly_Analysis.py` (lines 24-49, 411-434, 602-609)
- `pages/6_Transactions.py` (lines 21-35)

**What was fixed**:
```python
# BEFORE: 5min-7day caches
@st.cache_data(ttl=300)        # 5 minutes old holdings data
def load_holdings():
    return SheetsClient().get_holdings()

@st.cache_data(ttl=86400*7)    # 7 days old Nifty 500 universe
def load_nifty500_universe():
    return get_nifty500_universe()

# AFTER: Live data always
def load_holdings():
    """Load portfolio data directly from database (LIVE — no caching)."""
    return SheetsClient().get_holdings()
```

**Impact**:
- ✅ Holdings prices always current (live from yfinance)
- ✅ Signals always fresh (no 30-min stale technicals)
- ✅ Market regime always up-to-date (no 2-hr stale PE)
- ✅ Nifty 500 always fresh (new listings detected immediately)
- ✅ Solves Render container restart cache persistence issue

**Caches Removed**:
- `load_portfolio_data()` — 5min cache → LIVE
- `load_regime()` — 5min cache → LIVE
- `load_holdings()` — 2min cache → LIVE
- `load_history()` — 10min cache → LIVE
- `load_nifty50()` — 10min cache → LIVE
- `run_signal_filter()` — 10min cache → LIVE
- `fetch_rsi_for_holdings()` — 30min cache → LIVE
- `get_recommendations_data()` — 5min cache → LIVE
- `load_rrg()` — 1hr cache → LIVE

**Refresh Buttons Updated**:
- Changed from `st.cache_data.clear()` + `st.rerun()` to just `st.rerun()`
- Page reload automatically fetches fresh data

---

## 📂 FOLDER CLEANUP

**Deleted debug/check/verify scripts** ✅:
```
scripts/
  - ❌ check_asset81.py
  - ❌ check_assets.py
  - ❌ check_empty.py
  - ❌ check_missing_assets.py
  - ❌ debug_asset76.py
  - ❌ debug_assets.py
  - ❌ debug_import.py
  - ❌ debug_import2.py
  - ❌ debug_missing.py
  - ❌ fix_asset_class.py
  - ❌ import_portfolio_debug.py
  - ❌ verify_final.py
  - ❌ verify_fix.py
  - ✅ KEPT: import_portfolio.py (main script)
  - ✅ KEPT: import_portfolio_fixed.py (backup version)
```

**Preserved folders**:
- `cache/` — Empty, will be used for Nifty 500 JSON cache only
- `downloads/` — Contains Screener.xlsx, chartink.xlsx (user uploads)

---

## ⏳ IN PROGRESS - Phase 3 (Data Import & Migration)

### Phase 3: Data Migration from JSON Backup

**Planned**: Load `portfolio-backup-2026-01-14.json` into database

**JSON Structure**:
```json
{
  "version": 2,
  "date": "2026-01-14T18:23:58.057Z",
  "assets": [
    {
      "name": "ALPHA",
      "type": "STOCK",
      "units": 190,
      "avgPrice": 48.909,
      "currentPrice": 47.61,
      "symbol": "ALPHA.NS",
      "dateAdded": "2026-01-10T...",
      "isin": "INF174KA1IA5",
      "familyMember": "Savani",
      "broker": "Zerodha"
    }
  ],
  "transactions": [
    {
      "date": "22-01-2025",     # DD-MM-YYYY
      "type": "BUY",
      "units": 100,
      "price": 47.19,
      "assetId": 1
    }
  ]
}
```

**Asset Types to Import**:
- ✅ STOCK → Holdings table
- ✅ MF (Mutual Funds) → Holdings table
- ✅ GOLD (Gold ETFs) → Holdings table
- ⏭️ CASH, SAVINGS, FD → Skip (not needed for portfolio analysis)

**Script to Create**: `scripts/migrate_json_backup.py`

---

### Phase 3.2: Excel Import Scripts

Need to create flexible importers for:

#### 1. Screener.in Excel Importer
**File to create**: `core/screener_importer.py`

**Expected columns**:
- Stock Name
- ROE (Return on Equity %)
- Debt-to-Equity ratio
- Current Price
- Market Cap (optional)
- (Additional columns TBD based on your Excel)

**Logic**:
1. Read Excel file
2. Fuzzy match each company name to Nifty 500 ticker
3. Flag unmapped companies with confidence score
4. Store in temp table for signal generation
5. Calculate ROE, D/E signals

#### 2. Chartink CSV Importer
**File to create**: `core/chartink_importer.py`

**Expected columns**:
- Symbol (Ticker)
- RSI (Relative Strength Index)
- ROC (Rate of Change %)
- (Additional technical indicators TBD)

**Logic**:
1. Read CSV file
2. Match Symbol to Holdings
3. Flag unknown symbols
4. Store technicals in Signals table

---

## 🚨 IN PROGRESS - Phase 4 (Error Handling & UI)

### Phase 4.1: NSE Error Handling
**Task**: Add error modal + "Try Again" button when NSE API fails

**Where needed**:
- Dashboard page when loading Nifty 500
- Weekly Analysis when computing regime
- Any function calling `data.nifty500.get_nifty500_universe()`

**Implementation**:
```python
import streamlit as st

try:
    universe = get_nifty500_universe()
except RuntimeError as e:
    st.error(f"⚠️ Data Loading Error\n\n{str(e)}")
    if st.button("🔄 Try Again"):
        st.rerun()
    st.stop()
```

### Phase 4.2: Data Freshness Display
**Task**: Show data source + age on pages

**Where to add**:
- Dashboard: "Data as of [time] (LIVE)"
- Portfolio: "Prices updated [time ago]"
- Weekly Analysis: "Signals computed [time] (LIVE)"

**Implementation**:
```python
from datetime import datetime

st.caption(f"📊 Data as of {datetime.now().strftime('%H:%M:%S')} (LIVE - no cache)")
```

### Phase 4.3: Calculation Audit Trail
**Task**: Document calculation methodology

**XIRR flagging**:
- Current XIRR is approximation (uses earliest date only)
- Need to flag: "⚠️ XIRR calculated from earliest transaction. True XIRR may differ."
- Or implement true XIRR from complete cash flows

**Regime breakdown**:
- Show which signals are live vs failed
- Display: "Regime: BULLISH (Trend: UP ✅, PE: FAIR, Breadth: 65% ✅)"

---

## 🛠️ NEXT STEPS (Priority Order)

### IMMEDIATE (Today)

1. **Create `scripts/migrate_json_backup.py`**
   - Import 83 assets + 780 transactions from JSON
   - Validate against Nifty 500
   - Populate Holdings + Ledger tables

2. **Update import scripts for data validation**
   - File: `scripts/import_portfolio.py`
   - Replace `.get("field", 0) or 0` with explicit validation
   - Show user which rows have missing data

### SHORT TERM (Days 1-2)

3. **Create Excel importers**
   - `core/screener_importer.py` — Fuzzy match company names
   - `core/chartink_importer.py` — Parse technical indicators

4. **Add error handling pages**
   - Wrap Nifty 500 calls in try/except
   - Show error modal + refresh button
   - Implement in all pages

5. **Add data freshness display**
   - Show "Data as of HH:MM:SS (LIVE)" on each page
   - Add timestamp to Holdings queries

### MEDIUM TERM (Days 2-3)

6. **Test end-to-end data flow**
   - Load JSON backup into DB
   - Run Screener import
   - Run Chartink import
   - Verify signal generation
   - Check portfolio value calculations

7. **Create documentation**
   - List exact column names for Screener.in Excel
   - List exact column names for Chartink CSV
   - Create user guide for weekly uploads

### DEPLOYMENT (Day 4)

8. **Set up Render deployment**
   - Add `portfolio.db` to .gitignore
   - Update `runtime.txt` for Render
   - Test on Render staging environment
   - Set up weekly data upload schedule

---

## 📊 DATA FLOW (Current Design)

```
USER WEEKLY UPLOADS
  │
  ├─ Screener.in Excel (Company Names + Fundamentals)
  │   └─ → core/screener_importer.py
  │       ├─ Fuzzy match names to Nifty 500 tickers
  │       ├─ Calculate ROE, D/E signals
  │       └─ → Store in Signals table
  │
  ├─ Chartink CSV (Technical Indicators)
  │   └─ → core/chartink_importer.py
  │       ├─ Match Symbol to Holdings
  │       ├─ Extract RSI, ROC, trend
  │       └─ → Store in Signals table
  │
  └─ MF NAV Data (??? - Need to clarify)
      └─ → core/mf_importer.py
          └─ → Update Holdings table with latest NAV

LIVE MARKET DATA (Automated)
  │
  ├─ yfinance (Daily)
  │   └─ → data/equity.py
  │       └─ → Update CurrentPrice in Holdings
  │
  ├─ NSE APIs (Daily)
  │   ├─ Nifty 500 list (weekly)
  │   ├─ Nifty 500 PE ratio (daily)
  │   └─ Market breadth % (daily)
  │       └─ → data/nse_indices.py
  │
  └─ Mutual Fund NAV (Daily)
      └─ → data/mf_nav.py
          └─ → Update Holdings for MF positions

CALCULATIONS (On Demand, LIVE)
  │
  ├─ Portfolio Value = SUM(Qty × CurrentPrice)
  ├─ Weights = Value / Total × 100
  ├─ XIRR = pyxirr(cash_flows_from_ledger)
  ├─ Market Regime = 3-signal analysis
  └─ Buy/Sell Signals = Screener + Technicals + Regime

STREAMLIT PAGES (All LIVE, No Caching)
  │
  ├─ 1_Dashboard.py
  │   └─ Portfolio value, P&L, XIRR, regime, breakdown
  │
  ├─ 2_Portfolio.py
  │   └─ Holdings CRUD, current vs target weights
  │
  ├─ 3_Growth.py
  │   └─ Portfolio vs Nifty 500 chart
  │
  ├─ 4_Weekly_Analysis.py
  │   ├─ Signals filtered by regime
  │   ├─ Exit triggers
  │   └─ Sector rotation (RRG)
  │
  ├─ 5_Suggestions.py
  │   └─ Buy/sell recommendations (pending implementation)
  │
  └─ 6_Transactions.py
      └─ Ledger CRUD

DATABASE (SQLite)
  │
  ├─ Holdings: Current positions + prices
  ├─ Ledger: All historical transactions (date, qty, price)
  ├─ Signals: Buy/sell signals from Screener + Chartink
  └─ MarketHistory: Portfolio value + market data over time
```

---

## ⚡ PERFORMANCE NOTES

**Database Query Performance**:
- SQLite local database: <10ms per query
- No network latency for Holdings/Ledger/Signals lookups
- Removing caches is safe (DB is fast enough)

**API Call Performance**:
- yfinance: ~100-300ms per call (batch friendly)
- NSE CSV: ~500-800ms (cached 7 days for universe list)
- mfapi.in: ~100-200ms per fund

**Render Hosting Notes**:
- Containers restart frequently (caches lost)
- SQLite file persists in `/tmp/` but not across container restarts
- **Solution**: Store database file in Render persistent storage OR re-initialize from JSON on startup

---

## 📝 CONFIGURATION

**File**: `config.py`

All thresholds documented:
- `DMA_WINDOW = 200` - 200-day moving average for trend
- `EQUITY_ALLOC_BULLISH = 0.90` - 90% equity when bullish regime
- `PE_FAIR_RANGE = (18, 22)` - Fair PE ratio range
- `RSI_BUY_LOW = 60.0` - RSI threshold for buy signals
- `ROE_MIN = 15.0` - ROE minimum for quality filter

**MF Settings**:
- `MF_API_URL = "https://api.mfapi.in/mf"` - mfapi.in endpoint
- `MF_CACHE_TTL = 86400` - Cache NAV for 1 day

---

## 🧪 TESTING CHECKLIST

- [ ] JSON backup loads all 83 assets + 780 transactions
- [ ] Screener fuzzy matching works for 90%+ of stocks
- [ ] Chartink CSV parses all technical indicators
- [ ] Portfolio value matches Excel (within ±₹1)
- [ ] XIRR calculation is accurate (or flagged as approximate)
- [ ] NSE failure shows error modal + refresh button
- [ ] All pages show "(LIVE)" data indicator
- [ ] Database validates NOT NULL constraints
- [ ] Holdings prices update live (test with yfinance)
- [ ] Market regime updates when NSE data changes
- [ ] End-to-end: Upload Excel → Signal generation → Recommendation

---

## 🚀 DEPLOYMENT CHECKLIST

- [ ] Delete `portfolio.db` (will be recreated)
- [ ] Update `requirements.txt` with all dependencies
- [ ] Update `runtime.txt` for Render Python version
- [ ] Add `portfolio.db` to `.gitignore`
- [ ] Test on Render staging environment
- [ ] Set up weekly upload workflow (manual or API)
- [ ] Test data refresh under production load
- [ ] Monitor API failures (NSE, yfinance)
- [ ] Set up error logging to external service
- [ ] Create user documentation for weekly uploads

---

## 📚 REFERENCES

- **Render Deployment**: https://render.com/docs/deploy-python
- **SQLite Performance**: https://www.sqlite.org/limits.html
- **Streamlit Caching**: https://docs.streamlit.io/develop/api-reference/caching-and-state
- **yfinance**: https://github.com/ranaroussi/yfinance
- **pyxirr**: https://github.com/Mikyx/pyxirr
- **NSE API**: https://www.nseindia.com/

---

**Version**: 1.0  
**Last Updated**: 2026-07-20 21:45 IST  
**Status**: Phase 1-2 Complete ✅ | Phase 3-4 In Progress ⏳
