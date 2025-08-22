import requests
import pandas as pd
import streamlit as st

# ---------- Helpers ----------
def get_json(url, params=None, headers=None, timeout=15):
    try:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Request failed: {e}")
        return None

@st.cache_data(ttl=60)
def get_price_from_coingecko():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin"
    params = {
        "localization":"false","tickers":"false","market_data":"true",
        "community_data":"false","developer_data":"false","sparkline":"false"
    }
    data = get_json(url, params=params)
    if not data or "market_data" not in data:
        return None
    md = data["market_data"]
    return {
        "price_usd": md["current_price"]["usd"],
        "market_cap_usd": md["market_cap"]["usd"],
        "circulating_supply": md.get("circulating_supply"),
        "last_updated": data.get("last_updated"),
    }

@st.cache_data(ttl=300)
def get_estimated_tx_value_usd(days="30days"):
    url = "https://api.blockchain.info/charts/estimated-transaction-volume-usd"
    data = get_json(url, params={"timespan": days, "format": "json"})
    if not data or "values" not in data:
        return None
    df = pd.DataFrame(data["values"])
    df["x"] = pd.to_datetime(df["x"], unit="s")
    df.rename(columns={"x":"date","y":"tx_value_usd"}, inplace=True)
    return df

@st.cache_data(ttl=300)
def get_transactions_per_day(days="30days"):
    url = "https://api.blockchain.info/charts/n-transactions"
    data = get_json(url, params={"timespan": days, "format": "json"})
    if not data or "values" not in data:
        return None
    df = pd.DataFrame(data["values"])
    df["x"] = pd.to_datetime(df["x"], unit="s")
    df.rename(columns={"x":"date","y":"tx_count"}, inplace=True)
    return df

def format_orderbook_df(levels, side):
    if not levels:
        return pd.DataFrame(columns=["price","qty","notional","cum_qty","cum_notional"])
    rows=[]
    for p,q,*_ in levels:
        price = float(p); qty = float(q)
        rows.append({"price":price,"qty":qty,"notional":price*qty})
    df=pd.DataFrame(rows)
    if side=="bids": df=df.sort_values("price", ascending=False)
    else: df=df.sort_values("price", ascending=True)
    df["cum_qty"]=df["qty"].cumsum()
    df["cum_notional"]=df["notional"].cumsum()
    return df

@st.cache_data(ttl=15)
def get_orderbook_coinbase(product_id="BTC-USD"):
    url = f"https://api.exchange.coinbase.com/products/{product_id}/book"
    data = get_json(url, params={"level":2}, headers={"User-Agent":"btc-dashboard"})
    if not data: return None,None
    return format_orderbook_df(data.get("bids",[]),"bids"), format_orderbook_df(data.get("asks",[]),"asks")

@st.cache_data(ttl=15)
def get_orderbook_kraken(pair="XBTUSD", count=100):
    url = "https://api.kraken.com/0/public/Depth"
    data = get_json(url, params={"pair":pair,"count":count})
    if not data or "result" not in data:
        return None,None
    key = list(data["result"].keys())[0]
    ob = data["result"][key]
    return format_orderbook_df(ob.get("bids",[]),"bids"), format_orderbook_df(ob.get("asks",[]),"asks")

# ---------- UI ----------
st.set_page_config(page_title="BTC Dashboard", layout="wide")

# Theme toggle
mode = st.radio("Theme mode:", ["🌞 Light", "🌙 Dark"], horizontal=True)
if mode == "🌙 Dark":
    st.markdown(
        """
        <style>
        body, .stApp { background-color: #0e1117; color: #fafafa; }
        </style>
        """, unsafe_allow_html=True
    )

# Refresh button
if st.button("🔄 Refresh Now"):
    st.rerun()

st.title("⚖️ BTC 'Fundamental-ish' Dashboard")

# --- Top cards ---
col1, col2, col3, col4 = st.columns(4, gap="large")
price_data = get_price_from_coingecko()
if price_data:
    col1.metric("Price (USD)", f"{price_data['price_usd']:,.0f}")
    col2.metric("Market Cap (USD)", f"{price_data['market_cap_usd']/1e12:,.2f} T")
    col3.metric("Circulating Supply", f"{price_data['circulating_supply']:,.0f} BTC")
    col4.write(f"Last updated: {price_data['last_updated']}")

# --- On-chain data ---
vol_df = get_estimated_tx_value_usd()
tx_df = get_transactions_per_day()

if vol_df is not None and len(vol_df):
    st.subheader("On-chain Transaction Value (USD)")
    st.line_chart(vol_df.set_index("date")["tx_value_usd"])

if tx_df is not None and len(tx_df):
    st.subheader("Transactions per Day")
    st.line_chart(tx_df.set_index("date")["tx_count"])

# --- NVT history (approx) ---
if price_data and vol_df is not None and len(vol_df):
    tmp = vol_df.copy()
    tmp["NVT"] = price_data["market_cap_usd"] / tmp["tx_value_usd"]
    st.subheader("NVT (Approx) – last 30 days")
    st.line_chart(tmp.set_index("date")["NVT"])

# --- Order book snapshots ---
st.subheader("Order Book Snapshot")

tab1, tab2 = st.tabs(["Coinbase (BTC-USD)", "Kraken (XBTUSD)"])

with tab1:
    bids, asks = get_orderbook_coinbase("BTC-USD")
    if bids is not None and asks is not None:
        c1,c2 = st.columns(2)
        c1.write("Bids (top)"); c1.dataframe(bids.head(20), use_container_width=True)
        c2.write("Asks (top)"); c2.dataframe(asks.head(20), use_container_width=True)
        st.metric("Cumulative Bid Notional", f"${bids['notional'].sum():,.0f}")
        st.metric("Cumulative Ask Notional", f"${asks['notional'].sum():,.0f}")

with tab2:
    bids, asks = get_orderbook_kraken("XBTUSD", count=50)
    if bids is not None and asks is not None:
        c1,c2 = st.columns(2)
        c1.write("Bids (top)"); c1.dataframe(bids.head(20), use_container_width=True)
        c2.write("Asks (top)"); c2.dataframe(asks.head(20), use_container_width=True)
        st.metric("Cumulative Bid Notional", f"${bids['notional'].sum():,.0f}")
        st.metric("Cumulative Ask Notional", f"${asks['notional'].sum():,.0f}")
