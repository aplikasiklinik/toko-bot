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

# PERBAIKAN CSS: Menggunakan selector yang lebih aman agar tombol terlihat
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    .stMetric { background-color: #1A1C24; border: 1px solid #333; border-radius: 8px; }
    
    /* Membuat semua tombol menjadi lebar 100% tanpa merusak warna default */
    div.stButton > button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        font-weight: bold;
    }
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
    # Batasi log agar tidak memberatkan memori
    if len(st.session_state['logs']) > 50:
        st.session_state['logs'] = st.session_state['logs'][:50]

# --- 3. KONEKSI ---
def init_exchange(api, secret):
    try:
        if not api or not secret: return None
        return ccxt.tokocrypto({
            'apiKey': api, 'secret': secret,
            'enableRateLimit': True,
            'timeout': 30000, 
            'options': {'adjustForTimeDifference': True}
        })
    except: return None

# --- 4. FITUR SYNC ---
def sync_wallet(exchange, tp_pct, sl_pct):
    found = []
    try:
        bal = exchange.fetch_balance()
        # Cek saldo 'total' (free + used)
        for currency, amount in bal['total'].items():
            # Filter: Saldo > 0 dan bukan Stablecoin/Fiat
            if amount > 0 and currency not in ['USDT', 'BIDR', 'BUSD', 'USDC', 'IDR']:
                symbol = f"{currency}/USDT"
                
                try:
                    # Cek nilai koin dalam USDT
                    ticker = exchange.fetch_ticker(symbol)
                    price = ticker['last']
                    value_usdt = amount * price
                    
                    # Hanya ambil jika nilai aset > $1 (mengabaikan koin receh/debu)
                    if value_usdt > 1.0: 
                        current_db = load_positions()
                        # Cek apakah sudah ada di DB bot agar tidak duplikat
                        if not any(p['symbol'] == symbol for p in current_db):
                            new_pos = {
                                'symbol': symbol,
                                'buy_price': price, # Menggunakan harga saat ini sebagai referensi
                                'quantity': amount,
                                'tp': price * (1 + tp_pct/100),
                                'sl': price * (1 - sl_pct/100)
                            }
                            current_db.append(new_pos)
                            save_positions(current_db)
                            found.append(symbol)
                except Exception as e:
                    # Biasanya error terjadi jika pair tidak ada (misal koin delisting atau pair BTC)
                    pass
        return found
    except Exception as e:
        st.error(f"Sync Error: {str(e)}")
        return []

# --- 5. ANALISA ---
def get_target_coins(exchange):
    try:
        exchange.load_markets()
        tickers = exchange.fetch_tickers()
        usdt_pairs = [k for k in tickers.keys() if '/USDT' in k]
        # Urutkan berdasarkan volume agar likuid
        sorted_pairs = sorted(usdt_pairs, key=lambda x: tickers[x]['quoteVolume'] if 'quoteVolume' in tickers[x] else 0, reverse=True)
        return [x for x in sorted_pairs if 'USDC' not in x and 'BUSD' not in x][:20]
    except: return []

def analyze_coin(exchange, symbol, tf, rsi_limit):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=50)
        if not ohlcv or len(ohlcv) < 20: return None
        df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
        df['rsi'] = ta.rsi(df['close'], length=14)
        
        if df['rsi'].isnull().all(): return None
        
        rsi = df['rsi'].iloc[-1]
        price = df['close'].iloc[-1]
        status = "BUY" if rsi < rsi_limit else "WAIT"
        return {'Symbol': symbol, 'Harga': price, 'RSI': round(rsi, 2), 'Status': status}
    except: return None

# --- SIDEBAR ---
load_dotenv()
ENV_API_KEY = os.getenv('TOKO_API_KEY')
ENV_SECRET_KEY = os.getenv('TOKO_SECRET_KEY')

