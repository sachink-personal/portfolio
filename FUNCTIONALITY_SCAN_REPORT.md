# Functionality Scan Report — Database Schema Mismatches

**Date:** 2026-07-22  
**Status:** CRITICAL — Data Loss Bug Identified

---

## 1. Executive Summary

The codebase has 34 Python files, all compiling successfully (2 syntax errors were fixed during this scan). However, a critical **database schema mismatch** has been identified: the `append_signal` and `bulk_insert_signals` methods in `core/database.py` only insert 7 columns, while the Signals table supports 17 columns. This means **10 columns of data are silently lost** every time signals are saved.

---

## 2. Database Schema vs. Insert Methods

### 2.1 Signals Table Schema (from `core/database.py`)

```sql
CREATE TABLE IF NOT EXISTS Signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    Date TEXT NOT NULL,
    Ticker TEXT NOT NULL,
    Strategy TEXT,
    AssetClass TEXT,
    Action TEXT,
    Source TEXT,
    CompanyName TEXT,
    ROC_6M REAL,
    RSI_14D REAL,
    RSI_Weekly REAL,
    ROE REAL,
    MarketCap REAL,
    DebtToEquity REAL,
    Sector TEXT,
    SubSector TEXT,
    Metadata TEXT
)
```

**Total Columns: 17**

### 2.2 Current `append_signal` Method

```python
session.execute(
    text("""INSERT INTO Signals (Date, Ticker, Strategy, ROC_6M, RSI_Weekly, ROE, Sector)
            VALUES (:Date, :Ticker, :Strategy, :ROC_6M, :RSI_Weekly, :ROE, :Sector)"""),
    {...}
)
```

**Columns Inserted: 7**
- Date, Ticker, Strategy, ROC_6M, RSI_Weekly, ROE, Sector

**Columns MISSING (10):**
| Column | Status | Impact |
|--------|--------|--------|
| AssetClass | NOT INSERTED | Sector classification lost |
| Action | NOT INSERTED | Buy/Sell signal direction lost |
| Source | NOT INSERTED | Import source (chartink/screener) lost |
| CompanyName | NOT INSERTED | Company name lost |
| RSI_14D | NOT INSERTED | Daily RSI data lost |
| MarketCap | NOT INSERTED | Market cap data lost |
| DebtToEquity | NOT INSERTED | Debt ratio data lost |
| SubSector | NOT INSERTED | Sub-sector data lost |
| Metadata | NOT INSERTED | Raw export metadata lost |
| **Row Count** | **Only 7 of 17 columns** | **Data corruption risk** |

### 2.3 Current `bulk_insert_signals` Method

Same issue as `append_signal` — only 7 columns inserted instead of 17.

---

## 3. Impact on Import Pipeline

### 3.1 `chartink_importer.py` — Produces Full Data

The importer correctly extracts and maps 15 columns:
```python
signal_data.append({
    "Date": date,
    "Ticker": symbol,
    "Strategy": strategy,
    "AssetClass": "EQ",
    "Action": action,
    "Source": "chartink",
    "CompanyName": company_name,
    "ROC_6M": roc,
    "RSI_14D": rsi_daily,      ← LOST
    "RSI_Weekly": rsi_weekly,
    "ROE": None,
    "MarketCap": None,
    "DebtToEquity": None,
    "Sector": sector,
    "SubSector": sub_sector,
    "Metadata": json.dumps(chartink_data),
})
```

**When saved via `SheetsClient().append_signal()` or `SheetsClient().bulk_insert_signals()`, 10 of these 15 data columns are silently discarded.**

### 3.2 `screener_importer.py` — Produces Full Data

Similarly extracts 14 columns:
```python
screener_data.append({
    "Date": date,
    "Ticker": symbol,
    "Strategy": strategy,
    "AssetClass": "EQ",
    "Action": action,
    "Source": "screener",
    "CompanyName": company_name,
    "ROE": roe,
    "DebtToEquity": de,
    "Sector": sector,
    "SubSector": sub_sector,
    "Metadata": json.dumps(screener_data_raw),
})
```

**Same loss: 8 columns are silently discarded.**

---

## 4. Impact on UI Pages

### 4.1 `pages/4_Weekly_Analysis.py`

Reads from Signals table expecting:
```python
signals.columns: Ticker, Strategy, Sector, ROC_6M, RSI_Weekly, ROE
```
**Status:** ✅ Works — these 6 columns are correctly inserted.

**Missing Features Due to Lost Data:**
- RSI_14D (Daily RSI) — not available
- MarketCap, DebtToEquity — not available
- SubSector — not available
- Metadata — not available (raw export data)

