import streamlit as st
from supabase import create_client, Client
import pandas as pd

st.set_page_config(page_title="가족 투자 시상식 & 랭킹", layout="centered")

if "db_loaded" not in st.session_state or not st.session_state.db_loaded:
    st.warning("💡 최신 랭킹과 시상식을 보려면 먼저 메인 홈 화면(app.py)을 한 번 열어주세요!")
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
    st.error("데이터베이스에서 시상식 정보를 불러오는 중 오류가 발생했습니다.")
    st.stop()

prices_cache = st.session_state.prices
exchange_rate = st.session_state.exchange_rate
ticker_map = {str(r.get('종목명', '')).replace(" ", ""): str(r.get('티커', '')).strip() for r in stock_data}

# 📊 랭킹 분석 엔진 가동
user_ranking_list = []

for user_row in balance_data:
    user = str(user_row.get('사용자', '')).strip()
    if not user or user.lower() == 'nan': continue
    
    u_cash = float(user_row.get('현금잔액', 0))
    u_deposit = float(user_row.get('예금잔액', 0))
    u_initial = float(user_row.get('초기자본금', 1000000))
    
    # 1. 해당 유저의 보유 주식 가치 계산
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
        
    # 2. 거래 횟수(투자 열정) 계산
    trade_count = sum(1 for h_row in history_data if str(h_row.get('사용자', '')).strip() == user)
    
    u_total = u_cash + u_deposit + u_stock_value
    profit_amt = u_total - u_initial
    profit_rate = (profit_amt / u_initial * 100) if u_initial > 0 else 0
    if pd.isna(profit_rate): profit_rate = 0.0
    
    user_ranking_list.append({
        '사용자': user,
        '총자산': u_total,
        '예금잔액': u_deposit,
        '수익금': profit_amt,
        '수익률': profit_rate,
        '거래횟수': trade_count
    })

# --- 🖥️ 화면 UI 구성 ---
st.title("🏆 가족 자산관리 시뮬레이션 시상식")
st.write("우리 가족 중 가장 뛰어난 성과와 좋은 습관을 보여준 사람은 누구일까요?")
st.divider()

if not user_ranking_list:
    st.info("시상식에 참여할 유저 데이터가 존재하지 않습니다.")
    st.stop()

# 👑 부문별 데이터 정렬 가공
df_rank = pd.DataFrame(user_ranking_list)

# 1. 수익률 부문 상 (최고의 투자자 상)
rank_profit = df_rank.sort_values(by='수익률', ascending=False).to_dict('records')

# 2. 총 자산 부문 상 (우리 집 자산가 상)
rank_asset = df_rank.sort_values(by='총자산', ascending=False).to_dict('records')

# 3. 은행 저축 부문 상 (티끌 모아 태산 저축왕 상)
rank_deposit = df_rank.sort_values(by='예금잔액', ascending=False).to_dict('records')

# 4. 투자 열정 부문 상 (에너자이저 투자 상)
rank_trade = df_rank.sort_values(by='거래횟수', ascending=False).to_dict('records')


# 🏅 부문별 탭 시상식 진행
tab1, tab2, tab3, tab4 = st.tabs([
    "📈 최고의 투자자 상 (수익률)", 
    "👑 우리집 자산가 상 (총자산)", 
    "🏛️ 티끌모아 태산 상 (저축왕)", 
    "🔥 에너자이저 투자 상 (매매열정)"
])

medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]

with tab1:
    st.subheader("📈 최고의 투자자 상 (수익률 부문)")
    st.caption("순수 투자 실력과 감각으로 가장 높은 수익률을 기록한 투자자에게 수여합니다.")
    for i, u in enumerate(rank_profit[:5]):
        medal = medals[i] if i < len(medals) else f"{i+1}위"
        with st.container(border=True):
            col_u, col_d = st.columns([1, 2])
            with col_u: st.markdown(f"### {medal} {u['사용자']}")
            with col_d:
                color = "red" if u['수익률'] > 0 else "blue" if u['수익률'] < 0 else "black"
                st.markdown(f"**현재 수익률:** <span style='color:{color}; font-weight:bold;'>{u['수익률']:.2f}%</span>", unsafe_allow_html=True)
                st.caption(f"총 자산 가치: {u['총자산']:,.0f} 원 (수익금: {u['수익금']:,.0f} 원)")

with tab2:
    st.subheader("👑 우리집 자산가 상 (총자산 부문)")
    st.caption("현금, 예금, 주식 평가액을 모두 합쳐 현재 가장 거대한 자산을 굴리는 자산가 상입니다.")
    for i, u in enumerate(rank_asset[:5]):
        medal = medals[i] if i < len(medals) else f"{i+1}위"
        with st.container(border=True):
            col_u, col_d = st.columns([1, 2])
            with col_u: st.markdown(f"### {medal} {u['사용자']}")
            with col_d:
                st.markdown(f"**보유 총 자산:** <span style='color:#11B67A; font-weight:bold;'>{u['총자산']:,.0f} 원</span>", unsafe_allow_html=True)
                st.caption(f"예금 잔액: {u['예금잔액']:,.0f} 원 | 주식 및 현금 포함")

with tab3:
    st.subheader("🏛️ 티끌 모아 태산 상 (은행 예금 부문)")
    st.caption("주식 시장의 흔들림에 흔들리지 않고, 예금을 통해 차곡차곡 안전자산을 확보한 저축왕입니다.")
    for i, u in enumerate(rank_deposit[:5]):
        medal = medals[i] if i < len(medals) else f"{i+1}위"
        with st.container(border=True):
            col_u, col_d = st.columns([1, 2])
            with col_u: st.markdown(f"### {medal} {u['사용자']}")
            with col_d:
                st.markdown(f"**은행 예금 통장 잔액:** <span style='color:#0083ff; font-weight:bold;'>{u['예금잔액']:,.0f} 원</span>", unsafe_allow_html=True)
                st.caption(f"전체 자산 중 안전 자산 비중이 든든한 저축형 인재입니다.")

with tab4:
    st.subheader("🔥 에너자이저 투자 상 (투자 열정 부문)")
    st.caption("매수와 매도를 통해 시장의 흐름에 가장 기민하게 반응하고 많은 연구를 거듭한 열정 투자자입니다.")
    for i, u in enumerate(rank_trade[:5]):
        medal = medals[i] if i < len(medals) else f"{i+1}位"
        with st.container(border=True):
            col_u, col_d = st.columns([1, 2])
            with col_u: st.markdown(f"### {medal} {u['사용자']}")
            with col_d:
                st.markdown(f"**기록된 총 투자 횟수:** <span style='color:#ff4b4b; font-weight:bold;'>{u['거래횟수']} 회</span>", unsafe_allow_html=True)
                st.caption(f"끊임없이 모니터링하며 자산을 순환시킨 진정한 트레이더 상입니다.")

st.divider()
st.caption("💡 시상식 데이터는 메인 홈 화면(app.py)이 새로고침될 때 함께 갱신되어 완벽하게 연동됩니다.")
