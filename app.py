import streamlit as st
from supabase import create_client, Client
import yfinance as yf
import pandas as pd
from datetime import datetime
import requests

st.set_page_config(page_title="자산관리 시뮬레이션", layout="centered")

if "db_loaded" not in st.session_state:
    st.session_state.db_loaded = False
    st.session_state.balance_data = []
    st.session_state.history_data = []
    st.session_state.stock_data = []
    st.session_state.prices = {}
    st.session_state.exchange_rate = 1385.0

@st.cache_resource(ttl=3600)
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def load_all_data_to_ram():
    try:
        supabase = init_connection()
        
        st.session_state.balance_data = supabase.table("balance").select("*").execute().data
        st.session_state.history_data = supabase.table("history").select("*").execute().data
        st.session_state.stock_data = supabase.table("stocks").select("*").execute().data
        
        # 📅 하루 1회 자동 주가 및 환율 갱신 스케줄러
        today_date = datetime.now().strftime("%Y-%m-%d")
        settings_res = supabase.table("system_settings").select("*").execute().data
        
        settings_dict = {r.get('key'): r.get('value') for r in settings_res}
        last_update = settings_dict.get('last_stock_update', '2000-01-01')
        
        # 오늘 첫 접속자라면 주가 및 환율 자동 동기화 가동
        if last_update != today_date:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            })
            
            for stock in st.session_state.stock_data:
                ticker = str(stock.get('티커', '')).strip()
                sid = stock.get('id')
                if ticker:
                    try:
                        t = yf.Ticker(ticker, session=session)
                        val = 0.0
                        try: val = float(t.fast_info['last_price'])
                        except:
                            hist = t.history(period="1d")
                            if not hist.empty: val = float(hist['Close'].iloc[-1])
                        
                        if val > 0:
                            supabase.table("stocks").update({"현재가": val}).eq("id", sid).execute()
                            stock['현재가'] = val
                    except:
                        pass
            
            # 💡 [핵심 교체] 야후 대신 차단 걱정 없는 공인 무료 환율 API로 환율 100% 자동 수집!
            try:
                response = requests.get("https://open.er-api.com/v6/latest/USD")
                if response.status_code == 200:
                    exchange_data = response.json()
                    rate = float(exchange_data["rates"]["KRW"])
                    if rate > 1000:
                        supabase.table("system_settings").update({"value": str(rate)}).eq("key", "exchange_rate").execute()
                        settings_dict['exchange_rate'] = str(rate)
            except:
                pass
                
            supabase.table("system_settings").update({"value": today_date}).eq("key", "last_stock_update").execute()
            st.session_state.stock_data = supabase.table("stocks").select("*").execute().data

        # 금고(DB)에 저장된 최신 자동 수집 환율을 시스템에 고정
        db_rate = settings_dict.get('exchange_rate', '1385.0')
        st.session_state.exchange_rate = float(db_rate)

        for stock in st.session_state.stock_data:
            ticker = str(stock.get('티커', '')).strip()
            st.session_state.prices[ticker] = float(stock.get('현재가', 0))
            
        st.session_state.db_loaded = True
    except Exception as e:
        st.error(f"데이터베이스 통신 실패: {e}")

if not st.session_state.db_loaded:
    with st.spinner("🚀 클라우드 안전 금고 연결 중..."):
        load_all_data_to_ram()

balance_data = st.session_state.balance_data
history_data = st.session_state.history_data
stock_data = st.session_state.stock_data
prices_cache = st.session_state.prices
exchange_rate = st.session_state.exchange_rate

existing_users = [str(row.get('사용자', '')).strip() for row in balance_data if row.get('사용자', '')]

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
                    supabase = init_connection()
                    supabase.table("balance").insert({"사용자": new_user_input, "현금잔액": 1000000, "예금잔액": 0, "초기자본금": 1000000}).execute()
                    st.session_state.db_loaded = False 
                    st.session_state.user_id = new_user_input
                    st.success(f"🎉 {new_user_input}님의 금고 개설 완료!")
                    st.rerun()
    st.stop()

current_user = st.session_state.user_id

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
    
    raw_price = prices_cache.get(ticker, 0.0)
    
    if raw_price > 0:
        current_price = raw_price if is_korean else raw_price * exchange_rate
    else:
        current_price = (data['total_buy_cost'] / data['qty']) if data['qty'] > 0 else 0.0
        
    qty = data['qty']
    total_buy_cost = data['total_buy_cost']
    stock_value = current_price * qty
    
    if pd.isna(stock_value): stock_value = 0.0
    if pd.isna(total_buy_cost): total_buy_cost = 0.0
    
    total_stock_value += stock_value 
    
    profit_amt = stock_value - total_buy_cost
    profit_rate = (profit_amt / total_buy_cost * 100) if total_buy_cost > 0 else 0
    if pd.isna(profit_rate): profit_rate = 0.0
    
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
if pd.isna(total_profit_rate): total_profit_rate = 0.0

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

st.metric(label=f"💰 시작 원금: {initial_capital:,.0f} 원 (오늘의 자동 고정 환율: {exchange_rate:,.1f}원 적용)", value=f"{total_asset_value:,.0f} 원", delta=f"총 {total_profit_amt:,.0f} 원 ({total_profit_rate:,.2f}%) 수익")
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
st.caption(f"💡 오늘 가장 먼저 접속한 가족에 의해 주가와 환율이 하루 1회 자동으로 안전하게 수집 및 고정 관리됩니다.")
