"""
Page 6 — Transactions
Manage all portfolio transactions: view, add, edit, and delete.
"""
from __future__ import annotations

from datetime import date, datetime
import logging

import pandas as pd
import streamlit as st

import config
from core.database import get_engine, get_session

st.set_page_config(page_title="Transactions", page_icon="📝", layout="wide")
st.title("📝 Transactions Ledger")

# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_ledger():
    """Load ledger data."""
    from core.database import get_ledger
    return get_ledger()


@st.cache_data(ttl=300)
def load_holdings():
    """Load holdings data."""
    from core.database import get_holdings
    return get_holdings()


# ── Session state initialization ──────────────────────────────────────────────

if 'show_add_form' not in st.session_state:
    st.session_state.show_add_form = False

if 'show_edit_form' not in st.session_state:
    st.session_state.show_edit_form = False

if 'editing_idx' not in st.session_state:
    st.session_state.editing_idx = None

# Clear form state after action
if 'action_performed' not in st.session_state:
    st.session_state.action_performed = False


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("⚙️ Actions")
    if st.button("➕ Add Transaction", use_container_width=True):
        st.session_state.show_add_form = True
        st.session_state.editing_idx = None
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ── Load data ─────────────────────────────────────────────────────────────────

try:
    ledger_df = load_ledger()
    holdings_df = load_holdings()
except Exception as exc:
    st.error(f"Failed to load data: {exc}")
    st.stop()


# ── Transaction form functions ─────────────────────────────────────────────────

def get_form_data_from_row(row):
    """Extract form data from a ledger row."""
    if row is None:
        return {
            'Date': date.today(),
            'Ticker': '',
            'AssetClass': 'Stock',
            'Action': 'BUY',
            'Qty': 0.0,
            'ExecPrice': 0.0,
            'TotalValue': 0.0,
            'Charges': 0.0
        }
    
    default_date = row.get('Date', date.today())
    default_date = pd.to_datetime(default_date).date() if pd.notna(default_date) else date.today()
    
    return {
        'Date': default_date,
        'Ticker': str(row.get('Ticker', '')),
        'AssetClass': str(row.get('AssetClass', 'Stock')),
        'Action': str(row.get('Action', 'BUY')),
        'Qty': float(row.get('Qty', 0)),
        'ExecPrice': float(row.get('ExecPrice', 0)),
        'TotalValue': float(row.get('TotalValue', 0)),
        'Charges': float(row.get('Charges', 0))
    }


# ── Add Transaction ───────────────────────────────────────────────────────────

def add_transaction(data):
    """Add a new transaction to the ledger."""
    from core.database import append_ledger, upsert_holding, get_holdings
    
    if not data['Ticker']:
        st.error("Ticker/Symbol is required!")
        return False
    
    if data['Qty'] <= 0:
        st.error("Quantity must be greater than 0!")
        return False
    
    if data['ExecPrice'] <= 0:
        st.error("Execution price must be greater than 0!")
        return False
    
    try:
        # Append to ledger
        append_ledger({
            'Date': str(data['Date']),
            'Ticker': data['Ticker'],
            'AssetClass': data['AssetClass'],
            'Action': data['Action'],
            'Qty': data['Qty'],
            'ExecPrice': data['ExecPrice'],
            'TotalValue': data['TotalValue'],
            'Charges': data['Charges']
        })
        
        # Get fresh holdings data after adding transaction
        holdings_df = get_holdings()
        
        # Update holdings
        current_price = data['ExecPrice']
        
        if data['Action'] == 'BUY':
            existing = holdings_df[holdings_df['Ticker'] == data['Ticker']]
            
            if len(existing) > 0:
                old_qty = float(existing.iloc[0].get('Qty', 0))
                old_avg_price = float(existing.iloc[0].get('AvgBuyPrice', 0))
                new_qty = old_qty + data['Qty']
                old_total = old_qty * old_avg_price
                new_total = old_total + (data['Qty'] * data['ExecPrice'])
                new_avg_price = new_total / new_qty if new_qty > 0 else data['ExecPrice']
                
                upsert_holding({
                    'Ticker': data['Ticker'],
                    'Name': data['Ticker'],
                    'AssetClass': data['AssetClass'],
                    'Qty': new_qty,
                    'AvgBuyPrice': round(new_avg_price, 2),
                    'CurrentPrice': current_price,
                    'Value': round(new_qty * current_price, 2),
                    'TargetWeight': 0.0,
                    'CurrentWeight': 0.0
                })
            else:
                upsert_holding({
                    'Ticker': data['Ticker'],
                    'Name': data['Ticker'],
                    'AssetClass': data['AssetClass'],
                    'Qty': data['Qty'],
                    'AvgBuyPrice': data['ExecPrice'],
                    'CurrentPrice': current_price,
                    'Value': round(data['Qty'] * current_price, 2),
                    'TargetWeight': 0.0,
                    'CurrentWeight': 0.0
                })
        else:
            existing = holdings_df[holdings_df['Ticker'] == data['Ticker']]
            
            if len(existing) > 0:
                old_qty = float(existing.iloc[0].get('Qty', 0))
                new_qty = old_qty - data['Qty']
                
                if new_qty > 0:
                    upsert_holding({
                        'Ticker': data['Ticker'],
                        'Name': str(existing.iloc[0].get('Name', data['Ticker'])),
                        'AssetClass': data['AssetClass'],
                        'Qty': new_qty,
                        'AvgBuyPrice': float(existing.iloc[0].get('AvgBuyPrice', data['ExecPrice'])),
                        'CurrentPrice': current_price,
                        'Value': round(new_qty * current_price, 2),
                        'TargetWeight': 0.0,
                        'CurrentWeight': 0.0
                    })
                else:
                    from core.database import delete_holding
                    delete_holding(data['Ticker'])
        
        return True
        
    except Exception as exc:
        st.error(f"Failed to add transaction: {exc}")
        return False


