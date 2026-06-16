import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="자산관리 시뮬레이션", layout="centered")

# ==========================================
# 🚀 1. 렉 원천 차단: 내부 메모리(RAM) 초기화
# ==========================================
if "db_loaded" not in st.session_state:
    st.session_state.db_loaded = False
    st.session_state.balance_data = []
    st.session_state.history_data = []
    st.session_state.stock_data = []
    st.session_state.prices = {}
    st.session_state.exchange_rate = 1350.0

@st.cache_resource(ttl=3600)
def init_connection():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

def load_all_data_to_ram():
    try:
        client = init_connection()
        spreadsheet = client.open("ASSET_Simulation")
        st.session_state.balance_data = spreadsheet.worksheet("잔고").get_all_records()
        st.session_state.history_data = spreadsheet.worksheet("투자내역").get_all_records()
        st.session_state.stock_data = spreadsheet.worksheet("종목관리").get_all_records()
        
        # 주가도 최초 1번만 일괄 조회 후 메모리에 박제
        for stock in st.session_state.stock_data:
            ticker = str(stock.get('티커', '')).strip()
            if ticker and ticker not in st.session_state.prices:
                try:
                    hist = yf.Ticker(ticker).history(period="5d")
                    val = float(hist['Close'].iloc[-1]) if not hist.empty else 0.0
                    if val <= 0 and 'last_price' in yf.Ticker(ticker).fast_info:
                        val = float(yf.Ticker(ticker).fast_info['last_price'])
                    st.session_state.prices[ticker] = val if val > 0 else 0.0
                except:
                    st.session_state.prices[ticker] = 0.0
                    
        try:
            rate = float(yf.Ticker("USDKRW=X").fast_info['last_price'])
            st.session_state.exchange_rate = rate if rate > 0 else 1350.0
        except:
            pass
            
        st.session_state.db_loaded = True
    except Exception as e:
        st.error("초기 데이터 로딩 실패. 잠시 후 다시 시도해주세요.")

# 앱 실행 시 메모리가 비어있거나 '새로고침' 버튼을 눌렀을 때만 통신 실행
if not st.session_state.db_loaded:
    with st.spinner("🚀 서버 통신 중... (최초 1회만 실행되며 이후 렉이 사라집니다)"):
        load_all_data_to_ram()

# ==========================================
# 📊 2. 모든 로직은 메모리(session_state) 데이터만 사용 (통신 0번)
# ==========================================
balance_data = st.session_state.balance_data
history_data = st.session_state.history_data
stock_data = st.session_state.stock_data
prices_cache = st.session_state.prices
exchange_rate = st.session_state.exchange_rate

existing_users = [str(row.get('사용자', '')).strip() for row in balance_data if row.get('사용자', '')]

# --- 🔐 로그인 시스템 ---
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
                if new_user_input in existing_users: st.error("❌ 이미 존재하는 이름입니다!")
                else:
                    client = init_connection()
                    spreadsheet = client.open("ASSET_Simulation")
                    spreadsheet.worksheet("잔고").append_row([new_user_input, 1000000, 0, 1000000, "", ""])
                    st.session_state.db_loaded = False # 새 데이터를 반영하기 위해 메모리 리셋
                    st.session_state.user_id = new_user_input
                    st.success(f"🎉 {new_user_input}님의 금고 개설 완료! 새로고침 해주세요.")
                    st.rerun()
    st.stop()

current_user = st.session_state.user_id

# --- 자산 가공 (메모리에서 초고속 처리) ---
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

for name, data in user_portfolio.items():
    ticker = ticker_map.get(name, "")
    is_korean = ticker.endswith('.KS') or ticker.endswith('.KQ')
    
    # 야후 접속 없이 메모리에서 주가 즉시 호출
    raw_price = prices_cache.get(ticker, 0.0)
    if raw_price == 0.0:
        raw_price = (data['total_buy_cost'] / data['qty']) if data['qty'] > 0 else 0.0
        
    current_price = raw_price if is_korean else raw_price * exchange_rate
    qty = data['qty']
    total_buy_cost = data['total_buy_cost']
    stock_value = current_price * qty
    total_stock_value += stock_value 
    
    profit_amt = stock_value - total_buy_cost
    profit_rate = (profit_amt / total_buy_cost * 100) if total_buy_cost > 0 else 0
    
    stock_details.append({
        '종목명': name, 
        '보유 수량(주)': round(qty, 4), 
        '총 매수금액(원)': round(total_buy_cost),
        '현재 총 가치(원)': round(stock_value), 
        '수익률(%)': round(profit_rate, 2), 
        '수익금액(원)': round(profit_amt)
    })

total_asset_value = current_cash + current_deposit + total_stock_value
total_profit_amt = total_asset_value - initial_capital
total_profit_rate = (total_profit_amt / initial_capital * 100) if initial_capital > 0 else 0
today_str = datetime.now().strftime("%Y년 %m월 %d일 기준")

# --- UI 그리기 ---
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
    if is_hot in ['O', '0', 'V', 'TRUE', 'Y']:
        news_eval = str(stock.get('뉴스평가', '')).strip()
        icon = "🔴" if news_eval == '호재' else "🔵" if news_eval == '악재' else "🟡" if news_eval == '중립' else "📰"
        hot_news.append((str(stock.get('종목명', '')).strip(), str(stock.get('최근뉴스', '')).strip(), icon))

if hot_news:
    st.subheader("🔥 오늘의 핫이슈")
    for name, news, icon in hot_news[:5]: st.info(f"**[{name}]** {icon} {news}")
    st.divider()

st.metric(label=f"💰 시작 원금: {initial_capital:,.0f} 원", value=f"{total_asset_value:,.0f} 원", delta=f"총 {total_profit_amt:,.0f} 원 ({total_profit_rate:,.2f}%) 수익")
st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    with st.container(border=True): st.write("💵 **현금**"); st.subheader(f"{current_cash:,.0f}원")
with col2:
    with st.container(border=True): st.write("🏛️ **예금**"); st.subheader(f"{current_deposit:,.0f}원")
with col3:
    with st.container(border=True): st.write("📈 **주식가치**"); st.subheader(f"{total_stock_value:,.0f}원")

st.write("")
st.write("💼 **상세 주식 보유 내역**")
if stock_details:
    df_owned = pd.DataFrame(stock_details)
    try:
        def color_profit(val): return f"color: {'#ff4b4b' if val > 0 else '#0083ff' if val < 0 else 'black'}"
        styled_df = df_owned.style.format({'총 매수금액(원)': '{:,.0f}', '현재 총 가치(원)': '{:,.0f}', '수익금액(원)': '{:,.0f}', '수익률(%)': '{:,.2f}%'})
        styled_df = styled_df.map(color_profit, subset=['수익률(%)', '수익금액(원)']) if hasattr(styled_df, 'map') else styled_df.applymap(color_profit, subset=['수익률(%)', '수익금액(원)'])
        st.dataframe(styled_df, hide_index=True, use_container_width=True)
    except:
        st.dataframe(df_owned, hide_index=True, use_container_width=True)
else:
    st.info("아직 보유한 주식이 없어요. 투자를 시작해 보세요!")

st.divider()

# 버튼을 누르면 메모리를 강제로 지워서, 다음 화면에서 통신이 일어나도록 만듦
if st.button("🔄 실시간 주가 새로고침 (서버 동기화)", use_container_width=True):
    st.session_state.db_loaded = False
    st.rerun()
