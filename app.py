import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="자산관리 시뮬레이션", layout="centered")

# --- 🚀 속도 최적화 캐시 ---
@st.cache_data(ttl=600)
def get_exchange_rate():
    try: return float(yf.Ticker("USDKRW=X").fast_info['last_price'])
    except: return 1350.0

@st.cache_data(ttl=300)
def get_price(ticker):
    if not ticker: return 0.0
    try: 
        ticker_obj = yf.Ticker(ticker)
        hist = ticker_obj.history(period="7d")
        if not hist.empty: return float(hist['Close'].iloc[-1])
        if 'last_price' in ticker_obj.fast_info: return float(ticker_obj.fast_info['last_price'])
        return 0.0
    except: return 0.0

# --- 🔐 로그인 (사용자 설정) 시스템 ---
if "user_id" not in st.session_state:
    st.session_state.user_id = None

if not st.session_state.user_id:
    st.title("💼 자산관리 시뮬레이션에 오신 것을 환영합니다!")
    st.write("자신의 이름을 입력하고 나만의 금고를 열어보세요.")
    
    with st.form("login_form"):
        user_input = st.text_input("👤 이름 (예: 아빠, 엄마, 딸이름)")
        submitted = st.form_submit_button("내 금고 열기 🗝️")
        
        if submitted:
            if user_input.strip() == "":
                st.error("이름을 입력해 주세요!")
            else:
                st.session_state.user_id = user_input.strip()
                st.rerun()
    st.stop() # 로그인을 안 하면 아래 코드는 실행되지 않음

current_user = st.session_state.user_id

# --- 🔌 구글 시트 연결 ---
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
client = gspread.authorize(creds)
spreadsheet = client.open("ASSET_Simulation")

sheet_balance = spreadsheet.worksheet("잔고")
sheet_history = spreadsheet.worksheet("투자내역")
sheet_stocks = spreadsheet.worksheet("종목관리")

balance_data = sheet_balance.get_all_records()
history_data = sheet_history.get_all_records()
stock_data = sheet_stocks.get_all_records()
exchange_rate = get_exchange_rate()

# --- 👤 사용자 데이터 찾기 (없으면 자동 가입) ---
user_found = False
current_cash = 0.0
current_deposit = 0.0
initial_capital = 0.0

for row in balance_data:
    if str(row.get('사용자', '')) == current_user:
        current_cash = float(row.get('현금잔액', 0))
        current_deposit = float(row.get('예금잔액', 0))
        initial_capital = float(row.get('초기자본금', 1000000)) # 없으면 기본 100만 원
        user_found = True
        break

# 처음 온 사용자라면 100만 원을 주고 자동으로 시트에 등록합니다!
if not user_found:
    current_cash = 1000000.0
    current_deposit = 0.0
    initial_capital = 1000000.0
    sheet_balance.append_row([current_user, current_cash, current_deposit, initial_capital])

# --- 📊 데이터 가공 ---
ticker_map = {str(r.get('종목명', '')).replace(" ", ""): str(r.get('티커', '')).strip() for r in stock_data}

# 평단가(평균 매수 가격)와 수량 계산 로직
def get_user_portfolio():
    portfolio = {}
    for row in history_data:
        if str(row.get('사용자', '')) != current_user: continue # 내 투자 내역만 가져오기
        
        name = str(row.get('종목명', '')).replace(" ", "")
        kind = str(row.get('종류', row.get('종류(매수/매도)', ''))).strip()
        try: 
            qty = float(row.get('수량', 0))
            price = float(row.get('가격', 0))
        except: continue
        
        if name not in portfolio:
            portfolio[name] = {'qty': 0.0, 'total_buy_cost': 0.0}
            
        if kind == '매수':
            portfolio[name]['qty'] += qty
            portfolio[name]['total_buy_cost'] += qty * price
        elif kind == '매도':
            if portfolio[name]['qty'] > 0:
                avg_buy_price = portfolio[name]['total_buy_cost'] / portfolio[name]['qty']
                portfolio[name]['qty'] -= qty
                portfolio[name]['total_buy_cost'] -= avg_buy_price * qty
                
    return {k: v for k, v in portfolio.items() if round(v['qty'], 2) > 0}

user_portfolio = get_user_portfolio()

stock_details = []
total_stock_value = 0.0
price_error_flag = False

for name, data in user_portfolio.items():
    ticker = ticker_map.get(name, "")
    current_price = 0.0
    
    if ticker:
        raw_price = get_price(ticker)
        if raw_price == 0.0: price_error_flag = True
        is_korean = ticker.endswith('.KS') or ticker.endswith('.KQ')
        current_price = raw_price if is_korean else raw_price * exchange_rate
    else: price_error_flag = True
    
    qty = data['qty']
    total_buy_cost = data['total_buy_cost']
    stock_value = current_price * qty
    total_stock_value += stock_value
    
    profit_amt = stock_value - total_buy_cost
    profit_rate = (profit_amt / total_buy_cost * 100) if total_buy_cost > 0 else 0
    
    stock_details.append({
        '종목명': name,
        '보유 수량': qty,
        '총 매수금액': round(total_buy_cost),
        '현재 총 가치': round(stock_value),
        '수익률(%)': round(profit_rate, 2),
        '수익금액': round(profit_amt)
    })

