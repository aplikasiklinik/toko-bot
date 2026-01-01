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

# --- 1. KONFIGURASI HALAMAN (Wajib Paling Atas) ---
st.set_page_config(page_title="Tokocrypto Pro Stable", layout="wide", page_icon="🛡️")

# CSS Khusus untuk Tampilan Stabil & Gelap
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    .stMetric { background-color: #1A1C24; border: 1px solid #333; border-radius: 8px; padding: 10px; }
    div[data-testid="stExpander"] { background-color: #1A1C24; border: 1px solid #333; border-radius: 8px; }
    .stAlert { background-color: #1A1C24; border: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# --- 2. FUNGSI DATABASE & LOGGING (Safe I/O) ---
DB_FILE = "posisi_multi.json"

def load_positions():
    """Membaca database posisi dengan error handling ketat"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except: return []
    return []

def save_new_position(pos_data):
    """Menyimpan posisi baru tanpa menimpa data lama yang korup"""
    try:
        current = load_positions()
        current.append(pos_data)
        with open(DB_FILE, 'w') as f: json.dump(current, f)
        return True
    except Exception as e:
        print(f"Error Saving: {e}")
        return False

def remove_position(symbol):
    """Menghapus posisi yang sudah terjual"""
    try:
        current = load_positions()
        new_list = [p for p in current if p['symbol'] != symbol]
        with open(DB_FILE, 'w') as f: json.dump(new_list, f)
    except: pass

def add_log(msg, type="info"):
    """Menyimpan log ke session state"""
    if 'logs' not in st.session_state: st.session_state['logs'] = []
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state['logs'].insert(0, {"Waktu": ts, "Tipe": type, "Pesan": msg})
    # Batasi log agar memori tidak bocor
    if len(st.session_state['logs']) > 100: st.session_state['logs'].pop()

# --- 3. FUNGSI KONEKSI EXCHANGE ---
def init_exchange(api, secret):
    try:
        return ccxt.tokocrypto({
            'apiKey': api, 'secret': secret,
            'enableRateLimit': True, # Wajib True untuk mencegah Ban IP
            'timeout': 30000, 
            'options': {
                'adjustForTimeDifference': True,
                'defaultType': 'spot'
            }
        })
    except: return None

def get_financial_summary(exchange, active_positions):
    """Menghitung total kekayaan bersih secara real-time"""
    try:
        bal = exchange.fetch_balance()
        free_usdt = bal['USDT']['free']
        
        asset_value = 0
        for pos in active_positions:
            try:
                # Kita pakai harga terakhir dari cache jika memungkinkan untuk hemat API
                ticker = exchange.fetch_ticker(pos['symbol'])
                asset_value += (pos['quantity'] * ticker['last'])
            except: pass
            
        total_equity = free_usdt + asset_value
        return free_usdt, total_equity
    except: return 0.0, 0.0

# --- 4. FUNGSI ANALISA (CORE LOGIC) ---
def get_target_coins(exchange):
    try:
        exchange.load_markets()
        tickers = exchange.fetch_tickers()
        usdt_pairs = [k for k in tickers.keys() if '/USDT' in k]
        # Sortir berdasarkan Volume transaksi (Uang yang mengalir)
        sorted_pairs = sorted(usdt_pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        # Ambil Top 25, hindari Stablecoin
        filtered = [x for x in sorted_pairs if all(ex not in x for ex in ['USDC', 'FDUSD', 'TUSD', 'BUSD'])][:25]
        return filtered
    except: return []

def analyze_coin_strict(exchange, symbol, tf, rsi_limit):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=50)
        if not ohlcv or len(ohlcv) < 14: return None
        
        df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
        df['rsi'] = ta.rsi(df['close'], length=14)
        
        rsi = df['rsi'].iloc[-1]
        price = df['close'].iloc[-1]
        
        status = "BUY" if rsi < rsi_limit else "WAIT"
        return {'Symbol': symbol, 'Harga': price, 'RSI': round(rsi, 2), 'Status': status}
    except: return None

# --- 5. UI SIDEBAR (PENGATURAN) ---
load_dotenv()
with st.sidebar:
    st.header("🎛️ Panel Kontrol Utama")
    
    # KUNCI API
    api_key = os.getenv('TOKO_API_KEY')
    secret_key = os.getenv('TOKO_SECRET_KEY')
    
    if not api_key:
        api_key = st.text_input("API Key", type="password")
        secret_key = st.text_input("Secret Key", type="password")

    st.divider()

    # --- PENGATURAN YANG ANDA CARI (DITARUH DI ATAS) ---
    st.subheader("⏱️ Kecepatan & Refresh")
    refresh_rate = st.slider("Jeda Update (Detik)", min_value=1, max_value=60, value=5, 
                             help="Mengatur seberapa sering bot mengecek harga. 5-10 detik direkomendasikan.")
    
    st.divider()

    st.subheader("💰 Manajemen Uang")
    # Validasi Modal Min 10 USDT (Aturan Exchange)
    modal_per_trade = st.number_input("Modal Per Slot (USDT)", value=15.0, min_value=11.0, 
                                      help="Minimal 11 USDT agar order tidak ditolak Exchange.")
    total_slots = st.number_input("Jumlah Slot (Posisi Max)", 1, 10, 3)

    st.subheader("⚡ Strategi RSI")
    tf_selected = st.selectbox("Timeframe", ["15m", "5m"], index=1)
    rsi_threshold = st.number_input("Batas RSI Beli (<)", value=35)
    
    tp_pct = st.number_input("Take Profit (%)", 1.5)
    sl_pct = st.number_input("Stop Loss (%)", 2.0)

    st.divider()
    
    # TOMBOL KONTROL
    col_play, col_stop = st.columns(2)
    start_btn = col_play.button("▶️ START BOT", type="primary", use_container_width=True)
    stop_btn = col_stop.button("⏹️ STOP", use_container_width=True)

    if start_btn: st.session_state['bot_active'] = True
    if stop_btn: st.session_state['bot_active'] = False

    live_mode = st.toggle("🔴 LIVE MONEY (RESIKO ASLI)", value=True)

# --- 6. LOGIKA UTAMA (MAIN LOOP) ---
st.title("🛡️ Tokocrypto Pro Stable")

# Inisialisasi
if 'bot_active' not in st.session_state: st.session_state['bot_active'] = False
if 'logs' not in st.session_state: st.session_state['logs'] = []

if not api_key:
    st.warning("⚠️ API Key belum dimasukkan.")
    st.stop()

# Siapkan Exchange
exchange = init_exchange(api_key, secret_key)

# --- AREA DASHBOARD (ANTI-KEDIP) ---
# Kita gunakan st.empty() sebagai wadah utama.
# Loop akan memperbarui isi wadah ini tanpa me-reload halaman browser.
dashboard_placeholder = st.empty()
log_placeholder = st.empty()

# LOOP UTAMA
while st.session_state['bot_active']:
    
    # Gunakan Container di dalam loop untuk merender ulang isi dashboard
    with dashboard_placeholder.container():
        
        # A. UPDATE DATA KEUANGAN
        active_pos = load_positions()
        free_usdt, total_equity = get_financial_summary(exchange, active_pos)
        
        # Header Metrics
        c1, c2, c3 = st.columns(3)
        c1.metric("💵 Saldo Tunai", f"{free_usdt:.2f} USDT")
        c2.metric("💎 Total Aset Bersih", f"{total_equity:.2f} USDT", 
                  delta=f"{(total_equity - (total_slots * modal_per_trade)):.2f} PnL Est" if total_equity > 0 else None)
        c3.metric("🎰 Slot Terisi", f"{len(active_pos)} / {total_slots}")
        
        st.divider()

        # B. MONITORING POSISI (GUARDING)
        if active_pos:
            st.subheader(f"🔥 Portofolio Aktif ({len(active_pos)})")
            
            cols = st.columns(3) # Grid 3 kolom
            for i, pos in enumerate(active_pos):
                with cols[i % 3]: # Distribusi kartu ke grid
                    with st.container(border=True):
                        try:
                            # Fetch Harga
                            ticker = exchange.fetch_ticker(pos['symbol'])
                            curr_price = ticker['last']
                            
                            # Hitungan Finansial
                            entry = pos['buy_price']
                            qty = pos['quantity']
                            
                            # Kalkulasi PnL Real
                            # Fee Beli 0.1% sudah terjadi, Fee Jual 0.1% akan terjadi
                            # Kita estimasi bersih: (HargaJual * Qty * 0.999) - (HargaBeli * Qty)
                            val_now_clean = (curr_price * qty) * 0.999 
                            cost_clean = entry * qty
                            net_pnl = val_now_clean - cost_clean
                            pnl_pct = ((curr_price - entry) / entry) * 100
                            
                            # Tampilan Kartu
                            st.markdown(f"**{pos['symbol']}**")
                            c_p1, c_p2 = st.columns(2)
                            c_p1.caption("Harga Beli")
                            c_p1.write(f"{entry}")
                            c_p2.caption("Harga Kini")
                            c_p2.write(f"{curr_price}")
                            
                            st.divider()
                            
                            # Indikator Profit
                            color = "green" if net_pnl > 0 else "red"
                            st.markdown(f"<h3 style='text-align: center; color: {color}; margin: 0;'>${net_pnl:.4f}</h3>", unsafe_allow_html=True)
                            st.markdown(f"<p style='text-align: center; color: gray; margin: 0;'>({pnl_pct:.2f}%)</p>", unsafe_allow_html=True)
                            
                            # Progress Bar Visual
                            st.progress(min(max((curr_price - pos['sl']) / (pos['tp'] - pos['sl']), 0.0), 1.0))
                            st.caption(f"SL: {pos['sl']:.4f} ⟷ TP: {pos['tp']:.4f}")

                            # LOGIKA JUAL
                            action = None
                            if curr_price >= pos['tp']: action = "TAKE PROFIT"
                            elif curr_price <= pos['sl']: action = "STOP LOSS"
                            
                            if action:
                                if live_mode:
                                    exchange.create_market_sell_order(pos['symbol'], pos['quantity'])
                                    add_log(f"💰 SOLD {pos['symbol']} ({action}) | Net: ${net_pnl:.2f}", "sell")
                                else:
                                    add_log(f"SIMULASI SOLD {pos['symbol']}", "sell")
                                
                                remove_position(pos['symbol'])
                                st.rerun() # Refresh instan setelah jual

                        except Exception as e:
                            st.error(f"Err: {e}")

        # C. SCANNING (Hanya jika slot ada)
        if len(active_pos) < total_slots:
            st.divider()
            st.caption(f"📡 SCANNING MARKET (RSI < {rsi_threshold})...")
            
            # Cek Saldo Cukup gak?
            if free_usdt < modal_per_trade:
                st.warning(f"⚠️ Saldo Tunai ({free_usdt:.2f}) kurang dari Modal Per Slot ({modal_per_trade}). Deposit dulu.")
            else:
                targets = get_target_coins(exchange)
                
                # Scan loop
                found = None
                for sym in targets:
                    # Skip jika sudah punya
                    if any(p['symbol'] == sym for p in active_pos): continue
                    
                    data = analyze_coin_strict(exchange, sym, tf_selected, rsi_threshold)
                    if data and data['Status'] == "BUY":
                        found = data
                        break # Ketemu satu, langsung keluar loop untuk eksekusi
                    
                    # Tidak perlu sleep di sini agar scanning cepat, 
                    # kita mengandalkan refresh rate utama di bawah
                
                # Eksekusi Beli
                if found:
                    sym = found['Symbol']
                    price = found['Harga']
                    
                    st.success(f"🚀 SINYAL: {sym} RSI {found['RSI']} -> MEMBELI...")
                    
                    # Hitung Qty (Safety Margin 0.2% untuk fee & slippage)
                    qty_est = (modal_per_trade / price) * 0.998
                    tp = price * (1 + tp_pct/100)
                    sl = price * (1 - sl_pct/100)
                    
                    success = False
                    if live_mode:
                        try:
                            # FORCE ORDER BY QUOTE (USDT)
                            params = {'createMarketBuyOrderRequiresPrice': False}
                            exchange.create_market_buy_order(sym, modal_per_trade, params)
                            add_log(f"🛒 BOUGHT {sym} @ {price}", "buy")
                            success = True
                        except Exception as e:
                            st.error(f"Gagal Order: {e}")
                    else:
                        add_log(f"SIMULASI BUY {sym}", "buy")
                        success = True
                    
                    if success:
                        save_new_position({
                            'symbol': sym, 'buy_price': price, 'quantity': qty_est,
                            'tp': tp, 'sl': sl
                        })
                        st.rerun() # Refresh instan setelah beli

        else:
            st.info("🔒 Slot Penuh. Fokus memantau aset.")

    # UPDATE LOG DI LUAR CONTAINER UTAMA (Agar tetap persisten)
    with log_placeholder.container():
        with st.expander("📜 Riwayat Transaksi", expanded=True):
            if st.session_state['logs']:
                st.dataframe(pd.DataFrame(st.session_state['logs']), use_container_width=True)

    # --- JEDA GLOBAL (ANTI-KEDIP) ---
    # Ini kuncinya: Loop Python yang menunggu, BUKAN browser yang refresh.
    time.sleep(refresh_rate)

# Pesan jika bot mati
if not st.session_state['bot_active']:
    st.info("Bot Standby. Atur konfigurasi di Sidebar lalu klik START.")
