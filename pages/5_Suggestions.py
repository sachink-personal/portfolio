"""
Page 5 — Suggestions & Actions
On-demand rebalance plan: run the allocation engine, view buy/sell orders, export to CSV.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

import config

st.set_page_config(page_title="Suggestions", page_icon="💡", layout="wide")
st.title("💡 Suggestions & Actions")
st.caption("On-demand rebalance plan — run any time to see current recommendations.")


# ── Sidebar overrides ─────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("⚙️ Overrides")
    manual_pe = st.number_input("Nifty 50 PE (0 = auto)", min_value=0.0, max_value=60.0, value=0.0, step=0.1)
    manual_breadth = st.number_input("Market Breadth %", min_value=0.0, max_value=100.0, value=0.0, step=0.5)
    sip_amount = st.number_input(
        "New SIP capital this month (₹)",
        min_value=0.0,
        step=1000.0,
        value=0.0,
        help="Add your monthly SIP contribution here — will be included in buy sizing.",
    )

# ── Run engine button ─────────────────────────────────────────────────────────

run_button = st.button("🚀 Run Rebalance Analysis", type="primary", width="stretch")

if not run_button:
    st.info(
        "Click **Run Rebalance Analysis** to generate buy/sell recommendations "
        "based on current market regime and your signals data."
    )
    st.markdown("""