total_asset_value = current_cash + current_deposit + total_stock_value
total_profit_amt = total_asset_value - initial_capital
total_profit_rate = (total_profit_amt / initial_capital * 100) if initial_capital > 0 else 0

today_str = datetime.now().strftime("%Y년 %m월 %d일 기준")

# ==========================================
# --- 🖥️ 앱 화면 구성 ---
# ==========================================

# 로그아웃 버튼 (상단 우측)
col_title, col_logout = st.columns([4, 1])
with col_title:
    st.title(f"🏢 {current_user}의 자산관리 시뮬레이션")
with col_logout:
    st.write("") # 줄맞춤용
    if st.button("로그아웃 🚪"):
        st.session_state.user_id = None
        st.rerun()

# 💡 초등학교 6학년 맞춤 경제 교육
with st.expander("💡 꼭 알아야 할 자산관리 기초 (클릭해서 읽어보세요!)"):
    st.write("""
    우리가 관리할 수 있는 자산(재산)은 크게 3가지로 나눌 수 있어요. 이 세 가지를 어떻게 나누어 담느냐가 투자의 핵심입니다!
    
    * 💵 **현금 (Cash):** 지금 내 지갑이나 자유로운 통장에 있는 돈이에요. 당장 아이스크림을 사 먹을 땐 편하지만, 가만히 두면 돈이 스스로 늘어나지는 않아요.
    * 🏛️ **예금 (Deposit):** 당장 쓰지 않을 돈을 은행에 안전하게 맡겨두는 거예요. 은행이 내 돈을 보관해 주는 대신 **'이자'**라는 보너스를 조금씩 줍니다. 원금이 줄어들 걱정이 없는 가장 안전한 방법이에요.
    * 📈 **주식 (Stock):** 멋진 회사의 주인이 되는 티켓을 사는 거예요. 회사가 돈을 아주 많이 벌면 내 티켓의 가치도 쑥쑥 올라 큰 수익을 얻을 수 있지만, 회사가 어려워지면 내 돈도 줄어들 수 있는 진짜 **'투자'**랍니다.
    """)

st.divider()

# 📌 1. 총 자산 가치 및 수익률
st.subheader("💎 나의 총 자산")
st.caption(f"🗓️ {today_str}")

# 수익률 표시에 색상을 넣기 위한 메트릭
st.metric(
    label=f"💰 시작 원금(초기 자본금): {initial_capital:,.0f} 원", 
    value=f"{total_asset_value:,.0f} 원",
    delta=f"총 {total_profit_amt:,.0f} 원 ({total_profit_rate:,.2f}%) 수익"
)

st.divider()

# 📌 2. 자산 구성 요약
st.subheader("📊 자산 구성 요약")
col1, col2, col3 = st.columns(3)
with col1:
    with st.container(border=True):
        st.write("💵 **현금 잔액**")
        st.subheader(f"{current_cash:,.0f}원")
with col2:
    with st.container(border=True):
        st.write("🏛️ **은행 예금**")
        st.subheader(f"{current_deposit:,.0f}원")
with col3:
    with st.container(border=True):
        st.write("📈 **주식 총 가치**")
        st.subheader(f"{total_stock_value:,.0f}원")

st.write("")

# 📌 3. 주식 포트폴리오 상세
st.write("💼 **상세 주식 보유 내역**")
if stock_details:
    df_owned = pd.DataFrame(stock_details)
    
    # 데이터프레임 시각화 개선
    try:
        def color_profit(val):
            color = 'red' if val > 0 else 'blue' if val < 0 else 'black'
            return f'color: {color}'

        formatted_df = df_owned.style.format({
            '총 매수금액': '{:,.0f}',
            '현재 총 가치': '{:,.0f}',
            '수익금액': '{:,.0f}',
            '수익률(%)': '{:,.2f}%'
        }).applymap(color_profit, subset=['수익률(%)', '수익금액'])
        
        st.dataframe(formatted_df, hide_index=True, use_container_width=True)
    except:
        st.dataframe(df_owned, hide_index=True, use_container_width=True)
        
    if price_error_flag:
        st.error("⚠️ 일부 주식의 가격을 못 불러왔습니다. [새로고침] 버튼을 눌러주세요!")
else:
    st.info("아직 보유한 주식이 없어요. 왼쪽 메뉴에서 첫 투자를 시작해 보세요!")

st.divider()
if st.button("🔄 실시간 주식 가격 새로고침", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.success("원하는 메뉴를 위에서 선택해 주세요!")
