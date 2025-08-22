import requests, pandas as pd, streamlit as st, math

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
    params = {"localization":"false","tickers":"false","market_data":"true",
              "community_data":"false","developer_data":"false","sparkline":"false"}
    data = get_json(url, params=params)
    if not data or "market_data" not in data: return None
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
    if not data or "values" not in data: return None
    df = pd.DataFrame(data["values"])
    df["x"] = pd.to_datetime(df["x"], unit="s")
    df.rename(columns={"x":"date","y":"tx_value_usd"}, inplace=True)
    return df

@st.cache_data(ttl=300)
def get_transactions_per_day(days="30days"):
    url = "https://api.blockchain.info/charts/n-transactions"
    data = get_json(url, params={"timespan": days, "format": "json"})
    if not data or "values" not in data: return None
    df = pd.DataFrame(data["values"])
    df["x"] = pd.to_datetime(df["x"], unit="s")
    df.rename(columns={"x":"date","y":"tx_count"}, inplace=True)
    return df

def fmt_ob(levels, side):
    if not levels: return pd.DataFrame(columns=["price","qty","notional","cum_qty","cum_notional"])
    rows=[{"price":float(p),"qty":float(q),"notional":float(p)*float(q)} for p,q in levels]
    df=pd.DataFrame(rows).sort_values("price", ascending=(side!="bids"))
    df["cum_qty"]=df["qty"].cumsum(); df["cum_notional"]=df["notional"].cumsum(); return df

@st.cache_data(ttl=15)
def ob_binance(symbol="BTCUSDT", limit=100):
    data = get_json("https://api.binance.com/api/v3/depth", params={"symbol":symbol,"limit":limit})
    if not data: return None, None
    return fmt_ob(data.get("bids",[]),"bids"), fmt_ob(data.get("asks",[]),"asks")

st.set_page_config(page_title="BTC Fundamental-ish Dashboard", layout="wide")
st.title("⚖️ BTC 'Fundamental-ish' Dashboard")

with st.sidebar:
    mining_cost = st.number_input("Avg Mining Cost (USD)", 10000, 500000, 95000, 1000)
    levels = st.slider("Order book levels", 10, 500, 100, 10)

col1,col2,col3,col4=st.columns(4, gap="large")
pd.set_option("display.float_format", lambda x: f"{x:,.0f}")
price = get_price_from_coingecko()
if price:
    col1.metric("Price (USD)", f"{price['price_usd']:,.0f}")
    col2.metric("Market Cap (USD)", f"{price['market_cap_usd']/1e12:,.2f} T")
    col3.metric("Circulating Supply", f"{price['circulating_supply']:,.0f} BTC")
    col4.write(f"Last updated: {price['last_updated']}")

vol = get_estimated_tx_value_usd()
txd = get_transactions_per_day()
latest_vol = None
if vol is not None and len(vol):
    latest_vol = vol.iloc[-1]["tx_value_usd"]
    st.subheader("On-chain Transaction Value (USD)")
    st.line_chart(vol.set_index("date")["tx_value_usd"])
if txd is not None and len(txd):
    st.subheader("Transactions per Day")
    st.line_chart(txd.set_index("date")["tx_count"])

st.divider()
if price and latest_vol:
    nvt = price["market_cap_usd"] / latest_vol
    st.metric("NVT (Market Cap / On-chain USD Volume)", f"{nvt:,.1f}")
    prem = (price["price_usd"] - mining_cost)/mining_cost*100
    st.metric("Premium vs Avg Mining Cost", f"{prem:,.1f}%")
else:
    st.info("NVT belum tersedia (butuh market cap & on-chain USD).")

st.subheader("Order Book Snapshot (Binance BTCUSDT)")
bids, asks = ob_binance(limit=levels)
c1,c2=st.columns(2)
if bids is not None: c1.dataframe(bids.head(20), use_container_width=True)
if asks is not None: c2.dataframe(asks.head(20), use_container_width=True)
if bids is not None and asks is not None:
    st.metric("Cumulative Bid Notional", f"${bids['notional'].sum():,.0f}")
    st.metric("Cumulative Ask Notional", f"${asks['notional'].sum():,.0f}")
