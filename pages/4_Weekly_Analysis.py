"""
Page 4 — Weekly Analysis
Market regime detail, RSI health heatmap of current holdings, and approved signals table.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import io

import config
from core.recommendations import BuySellRecommendation

st.set_page_config(page_title="Weekly Analysis", page_icon="📅", layout="wide")
st.title("📅 Weekly Analysis")
st.caption(f"Week ending {date.today().strftime('%d %B %Y')}")


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_data():
    from core.sheets import SheetsClient
    sheets = SheetsClient()
    return sheets.get_holdings(), sheets.get_signals(), sheets.get_market_history()


@st.cache_data(ttl=300)
def load_regime(manual_pe: float, manual_breadth: float):
    from core.market_regime import MarketRegime
    return MarketRegime(
        manual_pe=manual_pe if manual_pe > 0 else None,
        manual_breadth=manual_breadth if manual_breadth > 0 else None,
    ).get_full_regime()


@st.cache_data(ttl=600)
def run_signal_filter(signals_key: str):
    """Cache the filtered signals. signals_key is used to bust cache when data changes."""
    from core.sheets import SheetsClient
    from core.signal_processor import SignalProcessor
    signals_df = SheetsClient().get_signals()
    return SignalProcessor(signals_df).filter_candidates()


@st.cache_data(ttl=1800)
def fetch_rsi_for_holdings(tickers_tuple: tuple):
    """Fetch current weekly RSI for each holding (slow — cached 30 min)."""
    from ta.momentum import RSIIndicator
    from data.equity import get_historical_ohlcv
    import pandas as pd

    results = {}
    for ticker in tickers_tuple:
        try:
            hist = get_historical_ohlcv(ticker, period="1y")
            if hist.empty or len(hist) < 15:
                results[ticker] = None
                continue
            # yfinance >=0.2 may return Close as a single-column DataFrame — squeeze to Series
            close = hist["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close.index = pd.to_datetime(close.index)
            weekly = close.resample("W").last().dropna()
            if len(weekly) < 15:
                results[ticker] = None
                continue
            rsi_s = RSIIndicator(close=weekly, window=14).rsi()
            if rsi_s is not None and not rsi_s.dropna().empty:
                results[ticker] = round(float(rsi_s.dropna().iloc[-1]), 1)
            else:
                results[ticker] = None
        except Exception:
            results[ticker] = None
    return results


# ── Sidebar ───────────────────────────────────────────────────────────────────

# ── Screening mode (from config) ─────────────────────────────────────────────
current_mode = config.SCREEN_MODE

with st.sidebar:
    st.subheader("⚙️ Manual Overrides")
    manual_pe = st.number_input("Nifty 50 PE (0 = auto)", min_value=0.0, max_value=60.0, value=0.0, step=0.1)
    manual_breadth = st.number_input("Market Breadth %", min_value=0.0, max_value=100.0, value=0.0, step=0.5)
    fetch_rsi = st.checkbox("Fetch live RSI for holdings (slow, ~30s)", value=True)
    if st.button("🔄 Refresh All", width="stretch"):
        st.cache_data.clear()
        st.rerun()

# ── File Uploads for Chartink and Screener Excel ─────────────────
st.sidebar.divider()
st.sidebar.subheader("📂 Upload Chartink Excel")
chartink_file = st.sidebar.file_uploader(
    "Upload Chartink Excel (.xlsx)",
    type=["xlsx"],
    help="Download Chartink export as Excel and upload for technical indicators (ROC, RSI)",
    key="chartink_uploader"
)

# Store Chartink file bytes in session state
if "chartink_upload_bytes" not in st.session_state:
    st.session_state.chartink_upload_bytes = None

if chartink_file is not None:
    try:
        chartink_bytes = chartink_file.getvalue()
        chartink_df_upload = pd.read_excel(io.BytesIO(chartink_bytes), engine='openpyxl')
        st.session_state.chartink_upload_bytes = chartink_bytes
        
        # Check required columns with flexible matching
        chartink_col_map = {
            "Symbol": ["Symbol", "SYMBOL", "symbol", "Ticker", "ticker", "scrip", " Scrip"],
            "ROC_6M": ["ROC_6M", "ROC 6M", "ROC", "roc_6m", "roc", "6M ROC", "6m ROC"],
            "RSI_Weekly": ["RSI_Weekly", "rsi_weekly", "RSI", "rsi", "RSI (W)", "rsi_w"]
        }
        
        chartink_cols_found = {}
        for col_key, possible_names in chartink_col_map.items():
            for col_name in chartink_df_upload.columns:
                for possible in possible_names:
                    if col_name.strip().lower() == possible.strip().lower():
                        chartink_cols_found[col_key] = col_name
                        break
                if col_key in chartink_cols_found:
                    break
        
        chartink_cols_present = list(chartink_cols_found.keys())
        
        if len(chartink_cols_present) >= 2:  # At least Symbol + one other column
            st.sidebar.success(f"✅ Loaded {len(chartink_df_upload)} Chartink records")
            st.sidebar.caption(f"Columns found: {', '.join(chartink_cols_present)}")
        else:
            expected = list(chartink_col_map.keys())
            st.sidebar.warning(f"Chartink file missing expected columns: {', '.join(expected)}")
            st.sidebar.caption(f"Available columns: {', '.join(chartink_df_upload.columns.tolist())}")
    except Exception as exc:
        st.sidebar.error(f"Failed to process Chartink file: {exc}")
        import traceback
        st.sidebar.code(traceback.format_exc())

st.sidebar.divider()
st.sidebar.subheader("📂 Upload Screener Excel")
screener_file = st.sidebar.file_uploader(
    "Upload Screener Excel (.xlsx)",
    type=["xlsx"],
    help="Download Screener.in export as Excel and upload for fundamentals (ROE, D/E)",
    key="screener_uploader"
)

# Store Screener file bytes in session state
if "screener_upload_bytes" not in st.session_state:
    st.session_state.screener_upload_bytes = None

if screener_file is not None:
    try:
        screener_bytes = screener_file.getvalue()
        screener_df_upload = pd.read_excel(io.BytesIO(screener_bytes), engine='openpyxl')
        st.session_state.screener_upload_bytes = screener_bytes
        
        # Check required columns with flexible matching
        screener_col_map = {
            "Symbol": ["Symbol", "SYMBOL", "symbol", "Ticker", "ticker", "scrip", " Scrip", "Name", "name"],
            "ROE %": ["ROE %", "ROE %", "RoE", "roe", "ROE", "Return on Equity", "RoE %"],
            "Debt / Eq": ["Debt / Eq", "D/E", "Debt-Eq", "Debt to Eq", "Debt/Equity", "Debt / Equity"]
        }
        
        screener_cols_found = {}
        for col_key, possible_names in screener_col_map.items():
            for col_name in screener_df_upload.columns:
                for possible in possible_names:
                    if col_name.strip().lower() == possible.strip().lower():
                        screener_cols_found[col_key] = col_name
                        break
                if col_key in screener_cols_found:
                    break
        
        screener_cols_present = list(screener_cols_found.keys())
        
        if len(screener_cols_present) >= 2:  # At least Symbol + one other column
            st.sidebar.success(f"✅ Loaded {len(screener_df_upload)} Screener records")
            st.sidebar.caption(f"Columns found: {', '.join(screener_cols_present)}")
        else:
            expected = list(screener_col_map.keys())
            st.sidebar.warning(f"Screener file missing expected columns: {', '.join(expected)}")
            st.sidebar.caption(f"Available columns: {', '.join(screener_df_upload.columns.tolist())}")
    except Exception as exc:
        st.sidebar.error(f"Failed to process Screener file: {exc}")
        import traceback
        st.sidebar.code(traceback.format_exc())

# ── Run Screen banner (top of page body) ─────────────────────────────────────
run_screen = False
with st.container(border=True):
    bc1, bc2 = st.columns([3, 1])
    with bc1:
        mode_label = "Nifty 500 yfinance"
        st.markdown(f"### 🤖 Auto-Screen &nbsp; `{mode_label}`")
    st.caption(
        "Scans all Nifty 500 stocks for ROC, RSI and quality filters. "
        "For manual screening:\n"
        "1. Run saved screeners on Screener.in and Chartink.com\n"
        "2. Export results as Excel files\n"
        "3. Upload below\n"
        "4. Click Refresh All to process"
    )
    with bc2:
        if st.button("🔄 Refresh All", width="stretch"):
            st.cache_data.clear()
            st.rerun()

# ── Load ──────────────────────────────────────────────────────────────────────

try:
    holdings, signals, market_history = load_data()
except Exception as exc:
    st.error(f"Failed to load portfolio data: {exc}")
    import traceback
    st.code(traceback.format_exc())
    st.stop()

try:
    regime = load_regime(manual_pe, manual_breadth)
except Exception as exc:
    st.error(f"Failed to compute market regime: {exc}")
    import traceback
    st.code(traceback.format_exc())
    st.stop()

# ── Regime Summary ────────────────────────────────────────────────────────────

st.subheader("📡 Regime Summary")

trend_d = regime["trend"]
val_d = regime["valuation"]
breadth_d = regime["breadth"]

col1, col2, col3, col4 = st.columns(4)
with col1:
    t = trend_d["trend"]
    st.metric("200-DMA Trend", t, f"{trend_d['distance_pct']:+.1f}% from DMA")
with col2:
    v = val_d["valuation"]
    pe_str = f"PE {val_d['pe']:.1f}" if val_d["pe"] else "PE N/A"
    st.metric("Valuation", v, pe_str)
with col3:
    b = breadth_d["status"]
    bpct = breadth_d["breadth_pct"]
    bstr = f"{bpct:.1f}%" if bpct else "Not set"
    st.metric("Market Breadth", b, bstr)
with col4:
    st.metric("Equity Allocation Cap", f"{regime['equity_cap']*100:.0f}%")

if breadth_d.get("warning"):
    st.warning(
        f"⚠️ Breadth Divergence: Only {breadth_d['breadth_pct']:.1f}% of Nifty 500 stocks "
        f"are above their 200-DMA (threshold: {config.BREADTH_WARNING_THRESHOLD}%). "
        "Avoid adding new positions until breadth recovers."
    )

# ── Regime PE gauge ───────────────────────────────────────────────────────────

if val_d["pe"]:
    pe_val = val_d["pe"]
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=pe_val,
        title={"text": "Nifty 50 P/E Ratio"},
        gauge={
            "axis": {"range": [8, 35]},
            "bar": {"color": "#4a90e2"},
            "steps": [
                {"range": [8, config.PE_UNDERVALUED], "color": "#d4edda"},
                {"range": [config.PE_UNDERVALUED, config.PE_OVERVALUED], "color": "#fff3cd"},
                {"range": [config.PE_OVERVALUED, 35], "color": "#f8d7da"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 3},
                "thickness": 0.75,
                "value": config.PE_OVERVALUED,
            },
        },
    ))
    fig_gauge.update_layout(height=250, margin=dict(t=30, b=10))
    st.plotly_chart(fig_gauge, width="stretch")

st.divider()

# ── Holdings RSI heatmap ──────────────────────────────────────────────────────

st.subheader("🌡️ Holdings RSI Health")

if holdings.empty:
    st.info("No holdings to analyse.")
else:
    equity_holdings = holdings.copy()
    if "AssetClass" in equity_holdings.columns:
        equity_holdings = equity_holdings[
            equity_holdings["AssetClass"].str.upper().isin(["EQUITY", "ETF"])
        ]

    tickers = equity_holdings["Ticker"].tolist() if not equity_holdings.empty else []

    if tickers:
        if fetch_rsi:
            with st.spinner("Fetching weekly RSI data… (~30s)"):
                rsi_map = fetch_rsi_for_holdings(tuple(tickers))
        else:
            # Use signals database RSI if available, else show placeholder
            rsi_map = {}
            if not signals.empty and "Ticker" in signals.columns and "RSI_Weekly" in signals.columns:
                for _, row in signals.iterrows():
                    if row["Ticker"] in tickers:
                        rsi_map[row["Ticker"]] = float(row["RSI_Weekly"])

        # Build heatmap data
        rsi_data = []
        for ticker in tickers:
            rsi = rsi_map.get(ticker)
            if rsi is None:
                status, color = "No data", "#e0e0e0"
            elif rsi < config.RSI_SELL:
                status, color = f"SELL TRIGGER ({rsi:.0f})", "#f8d7da"
            elif rsi < config.RSI_BUY_LOW:
                status, color = f"Neutral ({rsi:.0f})", "#fff3cd"
            elif rsi <= config.RSI_BUY_HIGH:
                status, color = f"Buy Zone ({rsi:.0f})", "#d4edda"
            else:
                status, color = f"Overbought ({rsi:.0f})", "#ffeeba"
            rsi_data.append({"Ticker": ticker, "RSI": rsi, "Status": status, "Color": color})

        rsi_df = pd.DataFrame(rsi_data)

        # Display as coloured cards
        cols_per_row = 4
        for i in range(0, len(rsi_data), cols_per_row):
            row_items = rsi_data[i : i + cols_per_row]
            row_cols = st.columns(len(row_items))
            for j, item in enumerate(row_items):
                with row_cols[j]:
                    rsi_str = f"{item['RSI']:.0f}" if item["RSI"] is not None else "—"
                    st.markdown(
                        f'<div style="background:{item["Color"]};padding:12px;border-radius:8px;'
                        f'text-align:center;margin:4px">'
                        f'<div style="font-size:16px;font-weight:bold">{item["Ticker"]}</div>'
                        f'<div style="font-size:24px;font-weight:bold">{rsi_str}</div>'
                        f'<div style="font-size:12px">{item["Status"]}</div>'
                        f"</div>",
                        unsafe_allow_html=True,
                    )

        if not fetch_rsi and not rsi_map:
            st.caption(
                "RSI values not shown. Check 'Fetch live RSI' in the sidebar, "
                "or run the auto-screen above to populate signals with RSI data."
            )
    else:
        st.info("No equity/ETF holdings to analyse.")

st.divider()

# ── Approved signals table ────────────────────────────────────────────────────

st.subheader("✅ Approved Candidates This Week")
signals_key = str(len(signals)) + str(signals.columns.tolist() if not signals.empty else "")
approved = run_signal_filter(signals_key)

if approved.empty:
    st.info(
        "No candidates passed all filters. "
        "Run the auto-screen above to populate signals, "
        "then click Refresh All."
    )
    st.markdown(
        f"""**Filter criteria applied:**
