import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="자산관리 시뮬레이션", layout="centered")

if "price_backup" not in st.session_state:
    st.session_state.price_backup = {}

# --- 🚀 철통 방어 캐시 시스템 ---
@st.cache_data(ttl=600)
def get_exchange_rate():
    try: 
        rate = float(yf.Ticker("USDKRW=X").fast_info['last_price'])
        return 1350.0 if pd.isna(rate) or rate <= 0 else rate
    except: return 1350.0

@st.cache_data(ttl=300)
def get_price(ticker):
    if not ticker: return 0.0
    try: 
        t = yf.Ticker(ticker)
        # 1차 시도: 실시간 가격
        if 'last_price' in t.fast_info: 
            val = float(t.fast_info['last_price'])
            if not pd.isna(val) and val > 0: return val
            
        # 2차 시도: 야후 서버가 뻗었을 때 최근 5일치 종가 강제 추적
        hist = t.history(period="5d")
        if not hist.empty: 
            val = float(hist['Close'].iloc[-1])
            if not pd.isna(val) and val > 0: return val
        return 0.0
    except: return 0.0

@st.cache_resource(ttl=600)
def init_connection():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_sheet_data():
    try:
        client = init_connection()
        spreadsheet = client.open("ASSET_Simulation")
        return (
            spreadsheet.worksheet("잔고").get_all_records(),
            spreadsheet.worksheet("투자내역").get_all_records(),
            spreadsheet.worksheet("종목관리").get_all_records()
        )
    except:
        return None, None, None

balance_data, history_data, stock_data = load_sheet_data()

if balance_data is None:
    st.warning("🚦 구글 시트 접속자가 많아 서버가 일시적으로 지연되고 있습니다. 약 1분 뒤에 새로고침(F5)을 눌러주세요!")
    st.stop()

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
                    client = init_connection()
                    spreadsheet = client.open("ASSET_Simulation")
                    spreadsheet.worksheet("잔고").append_row([new_user_input, 1000000, 0, 1000000, "", ""])
                    st.cache_data.clear()
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
        
        if raw_price > 0:
            st.session_state.price_backup[ticker] = raw_price
        else:
            raw_price = st.session_state.price_backup.get(ticker, 0.0)
            if raw_price > 0:
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
    
    profit_amt = stock_value - total_buy_cost
    profit_rate = (profit_amt / total_buy_cost * 100) if total_buy_cost > 0 else 0
    
    stock_details.append({
        '종목명': name, 
        '보유 수량(주)': clean_qty, 
        '총 매수금액(원)': round(total_buy_cost),
        '현재 총 가치(원)': round(stock_value), 
        '수익률(%)': round(profit_rate, 2), 
        '수익금액(원)': round(profit_amt)
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

hot_news = []
for stock in stock_data:
    is_hot = str(stock.get('핫한뉴스선정', '')).strip().upper()
    news_text = str(stock.get('최근뉴스', '')).strip()
    news_eval = str(stock.get('뉴스평가', '')).strip()
    name = str(stock.get('종목명', '')).strip()
    if is_hot in ['O', '0', 'V', 'TRUE', 'Y'] and news_text:
        if news_eval == '호재': icon = "🔴"
        elif news_eval == '악재': icon = "🔵"
        elif news_eval == '중립': icon = "🟡"
        else: icon = "📰"
        hot_news.append((name, news_text, icon))

if hot_news:
    st.subheader("🔥 오늘의 주식 시장 핫이슈")
    for name, news, icon in hot_news[:5]:
        st.info(f"**[{name}]** {icon} {news}")
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
        def color_profit(val): 
            if pd.isna(val): return ""
            return f"color: {'#ff4b4b' if val > 0 else '#0083ff' if val < 0 else 'black'}"
            
        styled_df = df_owned.style.format({
            '총 매수금액(원)': '{:,.0f}', 
            '현재 총 가치(원)': '{:,.0f}', 
            '수익금액(원)': '{:,.0f}', 
            '수익률(%)': '{:,.2f}%'
        })
        
        if hasattr(styled_df, 'map'):
            styled_df = styled_df.map(color_profit, subset=['수익률(%)', '수익금액(원)'])
        else:
            styled_df = styled_df.applymap(color_profit, subset=['수익률(%)', '수익금액(원)'])
            
        st.dataframe(styled_df, hide_index=True, use_container_width=True)
    except:
        df_safe = df_owned.copy()
        df_safe['총 매수금액(원)'] = df_safe['총 매수금액(원)'].apply(lambda x: f"{x:,.0f}")
        df_safe['현재 총 가치(원)'] = df_safe['현재 총 가치(원)'].apply(lambda x: f"{x:,.0f}")
        df_safe['수익금액(원)'] = df_safe['수익금액(원)'].apply(lambda x: f"{x:,.0f}")
        df_safe['수익률(%)'] = df_safe['수익률(%)'].apply(lambda x: f"{x:,.2f}%")
        st.dataframe(df_safe, hide_index=True, use_container_width=True)
    
    if price_error_flag:
        st.info("💡 야후 파이낸스 해외 서버 지연으로 인해 일부 종목 주가를 과거 데이터에서 안전하게 불러왔습니다.")
else:
    st.info("아직 보유한 주식이 없어요. 왼쪽 메뉴에서 첫 투자를 시작해 보세요!")

st.divider()

# 💡 실종되었던 새로고침 버튼을 아주 확실하게 재배치!
if st.button("🔄 실시간 주식 가격 새로고침", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