# ── Edit Transaction ──────────────────────────────────────────────────────────

def edit_transaction(data, idx):
    """Edit an existing transaction."""
    from core.database import append_ledger, delete_holding
    
    if not data['Ticker']:
        st.error("Ticker/Symbol is required!")
        return False
    
    if data['Qty'] <= 0:
        st.error("Quantity must be greater than 0!")
        return False
    
    if data['ExecPrice'] <= 0:
        st.error("Execution price must be greater than 0!")
        return False
    
    try:
        # Get the old transaction
        old_row = ledger_df.iloc[idx]
        old_qty = float(old_row.get('Qty', 0))
        old_action = str(old_row.get('Action', 'BUY'))
        old_ticker = str(old_row.get('Ticker', ''))
        
        # Check if ticker changed
        if old_ticker != data['Ticker']:
            st.error("Cannot change ticker for existing transactions!")
            return False
        
        # Get holding data
        holding = holdings_df[holdings_df['Ticker'] == old_ticker]
        
        if len(holding) > 0:
            old_holding_qty = float(holding.iloc[0].get('Qty', 0))
            old_holding_avg = float(holding.iloc[0].get('AvgBuyPrice', 0))
            
            qty_diff = data['Qty'] - old_qty
            price_diff = data['ExecPrice'] - float(old_row.get('ExecPrice', 0))
            
            new_qty = old_holding_qty + qty_diff
            current_price = data['ExecPrice']
            
            if new_qty > 0:
                old_total_value = old_holding_qty * old_holding_avg
                new_avg_price = (old_total_value + (qty_diff * old_row.get('ExecPrice', 0))) / new_qty
                new_avg_price = data['ExecPrice']
                
                from core.database import upsert_holding
                upsert_holding({
                    'Ticker': old_ticker,
                    'Name': str(holding.iloc[0].get('Name', old_ticker)),
                    'AssetClass': data['AssetClass'],
                    'Qty': new_qty,
                    'AvgBuyPrice': round(new_avg_price, 2),
                    'CurrentPrice': current_price,
                    'Value': round(new_qty * current_price, 2),
                    'TargetWeight': 0.0,
                    'CurrentWeight': 0.0
                })
        
        # Append the new transaction (keep history - don't overwrite)
        append_ledger({
            'Date': str(data['Date']),
            'Ticker': data['Ticker'],
            'AssetClass': data['AssetClass'],
            'Action': data['Action'],
            'Qty': data['Qty'],
            'ExecPrice': data['ExecPrice'],
            'TotalValue': data['TotalValue'],
            'Charges': data['Charges']
        })
        
        return True
        
    except Exception as exc:
        st.error(f"Failed to edit transaction: {exc}")
        return False


# ── Delete Transaction ────────────────────────────────────────────────────────

