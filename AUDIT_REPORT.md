# 🚨 CRITICAL AUDIT REPORT: Financial Calculation Risk Assessment

**Date**: 2026-07-20  
**Hosting**: Render  
**Risk Level**: 🔴 **CRITICAL** - Calculation accuracy compromised

---

## EXECUTIVE SUMMARY

Your system violates **all 4 critical user requirements**:

| Requirement | Status | Issues Found |
|-------------|--------|--------------|
| ❌ **NO hardcoded values** | VIOLATED | 60+ hardcoded ticker mappings, 50 hardcoded fallback tickers |
| ❌ **NO fallbacks/defaults** | VIOLATED | Silent Nifty 100 fallback, DB defaults=0, silent null→0 conversions |
| ❌ **ALL LIVE values** | VIOLATED | 7-day caches, 2-hour PE cache, 5-minute widget caches |
| ❌ **Flag missing values** | VIOLATED | Missing data silently becomes 0, no warnings to user |

**Financial Impact**: Portfolio calculations may be off by **0-100%** if any price data is missing.

---

## 🔴 CRITICAL FINDINGS

### 1. FALLBACK NIFTY 500 LIST (Hidden Silently)
**File**: `data/nifty500.py:36-47, 110-112`

```python
_FALLBACK_TICKERS = [
    "RELIANCE", "TCS", "HDFCBANK", ... # 50 stocks hardcoded
]

except Exception as exc:
    log.error("Nifty 500 download failed (%s). Using fallback Nifty 100 list.", exc)
    return [{"ticker": t, "sector": ""} for t in _FALLBACK_TICKERS]
```

**Problems**:
- ✗ If NSE API fails → silently switches to hardcoded 50-stock list
- ✗ Portfolio screened against wrong universe
- ✗ **Stocks outside hardcoded list NEVER screened**
- ✗ No warning to user on dashboard
- ✗ User unaware portfolio is incomplete

**Scenario**: NSE API unavailable → Your emerging market position never analyzed

**Status**: ❌ **VIOLATES**: No fallbacks, flag missing values

---

### 2. HARDCODED TICKER MAPPINGS (60+ Manual Entries)
**File**: `core/recommendations.py:31-61`

```python
_INDIAN_STOCK_MAPPING = {
    "RELIANCE INDUSTRIES": "RELIANCE",
    "HDFC BANK": "HDFCBANK",
    ... (60 more hardcoded mappings)
    "LT TIMEL": "LT",  # Duplicate/typo?
}
```

**Problems**:
- ✗ If Screener.in uses different naming → mapping fails silently
- ✗ Returns `None` instead of flagging mismatch
- ✗ Asset dropped from analysis without warning
- ✗ Hard to maintain → typos/duplicates already present ("LARSEN & TOUBRO" and "LT TIMEL" both→"LT")

**Scenario**: Screener names stock "LARSEN AND TOUBRO" but mapping looks for "LARSEN & TOUBRO" → stock skipped

**Status**: ❌ **VIOLATES**: No hardcoded values, flag missing values

---

### 3. STALE CACHED DATA (5 min - 7 days old)
**File**: Multiple pages and modules

| Component | Cache Location | TTL | Impact |
|-----------|-----------------|-----|--------|
| Nifty 500 Universe | `cache/nifty500.json` | **7 days** | New stocks added to market won't be screened |
| PE Ratio | `cache/nifty500_breadth.csv` | **2 hours** | Regime analysis on 2hr-old PE |
| Dashboard Data | `@st.cache_data(ttl=300)` | **5 min** | Holdings value 5min outdated |
| Weekly Signals | `@st.cache_data(ttl=1800)` | **30 min** | Buy/sell analysis on month-old technicals |

**Render Hosting Problem**:
- Containers restart frequently → caches lost
- Next restart → cache reloads all data (slow)
- Concurrent users see inconsistent data
- **No cache invalidation on data change**

**Scenario on Render**: Deploy app → caches clear → first user waits 30s → other users see stale cache

**Status**: ❌ **VIOLATES**: All LIVE values

---

### 4. SILENT ZERO DEFAULTS IN DATABASE
**File**: `core/database.py:57-76`

```sql
CREATE TABLE Holdings (
    Ticker TEXT PRIMARY KEY,
    Qty REAL DEFAULT 0,           ← Missing qty becomes 0
    AvgBuyPrice REAL DEFAULT 0,   ← Missing price becomes 0
    CurrentPrice REAL DEFAULT 0,  ← Missing price becomes 0
    Value REAL DEFAULT 0,         ← Will calculate wrong value
    TargetWeight REAL DEFAULT 0,  ← Missing weight becomes 0
    CurrentWeight REAL DEFAULT 0
)
```

**Problems**:
- ✗ Missing column values silently become 0
- ✗ Portfolio value calculation WRONG
  - Position without CurrentPrice → Value = Qty * 0 = 0
  - Total portfolio value artificially low
- ✗ No error thrown, query succeeds silently
- ✗ User sees wrong portfolio value in dashboard