### 4.2 `pages/5_Suggestions.py`

Reads from Signals table expecting:
```python
Columns: ROC 6M %, RSI (Wkly), ROE %, Sector, Action, Ticker
```
**Status:** ⚠️ Partially broken — `Action` column is NULL for all records because `append_signal` never saves it.

### 4.3 `pages/1_Dashboard.py`, `pages/2_Portfolio.py`, `pages/6_Transactions.py`

These use:
- `get_holdings()` ✅ — Schema matches, no issues
- `get_ledger()` ✅ — Schema matches, no issues
- `get_market_history()` ✅ — Schema matches, no issues

---

## 5. Other Schema Mismatches

### 5.1 Holdings Table

**Schema (9 columns):** Ticker, Name, AssetClass, Qty, AvgBuyPrice, CurrentPrice, Value, TargetWeight, CurrentWeight

**`upsert_holding` method:** Inserts all 9 columns. ✅

**`get_holdings` method:** Returns all 9 columns. ✅

**Status:** No mismatch.

### 5.2 Ledger Table

**Schema (9 columns):** id, Date, Ticker, AssetClass, Action, Qty, ExecPrice, TotalValue, Charges

**`append_ledger` method:** Inserts all 8 data columns (excluding id). ✅

**`bulk_insert_ledger` method:** Inserts all 8 data columns. ✅

**Status:** No mismatch.

### 5.3 MarketHistory Table

**Schema (7 columns):** id, Date, PortfolioValue, Nifty500Close, Nifty500_200DMA, PE_Ratio, BreadthPct

**`append_market_history` method:** Inserts all 6 data columns (excluding id), with NULL handling for optional fields. ✅

**Status:** No mismatch.

---

## 6. Critical Fix Required

### 6.1 Fix `append_signal` Method

Current:
```python
text("""INSERT INTO Signals (Date, Ticker, Strategy, ROC_6M, RSI_Weekly, ROE, Sector)
        VALUES (:Date, :Ticker, :Strategy, :ROC_6M, :RSI_Weekly, :ROE, :Sector)""")
```

**Required Fix:**
```python
text("""INSERT INTO Signals (Date, Ticker, Strategy, AssetClass, Action, Source, 
        CompanyName, ROC_6M, RSI_14D, RSI_Weekly, ROE, MarketCap, DebtToEquity, 
        Sector, SubSector, Metadata)
        VALUES (:Date, :Ticker, :Strategy, :AssetClass, :Action, :Source, 
        :CompanyName, :ROC_6M, :RSI_14D, :RSI_Weekly, :ROE, :MarketCap, 
        :DebtToEquity, :Sector, :SubSector, :Metadata)""")
```

### 6.2 Fix `bulk_insert_signals` Method

Same update needed — all 16 columns must be included.

### 6.3 Data Migration

Existing Signals records will have NULL values for the 10 missing columns. A migration script may be needed to back-fill data from the Metadata column if it contains raw export data, or re-import signals from source files.

---

## 7. Summary of All Issues Found

| Issue | Severity | Module | Description |
|-------|----------|--------|-------------|
| **Signals Column Loss** | 🔴 CRITICAL | core/database.py | `append_signal` and `bulk_insert_signals` insert only 7 of 17 columns |
| **Action Column Missing** | 🟡 MEDIUM | pages/5_Suggestions.py | Relies on Action column which is NULL for all records |
| **RSI_14D Not Stored** | 🟡 MEDIUM | core/database.py | Daily RSI data from chartink importer lost |
| **Metadata Lost** | 🟡 MEDIUM | core/database.py | Raw export data from importers not saved |
| **MarketCap/DebtToEquity Lost** | 🟢 LOW | core/database.py | Screener data lost |
| **SubSector Lost** | 🟢 LOW | core/database.py | Chartink sub-sector data lost |
| **Syntax Errors (Fixed)** | ✅ RESOLVED | core/chartink_importer.py | Removed injected metadata (lines 335-344) |
| **Syntax Errors (Fixed)** | ✅ RESOLVED | core/screener_importer.py | Removed injected metadata (lines 269-279) |

---

## 8. Recommended Priority Order

1. **Fix `append_signal` and `bulk_insert_signals` in `core/database.py`** to insert all 16 columns matching the Signals table schema.
2. **Update `SheetsClient` wrapper methods** (`get_signals`, etc.) to return all columns and document column meanings.
3. **Update `pages/5_Suggestions.py`** to handle the now-correct `Action` column.
4. **Create data migration script** to back-fill existing NULL columns from Metadata if possible.
5. **Add validation tests** to ensure all insert methods match their table schemas.