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
    
@st.cache_data(ttl=15)
def get_orderbook_coinbase(product_id="BTC-USD"):
    url = f"https://api.exchange.coinbase.com/products/{product_id}/book"
    data = get_json(url, params={"level":2}, headers={"User-Agent":"btc-dashboard"})
    if not data: 
        return None, None
    return format_orderbook_df(data.get("bids", []), "bids"), format_orderbook_df(data.get("asks", []), "asks")

@st.cache_data(ttl=15)
def get_orderbook_kraken(pair="XBTUSD", count=50):
    url = "https://api.kraken.com/0/public/Depth"
    data = get_json(url, params={"pair":pair,"count":count})
    if not data or "result" not in data:
        return None, None
    key = list(data["result"].keys())[0]
    ob = data["result"][key]
    return format_orderbook_df(ob.get("bids", []), "bids"), format_orderbook_df(ob.get("asks", []), "asks")

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
st.subheader("Bitcoin Rainbow Chart 🌈 (data: Blockchain.com)")

# Harga historis dari Blockchain.com (all-time)
mkt = get_json(
    "https://api.blockchain.info/charts/market-price",
    params={"timespan":"all", "format":"json"}
)
if mkt and "values" in mkt:
    dfp = pd.DataFrame(mkt["values"])
    dfp["date"] = pd.to_datetime(dfp["x"], unit="s")
    dfp.rename(columns={"y":"price"}, inplace=True)
    dfp = dfp[["date","price"]].sort_values("date").reset_index(drop=True)

    # Index hari i untuk rumus log bands
    dfp["i"] = (dfp["date"] - dfp["date"].min()).dt.days

    # Koefisien band (versi BlockchainCenter, disederhanakan)
    bands = [
        {"name":"Basically a Fire Sale", "a":2.7880,  "offset":1200, "color":"#2c7fb8"},
        {"name":"BUY!",                   "a":2.8010,  "offset":1225, "color":"#41b6c4"},
        {"name":"Accumulate",            "a":2.8150,  "offset":1250, "color":"#7fcdbb"},
        {"name":"Still cheap",           "a":2.8295,  "offset":1275, "color":"#c7e9b4"},
        {"name":"HODL!",                 "a":2.8445,  "offset":1293, "color":"#fee391"},
        {"name":"Is this a bubble?",     "a":2.8590,  "offset":1320, "color":"#fec44f"},
        {"name":"FOMO intensifies",      "a":2.8720,  "offset":1350, "color":"#fe9929"},
        {"name":"SELL! Seriously",       "a":2.8860,  "offset":1375, "color":"#ec7014"},
        {"name":"Max Bubble",            "a":2.9000,  "offset":1400, "color":"#cc4c02"},
    ]

    import numpy as np
    out = []
    for b in bands:
        val = np.power(10.0, (b["a"] * np.log(dfp["i"] + b["offset"]) - 19.463))
        tmp = dfp[["date"]].copy()
        tmp["value"] = val
        tmp["band"] = b["name"]
        tmp["color"] = b["color"]
        out.append(tmp)
    dfb = pd.concat(out, ignore_index=True)

    base = alt.Chart(dfp).encode(x="date:T")
    price_line = base.mark_line().encode(
        y=alt.Y("price:Q", scale=alt.Scale(type="log")),
        color=alt.value("black")
    )
    band_lines = alt.Chart(dfb).mark_line(opacity=0.85).encode(
        x="date:T",
        y=alt.Y("value:Q", scale=alt.Scale(type="log")),
        color=alt.Color("band:N", legend=alt.Legend(title="Bands"))
    )

    st.altair_chart((band_lines + price_line).interactive(), use_container_width=True)

    # Band posisi latest
    latest_row = dfp.iloc[-1]
    latest_date, latest_price = latest_row["date"], latest_row["price"]
    today_vals = dfb[dfb["date"] == latest_date].sort_values("value")
    if len(today_vals):
        band_name = today_vals.iloc[(today_vals["value"] - latest_price).abs().argsort().iloc[0]]["band"]
        st.caption(f"Latest band: **{band_name}**  |  Price: ${latest_price:,.0f}")
else:
    st.warning("Gagal load harga historis dari Blockchain.com untuk Rainbow Chart.")

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

st.subheader("Order Book Snapshot")
ob_tab1, ob_tab2 = st.tabs(["Coinbase (BTC-USD)", "Kraken (XBTUSD)"])

with ob_tab1:
    bids, asks = get_orderbook_coinbase("BTC-USD")
    if bids is not None and asks is not None:
        c1, c2 = st.columns(2)
        c1.write("Bids (top)")
        c1.dataframe(bids.head(20), use_container_width=True)
        c2.write("Asks (top)")
        c2.dataframe(asks.head(20), use_container_width=True)
        st.metric("Cumulative Bid Notional", f"${bids['notional'].sum():,.0f}")
        st.metric("Cumulative Ask Notional", f"${asks['notional'].sum():,.0f}")
    else:
        st.info("Order book Coinbase belum tersedia (rate limit?). Coba tekan Refresh.")

with ob_tab2:
    bids, asks = get_orderbook_kraken("XBTUSD", count=50)
    if bids is not None and asks is not None:
        c1, c2 = st.columns(2)
        c1.write("Bids (top)")
        c1.dataframe(bids.head(20), use_container_width=True)
        c2.write("Asks (top)")
        c2.dataframe(asks.head(20), use_container_width=True)
        st.metric("Cumulative Bid Notional", f"${bids['notional'].sum():,.0f}")
        st.metric("Cumulative Ask Notional", f"${asks['notional'].sum():,.0f}")
    else:
        st.info("Order book Kraken belum tersedia (rate limit?). Coba tekan Refresh.")

