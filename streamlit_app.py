import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import time
import json
import os
from io import StringIO
from dotenv import load_dotenv
from datetime import datetime

# --- 1. KONFIGURASI HALAMAN & CSS ---
st.set_page_config(page_title="Tokocrypto Ultra Sync", layout="wide", page_icon="♻️")

st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    .stMetric { background-color: #1A1C24; border: 1px solid #333; border-radius: 8px; }
    
    /* Perbaikan Tombol agar terlihat Jelas */
    div.stButton > button {
        width: 100%;
        border-radius: 6px;
        height: 3em;
        font-weight: bold;
        transition: all 0.3s;
    }
    div.stButton > button:hover {
        transform: scale(1.02);
    }
    
    /* Styling khusus untuk uploader */
    .stFileUploader {
        padding: 10px;
        border: 1px dashed #444;
        border-radius: 10px;
        background-color: #161920;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. DATABASE & FILE HANDLING ---
DB_FILE = "posisi_multi.json"
ENV_FILE = ".env"

def load_positions():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f: return json.load(f)
        except: return []
    return []

def save_positions(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f, indent=4)

def add_log(msg, type="info"):
    if 'logs' not in st.session_state: st.session_state['logs'] = []
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state['logs'].insert(0, {"Waktu": ts, "Tipe": type, "Pesan": msg})
    if len(st.session_state['logs']) > 50: st.session_state['logs'] = st.session_state['logs'][:50]

# Fungsi untuk menyimpan .env dari upload
def save_env_from_upload(uploaded_file):
    try:
        stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
        content = stringio.read()
        with open(ENV_FILE, "w") as f:
            f.write(content)
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan .env: {e}")
        return False

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

# --- 4. FITUR SYNC & IMPORT ---
def sync_wallet_api(exchange, tp_pct, sl_pct):
    found = []
    try:
        bal = exchange.fetch_balance()
        for currency, amount in bal['total'].items():
            if amount > 0 and currency not in ['USDT', 'BIDR', 'BUSD', 'USDC', 'IDR']:
                symbol = f"{currency}/USDT"
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    price = ticker['last']
                    value_usdt = amount * price
                    
                    if value_usdt > 1.0: 
                        current_db = load_positions()
                        if not any(p['symbol'] == symbol for p in current_db):
                            new_pos = {
                                'symbol': symbol,
                                'buy_price': price,
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
        st.error(f"Sync API Error: {str(e)}")
        return []

def import_manual_json(uploaded_file):
    try:
        new_data = json.load(uploaded_file)
        if not isinstance(new_data, list):
            st.error("Format JSON salah. Harus berupa List [].")
            return 0
        
        current_db = load_positions()
        count = 0
        for item in new_data:
            # Validasi struktur data minimal
            if 'symbol' in item and 'quantity' in item:
                # Cek duplikat
                if not any(p['symbol'] == item['symbol'] for p in current_db):
                    # Lengkapi data jika kurang
                    if 'buy_price' not in item: item['buy_price'] = 0
                    if 'tp' not in item: item['tp'] = 0
                    if 'sl' not in item: item['sl'] = 0
                    
                    current_db.append(item)
                    count += 1
        
        save_positions(current_db)
        return count
    except Exception as e:
        st.error(f"Gagal Import File: {e}")
        return 0

# --- 5. ANALISA ---
def get_target_coins(exchange):
    try:
        exchange.load_markets()
        tickers = exchange.fetch_tickers()
        usdt_pairs = [k for k in tickers.keys() if '/USDT' in k]
        sorted_pairs = sorted(usdt_pairs, key=lambda x: tickers[x]['quoteVolume'] if 'quoteVolume' in tickers[x] else 0, reverse=True)
        return [x for x in sorted_pairs if 'USDC' not in x][:20]
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
# Load env variables dari file lokal jika ada
load_dotenv(override=True)
ENV_API_KEY = os.getenv('TOKO_API_KEY')
ENV_SECRET_KEY = os.getenv('TOKO_SECRET_KEY')

with st.sidebar:
    st.header("🎛️ PENGATURAN AKUN")
    
    # --- FITUR 1: UPLOAD ENV ---
    with st.expander("🔑 API Keys (.env / Manual)", expanded=not (ENV_API_KEY and ENV_SECRET_KEY)):
        st.caption("Upload file `.env` berisi `TOKO_API_KEY` dan `TOKO_SECRET_KEY` agar tersimpan otomatis.")
        env_file = st.file_uploader("Upload .env", type=['env', 'txt'], key="env_uploader")
        
        if env_file:
            if save_env_from_upload(env_file):
                st.success("File .env tersimpan! Reload halaman...")
                time.sleep(1)
                st.rerun()

        st.divider()
        st.caption("Atau input manual:")
        api_key_input = st.text_input("API Key", value=ENV_API_KEY if ENV_API_KEY else "", type="password")
        secret_key_input = st.text_input("Secret Key", value=ENV_SECRET_KEY if ENV_SECRET_KEY else "", type="password")
    
    # Gunakan variabel
    api_key = api_key_input
    secret_key = secret_key_input

    st.divider()

    # --- FITUR 2: IMPORT DOMPET (API + FILE) ---
    st.markdown("### ♻️ MANAJEMEN DOMPET")
    
    tab_scan, tab_import = st.tabs(["📡 Scan API", "📂 Upload File"])
    
    with tab_scan:
        st.caption("Scan otomatis dari saldo Tokocrypto.")
        if st.button("🔍 SCAN VIA API", type="primary"):
            if api_key and secret_key:
                tmp_ex = init_exchange(api_key, secret_key)
                if tmp_ex:
                    with st.spinner("Sedang memindai saldo..."):
                        found = sync_wallet_api(tmp_ex, 1.5, 2.0)
                    if found:
                        st.success(f"Ditemukan: {len(found)} koin.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.warning("Tidak ada koin baru > $1.")
                else:
                    st.error("Koneksi Gagal.")
            else:
                st.error("API Key Kosong.")

    with tab_import:
        st.caption("Upload file JSON manual berisi posisi.")
        manual_file = st.file_uploader("File JSON Dompet", type=['json'])
        if manual_file:
            if st.button("📥 PROSES FILE"):
                count = import_manual_json(manual_file)
                if count > 0:
                    st.success(f"Berhasil import {count} posisi!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Tidak ada data yang diimport.")

    st.divider()

    # PENGATURAN TRADING
    st.markdown("### ⚙️ KONFIGURASI BOT")
    modal_per_trade = st.number_input("Modal / Slot (USDT)", 10.0, 1000.0, 11.0)
    total_slots = st.number_input("Max Slot", 1, 20, 3)
    
    c1, c2 = st.columns(2)
    tp_pct = c1.number_input("TP %", 0.5, 100.0, 1.5)
    sl_pct = c2.number_input("SL %", 0.5, 100.0, 2.0)
    
    tf_sel = st.selectbox("Timeframe", ["15m", "5m", "1h"], index=0)
    rsi_lim = st.slider("RSI Trigger (<)", 10, 50, 30)
    
    live_mode = st.toggle("🔴 LIVE TRADING", False)
    
    st.divider()
    
    # TOMBOL START
    refresh_rate = st.slider("Refresh (Detik)", 5, 60, 10)
    if st.button("MULAI BOT", type="primary") if not st.session_state.get('active') else False:
        st.session_state['active'] = True
        st.rerun()
        
    if st.button("MATIKAN BOT", type="secondary"):
        st.session_state['active'] = False
        st.rerun()

# --- MAIN UI ---
st.title("💎 Tokocrypto Ultra Manager")

if 'active' not in st.session_state: st.session_state['active'] = False
if 'logs' not in st.session_state: st.session_state['logs'] = []

# Cek Kredensial
if not api_key or not secret_key:
    st.warning("⚠️ Masukkan API Key di sidebar atau Upload file .env")
    st.stop()

exchange = init_exchange(api_key, secret_key)
placeholder = st.empty()

# LOGIKA LOOPING UTAMA
while st.session_state['active']:
    with placeholder.container():
        active_pos = load_positions()
        
        # 1. INFO SALDO & ASET
        try:
            bal = exchange.fetch_balance()
            free_usdt = bal['USDT']['free']
            
            coin_equity = 0
            for pos in active_pos:
                try:
                    tk = exchange.fetch_ticker(pos['symbol'])
                    coin_equity += (pos['quantity'] * tk['last'])
                except: pass
            
            total_wealth = free_usdt + coin_equity
            
            m1, m2, m3 = st.columns(3)
            m1.metric("USDT Tersedia", f"{free_usdt:.2f}")
            m2.metric("Total Aset Estimasi", f"${total_wealth:.2f}")
            m3.metric("Slot", f"{len(active_pos)} / {total_slots}")
        except Exception as e:
            st.error(f"Koneksi Error: {e}")
            free_usdt = 0

        st.divider()

        # 2. MONITORING
        if active_pos:
            st.subheader(f"🔥 Portofolio ({len(active_pos)})")
            cols = st.columns(3)
            for i, pos in enumerate(active_pos):
                with cols[i % 3]:
                    with st.container(border=True):
                        st.markdown(f"**{pos['symbol']}**")
                        try:
                            # Live Data
                            ticker = exchange.fetch_ticker(pos['symbol'])
                            curr = ticker['last']
                            entry = pos['buy_price']
                            qty = pos['quantity']
                            
                            # PnL Calculation
                            val_now = curr * qty
                            val_buy = entry * qty
                            pnl = val_now - val_buy
                            pnl_pct = (pnl/val_buy)*100 if val_buy > 0 else 0
                            
                            c_color = "green" if pnl >= 0 else "red"
                            st.markdown(f"<span style='color:{c_color}; font-size:20px'>${pnl:.2f} ({pnl_pct:.2f}%)</span>", unsafe_allow_html=True)
                            
                            # Progress Logic
                            st.caption(f"Price: {curr}")
                            if pos['tp'] > 0 and pos['sl'] > 0:
                                rng = pos['tp'] - pos['sl']
                                prog = (curr - pos['sl']) / rng if rng != 0 else 0.5
                                st.progress(max(0.0, min(1.0, prog)))
                                st.caption(f"SL: {pos['sl']:.4f} | TP: {pos['tp']:.4f}")
                            else:
                                st.warning("TP/SL belum diset (Import Manual)")

                            # JUAL LOGIC
                            act = None
                            if pos['tp'] > 0 and curr >= pos['tp']: act = "TP"
                            elif pos['sl'] > 0 and curr <= pos['sl']: act = "SL"
                            
                            if act:
                                if live_mode:
                                    try:
                                        exchange.create_market_sell_order(pos['symbol'], qty)
                                        add_log(f"JUAL SUKSES {pos['symbol']} ({act})", "sell")
                                        
                                        # Hapus dari DB
                                        new_db = [p for p in active_pos if p['symbol'] != pos['symbol']]
                                        save_positions(new_db)
                                        st.rerun()
                                    except Exception as e: add_log(f"GAGAL JUAL: {e}", "error")
                                else:
                                    add_log(f"SIMULASI JUAL {pos['symbol']} ({act})", "sell")
                                    # Hapus simulasi
                                    new_db = [p for p in active_pos if p['symbol'] != pos['symbol']]
                                    save_positions(new_db)
                                    st.rerun()

                        except: st.caption("Loading data...")
        else:
            st.info("Portofolio kosong. Menunggu sinyal buy atau scan manual.")

        # 3. AUTO BUY (SCANNING)
        if len(active_pos) < total_slots:
            st.divider()
            st.write(f"📡 Scanning Market ({tf_sel})...")
            
            if free_usdt >= modal_per_trade:
                targets = get_target_coins(exchange)
                scanned = 0
                for sym in targets:
                    if any(p['symbol'] == sym for p in active_pos): continue
                    
                    data = analyze_coin(exchange, sym, tf_sel, rsi_lim)
                    scanned += 1
                    
                    if data and data['Status'] == "BUY":
                        price = data['Harga']
                        qty = (modal_per_trade / price) * 0.995
                        tp = price * (1 + tp_pct/100)
                        sl = price * (1 - sl_pct/100)
                        
                        success = False
                        if live_mode:
                            try:
                                exchange.create_market_buy_order(sym, qty)
                                success = True
                                add_log(f"BUY {sym}", "buy")
                            except Exception as e: add_log(f"Error Buy {sym}: {e}", "error")
                        else:
                            success = True
                            add_log(f"SIMULASI BUY {sym}", "buy")
                        
                        if success:
                            new_pos = {'symbol': sym, 'buy_price': price, 'quantity': qty, 'tp': tp, 'sl': sl}
                            db = load_positions()
                            db.append(new_pos)
                            save_positions(db)
                            st.toast(f"Buy {sym} Sukses!")
                            st.rerun()
                        break
                    if scanned >= 5: break # Limit scan speed
            else:
                st.caption("Saldo USDT Kurang untuk membuka posisi baru.")

        # 4. LOGS
        with st.expander("Riwayat Aktivitas", expanded=True):
            for log in st.session_state['logs']:
                icon = "🟢" if log['Tipe'] == "buy" else "🔴" if log['Tipe'] == "sell" else "📝"
                st.text(f"{log['Waktu']} {icon} {log['Pesan']}")

    time.sleep(refresh_rate)
