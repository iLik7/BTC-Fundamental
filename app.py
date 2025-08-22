import datetime as dt
import numpy as np
import pandas as pd
import requests
import streamlit as st
import altair as alt

# =========================
# Helpers (HTTP & caching)
# =========================
def get_json(url, params=None, headers=None, timeout=15):
    try:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        # some endpoints return plain text ints; try json then fallback
        try:
            return r.json()
        except Exception:
            return r.text
    except Exception as e:
        st.error(f"Request failed: {e}")
        return None

@st.cache_data(ttl=60)
def get_price_from_coingecko():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin"
    params = {
        "localization":"false","tickers":"false",
        "market_data":"true","community_data":"false",
        "developer_data":"false","sparkline":"false"
    }
    j = get_json(url, params=params)
    if not j or "market_data" not in j:
        return None
    md = j["market_data"]
    return {
        "price_usd": md["current_price"]["usd"],
        "market_cap_usd": md["market_cap"]["usd"],
        "circulating_supply": md.get("circulating_supply"),
        "last_updated": j.get("last_updated")
    }

@st.cache_data(ttl=300)
def get_estimated_tx_value_usd(days="30days"):
    j = get_json("https://api.blockchain.info/charts/estimated-transaction-volume-usd",
                 params={"timespan":days,"format":"json"})
    if not j or "values" not in j: return None
    df = pd.DataFrame(j["values"])
    df["date"] = pd.to_datetime(df["x"], unit="s")
    df.rename(columns={"y":"tx_value_usd"}, inplace=True)
    return df[["date","tx_value_usd"]].sort_values("date")

@st.cache_data(ttl=300)
def get_transactions_per_day(days="30days"):
    j = get_json("https://api.blockchain.info/charts/n-transactions",
                 params={"timespan":days,"format":"json"})
    if not j or "values" not in j: return None
    df = pd.DataFrame(j["values"])
    df["date"] = pd.to_datetime(df["x"], unit="s")
    df.rename(columns={"y":"tx_count"}, inplace=True)
    return df[["date","tx_count"]].sort_values("date")

@st.cache_data(ttl=300)
def get_hashrate(days="90days"):
    j = get_json("https://api.blockchain.info/charts/hash-rate",
                 params={"timespan":days,"format":"json"})
    if not j or "values" not in j: return None
    df = pd.DataFrame(j["values"])
    df["date"] = pd.to_datetime(df["x"], unit="s")
    df.rename(columns={"y":"hashrate"}, inplace=True)
    return df[["date","hashrate"]].sort_values("date")

@st.cache_data(ttl=60)
def get_blockchain_info():
    # latest block (blockchain.info)
    return get_json("https://blockchain.info/latestblock")

@st.cache_data(ttl=60)
def get_block_height_fallback():
    # mempool.space fallback height (returns integer text)
    j = get_json("https://mempool.space/api/blocks/tip/height")
    try:
        return int(j)
    except Exception:
        return None

@st.cache_data(ttl=60)
def get_mempool_info():
    return get_json("https://mempool.space/api/mempool")

@st.cache_data(ttl=300)
def get_latest_blocks(limit=10):
    j = get_json("https://mempool.space/api/v1/blocks")
    if not isinstance(j, list): return None
    df = pd.DataFrame(j)
    return df.head(limit)

# ================
# Orderbook utils
# ================
def format_orderbook_df(levels, side):
    # levels can be [["price","size","num-orders"], ...] (Coinbase)
    # or [["price","volume","timestamp"], ...] (Kraken)
    if not isinstance(levels, (list, tuple)) or len(levels)==0:
        return pd.DataFrame(columns=["price","qty","notional","cum_qty","cum_notional"])
    rows=[]
    for row in levels:
        try:
            p = float(row[0]); q = float(row[1])
            rows.append({"price":p, "qty":q, "notional":p*q})
        except Exception:
            continue
    if not rows:
        return pd.DataFrame(columns=["price","qty","notional","cum_qty","cum_notional"])
    df = pd.DataFrame(rows)
    df = df.sort_values("price", ascending=(side!="bids"))
    df["cum_qty"] = df["qty"].cumsum()
    df["cum_notional"] = df["notional"].cumsum()
    return df

@st.cache_data(ttl=15)
def get_orderbook_coinbase(product_id="BTC-USD"):
    j = get_json(
        f"https://api.exchange.coinbase.com/products/{product_id}/book",
        params={"level":2},
        headers={"User-Agent":"btc-dashboard","Accept":"application/json"}
    )
    if not isinstance(j, dict) or "bids" not in j or "asks" not in j:
        return None, None
    return format_orderbook_df(j["bids"], "bids"), format_orderbook_df(j["asks"], "asks")

