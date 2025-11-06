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

# Przedziały głębokości
buckets = [
    (100, 1000, '100-1k'),
    (1000, 10000, '1k-10k'),
    (10000, 100000, '10k-100k'),
    (100000, 1000000, '100k-1M'),
    (1000000, 10000000, '1M-10M')
]
colors = ['#1f77b4', '#2ca02c', '#d62728', '#9467bd', '#8c564b']

@st.cache_data(ttl=refresh_interval)  # Cache na 5s, by nie spamować API
def fetch_data():
    base_url = 'https://api.binance.com/api/v3'
    data = {
        'current_price': 0.0,
        'volume_24h': 0.0,
        'bid_depths': [0] * len(buckets),
        'ask_depths': [0] * len(buckets),
        'buckets': [label for _, _, label in buckets],
        'times': [],
        'prices': [],
        'volumes': [],
        'error': None
    }
    
    # Ticker
    try:
        ticker_url = f'{base_url}/ticker/24hr?symbol={symbol}'
        response = requests.get(ticker_url, timeout=10)
        if response.status_code == 200:
            ticker = response.json()
            if 'lastPrice' in ticker:
                data['current_price'] = float(ticker['lastPrice'])
                data['volume_24h'] = float(ticker.get('quoteVolume', 0)) / 1e9
            else:
                data['error'] = f"Brak 'lastPrice' w odpowiedzi: {ticker.get('msg', 'Nieznany błąd')}"
        else:
            data['error'] = f"Błąd API (kod {response.status_code}): {response.text[:200]}"
    except Exception as e:
        data['error'] = f"Błąd pobierania tickera: {str(e)}"
    
    # Order book
    if not data['error']:
        try:
            depth_url = f'{base_url}/depth?symbol={symbol}&limit=100'
            response = requests.get(depth_url, timeout=10)
            if response.status_code == 200:
                orderbook = response.json()
                bids = np.array(orderbook.get('bids', []), dtype=float)
                asks = np.array(orderbook.get('asks', []), dtype=float)
                
                for price, amount in bids:
                    usd_value = amount * price
                    for i, (low, high, _) in enumerate(buckets):
                        if low <= usd_value < high:
                            data['bid_depths'][i] += usd_value
                            break
                
                for price, amount in asks:
                    usd_value = amount * price
                    for i, (low, high, _) in enumerate(buckets):
                        if low <= usd_value < high:
                            data['ask_depths'][i] += usd_value
                            break
            else:
                data['error'] = f"Błąd order book (kod {response.status_code})"
        except Exception as e:
            data['error'] = f"Błąd order book: {str(e)}"
    
    # OHLCV (historia)
    if not data['error']:
        try:
            end_time = int(time.time() * 1000)
            start_time = end_time - (14 * 24 * 60 * 60 * 1000)  # 2 tygodnie
            klines_url = f'{base_url}/klines?symbol={symbol}&interval=1h&startTime={start_time}&endTime={end_time}&limit=336'
            response = requests.get(klines_url, timeout=10)
            if response.status_code == 200:
                klines = response.json()
                if klines:
                    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df['close'] = df['close'].astype(float)
                    df['quote_volume'] = df['quote_asset_volume'].astype(float) / 1e9
                    
                    data['times'] = df['timestamp'].tolist()
                    data['prices'] = df['close'].tolist()
                    data['volumes'] = df['quote_volume'].tolist()
                else:
                    data['error'] = "Pusta historia cen"
            else:
                data['error'] = f"Błąd historii (kod {response.status_code})"
        except Exception as e:
            data['error'] = f"Błąd historii: {str(e)}"
    
    return data

def plot_charts(data):
    if data['error']:
        st.error(data['error'])
        return None
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})
    
    # Górny: Heatmap + cena
    times_num = mdates.date2num(data['times'])
    min_price, max_price = min(data['prices']), max(data['prices'])
    heatmap_data = np.outer(data['volumes'], np.ones(len(data['prices'])))
    im = ax1.imshow(heatmap_data.T, aspect='auto', cmap='hot', extent=[times_num[0], times_num[-1], min_price, max_price], alpha=0.7)
    ax1.plot(times_num, data['prices'], 'b-', linewidth=2, label='Cena historyczna')
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
    
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

# Interfejs
if st.button("Odśwież teraz"):
    with st.spinner("Pobieram dane z Binance..."):
        data = fetch_data()
    
    if data['error']:
        st.error(data['error'])
    else:
        # Wykres
        img_data = plot_charts(data)
        if img_data:
            st.image(img_data, use_column_width=True)
        
        # Metryki
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Aktualna cena", f"${data['current_price']:.0f}")
        with col2:
            st.metric("Wolumen 24h", f"${data['volume_24h']:.2f}B")
        
        st.caption(f"Ostatnia aktualizacja: {datetime.now().strftime('%H:%M:%S UTC')}")

# Auto-refresh (opcjonalny przycisk)
if st.button("Włącz auto-refresh (co 5s)"):
    st.info("Auto-refresh włączony – odświeżam co 5s (zatrzymaj reload strony).")
    for _ in range(20):  # Max 20 cykli (~2 min), by nie wisieć
        time.sleep(refresh_interval)
        st.rerun()
    st.warning("Auto-refresh zatrzymany po 2 min – kliknij ponownie, by wznowić.")