def delete_transaction(idx):
    """Delete a transaction."""
    from core.database import get_engine, text
    
    try:
        row = ledger_df.iloc[idx]
        ticker = str(row.get('Ticker', ''))
        action = str(row.get('Action', 'BUY'))
        qty = float(row.get('Qty', 0))
        
        # Delete from ledger
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text(f"DELETE FROM Ledger WHERE id = {row.name + 1}"))
            conn.commit()
        
        # Update holdings
        holding = holdings_df[holdings_df['Ticker'] == ticker]
        
        if len(holding) > 0:
            old_qty = float(holding.iloc[0].get('Qty', 0))
            new_qty = old_qty - qty if action == 'BUY' else old_qty + qty
            
            if new_qty <= 0:
                from core.database import delete_holding
                delete_holding(ticker)
            else:
                from core.database import upsert_holding
                upsert_holding({
                    'Ticker': ticker,
                    'Name': str(holding.iloc[0].get('Name', ticker)),
                    'AssetClass': str(holding.iloc[0].get('AssetClass', 'Stock')),
                    'Qty': new_qty,
                    'AvgBuyPrice': float(holding.iloc[0].get('AvgBuyPrice', 0)),
                    'CurrentPrice': float(holding.iloc[0].get('CurrentPrice', 0)),
                    'Value': round(new_qty * float(holding.iloc[0].get('CurrentPrice', 0)), 2),
                    'TargetWeight': 0.0,
                    'CurrentWeight': 0.0
                })
        
        return True
        
    except Exception as exc:
        st.error(f"Failed to delete transaction: {exc}")
        return False


# ── Main UI ───────────────────────────────────────────────────────────────────

st.subheader("📋 Transaction History")

if ledger_df.empty:
    st.info("No transactions found. Click '➕ Add Transaction' to begin.")
else:
    # Create display dataframe
    display_df = ledger_df.copy()
    display_df = display_df.sort_values('Date', ascending=False).reset_index(drop=True)
    
    # Format columns
    display_df['Date'] = pd.to_datetime(display_df['Date']).dt.strftime('%d %b %Y')
    display_df['ExecPrice'] = display_df['ExecPrice'].apply(lambda x: f"₹{x:,.2f}")
    display_df['TotalValue'] = display_df['TotalValue'].apply(lambda x: f"₹{x:,.2f}")
    display_df['Charges'] = display_df['Charges'].apply(lambda x: f"₹{x:,.2f}")
    
    # Add action badges
    def format_action(val):
        color = "#4CAF50" if val == "BUY" else "#F44336"
        return f'<span style="background-color:{color};color:white;padding:2px 8px;border-radius:3px;font-weight:bold;">{val}</span>'
    
    display_df['Action'] = display_df['Action'].apply(format_action)
    
    # Show as table with edit/delete buttons
    for idx in display_df.index:
        original_row = ledger_df.iloc[idx]
        
        col1, col2, col3, col4, col5, col6, col7 = st.columns([1.5, 1.5, 1, 1, 1.5, 1.5, 0.5])
        
        with col1:
            st.write(f"**{display_df.loc[idx, 'Date']}**")
        with col2:
            st.write(f"**{display_df.loc[idx, 'Ticker']}**")
        with col3:
            st.write(f"{display_df.loc[idx, 'Action']}")
        with col4:
            st.write(f"{display_df.loc[idx, 'AssetClass']}")
        with col5:
            qty = original_row['Qty']
            st.write(f"₹{qty:,.2f}")
        with col6:
            st.write(f"{display_df.loc[idx, 'ExecPrice']}")
        with col7:
            col7a, col7b = st.columns(2)
            with col7a:
                if st.button("✏️", key=f"edit_{idx}", help="Edit"):
                    st.session_state.show_edit_form = True
                    st.session_state.editing_idx = idx
                    st.session_state.edit_form_data = get_form_data_from_row(ledger_df.iloc[idx])
            with col7b:
                if st.button("🗑️", key=f"delete_{idx}", help="Delete"):
                    if delete_transaction(idx):
                        st.cache_data.clear()
                        st.rerun()
        
        st.caption(f"Value: {display_df.loc[idx, 'TotalValue']} | Charges: {display_df.loc[idx, 'Charges']}")
        st.divider()

