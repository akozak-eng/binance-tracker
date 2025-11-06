import streamlit as st
import requests
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.dates as mdates
from io import BytesIO
import base64
import time

# Konfiguracja
st.set_page_config(page_title="Binance Order Tracker", layout="wide")
st.title("🚀 Live Tracker Order Book - BTC/USDT")

symbol = 'BTCUSDT'  # Binance format
refresh_interval = 5  # Sekundy

# Przedziały głębokości (jak wcześniej)
buckets = [
    (100, 1000, '100-1k'),
    (1000, 10000, '1k-10k'),
    (10000, 100000, '10k-100k'),
    (100000, 1000000, '100k-1M'),
    (1000000, 10000000, '1M-10M')
]
colors = ['#1f77b4', '#2ca02c', '#d62728', '#9467bd', '#8c564b']

def fetch_data():
    base_url = 'https://api.binance.com/api/v3'
    
    # Ticker (cena + wolumen 24h)
    ticker_url = f'{base_url}/ticker/24hr?symbol={symbol}'
    ticker = requests.get(ticker_url).json()
    current_price = float(ticker['lastPrice'])
    volume_24h = float(ticker['quoteVolume']) / 1e9  # W miliardach USD
    
    # Order book (limit 100)
    depth_url = f'{base_url}/depth?symbol={symbol}&limit=100'
    orderbook = requests.get(depth_url).json()
    bids = np.array(orderbook['bids'], dtype=float)  # [price, amount]
    asks = np.array(orderbook['asks'], dtype=float)
    
    # Głębokość w bucketach
    bid_depths = [0] * len(buckets)
    ask_depths = [0] * len(buckets)
    
    for price, amount in bids:
        usd_value = amount * price
        for i, (low, high, _) in enumerate(buckets):
            if low <= usd_value < high:
                bid_depths[i] += usd_value
                break
    
    for price, amount in asks:
        usd_value = amount * price
        for i, (low, high, _) in enumerate(buckets):
            if low <= usd_value < high:
                ask_depths[i] += usd_value
                break
    
    # OHLCV (klines dla 2 tygodni, interval 1h dla więcej punktów)
    end_time = int(time.time() * 1000)
    start_time = end_time - (14 * 24 * 60 * 60 * 1000)  # 2 tygodnie
    klines_url = f'{base_url}/klines?symbol={symbol}&interval=1h&startTime={start_time}&endTime={end_time}&limit=336'  # ~2w w godzinach
    klines = requests.get(klines_url).json()
    
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['close'] = df['close'].astype(float)
    df['quote_volume'] = df['quote_asset_volume'].astype(float) / 1e9  # USD approx
    
    return {
        'times': df['timestamp'].tolist(),
        'prices': df['close'].tolist(),
        'volumes': df['quote_volume'].tolist(),
        'current_price': current_price,
        'volume_24h': volume_24h,
        'bid_depths': bid_depths,
        'ask_depths': ask_depths,
        'buckets': [label for _, _, label in buckets]
    }

def plot_charts(data):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})
    
    # Górny: Heatmap + cena
    times_num = mdates.date2num(data['times'])
    min_price, max_price = min(data['prices']), max(data['prices'])
    # Symulowana heatmapa (na podstawie wolumenu)
    heatmap_data = np.outer(data['volumes'], np.ones(len(data['prices'])))
    im = ax1.imshow(heatmap_data.T, aspect='auto', cmap='hot', extent=[times_num[0], times_num[-1], min_price, max_price], alpha=0.7)
    ax1.plot(times_num, data['prices'], 'b-', linewidth=2, label='Cena')
    ax1.axhline(y=data['current_price'], color='r', linestyle='--', label=f'Aktualna: ${data["current_price"]:.0f}')
    ax1.set_ylabel('Cena (USD)')
    ax1.set_title(f'{symbol} - Live Order Book | Wolumen 24h: ${data["volume_24h"]:.2f}B')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Dolny: Głębokość
    x = np.arange(len(data['buckets']))
    bottom_bid = np.cumsum([0] + data['bid_depths'][:-1]) / 1e6
    bottom_ask = np.cumsum([0] + data['ask_depths'][:-1]) / 1e6
    
    for i, (depth, bottom, color) in enumerate(zip(data['bid_depths'], bottom_bid, colors)):
        ax2.fill_between(x, bottom, bottom + depth/1e6, color=color, alpha=0.7, label=f'Bidy {data["buckets"][i]}')
    
    for i, (depth, bottom, color) in enumerate(zip(data['ask_depths'], bottom_ask, colors)):
        ax2.fill_between(x, bottom, bottom + depth/1e6, color=color, alpha=0.7, label=f'Asky {data["buckets"][i]}')
    
    ax2.set_xticks(x)
    ax2.set_xticklabels(data['buckets'])
    ax2.set_ylabel('Głębokość (mln USD)')
    ax2.set_title('Podział Orderów')
    ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax2.grid(True, alpha=0.3)
    
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
    fig.autofmt_xdate()
    plt.tight_layout()
    
    # Do Streamlit (base64)
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

# Interfejs
if st.button("Odśwież teraz"):
    with st.spinner("Pobieram dane z Binance..."):
        data = fetch_data()
    
    # Wykres
    img_data = plot_charts(data)
    st.image(img_data, use_column_width=True)
    
    # Metryki
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Aktualna cena", f"${data['current_price']:.0f}")
    with col2:
        st.metric("Wolumen 24h", f"${data['volume_24h']:.2f}B")
    
    st.caption(f"Ostatnia aktualizacja: {datetime.now().strftime('%H:%M:%S UTC')}")

# Auto-refresh (co 5s, ale tylko po pierwszym ładowaniu)
placeholder = st.empty()
with placeholder.container():
    if st.button("Włącz auto-refresh (co 5s)"):
        for _ in range(100):  # Ogranicz do 100 odświeżeń, by nie wisieć
            time.sleep(refresh_interval)
            st.rerun()
