import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="자산관리 시뮬레이션", layout="centered")

# --- 🚀 1. 주가 비상 기억 저장소(세션 스테이트) 초기화 ---
if "price_backup" not in st.session_state:
    st.session_state.price_backup = {}

# --- 🚀 속도 최적화 및 철통 방어 캐시 ---
# --- 🚀 철통 방어 캐시 시스템 ---
@st.cache_data(ttl=600)
def get_exchange_rate():
    try: 
@@ -23,43 +22,43 @@
def get_price(ticker):
    if not ticker: return 0.0
    try: 
        ticker_obj = yf.Ticker(ticker)
        if 'last_price' in ticker_obj.fast_info: 
            val = float(ticker_obj.fast_info['last_price'])
        t = yf.Ticker(ticker)
        # 1차 시도: 실시간 가격
        if 'last_price' in t.fast_info: 
            val = float(t.fast_info['last_price'])
            if not pd.isna(val) and val > 0: return val

        hist = ticker_obj.history(period="7d")
        # 2차 시도: 야후 서버가 뻗었을 때 최근 5일치 종가 강제 추적
        hist = t.history(period="5d")
        if not hist.empty: 
            val = float(hist['Close'].iloc[-1])
            if not pd.isna(val) and val > 0: return val
        return 0.0
    except: return 0.0

# --- 🔌 구글 시트 연결 캐시 ---
@st.cache_resource(ttl=600)
def init_connection():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

# --- 📊 구글 시트 데이터 가져오기 (원천 차단 캐시 적용!) ---
@st.cache_data(ttl=300) # 5분 동안 시트 데이터를 기억하여 구글 서버 과부하를 완전히 막습니다.
@st.cache_data(ttl=300)
def load_sheet_data():
    try:
        client = init_connection()
        spreadsheet = client.open("ASSET_Simulation")
        balance = spreadsheet.worksheet("잔고").get_all_records()
        history = spreadsheet.worksheet("투자내역").get_all_records()
        stocks = spreadsheet.worksheet("종목관리").get_all_records()
        return balance, history, stocks
        return (
            spreadsheet.worksheet("잔고").get_all_records(),
            spreadsheet.worksheet("투자내역").get_all_records(),
            spreadsheet.worksheet("종목관리").get_all_records()
        )
    except:
        return None, None, None

balance_data, history_data, stock_data = load_sheet_data()

# 구글 서버가 완전히 막혔을 때의 비상 안내 안내판
if balance_data is None:
    st.warning("🚦 구글 시트 서버의 응답이 일시적으로 지연되고 있습니다. 앱 내부 시스템은 안전하니 걱정마세요! 약 1분 뒤에 새로고침(F5)을 눌러주세요.")
    st.warning("🚦 구글 시트 접속자가 많아 서버가 일시적으로 지연되고 있습니다. 약 1분 뒤에 새로고침(F5)을 눌러주세요!")
    st.stop()

exchange_rate = get_exchange_rate()
@@ -97,7 +96,7 @@
                    client = init_connection()
                    spreadsheet = client.open("ASSET_Simulation")
                    spreadsheet.worksheet("잔고").append_row([new_user_input, 1000000, 0, 1000000, "", ""])
                    st.cache_data.clear() # 새 유저 등록 시 캐시 리셋
                    st.cache_data.clear()
                    st.session_state.user_id = new_user_input
                    st.success(f"🎉 {new_user_input}님의 첫 금고 개설 완료!")
                    st.rerun()
@@ -146,18 +145,22 @@
    if ticker:
        raw_price = get_price(ticker)

        # 💡 [핵심 방어막] 야후 파이낸스가 주가를 못 가져오면(0원) 기존 성공했던 기억 저장소 가격을 복원합니다.
        if raw_price > 0:
            st.session_state.price_backup[ticker] = raw_price
        else:
            raw_price = st.session_state.price_backup.get(ticker, 0.0)
            if raw_price > 0:
                price_error_flag = True # 백업 가격을 가동했다는 내부 신호 활성화
                price_error_flag = True

        is_korean = ticker.endswith('.KS') or ticker.endswith('.KQ')
        current_price = raw_price if is_korean else raw_price * exchange_rate

    qty = data['qty']
    
    # 💡 0.200000 처럼 꼬리가 길어지는 것을 방지 (깔끔하게 정돈)
    clean_qty = round(qty, 4)
    if clean_qty == int(clean_qty): clean_qty = int(clean_qty)

    total_buy_cost = data['total_buy_cost']
    stock_value = current_price * qty
    total_stock_value += stock_value 
@@ -167,7 +170,7 @@

    stock_details.append({
        '종목명': name, 
        '보유 수량(주)': qty, 
        '보유 수량(주)': clean_qty, 
        '총 매수금액(원)': round(total_buy_cost),
        '현재 총 가치(원)': round(stock_value), 
        '수익률(%)': round(profit_rate, 2), 
@@ -190,7 +193,6 @@

st.divider()

# 핫한 뉴스 노출 영역
hot_news = []
for stock in stock_data:
    is_hot = str(stock.get('핫한뉴스선정', '')).strip().upper()
@@ -241,7 +243,7 @@
    try:
        def color_profit(val): 
            if pd.isna(val): return ""
            return f"color: {'red' if val > 0 else 'blue' if val < 0 else 'black'}"
            return f"color: {'#ff4b4b' if val > 0 else '#0083ff' if val < 0 else 'black'}"

        styled_df = df_owned.style.format({
            '총 매수금액(원)': '{:,.0f}', 
@@ -265,6 +267,13 @@
        st.dataframe(df_safe, hide_index=True, use_container_width=True)

    if price_error_flag:
        st.info("💡 야후 파이낸스 해외 서버 지연으로 인해 일부 종목 주가를 백업 데이터에서 안전하게 불러왔습니다.")
        st.info("💡 야후 파이낸스 해외 서버 지연으로 인해 일부 종목 주가를 과거 데이터에서 안전하게 불러왔습니다.")
else:
    st.info("아직 보유한 주식이 없어요. 왼쪽 메뉴에서 첫 투자를 시작해 보세요!")

st.divider()

# 💡 실종되었던 새로고침 버튼을 아주 확실하게 재배치!
if st.button("🔄 실시간 주식 가격 새로고침", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