@st.cache_data(ttl=15)
def get_orderbook_kraken(pair="XBTUSD", count=50):
    j = get_json("https://api.kraken.com/0/public/Depth", params={"pair":pair,"count":count})
    if not isinstance(j, dict) or "result" not in j or not j["result"]:
        return None, None
    key = list(j["result"].keys())[0]
    ob = j["result"].get(key, {})
    return format_orderbook_df(ob.get("bids", []), "bids"), format_orderbook_df(ob.get("asks", []), "asks")

# =================
# Rainbow (Altair)
# =================
@st.cache_data(ttl=900)
def get_market_price_all():
    # Blockchain.com market price (USD), all-time
    j = get_json("https://api.blockchain.info/charts/market-price",
                 params={"timespan":"all","format":"json"})
    if not j or "values" not in j: return None
    df = pd.DataFrame(j["values"])
    df["date"] = pd.to_datetime(df["x"], unit="s")
    df.rename(columns={"y":"price"}, inplace=True)
    df = df[["date","price"]].sort_values("date").reset_index(drop=True)
    df["i"] = (df["date"] - df["date"].min()).dt.days
    return df

def build_rainbow_bands(price_df):
    # coefficients adapted to BlockchainCenter style (approx)
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
    out=[]
    for b in bands:
        val = np.power(10.0, (b["a"] * np.log(price_df["i"] + b["offset"]) - 19.463))
        tmp = price_df[["date"]].copy()
        tmp["value"] = val
        tmp["band"]  = b["name"]
        tmp["color"] = b["color"]
        out.append(tmp)
    bands_df = pd.concat(out, ignore_index=True)
    return bands_df, bands

# ===============
# UI STARTS HERE
# ===============
st.set_page_config(page_title="Bitcoin Command Center", layout="wide")
st.title("₿ Bitcoin Command Center")

# Theme toggle + refresh
mode = st.radio("Theme mode:", ["🌞 Light", "🌙 Dark"], horizontal=True)
if mode == "🌙 Dark":
    st.markdown("<style>body, .stApp { background-color: #0e1117; color: #fafafa; }</style>", unsafe_allow_html=True)

if st.button("🔄 Refresh Now"):
    st.rerun()

# Tabs
tab1, tab2, tab3 = st.tabs(["📊 Market & Valuation", "⚡ Mining & Network", "🔎 Explorer"])

# =========================
# Tab 1: Market & Valuation
# =========================
with tab1:
    price = get_price_from_coingecko()
    if price:
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Price (USD)", f"{price['price_usd']:,.0f}")
        c2.metric("Market Cap (USD)", f"{price['market_cap_usd']/1e12:,.2f} T")
        c3.metric("Circulating Supply", f"{price['circulating_supply']:,.0f} BTC")
        c4.write(f"Last updated: {price['last_updated']}")
    else:
        st.info("Gagal load harga dari CoinGecko (rate limit?). Coba Refresh.")

    vol_df = get_estimated_tx_value_usd()
    if vol_df is not None and len(vol_df):
        st.subheader("On-chain Transaction Value (USD)")
        st.line_chart(vol_df.set_index("date")["tx_value_usd"])
    else:
        st.info("On-chain USD (Blockchain.com) tidak tersedia saat ini.")

    tx_df = get_transactions_per_day()
    if tx_df is not None and len(tx_df):
        st.subheader("Transactions per Day")
        st.line_chart(tx_df.set_index("date")["tx_count"])

    # NVT history (approx: pakai mcap latest / volume harian)
    if price and vol_df is not None and len(vol_df):
        nvt_df = vol_df.copy()
        nvt_df["NVT"] = price["market_cap_usd"] / nvt_df["tx_value_usd"]
        st.subheader("NVT (Approx) – last 30 days")
        st.line_chart(nvt_df.set_index("date")["NVT"])

    # Rainbow Chart (Altair)
    st.subheader("Bitcoin Rainbow Chart 🌈 (data: Blockchain.com)")
    mp_df = get_market_price_all()
    if mp_df is not None and len(mp_df):
        bands_df, bands_meta = build_rainbow_bands(mp_df)
        # build color scale from meta to keep consistent colors
        domain = [b["name"] for b in bands_meta]
        range_  = [b["color"] for b in bands_meta]

        base = alt.Chart(mp_df).encode(x="date:T")
        price_line = base.mark_line(color="black").encode(
            y=alt.Y("price:Q", scale=alt.Scale(type="log"))
        )
        band_lines = alt.Chart(bands_df).mark_line(opacity=0.85).encode(
            x="date:T",
            y=alt.Y("value:Q", scale=alt.Scale(type="log")),
            color=alt.Color("band:N", legend=alt.Legend(title="Bands"),
                            scale=alt.Scale(domain=domain, range=range_))
        )
        st.altair_chart((band_lines + price_line).interactive(), use_container_width=True)

        # latest band label
        latest_date = mp_df.iloc[-1]["date"]
        latest_price = float(mp_df.iloc[-1]["price"])
        today_vals = bands_df[bands_df["date"]==latest_date].copy()
        if len(today_vals):
            idx = (today_vals["value"] - latest_price).abs().argsort().iloc[0]
            band_name = today_vals.iloc[idx]["band"]
            st.caption(f"Latest band: **{band_name}**  |  Price: ${latest_price:,.0f}")
    else:
        st.info("Rainbow data tidak tersedia saat ini.")

