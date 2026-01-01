import streamlit as st
import ccxt
import pandas as pd
import time
import json
import os
from io import StringIO
from dotenv import load_dotenv
from datetime import datetime

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Tokocrypto Manager", layout="wide", page_icon="💎")

# CSS Styling (Agar tampilan rapi & Tombol Full Width)
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    div.stButton > button { width: 100%; border-radius: 5px; height: 3em; font-weight: bold; }
    .success-box { padding: 10px; background-color: #1b5e20; border-radius: 5px; color: white; margin-bottom: 10px; text-align: center; }
    .warning-box { padding: 10px; background-color: #ff6f00; border-radius: 5px; color: white; margin-bottom: 10px; text-align: center; }
    .card { background-color: #262730; padding: 15px; border-radius: 10px; border: 1px solid #444; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 2. FILE HANDLING ---
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

def init_exchange(api, secret):
    try:
        if not api or not secret: return None
        return ccxt.tokocrypto({
            'apiKey': api, 'secret': secret,
            'enableRateLimit': True,
            'options': {'adjustForTimeDifference': True}
        })
    except: return None

# --- SIDEBAR: PENGATURAN ---
load_dotenv(override=True) # Load .env saat script mulai

with st.sidebar:
    st.header("🎛️ PENGATURAN")
    
    # === A. API KEY ===
    with st.expander("1. Kredensial API", expanded=True):
        # Upload .env
        env_upload = st.file_uploader("Upload .env", type=['env', 'txt'], key="env_upl")
        if env_upload is not None:
            stringio = StringIO(env_upload.getvalue().decode("utf-8"))
            content = stringio.read()
            with open(ENV_FILE, "w") as f: f.write(content)
            load_dotenv(override=True)
            st.success("✅ .env Tersimpan! Reloading...")
            time.sleep(1)
            st.rerun()

        # Input / Display
        SYS_API = os.getenv('TOKO_API_KEY')
        SYS_SECRET = os.getenv('TOKO_SECRET_KEY')
        
        api_key = st.text_input("API Key", value=SYS_API if SYS_API else "", type="password")
        secret_key = st.text_input("Secret Key", value=SYS_SECRET if SYS_SECRET else "", type="password")

        if api_key and secret_key:
            st.markdown('<div class="success-box">API Key Terdeteksi 👌</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="warning-box">API Key Kosong ❌</div>', unsafe_allow_html=True)

    st.divider()

    # === B. IMPORT JSON ===
    with st.expander("2. File Dompet JSON", expanded=True):
        json_upload = st.file_uploader("Upload posisi_multi.json", type=['json'], key="json_upl")
        
        if json_upload is not None:
            if st.button("📥 TERAPKAN FILE JSON", type="primary"):
                try:
                    data_json = json.load(json_upload)
                    if isinstance(data_json, list):
                        save_positions(data_json)
                        st.success(f"✅ Import {len(data_json)} koin sukses!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Format JSON salah (Harus List)")
                except Exception as e:
                    st.error(f"Error: {e}")

        # Status Database Lokal
        curr_db = load_positions()
        st.caption(f"💾 Database Lokal: {len(curr_db)} Posisi.")

    st.divider()
    
    # === C. KONTROL BOT ===
    c1, c2 = st.columns(2)
    start_btn = c1.button("MULAI")
    stop_btn = c2.button("STOP")
    
    if start_btn: 
        st.session_state['active'] = True
        st.rerun()
    if stop_btn: 
        st.session_state['active'] = False
        st.rerun()

# --- MAIN PAGE ---
st.title("💎 Tokocrypto Dashboard")

if 'active' not in st.session_state: st.session_state['active'] = False

# 1. Load Data
active_pos = load_positions()
exchange = init_exchange(api_key, secret_key)

# 2. Status Bar Atas
if active_pos:
    st.success(f"📂 STATUS: {len(active_pos)} koin dalam pantauan.")
else:
    st.warning("📂 STATUS: Dompet kosong. Silakan upload JSON.")

# 3. Konten Utama
placeholder = st.empty()

# --- MODE STOP (PREVIEW) ---
if not st.session_state['active']:
    with placeholder.container():
        st.info("Bot sedang ISTIRAHAT. Tekan 'MULAI' di sidebar untuk live trading.")
        
        if active_pos:
            st.subheader("📋 Preview Data (Static)")
            # MENGGUNAKAN st.table AGAR LEBIH STABIL (MENGHINDARI ERROR BROWSER)
            df = pd.DataFrame(active_pos)
            st.table(df) 

# --- MODE START (LIVE LOOP) ---
else:
    while st.session_state['active']:
        with placeholder.container():
            # Header Saldo
            try:
                if exchange:
                    bal = exchange.fetch_balance()
                    usdt = bal['USDT']['free']
                    st.metric("Saldo USDT", f"${usdt:.2f}")
                else:
                    st.warning("API Key Invalid / Koneksi Gagal")
            except: pass

            st.divider()

            # Grid Tampilan Koin
            if active_pos:
                cols = st.columns(3)
                for i, pos in enumerate(active_pos):
                    with cols[i % 3]:
                        # Style Kartu Manual (HTML)
                        with st.container(border=True):
                            st.markdown(f"### {pos['symbol']}")
                            
                            # Ambil Harga Live
                            live_price = 0
                            try:
                                if exchange:
                                    tk = exchange.fetch_ticker(pos['symbol'])
                                    live_price = tk['last']
                            except: pass
                            
                            # Tampilkan Data
                            c1, c2 = st.columns(2)
                            c1.caption("Entry"); c1.write(f"{pos['buy_price']}")
                            
                            if live_price > 0:
                                c2.caption("Live"); c2.write(f"{live_price}")
                                
                                # Hitung PnL
                                pnl = (live_price - pos['buy_price']) * pos['quantity']
                                pct = (pnl / (pos['buy_price'] * pos['quantity'])) * 100
                                color = "#00ff00" if pnl >= 0 else "#ff4b4b"
                                
                                st.markdown(f"<h3 style='color:{color}; margin:0'>${pnl:.2f} ({pct:.2f}%)</h3>", unsafe_allow_html=True)
                                
                                # Progress TP/SL
                                if pos['tp'] != pos['sl']:
                                    prog = (live_price - pos['sl']) / (pos['tp'] - pos['sl'])
                                    st.progress(min(max(prog, 0.0), 1.0))
                                st.caption(f"🔻 {pos['sl']} | 🎯 {pos['tp']}")
                                
                                # LOGIKA JUAL (Contoh)
                                action = ""
                                if live_price >= pos['tp']: action = "TP"
                                elif live_price <= pos['sl']: action = "SL"
                                
                                if action:
                                    st.toast(f"SIGNAL {action}: {pos['symbol']}")
                                    # Tambahkan logika exchange.create_market_sell_order disini jika mau auto-sell
                            else:
                                c2.caption("Live"); c2.write("Loading...")
                                st.spinner("Menunggu API...")
            
            else:
                st.info("Tidak ada data koin.")
        
        # Jeda refresh 5 detik
        time.sleep(5)
