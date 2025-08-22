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
def get_price_history(days=30):
    import requests, pandas as pd
    j = requests.get(
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
        params={"vs_currency":"usd","days":days},
        timeout=15
    ).json()
    df = pd.DataFrame(j["prices"], columns=["ts","price"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    return df

hist = get_price_history(30)
st.subheader("BTC Price (30D)")
st.line_chart(hist.set_index("ts")["price"])

@st.cache_data(ttl=300)
def get_estimated_tx_value_usd(days="30days"):
    url = "https://api.blockchain.info/charts/estimated-transaction-volume-usd"
    data = get_json(url, params={"timespan": days, "format": "json"})
    if not data or "values" not in data: return None
    df = pd.DataFrame(data["values"])
    df["x"] = pd.to_datetime(df["x"], unit="s")
    df.rename(columns={"x":"date","y":"tx_value_usd"}, inplace=True)
    return df
# NVT history (approx): pakai mcap terakhir / volume on-chain harian
if price_data and vol_df is not None and len(vol_df):
    tmp = vol_df.copy()
    tmp["NVT"] = price_data["market_cap_usd"] / tmp["tx_value_usd"]
    st.subheader("NVT (Approx) – last 30 days")
    st.line_chart(tmp.set_index("date")["NVT"])

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
    
@st.cache_data(ttl=15)
def get_orderbook_coinbase(product_id="BTC-USD"):
    url = f"https://api.exchange.coinbase.com/products/{product_id}/book"
    data = get_json(url, params={"level":2}, headers={"User-Agent":"btc-dashboard"})
    if not data:
        return None, None
    bids = format_orderbook_df(data.get("bids", []), "bids")
    asks = format_orderbook_df(data.get("asks", []), "asks")
    return bids, asks

@st.cache_data(ttl=15)
def get_orderbook_kraken(pair="XBTUSD", count=100):
    url = "https://api.kraken.com/0/public/Depth"
    data = get_json(url, params={"pair": pair, "count": count})
    if not data or "result" not in data:
        return None, None
    key = list(data["result"].keys())[0]
    ob = data["result"][key]
    bids = format_orderbook_df(ob.get("bids", []), "bids")
    asks = format_orderbook_df(ob.get("asks", []), "asks")
    return bids, asks

st.set_page_config(page_title="BTC Fundamental-ish Dashboard", layout="wide")
st.title("⚖️ BTC 'Fundamentalis' Dashboard")

with st.sidebar:
    if st.sidebar.button("Refresh now"):
    st.rerun()

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

st.subheader("Order Book Snapshot")
if exchange.startswith("Binance"):
    bids, asks = get_orderbook_binance(symbol="BTCUSDT", limit=levels)
elif exchange.startswith("Coinbase"):
    bids, asks = get_orderbook_coinbase(product_id="BTC-USD")
else:
    bids, asks = get_orderbook_kraken(pair="XBTUSD", count=levels)
