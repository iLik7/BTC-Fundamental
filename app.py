import requests
import pandas as pd
import streamlit as st
import datetime
import math

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
    params = {"localization":"false","tickers":"false","market_data":"true"}
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

# --- Blockchain.com stats ---
@st.cache_data(ttl=300)
def get_estimated_tx_value_usd(days="30days"):
    url = "https://api.blockchain.info/charts/estimated-transaction-volume-usd"
    data = get_json(url, params={"timespan":days,"format":"json"})
    if not data or "values" not in data: return None
    df = pd.DataFrame(data["values"])
    df["date"] = pd.to_datetime(df["x"], unit="s")
    df.rename(columns={"y":"tx_value_usd"}, inplace=True)
    return df[["date","tx_value_usd"]]

@st.cache_data(ttl=300)
def get_transactions_per_day(days="30days"):
    url = "https://api.blockchain.info/charts/n-transactions"
    data = get_json(url, params={"timespan":days,"format":"json"})
    if not data or "values" not in data: return None
    df = pd.DataFrame(data["values"])
    df["date"] = pd.to_datetime(df["x"], unit="s")
    df.rename(columns={"y":"tx_count"}, inplace=True)
    return df[["date","tx_count"]]

@st.cache_data(ttl=300)
def get_hashrate(days="30days"):
    url = "https://api.blockchain.info/charts/hash-rate"
    data = get_json(url, params={"timespan":days,"format":"json"})
    if not data or "values" not in data: return None
    df = pd.DataFrame(data["values"])
    df["date"] = pd.to_datetime(df["x"], unit="s")
    df.rename(columns={"y":"hashrate"}, inplace=True)
    return df[["date","hashrate"]]

@st.cache_data(ttl=60)
def get_blockchain_info():
    return get_json("https://blockchain.info/latestblock")

@st.cache_data(ttl=60)
def get_mempool_info():
    return get_json("https://mempool.space/api/mempool")

@st.cache_data(ttl=300)
def get_latest_blocks(limit=10):
    data = get_json("https://mempool.space/api/v1/blocks")
    if not data: return None
    df = pd.DataFrame(data)
    return df.head(limit)

# ---------- UI ----------
st.set_page_config(page_title="Bitcoin Command Center", layout="wide")
st.title("₿ Bitcoin Command Center")

# Theme toggle
mode = st.radio("Theme mode:", ["🌞 Light", "🌙 Dark"], horizontal=True)
if mode == "🌙 Dark":
    st.markdown("<style>body, .stApp { background-color: #0e1117; color: #fafafa; }</style>", unsafe_allow_html=True)

if st.button("🔄 Refresh Now"):
    st.rerun()

# --- Tabs ---
tab1, tab2, tab3 = st.tabs(["📊 Market & Valuation", "⚡ Mining & Network", "🔎 Explorer"])

# --- Tab 1 ---
with tab1:
    price_data = get_price_from_coingecko()
    if price_data:
        col1,col2,col3 = st.columns(3)
        col1.metric("Price (USD)", f"{price_data['price_usd']:,.0f}")
        col2.metric("Market Cap (USD)", f"{price_data['market_cap_usd']/1e12:,.2f} T")
        col3.metric("Circulating Supply", f"{price_data['circulating_supply']:,.0f} BTC")

    vol_df = get_estimated_tx_value_usd()
    tx_df = get_transactions_per_day()

    if vol_df is not None:
        st.subheader("On-chain Transaction Value (USD)")
        st.line_chart(vol_df.set_index("date")["tx_value_usd"])

    if tx_df is not None:
        st.subheader("Transactions per Day")
        st.line_chart(tx_df.set_index("date")["tx_count"])

    # NVT history
    if price_data and vol_df is not None:
        tmp = vol_df.copy()
        tmp["NVT"] = price_data["market_cap_usd"] / tmp["tx_value_usd"]
        st.subheader("NVT (Approx) – last 30 days")
        st.line_chart(tmp.set_index("date")["NVT"])

    # Rainbow Chart (simplified bands)
    import altair as alt

st.subheader("Bitcoin Rainbow Chart 🌈")

hist = get_json(
    "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart", 
    params={"vs_currency":"usd","days":"max"}
)

if hist and "prices" in hist:
    df = pd.DataFrame(hist["prices"], columns=["ts","price"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms")

    # bikin dummy regression bands (log bands)
    df["low"] = df["price"] * 0.2
    df["mid"] = df["price"]
    df["high"] = df["price"] * 5

    base = alt.Chart(df).encode(x="date:T")

    area_low = base.mark_line(color="blue").encode(y="low:Q")
    area_mid = base.mark_line(color="green").encode(y="mid:Q")
    area_high = base.mark_line(color="red").encode(y="high:Q")
    price_line = base.mark_line(color="black").encode(y="price:Q")

    chart = (area_low + area_mid + area_high + price_line).interactive()
    st.altair_chart(chart, use_container_width=True)

# --- Tab 2 ---
with tab2:
    st.subheader("Bitcoin Average Mining Costs")
    # Mock example (could replace with API if available)
    today = datetime.date.today()
    st.write("Latest Stats")
    st.write("Date:", today)
    st.metric("BTC Average Mining Cost", "$96,036", "$94,076 previous")

    block_info = get_blockchain_info()
    if block_info:
        st.metric("Current Block Height", block_info.get("height"))

    hashrate_df = get_hashrate("90days")
    if hashrate_df is not None:
        st.subheader("Hashrate (90 days)")
        st.line_chart(hashrate_df.set_index("date")["hashrate"])

    mempool = get_mempool_info()
    if mempool:
        st.metric("Mempool TX Count", f"{mempool.get('count',0):,}")
        st.metric("Mempool vSize (MB)", f"{mempool.get('vsize',0)/1e6:,.2f} MB")

# --- Tab 3 ---
with tab3:
    st.subheader("Latest Blocks")
    blocks = get_latest_blocks()
    if blocks is not None:
        st.dataframe(blocks[["height","tx_count","size","timestamp","extras"]])
