# BTC-Fundamental

Hub dashboard BTC (satu halaman, 4 tab): **Fuel Gauge**, **Time Matrix 2027**, **500-Day Simulator**, **SPX Tracker**.

- `index.html` — hasil build, ini yang di-hosting (statis, tanpa server).
- `src/` — file sumber tiap tool. Edit di sini, lalu `python3 build.py` untuk membangun ulang `index.html`.
- `app.py` — versi Streamlit lama (tidak dipakai oleh hosting statis).

## Hosting (GitHub Pages)
Settings → Pages → Source: *Deploy from a branch* → Branch: `main` / `(root)`. Situs: `https://ilik7.github.io/BTC-Fundamental/`

Tab bisa dibuka langsung: `#fuel`, `#matrix`, `#sim`, `#spx`.
Data live (OKX/Bybit/Hyperliquid/Binance, CoinGecko, alternative.me) di-fetch dari browser, jadi harus dibuka lewat browser biasa.
