import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="명예의 전당", layout="centered")

if "user_id" not in st.session_state or not st.session_state.user_id:
    st.warning("👤 먼저 메인 홈 화면(app.py)에서 이름을 입력하고 로그인해 주세요!")
    st.stop()

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

# --- 🔌 구글 시트 연결 ---
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
client = gspread.authorize(creds)
spreadsheet = client.open("ASSET_Simulation")

balance_data = spreadsheet.worksheet("잔고").get_all_records()
history_data = spreadsheet.worksheet("투자내역").get_all_records()
stock_data = spreadsheet.worksheet("종목관리").get_all_records()
exchange_rate = get_exchange_rate()

ticker_map = {str(r.get('종목명', '')).replace(" ", ""): str(r.get('티커', '')).strip() for r in stock_data}

# --- 📊 모든 사용자 자산 계산 ---
users_stats = {}

for row in balance_data:
    user = str(row.get('사용자', '')).strip()
    if not user: continue
    users_stats[user] = {
        '현금': float(row.get('현금잔액', 0)),
        '예금': float(row.get('예금잔액', 0)),
        '초기자본': float(row.get('초기자본금', 1000000)),
        '주식가치': 0.0,
        '총자산': 0.0,
        '수익률': 0.0,
        '매도횟수': 0,
        '보유종목수': 0,
        '포트폴리오': {}
    }

for row in history_data:
    user = str(row.get('사용자', '')).strip()
    if user not in users_stats: continue
    
    name = str(row.get('종목명', '')).replace(" ", "")
    kind = str(row.get('종류', row.get('종류(매수/매도)', ''))).strip()
    try: qty = float(row.get('수량', 0))
    except: qty = 0.0
    
    if kind == '매도': users_stats[user]['매도횟수'] += 1
    
    if name not in users_stats[user]['포트폴리오']:
        users_stats[user]['포트폴리오'][name] = 0.0
        
    if kind == '매수': users_stats[user]['포트폴리오'][name] += qty
    elif kind == '매도': users_stats[user]['포트폴리오'][name] -= qty

for user, stats in users_stats.items():
    owned_stocks = {k: v for k, v in stats['포트폴리오'].items() if round(v, 2) > 0}
    stats['보유종목수'] = len(owned_stocks)
    
    for name, qty in owned_stocks.items():
        ticker = ticker_map.get(name, "")
        if ticker:
            raw_price = get_price(ticker)
            is_korean = ticker.endswith('.KS') or ticker.endswith('.KQ')
            current_price = raw_price if is_korean else raw_price * exchange_rate
            stats['주식가치'] += current_price * qty
            
    stats['총자산'] = stats['현금'] + stats['예금'] + stats['주식가치']
    stats['수익률'] = ((stats['총자산'] - stats['초기자본']) / stats['초기자본']) * 100 if stats['초기자본'] > 0 else 0

# --- 🏆 랭킹 계산 ---
ranking_yield = sorted(users_stats.items(), key=lambda x: x[1]['수익률'], reverse=True)
ranking_deposit = sorted(users_stats.items(), key=lambda x: x[1]['예금'], reverse=True)
ranking_hold = sorted(users_stats.items(), key=lambda x: x[1]['매도횟수']) # 매도 횟수가 적을수록 인내심 높음
ranking_diverse = sorted(users_stats.items(), key=lambda x: x[1]['보유종목수'], reverse=True)

# --- 🖥️ 화면 구성 ---
st.title("🏆 실시간 랭킹 및 명예의 전당")
st.write("우리 가족 중 현재 최고의 자산가는 누구일까요?")

st.divider()

st.subheader("🥇 현재 타이틀 홀더")

col1, col2 = st.columns(2)

with col1:
    with st.container(border=True):
        st.write("📈 **최고의 투자가 상 (수익률 1위)**")
        if ranking_yield:
            st.subheader(f"👑 {ranking_yield[0][0]}")
            st.caption(f"현재 수익률: {ranking_yield[0][1]['수익률']:.2f}% (총 자산 {ranking_yield[0][1]['총자산']:,.0f}원)")
        
    with st.container(border=True):
        st.write("🐜 **성실한 개미 상 (저축왕)**")
        if ranking_deposit:
            st.subheader(f"👑 {ranking_deposit[0][0]}")
            st.caption(f"현재 예금 잔액: {ranking_deposit[0][1]['예금']:,.0f}원")

with col2:
    with st.container(border=True):
        st.write("🧘 **버핏의 인내심 상 (최소 매도)**")
        if ranking_hold:
            st.subheader(f"👑 {ranking_hold[0][0]}")
            st.caption(f"주식을 팔지 않고 버틴 횟수 1위! (매도 단 {ranking_hold[0][1]['매도횟수']}회)")
            
    with st.container(border=True):
        st.write("🥚 **바구니 마스터 상 (분산투자)**")
        if ranking_diverse:
            st.subheader(f"👑 {ranking_diverse[0][0]}")
            st.caption(f"계란을 한 바구니에 담지 않았어요! (총 {ranking_diverse[0][1]['보유종목수']}개 기업 분산)")

st.divider()

st.subheader("📊 전체 가족 수익률 랭킹 보드")
df_board = []
for idx, (user, stats) in enumerate(ranking_yield):
    df_board.append({
        "순위": f"{idx+1}위",
        "이름": user,
        "총 자산": f"{stats['총자산']:,.0f}원",
        "수익률": f"{stats['수익률']:.2f}%"
    })
st.dataframe(pd.DataFrame(df_board), hide_index=True, use_container_width=True)

st.sidebar.success("원하는 메뉴를 위에서 선택해 주세요!")