with st.sidebar:
    st.header("🎛️ PANEL KONTROL")
    
    # 1. API KEY
    with st.expander("🔐 Kredensial API", expanded=not (ENV_API_KEY and ENV_SECRET_KEY)):
        api_key = st.text_input("API Key", value=ENV_API_KEY if ENV_API_KEY else "", type="password")
        secret_key = st.text_input("Secret Key", value=ENV_SECRET_KEY if ENV_SECRET_KEY else "", type="password")
    
    st.divider()

    # 2. TOMBOL SYNC (Posisi diperjelas)
    st.markdown("### ♻️ DOMPET SINKRONISASI")
    st.info("Klik tombol ini untuk memasukkan koin yang sudah Anda beli di Tokocrypto ke dalam bot.")
    
    # Menggunakan type='primary' bawaan Streamlit (warna merah/solid)
    if st.button("🔍 SCAN DOMPET SEKARANG", type="primary"):
        if api_key and secret_key:
            tmp_ex = init_exchange(api_key, secret_key)
            if tmp_ex:
                with st.spinner("Sedang memindai dompet Tokocrypto..."):
                    # Default TP 1.5% dan SL 2.0% untuk posisi hasil sync
                    found_coins = sync_wallet(tmp_ex, 1.5, 2.0) 
                
                if found_coins:
                    st.success(f"BERHASIL IMPORT: {', '.join(found_coins)}")
                    time.sleep(2) # Beri waktu user membaca notifikasi
                    st.rerun()
                else:
                    st.warning("Tidak ditemukan koin baru (Nilai aset > $1 USD).")
            else:
                st.error("Koneksi API Gagal. Cek Key/Secret.")
        else:
            st.error("API Key belum diisi!")
            
    st.divider()

    # 3. SETTING TRADING
    st.markdown("### ⚙️ PENGATURAN")
    modal_per_trade = st.number_input("Modal Per Slot (USDT)", min_value=10.0, value=11.0)
    total_slots = st.number_input("Jumlah Slot Max", 1, 20, 3)
    
    c_tp, c_sl = st.columns(2)
    tp_pct = c_tp.number_input("TP (%)", 0.1, 100.0, 1.5)
    sl_pct = c_sl.number_input("SL (%)", 0.1, 100.0, 2.0)
    
    st.caption("STRATEGI RSI")
    tf_sel = st.selectbox("Timeframe", ["15m", "5m", "1h"], index=1)
    rsi_lim = st.number_input("RSI Limit (<)", 10, 50, 30)
    
    live_mode = st.toggle("🔴 LIVE TRADING (Real Money)", value=False)
    if live_mode:
        st.caption("⚠️ Bot akan melakukan order asli.")
    else:
        st.caption("🛡️ Mode Simulasi (Paper Trading).")
    
    st.divider()
    
    # 4. START/STOP
    st.markdown("### ▶️ OPERASI")
    refresh_rate = st.slider("Refresh Rate (Detik)", 5, 60, 10)
    
    col_play, col_stop = st.columns(2)
    start_btn = col_play.button("MULAI BOT")
    stop_btn = col_stop.button("MATIKAN BOT")

    if start_btn: st.session_state['active'] = True
    if stop_btn: st.session_state['active'] = False

# --- MAIN UI ---
st.title("💎 Tokocrypto Ultra Sync Bot")

# Inisialisasi Session State
if 'active' not in st.session_state: st.session_state['active'] = False
if 'logs' not in st.session_state: st.session_state['logs'] = []

# Cek API Key sebelum lanjut
if not api_key or not secret_key:
    st.warning("👈 Silakan masukkan API Key dan Secret Key di menu sebelah kiri.")
    st.stop()

exchange = init_exchange(api_key, secret_key)
placeholder = st.empty()

