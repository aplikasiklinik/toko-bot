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

st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    div.stButton > button { width: 100%; border-radius: 5px; height: 3em; font-weight: bold; }
    .success-box { padding: 10px; background-color: #1b5e20; border-radius: 5px; color: white; margin-bottom: 10px; text-align: center; }
    .error-box { padding: 10px; background-color: #b71c1c; border-radius: 5px; color: white; margin-bottom: 10px; text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- 2. DATABASE & FUNGSI ---
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
        # SETUP KHUSUS UNTUK MENGHINDARI BLOKIR 451
        exchange = ccxt.tokocrypto({
            'apiKey': api, 
            'secret': secret,
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
                'recvWindow': 60000
            },
            # Menambahkan User-Agent agar tidak terdeteksi sebagai bot script
            'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        return exchange
    except: return None

# --- SIDEBAR ---
load_dotenv(override=True)

with st.sidebar:
    st.header("🎛️ PANEL KONTROL")
    
    # 1. API KEY
    with st.expander("🔑 API Key Setup", expanded=True):
        env_up = st.file_uploader("Upload .env", type=['env', 'txt'])
        if env_up:
            stringio = StringIO(env_up.getvalue().decode("utf-8"))
            with open(ENV_FILE, "w") as f: f.write(stringio.read())
            load_dotenv(override=True)
            st.rerun()

        SYS_API = os.getenv('TOKO_API_KEY')
        SYS_SECRET = os.getenv('TOKO_SECRET_KEY')
        
        api_key = st.text_input("API Key", value=SYS_API if SYS_API else "", type="password")
        secret_key = st.text_input("Secret Key", value=SYS_SECRET if SYS_SECRET else "", type="password")

        if api_key and secret_key:
            st.success("API Key Terdeteksi 👌")
        else:
            st.warning("API Key Kosong")

    st.divider()

    # 2. JSON UPLOAD
    with st.expander("📂 File JSON Dompet", expanded=True):
        json_up = st.file_uploader("Upload posisi_multi.json", type=['json'])
        if json_up:
            if st.button("📥 LOAD JSON"):
                try:
                    data = json.load(json_up)
                    save_positions(data)
                    st.success(f"Sukses load {len(data)} data!")
                    time.sleep(1)
                    st.rerun()
                except: st.error("File JSON Rusak")
        
        curr = load_positions()
        st.caption(f"Total Data: {len(curr)} Koin")

    st.divider()
    
    # 3. TOMBOL START
    if st.button("MULAI BOT", type="primary"):
        st.session_state['active'] = True
        st.rerun()
        
    if st.button("STOP BOT"):
        st.session_state['active'] = False
        st.rerun()

# --- MAIN SCREEN ---
st.title("💎 Tokocrypto Monitor")

if 'active' not in st.session_state: st.session_state['active'] = False

active_pos = load_positions()
exchange = init_exchange(api_key, secret_key)
placeholder = st.empty()

# --- MODE STOP ---
if not st.session_state['active']:
    with placeholder.container():
        st.info("Tekan 'MULAI BOT' di sidebar.")
        if active_pos:
            st.markdown("### Preview Data JSON (Mode Offline)")
            # Menggunakan TABLE agar tidak error Javascript
            st.table(pd.DataFrame(active_pos))

# --- MODE START ---
else:
    while st.session_state['active']:
        with placeholder.container():
            # 1. CEK KONEKSI DAN SALDO
            api_connected = False
            try:
                if exchange:
                    # Coba fetch balance
                    bal = exchange.fetch_balance()
                    usdt = bal['USDT']['free']
                    st.metric("Saldo USDT", f"${usdt:.2f}")
                    api_connected = True
                else:
                    st.error("Setup Exchange Gagal")
            except Exception as e:
                err_msg = str(e)
                if "451" in err_msg:
                    st.markdown("""
                    <div class="error-box">
                        <b>⛔ AKSES DIBLOKIR (Error 451)</b><br>
                        Tokocrypto memblokir IP ini. <br>
                        1. Jangan gunakan Streamlit Cloud (Gunakan Localhost).<br>
                        2. Matikan VPN.<br>
                        3. Pastikan Anda di IP Indonesia.
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.error(f"Koneksi API Error: {e}")

            st.divider()

            # 2. TAMPILAN KOIN
            if active_pos:
                st.subheader(f"🔥 Live Harga ({len(active_pos)} Koin)")
                cols = st.columns(3)
                for i, pos in enumerate(active_pos):
                    with cols[i % 3]:
                        with st.container(border=True):
                            st.markdown(f"#### {pos['symbol']}")
                            
                            # Ambil Harga
                            price_now = 0
                            if api_connected:
                                try:
                                    ticker = exchange.fetch_ticker(pos['symbol'])
                                    price_now = ticker['last']
                                except: pass
                            
                            # Tampilan
                            c1, c2 = st.columns(2)
                            c1.caption("Beli"); c1.write(f"{pos['buy_price']}")
                            
                            if price_now > 0:
                                c2.caption("Sekarang"); c2.write(f"{price_now}")
                                
                                # PnL
                                pnl = (price_now - pos['buy_price']) * pos['quantity']
                                color = "green" if pnl >= 0 else "red"
                                st.markdown(f"<h3 style='color:{color}; margin:0'>${pnl:.3f}</h3>", unsafe_allow_html=True)
                                
                                # Progress bar
                                if pos['tp'] != pos['sl']:
                                    prog = (price_now - pos['sl']) / (pos['tp'] - pos['sl'])
                                    st.progress(min(max(prog, 0.0), 1.0))
                                st.caption(f"SL: {pos['sl']} -> TP: {pos['tp']}")
                                
                            else:
                                c2.caption("Sekarang"); c2.write("-")
                                st.warning("Menunggu Koneksi...")
            
            else:
                st.info("Tidak ada data JSON. Silakan upload.")

        time.sleep(5)
