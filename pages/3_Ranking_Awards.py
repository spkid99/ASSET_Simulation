import streamlit as st
from supabase import create_client, Client
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="랭킹 보드", layout="centered")

if "db_loaded" not in st.session_state or not st.session_state.db_loaded:
    st.warning("💡 최신 랭킹을 보려면 먼저 메인 홈 화면(app.py)을 한 번 열어주세요!")
    st.stop()

@st.cache_resource(ttl=3600)
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

try:
    balance_data = supabase.table("balance").select("*").execute().data
    history_data = supabase.table("history").select("*").execute().data
    stock_data = supabase.table("stocks").select("*").execute().data
except:
    st.error("데이터를 불러오는 중 오류가 발생했습니다.")
    st.stop()

prices_cache = st.session_state.prices
exchange_rate = st.session_state.exchange_rate
ticker_map = {str(r.get('종목명', '')).replace(" ", ""): str(r.get('티커', '')).strip() for r in stock_data}

user_assets = []

for user_row in balance_data:
    user = str(user_row.get('사용자', '')).strip()
    if not user: continue
    
    u_cash = float(user_row.get('현금잔액', 0))
    u_deposit = float(user_row.get('예금잔액', 0))
    u_initial = float(user_row.get('초기자본금', 1000000))
    
    # 해당 유저의 포트폴리오 계산
    portfolio = {}
    for h_row in history_data:
        if str(h_row.get('사용자', '')).strip() != user: continue
        name = str(h_row.get('종목명', '')).replace(" ", "")
        kind = str(h_row.get('종류', '매수')).strip()
        try: qty = float(h_row.get('수량', 0))
        except: qty = 0.0
        
        if kind == '매수': portfolio[name] = portfolio.get(name, 0) + qty
        elif kind == '매도': portfolio[name] = portfolio.get(name, 0) - qty
        
    u_stock_value = 0.0
    for name, qty in portfolio.items():
        if qty <= 0: continue
        ticker = ticker_map.get(name, "")
        raw_price = prices_cache.get(ticker, 0.0)
        is_korean = ticker.endswith('.KS') or ticker.endswith('.KQ')
        u_stock_value += (raw_price if is_korean else raw_price * exchange_rate) * qty
        
    u_total = u_cash + u_deposit + u_stock_value
    profit_amt = u_total - u_initial
    profit_rate = (profit_amt / u_initial * 100) if u_initial > 0 else 0
    
    user_assets.append({
        '사용자': user,
        '총 자산': u_total,
        '수익금': profit_amt,
        '수익률(%)': profit_rate
    })

st.title("🏆 가족 투자 랭킹 보드")
st.write("누가 가장 현명하게 자산을 불리고 있을까요?")
st.divider()

if not user_assets:
    st.info("아직 참가자가 없습니다.")
else:
    # 수익률 기준으로 내림차순 정렬
    user_assets.sort(key=lambda x: x['수익률(%)'], reverse=True)
    
    medals = ["🥇", "🥈", "🥉"]
    
    for i, u in enumerate(user_assets):
        medal = medals[i] if i < 3 else f"{i+1}위"
        
        with st.container(border=True):
            c1, c2 = st.columns([1, 2])
            with c1:
                st.subheader(f"{medal} {u['사용자']}")
            with c2:
                profit_color = "red" if u['수익률(%)'] > 0 else "blue" if u['수익률(%)'] < 0 else "black"
                st.markdown(f"**총 자산:** {u['총 자산']:,.0f} 원")
                st.markdown(f"**수익률:** <span style='color:{profit_color}; font-weight:bold;'>{u['수익률(%)']:.2f}%</span> ({u['수익금']:,.0f}원)", unsafe_allow_html=True)
                
    st.divider()
    st.caption("💡 랭킹은 1시간 단위로 변동될 수 있습니다. 홈 화면을 새로고침하면 최신 데이터가 반영됩니다.")