- 6-Month ROC > {config.ROC_MIN}%
- Weekly RSI between {config.RSI_BUY_LOW} and {config.RSI_BUY_HIGH}
- ROE > {config.ROE_MIN}%"""
    )
else:
    st.success(f"{len(approved)} candidates passed all filters.")
    display_cols = [c for c in ["Ticker", "Strategy", "Sector", "ROC_6M", "RSI_Weekly", "ROE"] if c in approved.columns]
    fmt = approved[display_cols].copy()
    for col in ("ROC_6M", "RSI_Weekly", "ROE"):
        if col in fmt:
            fmt[col] = fmt[col].apply(lambda x: f"{x:.1f}")
    st.dataframe(fmt, width="stretch", hide_index=True)

st.divider()

# ── Buy/Sell Recommendations Engine ───────────────────────────────────────────
st.subheader("⚖️ Buy/Sell Recommendations")

# Load all required data for recommendations
@st.cache_data(ttl=300)
def get_recommendations_data():
    from core.sheets import SheetsClient
    from core.recommendations import BuySellRecommendation, load_chartink_data, load_screener_data, load_holdings_data
    
    sheets = SheetsClient()
    holdings = sheets.get_holdings()
    signals = sheets.get_signals()
    market_history = sheets.get_market_history()
    
    # Load Chartink data from upload or downloads
    chartink_df = load_chartink_data()
    if st.session_state.chartink_upload_bytes is not None:
        chartink_df = load_chartink_data(excel_bytes=st.session_state.chartink_upload_bytes)
    
    # Load Screener data from upload
    screener_df = load_screener_data()
    if st.session_state.screener_upload_bytes is not None:
        screener_df = load_screener_data(excel_bytes=st.session_state.screener_upload_bytes)
    
    return holdings, chartink_df, screener_df

holdings, chartink_df, screener_df = get_recommendations_data()

# Generate recommendations
def generate_recommendations(regime_data, chartink_df, screener_df, holdings_df):
    """Generate buy/sell recommendations"""
    if chartink_df is None or chartink_df.empty:
        return None
    
    recommender = BuySellRecommendation()
    recommender.set_regime(regime_data)
    
    if chartink_df is not None and not chartink_df.empty:
        recommender.set_chartink_data(chartink_df)
    
    if screener_df is not None and not screener_df.empty:
        recommender.set_screener_data(screener_df)
    
    if holdings_df is not None and not holdings_df.empty:
        recommender.set_holdings(holdings_df)
    
    return recommender.generate_recommendations()

recs = None
if chartink_df is not None and not chartink_df.empty:
    with st.spinner("Generating Buy/Sell Recommendations..."):
        recs = generate_recommendations(regime, chartink_df, screener_df, holdings)

if recs:
    # Display summary
    shield_col1, shield_col2 = st.columns(2)
    with shield_col1:
        shield_status = recs.get('defensive_shield_status', 'UNKNOWN')
        shield_color = '#d4edda' if shield_status == 'CLEAR' else '#f8d7da'
        st.markdown(
            f'<div style="background:{shield_color};padding:12px;border-radius:8px;'
            f'text-align:center;">'
            f'<strong>🛡️ DEFENSIVE SHIELD</strong><br>'
            f'{shield_status}'
            f'</div>',
            unsafe_allow_html=True
        )
    with shield_col2:
        st.caption(recs.get('defensive_shield_reason', ''))
    
    if recs['defensive_shield_status'] == 'TRIGGERED':
        st.warning("⚠️ Market Regime is Defensive - No new buyings recommended")
        st.info("Recommendations shown below are for informational purposes only.")
    
    st.markdown("---")
    
    # Buy Suggestions
    if recs.get('buy_suggestions'):
        st.success(f"➡️ BUY SUGGESTIONS: {len(recs['buy_suggestions'])} candidates")
        
        for i, item in enumerate(recs['buy_suggestions'][:10], 1):
            ticker = item.get('ticker', 'N/A')
            price = item.get('price', 'N/A')
            reasons = item.get('reasons', [])
            chartink_data = item.get('chartink_data', {})
            screener_data = item.get('screener_data', {})
            
            with st.expander(f"#{i} {ticker} @ ₹{price}", expanded=False):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Technical Factors")
                    roc = chartink_data.get('ROC', chartink_data.get('roc', chartink_data.get('ROC_6M', 'N/A')))
                    rsi = chartink_data.get('rsi', chartink_data.get('RSI', chartink_data.get('RSI_Weekly', 'N/A')))
                    st.write(f"**ROC:** {roc}")
                    st.write(f"**RSI:** {rsi}")
                
                with col2:
                    st.subheader("Fundamental Factors")
                    if screener_data:
                        roe = screener_data.get('ROE', screener_data.get('ROE %', 'N/A'))
                        de = screener_data.get('Debt / Eq', screener_data.get('D/E', 'N/A'))
                    else:
                        roe = 'N/A'
                        de = 'N/A'
                    st.write(f"**ROE:** {roe}")
                    st.write(f"**D/E:** {de}")
                
                st.subheader("Reasons")
                for reason in reasons:
                    st.write(f"- {reason}")
                
                st.markdown("---")
    else:
        st.info("No BUY suggestions at this time.")
    
    st.markdown("---")
    
    # Sell Recommendations
    if recs.get('sell_recommendations'):
        st.error(f"⬇️ SELL RECOMMENDATIONS: {len(recs['sell_recommendations'])} holdings")
        
        for i, item in enumerate(recs['sell_recommendations'][:10], 1):
            ticker = item.get('ticker', 'N/A')
            price = item.get('price', 'N/A')
            reasons = item.get('reasons', [])
            chartink_data = item.get('chartink_data', {})
            screener_data = item.get('screener_data', {})
            holdings_data = item.get('holdings_data', {})
            
            with st.expander(f"#{i} {ticker} @ ₹{price}", expanded=False):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Current Holdings")
                    qty = holdings_data.get('Quantity', 'N/A')
                    avg_price = holdings_data.get('Avg Buy Price', 'N/A')
                    st.write(f"**Quantity:** {qty}")
                    st.write(f"**Avg Buy:** ₹{avg_price}")
                
                with col2:
                    st.subheader("Sell Reasons")
                    for reason in reasons:
                        st.write(f"- {reason}")
                
                st.subheader("Technical Factors")
                rsi = chartink_data.get('rsi', chartink_data.get('RSI', chartink_data.get('RSI_Weekly', 'N/A')))
                st.write(f"**RSI:** {rsi}")
                
                st.markdown("---")
    else:
        st.info("No immediate SELL recommendations.")
    
    st.markdown("---")
    
    # Hold Recommendations
    if recs.get('hold_recommendations'):
        st.info(f"➡️ HOLD RECOMMENDATIONS: {len(recs['hold_recommendations'])} holdings")
        
        for i, item in enumerate(recs['hold_recommendations'][:10], 1):
            ticker = item.get('ticker', 'N/A')
            price = item.get('price', 'N/A')
            reasons = item.get('reasons', [])
            holdings_data = item.get('holdings_data', {})
            
            with st.expander(f"#{i} {ticker} @ ₹{price}", expanded=False):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Current Holdings")
                    qty = holdings_data.get('Quantity', 'N/A')
                    avg_price = holdings_data.get('Avg Buy Price', 'N/A')
                    st.write(f"**Quantity:** {qty}")
                    st.write(f"**Avg Buy:** ₹{avg_price}")
                
                with col2:
                    st.subheader("Recommendation")
                    for reason in reasons:
                        st.write(f"- {reason}")
                
                st.markdown("---")
    else:
        st.info("All holdings are in good standing.")
else:
    st.warning("⚠️ Please upload Chartink Excel to generate recommendations")

st.markdown("---")

# ── Sector Rotation (Auto-computed RRG) ──────────────────────────────────────
st.subheader("🔄 Sector Rotation (Auto-computed RRG)")
st.caption(
    "Relative Rotation computed from NSE sectoral indices vs Nifty 500. "
    "**Leading** and **Improving** sectors are eligible for new buys."
)

@st.cache_data(ttl=3600)  # Cache 1 hour
def load_rrg():
    from data.sector_rrg import compute_sector_rrg
    return compute_sector_rrg(period="1y")

rrg_col, rrg_refresh_col = st.columns([4, 1])
with rrg_refresh_col:
    if st.button("🔄 Refresh RRG", width="stretch"):
        st.cache_data.clear()
        st.rerun()

with st.spinner("Computing sector rotation…"):
    rrg_df = load_rrg()

if rrg_df.empty:
    st.warning("Sector RRG data unavailable — NSE index tickers may be temporarily blocked by yfinance.")
else:
    from data.sector_rrg import QUADRANT_META, get_buy_eligible_sectors
    eligible_sectors = get_buy_eligible_sectors(rrg_df)

    # Display as colour-coded cards grouped by quadrant
    for quadrant in ["Leading", "Improving", "Weakening", "Lagging"]:
        qrows = rrg_df[rrg_df["Quadrant"] == quadrant]
        if qrows.empty:
            continue
        meta = QUADRANT_META[quadrant]
        sector_names = " · ".join(qrows["Sector"].tolist())
        st.markdown(
            f'<div style="background:{meta["color"]};padding:10px 14px;'
            f'border-radius:6px;margin:4px 0">'
            f'<strong>{meta["emoji"]} {quadrant}</strong> &nbsp;|&nbsp; '
            f'{sector_names} &nbsp;'
            f'<span style="color:#666;font-size:12px">— {meta["desc"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Detailed table
    with st.expander("📋 Full RRG table"):
        display_rrg = rrg_df[["Sector", "Quadrant", "RS_Ratio", "RS_Momentum"]].copy()
        display_rrg["RS_Ratio"] = display_rrg["RS_Ratio"].apply(lambda x: f"{x:.1f}")
        display_rrg["RS_Momentum"] = display_rrg["RS_Momentum"].apply(lambda x: f"{x:.1f}")
        st.dataframe(display_rrg, width="stretch", hide_index=True)

    # Cross-reference approved candidates with eligible sectors
    if not approved.empty and "Sector" in approved.columns:
        st.divider()
        st.subheader("✅ Candidates in Leading / Improving Sectors")
        sector_filtered = approved[
            approved["Sector"].str.split(" & ").explode()
            .str.strip()
            .isin(eligible_sectors)
            .groupby(level=0).any()
        ] if not eligible_sectors else approved[
            approved["Sector"].apply(
                lambda s: any(es.lower() in str(s).lower() for es in eligible_sectors)
            )
        ]
        if sector_filtered.empty:
            st.info(
                "No approved candidates matched Leading/Improving sectors. "
                "All candidates still shown in the table above."
            )
        else:
            st.success(
                f"{len(sector_filtered)} of {len(approved)} candidates are in "
                "momentum-aligned sectors."
            )
            sc = [c for c in ["Ticker", "Sector", "ROC_6M", "RSI_Weekly", "ROE"] if c in sector_filtered.columns]
            st.dataframe(sector_filtered[sc], width="stretch", hide_index=True)

