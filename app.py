import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="우리 딸의 첫 투자", layout="centered")

# --- 🚀 속도 최적화 캐시 (가격 불러오기 방어력 강화) ---
@st.cache_data(ttl=600)
def get_exchange_rate():
    try: return float(yf.Ticker("USDKRW=X").fast_info['last_price'])
    except: return 1350.0

@st.cache_data(ttl=300)
def get_price(ticker):
    try: 
        ticker_obj = yf.Ticker(ticker)
        # 1. 1순위: 가장 빠른 실시간 가격 찾기
        if 'last_price' in ticker_obj.fast_info:
            return float(ticker_obj.fast_info['last_price'])
        # 2. 2순위: 주말/휴장일이라 실시간 가격이 없으면 최근 5일 중 마지막 가격 가져오기
        hist = ticker_obj.history(period="5d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
        return 0.0
    except: 
        return 0.0

# --- 🔌 구글 시트 연결 ---
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
client = gspread.authorize(creds)
spreadsheet = client.open("ASSET_Simulation")

sheet_balance = spreadsheet.worksheet("잔고")
sheet_history = spreadsheet.worksheet("투자내역")
sheet_stocks = spreadsheet.worksheet("종목관리") # 티커(종목코드) 찾기용

balance_data = sheet_balance.get_all_records()
history_data = sheet_history.get_all_records()
stock_data = sheet_stocks.get_all_records()

current_cash = float(balance_data[0].get('현금잔액', 0)) if balance_data else 0
current_deposit = float(balance_data[0].get('예금잔액', 0)) if balance_data else 0
exchange_rate = get_exchange_rate()

# --- 📊 데이터 가공 ---
# 1. 티커(종목코드) 딕셔너리 만들기 (띄어쓰기 완벽 제거)
ticker_map = {}
for row in stock_data:
    name = str(row.get('종목명', '')).strip()
    ticker = str(row.get('티커', '')).strip()
    ticker_map[name] = ticker

# 2. 내 주식 수량 계산
def get_owned_stocks():
    owned = {}
    for row in history_data:
        name = str(row.get('종목명', '')).strip()
        kind = str(row.get('종류(매수/매도)', row.get('종류', ''))).strip()
        try: qty = float(row.get('수량', 0))
        except: qty = 0.0
        if kind == '매수': owned[name] = owned.get(name, 0) + qty
        elif kind == '매도': owned[name] = owned.get(name, 0) - qty
    return {k: round(v, 2) for k, v in owned.items() if round(v, 2) > 0}

owned_stocks = get_owned_stocks()

# 3. 주식 가치 계산
stock_portfolio = []
total_stock_value = 0.0
price_error_flag = False

for name, qty in owned_stocks.items():
    ticker = ticker_map.get(name, "")
    current_price = 0.0
    
    if ticker:
        raw_price = get_price(ticker)
        if raw_price == 0.0:
            price_error_flag = True
            
        is_korean = ticker.endswith('.KS') or ticker.endswith('.KQ')
        current_price = raw_price if is_korean else raw_price * exchange_rate
    else:
        price_error_flag = True # 티커를 못 찾았을 때
    
    stock_value = current_price * qty
    total_stock_value += stock_value
    
    stock_portfolio.append({
        '종목명': name,
        '보유 수량(주)': qty,
        '현재 1주 가격(원)': round(current_price),
        '현재 총 가치(원)': round(stock_value)
    })

total_asset_value = current_cash + current_deposit + total_stock_value

# ==========================================
# --- 🖥️ 앱 화면 구성 ---
# ==========================================

st.title("우리 딸의 첫 투자 시뮬레이션 🚀")

col_ref1, col_ref2 = st.columns(2)
with col_ref1: st.caption(f"💵 **참고 환율:** $1 = {exchange_rate:,.2f}원")
with col_ref2: st.caption("📈 **참고 예금금리:** 연 3.5%")

st.divider()

st.subheader("💎 우리집 현재 총 자산")
st.metric(label="(현금 + 예금 + 주식의 현재 가치)", value=f"{total_asset_value:,.0f} 원")

st.divider()

st.subheader("📋 자산 구성 요약")
col1, col2, col3 = st.columns(3)
with col1:
    with st.container(border=True):
        st.write("💰 **현금 잔액**")
        st.subheader(f"{current_cash:,.0f}원")
with col2:
    with st.container(border=True):
        st.write("🏦 **예금 잔액**")
        st.subheader(f"{current_deposit:,.0f}원")
with col3:
    with st.container(border=True):
        st.write("📈 **주식 총 가치**")
        st.subheader(f"{total_stock_value:,.0f}원")

st.write("")

st.write("📦 **상세 주식 보유 내역**")
if stock_portfolio:
    df_owned = pd.DataFrame(stock_portfolio)
    
    try:
        formatted_df = df_owned.style.format({
            '현재 1주 가격(원)': '{:,.0f}',
            '현재 총 가치(원)': '{:,.0f}'
        })
        st.dataframe(formatted_df, hide_index=True, use_container_width=True)
    except:
        st.dataframe(df_owned, hide_index=True, use_container_width=True)
        
    if price_error_flag:
        st.error("⚠️ 일부 주식의 가격을 못 불러와 0원으로 표시되었습니다. 구글 시트의 [종목관리]와 [투자내역]의 종목명 띄어쓰기가 완벽히 똑같은지 확인해 주시거나, 아래 새로고침 버튼을 눌러주세요!")
else:
    st.info("아직 보유한 주식이 없어요. 왼쪽 메뉴의 'Stock Market'에서 첫 투자를 시작해 보세요!")

st.divider()
if st.button("🔄 실시간 주식 가격 새로고침", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.success("원하는 메뉴를 위에서 선택해 주세요!")