**Example Scenario**:
```
Excel has: INFY, Qty=100, AvgPrice=1500, CurrentPrice=2000, Value=200000
Missing CurrentPrice in some rows → becomes 0
SUM(Value) = 190,000 (missing one position entirely!)
```

**Status**: ❌ **VIOLATES**: No defaults, flag missing values

---

### 5. SILENT NULL→ZERO CONVERSIONS IN IMPORTS
**File**: `scripts/import_portfolio.py:52-55, 173-174`

```python
# Lines 52-55: Holdings parsing
units = float(a.get("units", 0) or 0)       # Missing units → 0
avg   = float(a.get("avgPrice", 0) or 0)    # Missing price → 0
curr  = float(a.get("currentPrice", 0) or 0)  # Missing current → 0
value = float(a.get("value", 0) or 0)       # Missing value → 0

# Lines 173-174: Ledger parsing
units = float(tx.get("units", 0) or 0)
price = float(tx.get("price", 0) or 0)
```

**Problems**:
- ✗ No validation of required fields
- ✗ Missing Excel data → becomes 0 without warning
- ✗ Incomplete portfolio imported silently
- ✗ User unaware of missing data

**Scenario**: Excel has typo in column name ("Qty" instead of "qty")
- Script doesn't find column → treats as 0
- Imports portfolio with 0 units
- User doesn't know

**Status**: ❌ **VIOLATES**: No defaults, flag missing values

---

### 6. XIRR CALCULATION USES APPROXIMATION (No Flag)
**File**: `pages/1_Dashboard.py:79-108`

```python
# Holdings-based XIRR calculation (APPROXIMATION)
if invested > 0:
    # Simple XIRR: Invested at beginning, current value at end
    cash_flows = [
        (earliest_date, -invested),
        (date.today(), portfolio_value)
    ]
    result = _xirr(dates, amounts)
    
    # Fallback to Ledger-based XIRR if Holdings is not available
    # (Also an approximation — ignores intermediate buys/sells)
```

**Problems**:
- ✗ Uses **earliest transaction date** (not actual entry date)
- ✗ Ignores all intermediate cash flows (buys/sells between dates)
- ✗ Result differs from true XIRR
- ✗ **User not told it's approximate**
- ✗ No note saying "XIRR calculation incomplete"

**Example**:
```
True history:
  2024-01-01: Buy ₹100,000
  2024-06-01: Buy ₹50,000
  2026-07-20: Value ₹200,000

Code does:
  cash_flows = [(2024-01-01, -100000), (2026-07-20, 200000)]
  XIRR = ~48%

True XIRR = ~25% (accounting for mid-year buy)
```

**Status**: ❌ **Calculation accuracy compromised**

---

### 7. PARTIAL MARKET REGIME (Data Quality Unknown)
**File**: `core/market_regime.py:40-130`

**Problems**:
- ✗ If PE fetch fails → returns `None` for PE signal
- ✗ If Breadth CSV missing → uses "historical average" fallback
- ✗ User sees regime based on 1-2 incomplete signals
- ✗ No indication which signals are live vs fallback

**Scenario**: 
- Breadth API down → uses average breadth from cache
- Market regime marked "BULLISH" based on incomplete data
- Recommendation to buy made on false signal

**Status**: ❌ **VIOLATES**: Flag missing values

---

## 🟡 HIGH-RISK ISSUES

### 8. SCREENER.IN IMPORT REQUIREMENTS
**File**: Scripts reference Screener.in but no column mapping defined

**Problems**:
- ✗ No documentation of required columns
- ✗ Column name variations not handled
- ✗ If Screener.in format changes → import breaks silently

**Required columns** (assumed, not documented):
- Company Name
- ROE %
- Debt-to-Equity
- Price
- Market Cap (?)

### 9. CHARTINK IMPORT REQUIREMENTS
**File**: `pages/4_Weekly_Analysis.py`, `core/recommendations.py`

**Problems**:
- ✗ Column names hardcoded: `['Symbol', 'Symbol Name', 'symbol', 'SYMBOL']`
- ✗ If Chartink CSV has "TICKER" instead → fails silently
- ✗ RSI_Weekly, ROC_6M column names not flexible

---

## 📊 DATA FRESHNESS TIMELINE

```
When user opens Dashboard:
├─ Page loads → checks cache_data(ttl=300)
│  ├─ If < 5 min old → uses cached data ✗ STALE
│  └─ If > 5 min old → calls load_portfolio_data()
│     ├─ get_holdings() → queries portfolio.db (LIVE)
│     ├─ get_market_history() → queries portfolio.db (LIVE)
│     └─ get_ledger() → queries portfolio.db (LIVE)
├─ Market regime calculation
│  ├─ get_trend() → yfinance (LIVE)
│  ├─ get_pe() → Nifty PE via NSE (may return None if API fails)
│  └─ get_breadth() → loads cache/nifty500_breadth.csv (2 hrs old!)
└─ Display

ISSUE: Different data ages mixed (5min dashboard, 2hr breadth, live prices)
```

