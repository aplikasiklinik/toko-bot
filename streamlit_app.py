import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import time
import json
import os
from dotenv import load_dotenv
from datetime import datetime

# --- 1. CONFIG ---
st.set_page_config(page_title="Tokocrypto Sync Bot", layout="wide", page_icon="♻️")
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    .stMetric { background-color: #1A1C24; border: 1px solid #333; border-radius: 8px; }
    .stContainer { background-color: #1A1C24; border: 1px solid #333; border-radius: 8px; padding: 15px; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 2. DATABASE ---
DB_FILE = "posisi_multi.json"

def load_positions():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f: return json.load(f)
        except: return []
    return []

def save_positions(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f)

def add_log(msg, type="info"):
    if 'logs' not in st.session_state: st.session_state['logs'] = []
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state['logs'].insert(0, {"Waktu": ts, "Tipe": type, "Pesan": msg})

# --- 3. KONEKSI ---
def init_exchange(api, secret):
    try:
        return ccxt.tokocrypto({
            'apiKey': api, 'secret': secret,
            'enableRateLimit': True,
            'timeout': 30000, 
            'options': {'adjustForTimeDifference': True}
        })
    except: return None

# --- 4. FITUR BARU: AUTO-SYNC WALLET ---
def sync_wallet(exchange, tp_pct, sl_pct):
    """Mencari koin di dompet yang belum ada di database bot"""
    found_coins = []
    try:
        # Ambil semua saldo
        bal = exchange.fetch_balance()
        items = bal['total']
        
        current_db = load_positions()
        existing_symbols = [p['symbol'] for p in current_db]
        
        for currency, amount in items.items():
            # Filter koin receh (kurang dari 0.0001 diabaikan) dan bukan USDT
            if amount > 0 and currency not in ['USDT', 'BIDR']:
                symbol = f"{currency}/USDT"
                
                # Cek apakah sudah ada di DB bot?
                if symbol in existing_symbols:
                    continue
                
                # Cek nilai koin (Apakah > 5 USDT?)
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    price = ticker['last']
                    value_usdt = amount * price
                    
                    if value_usdt > 5.0: # Hanya impor jika nilainya > 5 Dollar
                        # Karena kita tidak tahu harga beli aslinya, kita anggap harga sekarang sebagai patokan
                        new_pos = {
                            'symbol': symbol,
                            'buy_price': price, # Anggap beli di harga sekarang
                            'quantity': amount,
                            'tp': price * (1 + tp_pct/100),
                            'sl': price * (1 - sl_pct/100)
                        }
                        current_db.append(new_pos)
                        found_coins.append(symbol)
                except:
                    continue # Skip jika gagal ambil harga (misal koin delisted)
        
        if found_coins:
            save_positions(current_db)
            return True, found_coins
        return False, []
        
    except Exception as e:
        return False, [str(e)]

# --- 5. ANALISA ---
def get_target_coins(exchange):
    try:
        exchange.load_markets()
        tickers = exchange.fetch_tickers()
        usdt_pairs = [k for k in tickers.keys() if '/USDT' in k]
        sorted_pairs = sorted(usdt_pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        return [x for x in sorted_pairs if 'USDC' not in x][:20]
    except: return []

def analyze_coin(exchange, symbol, tf, rsi_limit):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=50)
        if not ohlcv: return None
        df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
        df['rsi'] = ta.rsi(df['close'], length=14)
        rsi = df['rsi'].iloc[-1]
        price = df['close'].iloc[-1]
        status = "BUY" if rsi < rsi_limit else "WAIT"
        return {'Symbol': symbol, 'Harga': price, 'RSI': round(rsi, 2), 'Status': status}
    except: return None

# --- SIDEBAR ---
load_dotenv()
with st.sidebar:
    st.header("🎛️ Panel Kontrol")
    
    # API KEY
    api_key = os.getenv('TOKO_API_KEY')
    secret_key = os.getenv('TOKO_SECRET_KEY')
    if not api_key:
        api_key = st.text_input("API Key", type="password")
        secret_key = st.text_input("Secret Key", type="password")

    st.divider()
    
    # --- TOMBOL SAKTI IMPOR SALDO ---
    st.subheader("♻️ Sinkronisasi Saldo")
    st.info("Klik tombol ini jika Anda punya koin di Tokocrypto tapi tidak muncul di Bot.")
    if st.button("🔍 SCAN & IMPOR DOMPET"):
        # Kita butuh exchange sementara untuk tombol ini
        tmp_ex = init_exchange(api_key, secret_key)
        if tmp_ex:
            is_found, list_coins = sync_wallet(tmp_ex, 1.5, 2.0) # Default TP 1.5%, SL 2%
            if is_found:
                st.success(f"Berhasil mengimpor: {', '.join(list_coins)}")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("Tidak ditemukan koin baru (Nilai > 5 USDT) di dompet.")
        else:
            st.error("Koneksi API Gagal.")
    
    st.divider()

    # SETTING TRADING
    refresh_rate = st.slider("Kecepatan Refresh (Detik)", 5, 60, 10)
    modal_per_trade = st.number_input("Modal Per Slot (USDT)", 11.0)
    total_slots = st.number_input("Max Slot", 1, 10, 3)
    
    st.caption("TARGET")
    tp_pct = st.number_input("Take Profit (%)", 1.5)
    sl_pct = st.number_input("Stop Loss (%)", 2.0)
    
    st.caption("STRATEGI")
    tf_sel = st.selectbox("Timeframe", ["15m", "5m"], index=1)
    rsi_lim = st.number_input("RSI Limit (<)", 35)
    
    live_mode = st.toggle("🔴 LIVE TRADING", value=True)
    
    col1, col2 = st.columns(2)
    start_btn = col1.button("▶️ START", type="primary", use_container_width=True)
    stop_btn = col2.button("⏹️ STOP", use_container_width=True)

    if start_btn: st.session_state['active'] = True
    if stop_btn: st.session_state['active'] = False

# --- MAIN UI ---
st.title("♻️ Tokocrypto Sync & Auto Trade")

if 'active' not in st.session_state: st.session_state['active'] = False
if 'logs' not in st.session_state: st.session_state['logs'] = []
if not api_key: st.stop()

exchange = init_exchange(api_key, secret_key)
placeholder = st.empty()

while st.session_state['active']:
    with placeholder.container():
        active_pos = load_positions()
        
        # 1. INFO BALANCE
        try:
            bal = exchange.fetch_balance()
            free_usdt = bal['USDT']['free']
            
            # Hitung Equity
            asset_val = 0
            for pos in active_pos:
                try:
                    tk = exchange.fetch_ticker(pos['symbol'])
                    asset_val += (pos['quantity'] * tk['last'])
                except: pass
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Saldo Tunai", f"{free_usdt:.2f} USDT")
            c2.metric("Total Aset", f"{free_usdt + asset_val:.2f} USDT")
            c3.metric("Slot", f"{len(active_pos)} / {total_slots}")
        except: st.error("Gagal ambil saldo.")

        st.divider()

        # 2. MONITORING
        if active_pos:
            st.subheader(f"🔥 Posisi Aktif ({len(active_pos)})")
            
            # Grid layout
            cols = st.columns(3)
            for i, pos in enumerate(active_pos):
                with cols[i % 3]:
                    with st.container():
                        try:
                            # Data
                            ticker = exchange.fetch_ticker(pos['symbol'])
                            curr_price = ticker['last']
                            entry = pos['buy_price']
                            
                            # PnL
                            qty = pos['quantity']
                            val_now = curr_price * qty
                            # Estimasi modal awal (jika hasil import, entry = harga saat import)
                            invested = entry * qty 
                            pnl_usdt = val_now - invested
                            pnl_pct = ((curr_price - entry) / entry) * 100
                            
                            st.markdown(f"**{pos['symbol']}**")
                            
                            m1, m2 = st.columns(2)
                            m1.caption("Harga Kini")
                            m1.write(f"{curr_price}")
                            m2.caption("Profit/Rugi")
                            color = "green" if pnl_usdt > 0 else "red"
                            m2.markdown(f":{color}[${pnl_usdt:.2f}]")

                            st.progress(min(max((curr_price - pos['sl']) / (pos['tp'] - pos['sl']), 0.0), 1.0))
                            st.caption(f"SL: {pos['sl']:.4f} ⟷ TP: {pos['tp']:.4f}")
                            
                            # LOGIKA JUAL
                            action = None
                            if curr_price >= pos['tp']: action = "TP"
                            elif curr_price <= pos['sl']: action = "SL"
                            
                            if action:
                                if live_mode:
                                    exchange.create_market_sell_order(pos['symbol'], pos['quantity'])
                                    add_log(f"SOLD {pos['symbol']} ({action})", "sell")
                                else:
                                    add_log(f"SIMULASI SOLD {pos['symbol']}", "sell")
                                
                                # Hapus dari DB
                                current_db = load_positions()
                                new_db = [p for p in current_db if p['symbol'] != pos['symbol']]
                                save_positions(new_db)
                                st.rerun()

                        except Exception as e: st.error(f"Err: {e}")
        
        # 3. SCANNING
        if len(active_pos) < total_slots:
            st.divider()
            st.caption(f"📡 SCANNING... (RSI < {rsi_lim})")
            if free_usdt >= modal_per_trade:
                targets = get_target_coins(exchange)
                for sym in targets:
                    if any(p['symbol'] == sym for p in active_pos): continue
                    
                    data = analyze_coin(exchange, sym, tf_sel, rsi_lim)
                    if data and data['Status'] == "BUY":
                        sym = data['Symbol']
                        price = data['Harga']
                        st.success(f"🚀 BUY {sym} @ {price}")
                        
                        qty = (modal_per_trade / price) * 0.998
                        tp = price * (1 + tp_pct/100)
                        sl = price * (1 - sl_pct/100)
                        
                        sukses = False
                        if live_mode:
                            try:
                                params = {'createMarketBuyOrderRequiresPrice': False}
                                exchange.create_market_buy_order(sym, modal_per_trade, params)
                                sukses = True
                                add_log(f"BUY {sym}", "buy")
                            except: st.error("Gagal Beli")
                        else:
                            sukses = True
                            add_log(f"SIMULASI BUY {sym}", "buy")
                        
                        if sukses:
                            new_pos = {'symbol': sym, 'buy_price': price, 'quantity': qty, 'tp': tp, 'sl': sl}
                            current_db = load_positions()
                            current_db.append(new_pos)
                            save_positions(current_db)
                            st.rerun()
                        break
            else:
                st.warning("Saldo tidak cukup untuk slot baru.")
        else:
            st.info("Slot Penuh.")

    # Jeda Global
    time.sleep(refresh_rate)
