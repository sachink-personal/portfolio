"""
Streamlit multi-page portfolio dashboard — root entry point.
Run: streamlit run app.py
"""
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Portfolio Manager",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 Quantitative Portfolio Manager")
st.markdown(
    "A rule-based semi-automatic portfolio system for the Indian market. "
    "Navigate using the sidebar."
)

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.info("**1 Dashboard**\nOverview & regime")
with col2:
    st.info("**2 Portfolio**\nHoldings & weights")
with col3:
    st.info("**3 Growth**\nNAV vs Nifty 500")
with col4:
    st.info("**4 Analysis**\nWeekly signals")
with col5:
    st.info("**5 Suggestions**\nRebalance plan")

st.divider()
st.caption(
    "First time? Run `python main.py --init` to create the Google Sheet structure, "
    "then run `python main.py --test` to verify email notifications."
)