# LOOP UTAMA
while st.session_state['active']:
    with placeholder.container():
        active_pos = load_positions()
        
        # 1. INFO KEUANGAN
        try:
            # Ambil saldo realtime untuk menghitung total kekayaan
            bal = exchange.fetch_balance()
            free_usdt = bal['USDT']['free']
            
            # Hitung Equity Koin yang sedang hold
            coin_equity = 0
            for pos in active_pos:
                try:
                    tk = exchange.fetch_ticker(pos['symbol'])
                    coin_equity += (pos['quantity'] * tk['last'])
                except: pass
            
            total_wealth = free_usdt + coin_equity
            
            # Tampilan Metric
            m1, m2, m3 = st.columns(3)
            m1.metric("💵 Uang Tunai (USDT)", f"{free_usdt:.2f}")
            m2.metric("💰 Estimasi Total Aset", f"${total_wealth:.2f}")
            m3.metric("🎰 Slot Terpakai", f"{len(active_pos)} / {total_slots}")
            
        except Exception as e:
            st.error(f"Gagal mengambil data saldo: {str(e)}")
            free_usdt = 0 # Fallback

        st.divider()

        # 2. MONITORING POSISI
        if active_pos:
            st.subheader(f"🔥 Portofolio Aktif ({len(active_pos)})")
            
            # Grid layout untuk kartu koin
            cols = st.columns(3)
            for i, pos in enumerate(active_pos):
                with cols[i % 3]:
                    with st.container(border=True):
                        st.markdown(f"### **{pos['symbol']}**")
                        try:
                            # Data Live Ticker
                            ticker = exchange.fetch_ticker(pos['symbol'])
                            curr_price = ticker['last']
                            entry = pos['buy_price']
                            qty = pos['quantity']
                            
                            # Hitung Profit/Loss
                            invested = entry * qty
                            val_now = curr_price * qty
                            pnl_usdt = val_now - invested
                            pnl_pct = (pnl_usdt / invested) * 100 if invested > 0 else 0
                            
                            # Tampilan Data
                            c1, c2 = st.columns(2)
                            c1.caption("Harga Beli"); c1.write(f"{entry}")
                            c2.caption("Harga Kini"); c2.write(f"{curr_price}")
                            
                            color = "green" if pnl_usdt >= 0 else "red"
                            st.markdown(f"<h3 style='color:{color}; margin:0'>${pnl_usdt:.2f} ({pnl_pct:.2f}%)</h3>", unsafe_allow_html=True)
                            
                            # Progress Bar TP/SL
                            range_price = pos['tp'] - pos['sl']
                            progress = 0.5
                            if range_price > 0:
                                progress = (curr_price - pos['sl']) / range_price
                            progress = max(0.0, min(1.0, progress))
                            st.progress(progress)
                            st.caption(f"🔻 SL: {pos['sl']:.4f} | 🎯 TP: {pos['tp']:.4f}")
                            
                            # LOGIKA JUAL (TP/SL)
                            action = None
                            if curr_price >= pos['tp']: action = "TAKE PROFIT"
                            elif curr_price <= pos['sl']: action = "STOP LOSS"
                            
                            if action:
                                msg_jual = ""
                                if live_mode:
                                    try:
                                        exchange.create_market_sell_order(pos['symbol'], pos['quantity'])
                                        msg_jual = f"✅ JUAL {pos['symbol']} ({action})"
                                        add_log(msg_jual, "sell")
                                    except Exception as e:
                                        add_log(f"❌ Gagal Jual {pos['symbol']}: {e}", "error")
                                        action = None # Batalkan hapus DB jika error API
                                else:
                                    msg_jual = f"🤖 SIMULASI JUAL {pos['symbol']} ({action})"
                                    add_log(msg_jual, "sell")
                                
                                if action:
                                    # Hapus dari database lokal
                                    new_db = [p for p in active_pos if p['symbol'] != pos['symbol']]
                                    save_positions(new_db)
                                    st.toast(msg_jual)
                                    time.sleep(1)
                                    st.rerun()

                        except Exception as e: 
                            st.warning(f"Waiting data... {e}")

        else:
            st.info("Belum ada posisi aktif. Bot sedang memantau pasar atau menunggu hasil Scan Dompet.")

        # 3. SCANNING MARKET (Hanya jika ada slot kosong)
        if len(active_pos) < total_slots:
            st.divider()
            st.write(f"📡 Memindai Pasar (RSI < {rsi_lim}) pada TF {tf_sel}...")
            
            if free_usdt >= modal_per_trade:
                targets = get_target_coins(exchange)
                # Loop scanning (dibatasi 5 koin per refresh agar tidak kena rate limit)
                scanned_count = 0
                for sym in targets:
                    if any(p['symbol'] == sym for p in active_pos): continue
                    
                    data = analyze_coin(exchange, sym, tf_sel, rsi_lim)
                    scanned_count += 1
                    
                    if data and data['Status'] == "BUY":
                        sym = data['Symbol']
                        price = data['Harga']
                        
                        # Hitung Quantity (99.5% dari modal untuk fee safety)
                        qty = (modal_per_trade / price) * 0.995
                        tp = price * (1 + tp_pct/100)
                        sl = price * (1 - sl_pct/100)
                        
                        sukses = False
                        if live_mode:
                            try:
                                # Tokocrypto butuh penyesuaian untuk market buy, kadang by quote amount
                                # Disini kita pakai standar CCXT quantity
                                params = {} 
                                exchange.create_market_buy_order(sym, qty, params)
                                sukses = True
                                add_log(f"BUY {sym} @ {price}", "buy")
                            except Exception as e: 
                                add_log(f"Gagal Beli {sym}: {e}", "error")
                        else:
                            sukses = True
                            add_log(f"SIMULASI BUY {sym} @ {price}", "buy")
                        
                        if sukses:
                            new_pos = {'symbol': sym, 'buy_price': price, 'quantity': qty, 'tp': tp, 'sl': sl}
                            current_db = load_positions()
                            current_db.append(new_pos)
                            save_positions(current_db)
                            st.toast(f"🚀 POSISI BARU: {sym}")
                            time.sleep(1)
                            st.rerun()
                        break # Stop scanning setelah dapat 1 koin, lanjut next loop
                    
                    if scanned_count >= 5: break # Batasi scan per refresh
            else:
                st.warning(f"Saldo USDT tidak cukup untuk membuka posisi baru (Min: {modal_per_trade}).")
        else:
            st.success("🔒 Slot Penuh. Fokus memantau aset yang ada.")

        # 4. LOG AKTIVITAS
        with st.expander("📜 Log Aktivitas", expanded=True):
            for log in st.session_state['logs']:
                icon = "🟢" if log['Tipe'] == "buy" else "🔴" if log['Tipe'] == "sell" else "ℹ️"
                st.text(f"{log['Waktu']} {icon} {log['Pesan']}")

    # Jeda loop agar tidak CPU 100% dan UI Freeze
    time.sleep(refresh_rate)