---

## 🛠️ RENDER HOSTING SPECIFIC ISSUES

### Container Restarts Clear Caches
```
1. Deploy new version
2. Render restarts container
3. All caches in memory cleared
4. Next user request triggers redownload
   ├─ 7-day Nifty 500 cache → redownloads (slow)
   └─ User waits for NSE CSV download
5. Subsequent users get fresh cache for 7 days
```

**Problem**: Inconsistent data freshness between deployments

### No Persistent Cache Storage
- Memory caches lost on restart
- No Redis/Memcached configured
- File caches (`cache/nifty500.json`) may not persist on Render

### Concurrent User Sessions
```
User A loads dashboard → triggers cache build
User B loads dashboard at same time → gets partial/stale cache
User C refreshes → different cache version
```

---

## 🎯 FINANCIAL IMPACT ASSESSMENT

### Scenario 1: Missing CurrentPrice
```
Portfolio has 5 stocks:
  RELIANCE: ₹100,000
  TCS:      ₹100,000
  INFY:     ₹100,000  ← CurrentPrice missing (cached as 0)
  WIPRO:    ₹100,000
  LT:       ₹100,000

Calculated portfolio value: ₹400,000 (WRONG by ₹100,000!)
User thinks portfolio is down 20% when actually down 0%
Decision impact: May sell unnecessarily
```

### Scenario 2: NSE Fallback Active
```
Portfolio has 50 stocks, including emerging names:
  - RELIANCENL (new listing)
  - PAGE INDUSTRIES (not in top 50)
  - SUNPRINT (below threshold)

NSE API fails → fallback to hardcoded 50
These 3 stocks never analyzed
Buy signals for them never generated
Opportunity cost: Missed 20%+ gains
User unaware positions weren't screened
```

### Scenario 3: Stale Regime Analysis
```
Monday: Markets crash, Breadth drops to 25%
        Dashboard shows "BULLISH" (2-hour-old breadth = 75%)
        Recommends BUY

User buys on false signal
Real regime: BEARISH
Losses: -15%
```

---

## ✅ REQUIRED FIXES (Priority Order)

### 🔴 CRITICAL (Do First)

1. **Remove all DEFAULT 0 from database**
   - Change to `NOT NULL`
   - Require validation before insert
   - Fail loudly on missing data

2. **Remove Nifty 100 Fallback**
   - Delete `_FALLBACK_TICKERS` list
   - If NSE fails → display error message
   - Don't silently use incomplete universe

3. **Remove Hardcoded Ticker Mappings**
   - Delete `_INDIAN_STOCK_MAPPING`
   - Use Nifty 500 CSV as source of truth
   - If ticker not found → raise error with ticker name

4. **Add Data Validation**
   - Every import must validate required fields
   - If missing → list problematic rows to user
   - Don't silently convert missing data to 0

5. **Remove Spreadsheet Caches**
   - Implement Redis for persistent cache across restarts
   - Or switch to `ttl=0` (no caching) during pilot

### 🟡 HIGH (Do Second)

6. **Add Calculation Audit Trail**
   - Show data freshness on dashboard
   - Flag approximations (XIRR, regime signals)
   - Display which data is live vs cached

7. **Excel Column Mapping**
   - Document exact column names for Screener.in
   - Document exact column names for Chartink
   - Add flexible column name matching (multiple variations)

8. **Cache Invalidation**
   - When Holdings change → clear all caches
   - When Ledger updated → clear XIRR cache
   - When market opens/closes → refresh prices

### 🟢 MEDIUM (Do Third)

9. **Add Unit Tests**
   - Test missing data handling
   - Test XIRR calculation accuracy
   - Test Screener/Chartink parsing

10. **Complete Type Annotations**
    - Add return types to all functions
    - Flag Optional[] returns explicitly

---

## 📋 QUESTIONS FOR YOU

Before fixing, need clarification:

1. **Screener.in Excel Format**:
   - What exact column names are used?
   - Example: "ROE %", "ROE %" "Return on Equity"?
   - Is there a "Ticker" column or company name only?

2. **Chartink CSV Format**:
   - What exact column names are exported?
   - Example: "Symbol", "Stock", "Ticker"?
   - Does it include dates of data collection?

3. **Cache Requirements**:
   - On Render, how often are you deploying?
   - Can you use Redis for persistent cache?
   - Or should caches be disabled entirely (live data only)?

4. **Nifty 500 Fallback**:
   - If NSE fails, should app show error?
   - Or should it continue with partial data with warning?

---

## 📌 NEXT STEPS

1. **Immediate**: Run `python scripts/validate_portfolio.py` (if exists) to check current data quality
2. **Week 1**: Fix critical issues (defaults, fallbacks, mappings)
3. **Week 2**: Add validation and error flagging
4. **Week 3**: Implement caching strategy for Render
5. **Week 4**: Add unit tests

---

**Prepared by**: Copilot Audit  
**Severity**: 🔴 CRITICAL  
**Action Required**: YES - Accuracy impacts financial decisions
