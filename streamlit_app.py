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

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Tokocrypto Manager", layout="wide", page_icon="💎")

# CSS Styling
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    div.stButton > button { width: 100%; border-radius: 5px; height: 3em; font-weight: bold; }
    .success-box { padding: 10px; background-color: #1b5e20; border-radius: 5px; color: white; margin-bottom: 10px; }
    .warning-box { padding: 10px; background-color: #ff6f00; border-radius: 5px; color: white; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 2. FILE HANDLING (.env & JSON) ---
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

# Fungsi Log
def add_log(msg, type="info"):
    if 'logs' not in st.session_state: st.session_state['logs'] = []
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state['logs'].insert(0, {"Waktu": ts, "Tipe": type, "Pesan": msg})
    if len(st.session_state['logs']) > 50: st.session_state['logs'] = st.session_state['logs'][:50]

# --- 3. INIT API ---
def init_exchange(api, secret):
    try:
        return ccxt.tokocrypto({
            'apiKey': api, 'secret': secret,
            'enableRateLimit': True,
            'options': {'adjustForTimeDifference': True}
        })
    except: return None

# --- SIDEBAR LOGIC (DIPERBAIKI) ---
load_dotenv(override=True) # Load awal

with st.sidebar:
    st.header("🎛️ PENGATURAN")
    
    # --- BAGIAN 1: API KEY (.ENV) ---
    st.subheader("1. Kredensial API")
    
    # Uploader .env
    env_upload = st.file_uploader("Upload .env (API Key)", type=['env', 'txt'], key="env_upl")
    if env_upload is not None:
        # Baca dan Simpan File
        stringio = StringIO(env_upload.getvalue().decode("utf-8"))
        content = stringio.read()
        with open(ENV_FILE, "w") as f:
            f.write(content)
        
        # Load ulang environment variable SEKETIKA
        load_dotenv(override=True)
        st.success("✅ .env Berhasil Disimpan!")
        time.sleep(1)
        st.rerun() # Refresh halaman agar variabel terbaca

    # Cek apakah variabel sudah ada di sistem
    SYS_API = os.getenv('TOKO_API_KEY')
    SYS_SECRET = os.getenv('TOKO_SECRET_KEY')

    # Input manual (Otomatis terisi jika .env berhasil di-load)
    api_key = st.text_input("API Key", value=SYS_API if SYS_API else "", type="password")
    secret_key = st.text_input("Secret Key", value=SYS_SECRET if SYS_SECRET else "", type="password")

    if api_key and secret_key:
        st.markdown('<div class="success-box">API Key Terdeteksi 👌</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="warning-box">API Key Belum Diisi ❌</div>', unsafe_allow_html=True)

    st.divider()

    # --- BAGIAN 2: JSON DOMPET ---
    st.subheader("2. File Dompet JSON")
    
    json_upload = st.file_uploader("Upload posisi_multi.json", type=['json'], key="json_upl")
    
    # Tombol Proses (Hanya muncul jika file dipilih)
    if json_upload is not None:
        if st.button("📥 TERAPKAN FILE JSON", type="primary"):
            try:
                # Baca JSON
                data_json = json.load(json_upload)
                
                # Validasi sederhana
                if isinstance(data_json, list):
                    save_positions(data_json) # Simpan ke file lokal
                    st.success(f"✅ Berhasil import {len(data_json)} koin!")
                    time.sleep(1)
                    st.rerun() # Refresh halaman untuk menampilkan data
                else:
                    st.error("Format JSON salah (harus dimulai dengan [ ... ] )")
            except Exception as e:
                st.error(f"Error membaca file: {e}")

    # Indikator Database Lokal
    curr_db = load_positions()
    if len(curr_db) > 0:
        st.caption(f"💾 Database Lokal: {len(curr_db)} Posisi Tersimpan.")
    else:
        st.caption("💾 Database Lokal: Kosong.")

    st.divider()
    
    # --- BAGIAN 3: TOMBOL KONTROL ---
    start_btn = st.button("MULAI BOT")
    stop_btn = st.button("STOP BOT")
    
    if start_btn: 
        st.session_state['active'] = True
        st.rerun()
    if stop_btn: 
        st.session_state['active'] = False
        st.rerun()

# --- MAIN PAGE LOGIC ---
st.title("💎 Tokocrypto Dashboard")

if 'active' not in st.session_state: st.session_state['active'] = False

# 1. LOAD DATA POSISI (Selalu diload agar terlihat walau bot mati)
active_pos = load_positions()

# 2. TAMPILKAN STATUS DATABASE JSON (Agar user tahu file masuk/tidak)
if active_pos:
    st.success(f"📂 File JSON Terbaca: {len(active_pos)} koin siap ditradingkan.")
else:
    st.warning("📂 Belum ada data posisi. Silakan Upload JSON atau Scan API.")

# 3. CEK KONEKSI API
exchange = init_exchange(api_key, secret_key)
if not exchange:
    st.error("⚠️ API Key belum valid. Bot hanya akan menampilkan data JSON (Mode Read-Only).")

# 4. CONTAINER UTAMA
placeholder = st.empty()

# JIKA BOT STOP (Tampilan Statis)
if not st.session_state['active']:
    with placeholder.container():
        st.info("Tekan tombol 'MULAI BOT' di sidebar untuk mengaktifkan refresh otomatis.")
        
        # Tampilkan Tabel Data JSON mentah agar user yakin data masuk
        if active_pos:
            st.markdown("### Preview Data JSON:")
            df_preview = pd.DataFrame(active_pos)
            st.dataframe(df_preview, use_container_width=True)

# JIKA BOT AKTIF (Looping)
else:
    # Loop Refresh
    while st.session_state['active']:
        with placeholder.container():
            # Reload data terbaru dari file
            active_pos = load_positions()
            
            # --- A. INFO SALDO (Perlu API) ---
            free_usdt = 0
            if exchange:
                try:
                    bal = exchange.fetch_balance()
                    free_usdt = bal['USDT']['free']
                    st.metric("Saldo USDT (Exchange)", f"{free_usdt:.2f}")
                except Exception as e:
                    st.warning(f"Gagal ambil saldo: {e}")

            st.divider()

            # --- B. PORTOFOLIO ---
            if active_pos:
                st.subheader(f"🔥 Live Monitoring ({len(active_pos)} Koin)")
                cols = st.columns(3)
                for i, pos in enumerate(active_pos):
                    with cols[i % 3]:
                        with st.container(border=True):
                            st.markdown(f"**{pos['symbol']}**")
                            
                            current_price = 0
                            # Coba ambil harga live jika API ada
                            if exchange:
                                try:
                                    tik = exchange.fetch_ticker(pos['symbol'])
                                    current_price = tik['last']
                                except: pass
                            
                            # Tampilkan Data dari JSON
                            c1, c2 = st.columns(2)
                            c1.caption("Entry JSON"); c1.write(pos['buy_price'])
                            
                            if current_price > 0:
                                c2.caption("Harga Live"); c2.write(current_price)
                                # Hitung PnL
                                pnl = (current_price - pos['buy_price']) * pos['quantity']
                                color = "green" if pnl >= 0 else "red"
                                st.markdown(f"<h4 style='color:{color}'>${pnl:.2f}</h4>", unsafe_allow_html=True)
                                
                                # Logic Progress Bar
                                if pos['tp'] and pos['sl']:
                                    denom = pos['tp'] - pos['sl']
                                    if denom != 0:
                                        prog = (current_price - pos['sl']) / denom
                                        st.progress(min(max(prog, 0.0), 1.0))
                                    st.caption(f"SL: {pos['sl']} | TP: {pos['tp']}")
                                    
                                    # LOGIC JUAL (Contoh Sederhana)
                                    # ... (Logic jual sama seperti sebelumnya) ...
                            else:
                                c2.caption("Harga Live"); c2.write("Waiting API...")
                                st.info("Menunggu koneksi API untuk harga...")
            else:
                st.info("Tidak ada posisi aktif.")

        # Delay loop
        time.sleep(5)
