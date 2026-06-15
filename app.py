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
        if 'last_price' in ticker_obj.fast_info: return float(ticker_obj.fast_info['last_price'])
        hist = ticker_obj.history(period="7d")
        if not hist.empty: return float(hist['Close'].iloc[-1])
        return 0.0
    except: return 0.0

# --- 🔌 구글 시트 연결 ---
@st.cache_resource(ttl=600)
def init_connection():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    return client.open("ASSET_Simulation")

spreadsheet = init_connection()
sheet_balance = spreadsheet.worksheet("잔고")
sheet_history = spreadsheet.worksheet("투자내역")
sheet_stocks = spreadsheet.worksheet("종목관리")

balance_data = sheet_balance.get_all_records()
history_data = sheet_history.get_all_records()
stock_data = sheet_stocks.get_all_records()
exchange_rate = get_exchange_rate()

existing_users = [str(row.get('사용자', '')).strip() for row in balance_data if row.get('사용자', '')]

# --- 🔐 로그인 / 회원 등록 시스템 ---
if "user_id" not in st.session_state:
    st.session_state.user_id = None

if not st.session_state.user_id:
    st.title("💼 자산관리 시뮬레이션 시스템")
    st.write("나만의 자산관리 금고를 열거나 새 금고를 만들어보세요.")
    
    menu = st.radio("원하는 작업을 선택하세요", ["🔐 로그인", "📝 신규 유저 등록"], horizontal=True)
    
    if menu == "🔐 로그인":
        with st.form("login_form"):
            user_input = st.text_input("👤 본인의 이름 입력").strip()
            submitted = st.form_submit_button("금고 열기 🗝️")
            if submitted:
                if not user_input: st.error("이름을 입력해 주세요!")
                elif user_input in existing_users:
                    st.session_state.user_id = user_input
                    st.rerun()
                else: st.error("❌ 등록되지 않은 사용자입니다.")
                    
    elif menu == "📝 신규 유저 등록":
        with st.form("register_form"):
            new_user_input = st.text_input("👤 새 유저 이름 입력 (중복 불가)").strip()
            submitted = st.form_submit_button("새 금고 만들기 🔨")
            if submitted:
                if not new_user_input: st.error("등록할 이름을 입력해 주세요!")
                elif new_user_input in existing_users: st.error("❌ 이미 존재하는 이름입니다!")
                else:
                    sheet_balance.append_row([new_user_input, 1000000, 0, 1000000, "", ""])
                    st.session_state.user_id = new_user_input
                    st.success(f"🎉 {new_user_input}님의 첫 금고 개설 완료!")
                    st.rerun()
    st.stop()

current_user = st.session_state.user_id

# --- 📊 자산 데이터 가공 ---
current_cash, current_deposit, initial_capital = 0.0, 0.0, 1000000.0
for row in balance_data:
    if str(row.get('사용자', '')).strip() == current_user:
        current_cash = float(row.get('현금잔액', 0))
        current_deposit = float(row.get('예금잔액', 0))
        initial_capital = float(row.get('초기자본금', 1000000))
        break

ticker_map = {str(r.get('종목명', '')).replace(" ", ""): str(r.get('티커', '')).strip() for r in stock_data}

def get_user_portfolio():
    portfolio = {}
    for row in history_data:
        if str(row.get('사용자', '')).strip() != current_user: continue
        name = str(row.get('종목명', '')).replace(" ", "")
        kind = str(row.get('종류', row.get('종류(매수/매도)', ''))).strip()
        try: qty, price = float(row.get('수량', 0)), float(row.get('가격', 0))
        except: continue
        
        if name not in portfolio: portfolio[name] = {'qty': 0.0, 'total_buy_cost': 0.0}
        if kind == '매수':
            portfolio[name]['qty'] += qty
            portfolio[name]['total_buy_cost'] += qty * price
        elif kind == '매도' and portfolio[name]['qty'] > 0:
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
        '종목명': name, '보유 수량': qty, '총 매수금액': round(total_buy_cost),
        '현재 총 가치': round(stock_value), '수익률(%)': round(profit_rate, 2), '수익금액': round(profit_amt)
    })

total_asset_value = current_cash + current_deposit + total_stock_value
total_profit_amt = total_asset_value - initial_capital
total_profit_rate = (total_profit_amt / initial_capital * 100) if initial_capital > 0 else 0
today_str = datetime.now().strftime("%Y년 %m월 %d일 기준")

# --- 🖥️ 대시보드 UI ---
col_title, col_logout = st.columns([4, 1])
with col_title: st.title(f"🏢 {current_user}의 자산관리")
with col_logout:
    st.write("")
    if st.button("로그아웃 🚪", use_container_width=True):
        st.session_state.user_id = None
        st.rerun()

st.divider()

# 💡 핫한 뉴스 노출 영역 추가
hot_news = []
for stock in stock_data:
    is_hot = str(stock.get('핫한뉴스선정', '')).strip().upper()
    news_text = str(stock.get('최근뉴스', '')).strip()
    name = str(stock.get('종목명', '')).strip()
    if is_hot in ['O', '0', 'V', 'TRUE', 'Y'] and news_text:
        hot_news.append((name, news_text))

if hot_news:
    st.subheader("🔥 오늘의 주식 시장 핫이슈")
    for name, news in hot_news[:5]: # 최대 5개까지만 노출
        st.info(f"**[{name}]** {news}")
    st.divider()

st.subheader("💎 나의 총 자산")
st.caption(f"🗓️ {today_str}")
st.metric(
    label=f"💰 시작 원금: {initial_capital:,.0f} 원", 
    value=f"{total_asset_value:,.0f} 원",
    delta=f"총 {total_profit_amt:,.0f} 원 ({total_profit_rate:,.2f}%) 수익"
)

st.divider()
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
st.write("💼 **상세 주식 보유 내역**")
if stock_details:
    df_owned = pd.DataFrame(stock_details)
    try:
        def color_profit(val): return f"color: {'red' if val > 0 else 'blue' if val < 0 else 'black'}"
        formatted_df = df_owned.style.format({
            '총 매수금액': '{:,.0f}', '현재 총 가치': '{:,.0f}', '수익금액': '{:,.0f}', '수익률(%)': '{:,.2f}%'
        }).applymap(color_profit, subset=['수익률(%)', '수익금액'])
        st.dataframe(formatted_df, hide_index=True, use_container_width=True)
    except:
        st.dataframe(df_owned, hide_index=True, use_container_width=True)
    
    if price_error_flag:
        st.error("⚠️ 일부 주식 가격을 불러오지 못했습니다. 아래 새로고침 버튼을 눌러주세요!")
else:
    st.info("아직 보유한 주식이 없어요. 왼쪽 메뉴에서 첫 투자를 시작해 보세요!")

st.divider()
if st.button("🔄 실시간 주식 가격 새로고침", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