**How it works:**
1. Reads your current holdings from the database.
2. Fetches Nifty 500 price data to determine the market regime.
3. Reads signals for screener candidates.
4. Applies momentum + quality filters (ROC, RSI, ROE).
5. Checks each holding for exit triggers (RSI < 40, price < 200-DMA).
6. Sizes buys using Inverse Volatility Weighting.
7. Adjusts everything based on the equity allocation cap.
""")
    st.stop()

# ── Run the engine ────────────────────────────────────────────────────────────

with st.spinner("Running analysis… (fetching prices and computing regime)"):
    try:
        from core.sheets import SheetsClient
        from core.market_regime import MarketRegime
        from core.signal_processor import SignalProcessor
        from core.allocation import AllocationEngine
        from core.rebalance import format_plan_as_html, format_plan_as_text

        sheets = SheetsClient()
        holdings = sheets.get_holdings()
        signals_df = sheets.get_signals()

        regime = MarketRegime(
            manual_pe=manual_pe if manual_pe > 0 else None,
            manual_breadth=manual_breadth if manual_breadth > 0 else None,
        ).get_full_regime()

        processor = SignalProcessor(signals_df)
        approved = processor.filter_candidates()
        exits = processor.get_exit_signals(holdings)

        portfolio_value = float(holdings["Value"].sum()) if not holdings.empty else 0.0
        total_capital = portfolio_value + sip_amount

        engine = AllocationEngine(holdings, regime, approved, total_capital)
        plan = engine.generate_rebalance_plan(exits)

        # Inject SIP into buy sizing
        if sip_amount > 0 and plan.get("buys"):
            sell_proceeds = sum(s["current_value"] for s in plan.get("sells", []))
            available = sell_proceeds + sip_amount
            for b in plan["buys"]:
                b["target_value"] = round(available * (b["weight"] / 100), 0)

    except Exception as exc:
        st.error(f"Analysis failed: {exc}")
        st.stop()

# ── Regime banner ─────────────────────────────────────────────────────────────

trend = regime["trend"]["trend"]
eq_cap = regime["equity_cap"]
regime_color = {"BULLISH": "#d4edda", "BEARISH": "#f8d7da"}.get(trend, "#fff3cd")
regime_border = {"BULLISH": "#28a745", "BEARISH": "#dc3545"}.get(trend, "#ffc107")

st.markdown(
    f'<div style="background:{regime_color};border:2px solid {regime_border};'
    f'padding:14px;border-radius:8px;margin:10px 0">'
    f'<strong>Market Regime:</strong> {regime["regime_label"]} &nbsp;|&nbsp; '
    f'<strong>Equity Cap:</strong> {eq_cap*100:.0f}% &nbsp;|&nbsp; '
    f'<strong>Portfolio Value:</strong> ₹{portfolio_value:,.0f}'
    + (f' &nbsp;|&nbsp; <strong>+SIP:</strong> ₹{sip_amount:,.0f}' if sip_amount > 0 else "")
    + "</div>",
    unsafe_allow_html=True,
)

# ── Alert boxes ───────────────────────────────────────────────────────────────

if plan.get("fd_action"):
    st.warning(plan["fd_action"])

if plan.get("deployment_note"):
    if "UNDERVALUED" in plan["deployment_note"]:
        st.success(plan["deployment_note"])
    else:
        st.error(plan["deployment_note"])

st.divider()

# ── Sell table ────────────────────────────────────────────────────────────────

sells = plan.get("sells", [])
st.subheader(f"🔴 Exit Orders ({len(sells)})")
if sells:
    sell_df = pd.DataFrame(sells)
    sell_df.columns = ["Ticker", "Exit Reason", "Current Value ₹"]
    sell_df["Current Value ₹"] = sell_df["Current Value ₹"].apply(lambda x: f"₹{x:,.0f}")
    st.dataframe(sell_df, width="stretch", hide_index=True)
    st.caption(
        f"Exit triggers: RSI < {config.RSI_SELL} (weekly) OR price below personal 200-DMA. "
        "Review before executing."
    )
else:
    st.success("No exit signals triggered. All holdings are within healthy parameters.")

st.divider()

# ── Buy table ─────────────────────────────────────────────────────────────────

buys = plan.get("buys", [])
st.subheader(f"🟢 Buy Orders ({len(buys)})")
if buys:
    sell_proceeds = sum(s["current_value"] for s in sells)
    total_deploy = sell_proceeds + sip_amount
    if total_deploy > 0:
        st.caption(
            f"Deployable capital: ₹{sell_proceeds:,.0f} (sell proceeds)"
            + (f" + ₹{sip_amount:,.0f} (SIP)" if sip_amount > 0 else "")
            + f" = ₹{total_deploy:,.0f}"
        )

    buy_df = pd.DataFrame(buys)
    buy_df = buy_df.rename(columns={
        "ticker": "Ticker", "sector": "Sector", "roc_6m": "ROC 6M %",
        "rsi": "RSI (Wkly)", "roe": "ROE %", "weight": "Weight %",
        "target_value": "Target ₹",
    })
    buy_df["ROC 6M %"] = buy_df["ROC 6M %"].apply(lambda x: f"{x:.1f}%")
    buy_df["RSI (Wkly)"] = buy_df["RSI (Wkly)"].apply(lambda x: f"{x:.1f}")
    buy_df["ROE %"] = buy_df["ROE %"].apply(lambda x: f"{x:.1f}%")
    buy_df["Weight %"] = buy_df["Weight %"].apply(lambda x: f"{x:.1f}%")
    buy_df["Target ₹"] = buy_df["Target ₹"].apply(lambda x: f"₹{x:,.0f}")
    display_cols = [c for c in ["Ticker", "Sector", "ROC 6M %", "RSI (Wkly)", "ROE %", "Weight %", "Target ₹"] if c in buy_df.columns]
    st.dataframe(buy_df[display_cols], width="stretch", hide_index=True)
    st.caption(
        "Weights computed via Inverse Volatility (lower-volatility stocks get larger allocation). "
        "Target ₹ is proportional to deployable capital."
    )
else:
    if trend == "BEARISH":
        st.warning("No new buys recommended — market is in a BEARISH regime.")
    elif plan.get("deployment_note") and "OVERVALUED" in (plan.get("deployment_note") or ""):
        st.warning("No new buys recommended — Nifty PE is OVERVALUED.")
    elif approved.empty:
        st.info(
            "No qualified candidates in signals. "
            "Run the auto-screen from the Weekly Analysis page to populate signals."
        )
    else:
        st.info("All approved candidates are already held.")

st.divider()

# ── Export & email ────────────────────────────────────────────────────────────

col_exp, col_email = st.columns(2)

with col_exp:
    st.subheader("📥 Export Plan")
    all_rows = []
    for s in sells:
        all_rows.append({"Action": "SELL", "Ticker": s["ticker"], "Reason": s["reason"], "Amount ₹": s["current_value"]})
    for b in buys:
        all_rows.append({"Action": "BUY", "Ticker": b["ticker"], "Reason": f"ROC:{b['roc_6m']:.1f}% RSI:{b['rsi']:.1f} ROE:{b['roe']:.1f}%", "Amount ₹": b["target_value"]})
    if all_rows:
        csv_data = pd.DataFrame(all_rows).to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download as CSV",
            data=csv_data,
            file_name=f"rebalance_plan_{date.today().isoformat()}.csv",
            mime="text/csv",
            width="stretch",
        )
    else:
        st.info("No orders to export.")

with col_email:
    st.subheader("📧 Email This Plan")
    if st.button("Send Rebalance Email Now", width="stretch"):
        with st.spinner("Sending email…"):
            try:
                from core.rebalance import format_plan_as_html
                from notifications.email_sender import EmailSender
                html = format_plan_as_html(plan, portfolio_value)
                ok = EmailSender().send_monthly_rebalance(html, date.today().isoformat())
                if ok:
                    st.success("Email sent to your inbox.")
                else:
                    st.error("Email failed. Check EMAIL_SENDER / EMAIL_PASSWORD in .env")
            except Exception as exc:
                st.error(f"Email error: {exc}")

# ── Plain text summary (debug / copy) ────────────────────────────────────────

with st.expander("🔍 Plain text summary (for copy-paste)"):
    from core.rebalance import format_plan_as_text
    st.text(format_plan_as_text(plan))