# =========================
# Tab 2: Mining & Network
# =========================
with tab2:
    # ---- Average Mining Cost (manual/estimator) ----
    st.subheader("Bitcoin Average Mining Costs (est.)")
    # contoh angka statis (update manual sesuai sumbermu, mis. MacroMicro)
    latest_date = "2025-08-20"
    latest_cost = 96036
    prev_cost   = 94076
    delta = latest_cost - prev_cost
    pct = (delta / prev_cost * 100.0) if prev_cost else 0.0

    c1,c2,c3 = st.columns(3)
    c1.write("Latest Stats")
    c1.write(latest_date)
    c2.metric("Avg Mining Cost (USD)", f"${latest_cost:,.0f}",
              delta=f"{delta:+,}  ({pct:+.2f}%)")
    c3.caption(f"${prev_cost:,.0f} previous")

    st.markdown("---")

    # ---- Network live: block height, hashrate, mempool ----
    block = get_blockchain_info()
    height = block["height"] if isinstance(block, dict) and "height" in block else None
    if not height:
        height = get_block_height_fallback()
    if height:
        st.metric("Current Block Height", f"{height:,}")
    else:
        st.info("Tidak dapat memuat block height saat ini.")

    hdf = get_hashrate("90days")
    if hdf is not None and len(hdf):
        st.subheader("Hashrate (90 days)")
        st.line_chart(hdf.set_index("date")["hashrate"])
    else:
        st.info("Hashrate tidak tersedia saat ini.")

    mempool = get_mempool_info()
    if isinstance(mempool, dict):
        count = mempool.get("count", 0)
        vsize = mempool.get("vsize", 0) / 1e6
        st.metric("Mempool TX Count", f"{count:,}")
        st.metric("Mempool vSize (MB)", f"{vsize:,.2f} MB")
    else:
        st.info("Mempool info tidak tersedia saat ini.")

    st.markdown("---")
    # ---- Order book snapshots (Coinbase & Kraken) ----
    st.subheader("Order Book Snapshot")
    ob1, ob2 = st.tabs(["Coinbase (BTC-USD)", "Kraken (XBTUSD)"])

    with ob1:
        bids, asks = get_orderbook_coinbase("BTC-USD")
        if bids is None or asks is None or bids.empty or asks.empty:
            st.info("Order book Coinbase belum tersedia (rate limit / blocked). Coba tekan Refresh.")
        else:
            c1, c2 = st.columns(2)
            c1.write("Bids (top)")
            c1.dataframe(bids.head(20), use_container_width=True)
            c2.write("Asks (top)")
            c2.dataframe(asks.head(20), use_container_width=True)
            st.metric("Cumulative Bid Notional", f"${bids['notional'].sum():,.0f}")
            st.metric("Cumulative Ask Notional", f"${asks['notional'].sum():,.0f}")

    with ob2:
        bids, asks = get_orderbook_kraken("XBTUSD", count=50)
        if bids is None or asks is None or bids.empty or asks.empty:
            st.info("Order book Kraken belum tersedia (rate limit / blocked). Coba tekan Refresh.")
        else:
            c1, c2 = st.columns(2)
            c1.write("Bids (top)")
            c1.dataframe(bids.head(20), use_container_width=True)
            c2.write("Asks (top)")
            c2.dataframe(asks.head(20), use_container_width=True)
            st.metric("Cumulative Bid Notional", f"${bids['notional'].sum():,.0f}")
            st.metric("Cumulative Ask Notional", f"${asks['notional'].sum():,.0f}")

# =================
# Tab 3: Explorer
# =================
with tab3:
    st.subheader("Latest Blocks")
    blocks = get_latest_blocks(limit=10)
    if blocks is not None and len(blocks):
        cols = [c for c in ["height","tx_count","size","timestamp"] if c in blocks.columns]
        st.dataframe(blocks[cols], use_container_width=True)
        st.caption("Sumber: mempool.space")
    else:
        st.info("Blocks belum bisa dimuat (rate limit?). Tekan Refresh sebentar lagi.")
