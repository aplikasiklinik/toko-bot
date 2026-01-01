import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import time
import json
import os
from dotenv import load_dotenv
from datetime import datetime

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Tokocrypto Ultra Sync", layout="wide", page_icon="♻️")
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    .stMetric { background-color: #1A1C24; border: 1px solid #333; border-radius: 8px; }
    /* Membuat tombol Start/Stop lebih besar */
    button[kind="primary"] { width: 100%; border: 1px solid #00FF00; }
    button[kind="secondary"] { width: 100%; border: 1px solid #FF0000; }
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

# --- 4. FITUR SYNC (DIPERBAIKI) ---
def sync_wallet(exchange, tp_pct, sl_pct):
    found = []
    try:
        bal = exchange.fetch_balance()
        # Cek semua saldo
        for currency, amount in bal['total'].items():
            # Hanya ambil jika saldo > 0 dan bukan uang fiat/stablecoin
            if amount > 0 and currency not in ['USDT', 'BIDR', 'BUSD', 'USDC']:
                symbol = f"{currency}/USDT"
                
                # Cek nilai dalam USDT
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    price = ticker['last']
                    value_usdt = amount * price
                    
                    # Minimal nilai $1 agar koin 'debu' tidak masuk
                    if value_usdt > 1.0: 
                        # Cek apakah sudah ada di DB bot?
                        current_db = load_positions()
                        if not any(p['symbol'] == symbol for p in current_db):
                            # Masukkan ke DB
                            new_pos = {
                                'symbol': symbol,
                                'buy_price': price, # Anggap harga sekarang sbg entry
                                'quantity': amount,
                                'tp': price * (1 + tp_pct/100),
                                'sl': price * (1 - sl_pct/100)
                            }
                            current_db.append(new_pos)
                            save_positions(current_db)
                            found.append(symbol)
                except: pass
        return found
    except Exception as e:
        st.error(f"Sync Error: {e}")
        return []

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

# --- SIDEBAR (LAYOUT BARU) ---
load_dotenv()
ENV_API_KEY = os.getenv('TOKO_API_KEY')
ENV_SECRET_KEY = os.getenv('TOKO_SECRET_KEY')

with st.sidebar:
    st.header("🎛️ PANEL KONTROL")
    
    # 1. API KEY (Wajib diisi dulu)
    api_key = ENV_API_KEY if ENV_API_KEY else st.text_input("API Key", type="password")
    secret_key = ENV_SECRET_KEY if ENV_SECRET_KEY else st.text_input("Secret Key", type="password")
    
    st.divider()

    # 2. TOMBOL SYNC (POSISI PALING ATAS & JELAS)
    st.markdown("### ♻️ DOMPET SINKRONISASI")
    st.info("Tekan tombol di bawah jika koin yang Anda beli tidak muncul di layar.")
    
    if st.button("🔍 SCAN DOMPET TOKOCRYPTO SEKARANG", type="primary"):
        if api_key and secret_key:
            tmp_ex = init_exchange(api_key, secret_key)
            if tmp_ex:
                with st.spinner("Sedang memeriksa dompet Tokocrypto Anda..."):
                    found = sync_wallet(tmp_ex, 1.5, 2.0) # Default TP 1.5, SL 2
                
                if found:
                    st.success(f"BERHASIL IMPOR: {', '.join(found)}")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Tidak ditemukan koin baru (Nilai > $1).")
            else:
                st.error("Koneksi Gagal.")
        else:
            st.error("API Key Belum Diisi!")
            
    st.divider()

    # 3. SETTING TRADING
    st.markdown("### ⚙️ PENGATURAN")
    modal_per_trade = st.number_input("Modal Per Slot (USDT)", 11.0)
    total_slots = st.number_input("Jumlah Slot Max", 1, 10, 3)
    
    st.caption("TARGET PROFIT/LOSS")
    c_tp, c_sl = st.columns(2)
    tp_pct = c_tp.number_input("TP %", 1.5)
    sl_pct = c_sl.number_input("SL %", 2.0)
    
    st.caption("STRATEGI RSI")
    tf_sel = st.selectbox("Timeframe", ["15m", "5m"], index=1)
    rsi_lim = st.number_input("RSI Limit (<)", 35)
    
    live_mode = st.toggle("🔴 LIVE TRADING", value=True)
    
    st.divider()
    
    # 4. START/STOP
    st.markdown("### ▶️ OPERASI")
    refresh_rate = st.slider("Kecepatan Refresh (Detik)", 3, 30, 5)
    
    col_play, col_stop = st.columns(2)
    start_btn = col_play.button("MULAI BOT")
    stop_btn = col_stop.button("MATIKAN BOT")

    if start_btn: st.session_state['active'] = True
    if stop_btn: st.session_state['active'] = False

# --- MAIN UI ---
st.title("💎 Tokocrypto Ultra Sync Bot")

if 'active' not in st.session_state: st.session_state['active'] = False
if 'logs' not in st.session_state: st.session_state['logs'] = []
if not api_key: st.warning("Masukkan API Key di Sidebar sebelah kiri."); st.stop()

exchange = init_exchange(api_key, secret_key)
placeholder = st.empty()

# LOOP UTAMA
while st.session_state['active']:
    with placeholder.container():
        active_pos = load_positions()
        
        # 1. INFO KEUANGAN
        try:
            bal = exchange.fetch_balance()
            free_usdt = bal['USDT']['free']
            
            # Hitung Nilai Aset Koin
            coin_equity = 0
            for pos in active_pos:
                try:
                    tk = exchange.fetch_ticker(pos['symbol'])
                    coin_equity += (pos['quantity'] * tk['last'])
                except: pass
            
            total_wealth = free_usdt + coin_equity
            
            m1, m2, m3 = st.columns(3)
            m1.metric("💵 Uang Tunai", f"{free_usdt:.2f} USDT")
            m2.metric("💰 Total Kekayaan", f"{total_wealth:.2f} USDT")
            m3.metric("🎰 Slot Terpakai", f"{len(active_pos)} / {total_slots}")
        except: st.error("Gagal mengambil data saldo.")

        st.divider()

        # 2. MONITORING POSISI
        if active_pos:
            st.subheader(f"🔥 Portofolio Aktif ({len(active_pos)})")
            
            cols = st.columns(3)
            for i, pos in enumerate(active_pos):
                with cols[i % 3]:
                    with st.container():
                        st.markdown(f"### {pos['symbol']}")
                        try:
                            # Data Live
                            ticker = exchange.fetch_ticker(pos['symbol'])
                            curr_price = ticker['last']
                            entry = pos['buy_price']
                            qty = pos['quantity']
                            
                            # PnL
                            invested = entry * qty
                            val_now = curr_price * qty
                            pnl_usdt = val_now - invested
                            
                            # Tampilan
                            c1, c2 = st.columns(2)
                            c1.caption("Harga Masuk"); c1.write(f"{entry}")
                            c2.caption("Harga Kini"); c2.write(f"{curr_price}")
                            
                            color = "green" if pnl_usdt > 0 else "red"
                            st.markdown(f"<h4 style='color:{color}'>${pnl_usdt:.3f}</h4>", unsafe_allow_html=True)
                            
                            st.progress(min(max((curr_price - pos['sl']) / (pos['tp'] - pos['sl']), 0.0), 1.0))
                            st.caption(f"SL: {pos['sl']:.4f} <---> TP: {pos['tp']:.4f}")
                            
                            # Logic Jual
                            action = None
                            if curr_price >= pos['tp']: action = "TP"
                            elif curr_price <= pos['sl']: action = "SL"
                            
                            if action:
                                if live_mode:
                                    exchange.create_market_sell_order(pos['symbol'], pos['quantity'])
                                    add_log(f"JUAL {pos['symbol']} ({action})", "sell")
                                else:
                                    add_log(f"SIMULASI JUAL {pos['symbol']}", "sell")
                                
                                # Hapus Posisi
                                new_db = [p for p in active_pos if p['symbol'] != pos['symbol']]
                                save_positions(new_db)
                                st.rerun()

                        except: st.warning("Data loading...")

        # 3. SCANNING
        if len(active_pos) < total_slots:
            st.divider()
            st.info(f"📡 SCANNING MARKET (RSI < {rsi_lim})...")
            
            if free_usdt >= modal_per_trade:
                targets = get_target_coins(exchange)
                for sym in targets:
                    if any(p['symbol'] == sym for p in active_pos): continue
                    
                    data = analyze_coin(exchange, sym, tf_sel, rsi_lim)
                    if data and data['Status'] == "BUY":
                        sym = data['Symbol']
                        price = data['Harga']
                        st.success(f"🚀 BUY SIGNAL: {sym} @ {price}")
                        
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
                            except Exception as e: st.error(f"Gagal Beli: {e}")
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
            st.success("🔒 Semua Slot Terisi. Fokus Menjaga Aset.")

    time.sleep(refresh_rate)