# Add Transaction Modal
if st.session_state.show_add_form:
    st.divider()
    st.subheader("➕ Add New Transaction")
    
    with st.form("add_transaction_form"):
        c1, c2 = st.columns(2)
        with c1:
            trans_date = st.date_input("Transaction Date", value=date.today())
            ticker = st.text_input("Ticker/Symbol", placeholder="e.g., TCS, HDFCFD_01, PPAS")
        
        with c2:
            asset_class = st.selectbox(
                "Asset Class",
                options=["Stock", "Mutual Fund", "FD", "ETF"],
                index=0
            )
            action = st.selectbox(
                "Action",
                options=["BUY", "SELL"],
                index=0
            )
        
        col1, col2 = st.columns(2)
        with col1:
            qty = st.number_input("Quantity", min_value=0.0, value=0.0, step=0.01)
            exec_price = st.number_input("Execution Price", min_value=0.0, value=0.0, step=0.01)
        
        with col2:
            total_value = st.number_input("Total Value", min_value=0.0, value=0.0, step=1.0)
            charges = st.number_input("Charges & Taxes", min_value=0.0, value=0.0, step=1.0)
        
        # Auto-calculate total value if not provided
        if total_value == 0.0 and qty > 0 and exec_price > 0:
            total_value = round(qty * exec_price, 2)
        
        st.caption(f"Total Value = Qty × Price: **₹{total_value:,.2f}**")
        
        submitted = st.form_submit_button("Save Transaction", use_container_width=True)
        cancel = st.form_submit_button("❌ Cancel", use_container_width=True)
    
    if submitted:
        form_data = {
            'Date': trans_date,
            'Ticker': ticker.upper() if ticker else '',
            'AssetClass': asset_class,
            'Action': action,
            'Qty': qty,
            'ExecPrice': exec_price,
            'TotalValue': total_value,
            'Charges': charges
        }
        
        if add_transaction(form_data):
            st.session_state.show_add_form = False
            st.session_state.action_performed = True
            st.cache_data.clear()
            st.rerun()
        else:
            st.error("Transaction failed to save.")
    
    if cancel:
        st.session_state.show_add_form = False
        st.rerun()
    
    st.divider()

# Edit Transaction Modal
if st.session_state.show_edit_form and 'edit_form_data' in st.session_state:
    st.divider()
    st.subheader("✏️ Edit Transaction")
    
    form_data = st.session_state.edit_form_data.copy()
    
    with st.form("edit_transaction_form"):
        c1, c2 = st.columns(2)
        with c1:
            trans_date = st.date_input("Transaction Date", value=form_data['Date'])
            ticker = st.text_input("Ticker/Symbol", value=form_data['Ticker'], disabled=True)
        
        with c2:
            asset_class = st.selectbox(
                "Asset Class",
                options=["Stock", "Mutual Fund", "FD", "ETF"],
                index=["Stock", "Mutual Fund", "FD", "ETF"].index(form_data['AssetClass'])
            )
            action = st.selectbox(
                "Action",
                options=["BUY", "SELL"],
                index=0 if form_data['Action'] == "BUY" else 1
            )
        
        col1, col2 = st.columns(2)
        with col1:
            qty = st.number_input("Quantity", min_value=0.0, value=form_data['Qty'], step=0.01)
            exec_price = st.number_input("Execution Price", min_value=0.0, value=form_data['ExecPrice'], step=0.01)
        
        with col2:
            total_value = st.number_input("Total Value", min_value=0.0, value=form_data['TotalValue'], step=1.0)
            charges = st.number_input("Charges & Taxes", min_value=0.0, value=form_data['Charges'], step=1.0)
        
        # Auto-calculate total value if not provided
        if total_value == 0.0 and qty > 0 and exec_price > 0:
            total_value = round(qty * exec_price, 2)
        
        st.caption(f"Total Value = Qty × Price: **₹{total_value:,.2f}**")
        
        submitted = st.form_submit_button("Save Changes", use_container_width=True)
        cancel = st.form_submit_button("❌ Cancel", use_container_width=True)
    
    if submitted:
        edit_data = {
            'Date': trans_date,
            'Ticker': ticker,
            'AssetClass': asset_class,
            'Action': action,
            'Qty': qty,
            'ExecPrice': exec_price,
            'TotalValue': total_value,
            'Charges': charges
        }
        
        if edit_transaction(edit_data, st.session_state.editing_idx):
            st.session_state.show_edit_form = False
            st.session_state.action_performed = True
            st.cache_data.clear()
            st.rerun()
        else:
            st.error("Transaction failed to save.")
    
    if cancel:
        st.session_state.show_edit_form = False
        st.rerun()
    
    st.divider()

# Summary
if not ledger_df.empty:
    total_transactions = len(ledger_df)
    total_buy_value = ledger_df[ledger_df['Action'] == 'BUY']['TotalValue'].sum()
    total_sell_value = ledger_df[ledger_df['Action'] == 'SELL']['TotalValue'].sum()
    total_charges = ledger_df['Charges'].sum()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Transactions", total_transactions)
    with col2:
        st.metric("Total Buy Value", f"₹{total_buy_value:,.2f}")
    with col3:
        st.metric("Total Sell Value", f"₹{total_sell_value:,.2f}")
    with col4:
        st.metric("Total Charges", f"₹{total_charges:,.2f}")