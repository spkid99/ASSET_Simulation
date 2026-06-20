import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Masters Investment 시상식 & 랭킹", layout="centered")

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

user_ranking_list = []
now = datetime.now()

for user_row in balance_data:
    user = str(user_row.get('사용자', '')).strip()
    if not user or user.lower() == 'nan': continue
    
    u_cash = float(user_row.get('현금잔액', 0))
    u_deposit = float(user_row.get('예금잔액', 0))
    u_initial = float(user_row.get('초기자본금', 1000000))
    
    portfolio = {}
    for h_row in history_data:
        if str(h_row.get('사용자', '')).strip() != user: continue
        name = str(h_row.get('종목명', '')).replace(" ", "")
        kind = str(h_row.get('종류', '매수')).strip()
        try: qty = float(h_row.get('수량', 0))
        except: qty = 0.0
        
        time_str = str(h_row.get('시간', ''))
        try: trade_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except: trade_time = now
        
        if name not in portfolio: portfolio[name] = {'qty': 0.0, 'first_buy': None}
        
        if kind == '매수':
            portfolio[name]['qty'] += qty
            if portfolio[name]['first_buy'] is None:
                portfolio[name]['first_buy'] = trade_time
        elif kind == '매도':
            portfolio[name]['qty'] -= qty
            if portfolio[name]['qty'] <= 0.0001: 
                portfolio[name]['qty'] = 0.0
                portfolio[name]['first_buy'] = None
                
    u_stock_value = 0.0
    longest_days = -1
    longest_stock = "보유 주식 없음"
    
    for name, data in portfolio.items():
        if data['qty'] > 0:
            ticker = ticker_map.get(name, "")
            raw_price = prices_cache.get(ticker, 0.0)
            is_korean = ticker.endswith('.KS') or ticker.endswith('.KQ')
            u_stock_value += (raw_price if is_korean else raw_price * exchange_rate) * data['qty']
            
            if data['first_buy']:
                days_held = (now - data['first_buy']).days
                if days_held > longest_days:
                    longest_days = days_held
                    longest_stock = name
                    
    if longest_days == -1: longest_days = 0
    
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
        '최장보유일': longest_days,
        '최장보유종목': longest_stock
    })

# --- 🖥️ 화면 UI 구성 ---
st.title("🏆 Masters Investment 시상식")
with st.container(border=True):
    st.write("🎉 **[시상식 안내] 매월 마지막 주 토요일은 시상식 날입니다!**")
    st.write("유저 중 가장 뛰어난 성과와 올바른 투자 습관을 보여준 사람에게 멋진 상과 상품이 수여됩니다. 매월 4가지 상표 중 하나의 부문만 돌아가며 시상하니, 목표를 세워 도전해 보세요!")

st.divider()

if not user_ranking_list:
    st.info("시상식에 참여할 유저 데이터가 존재하지 않습니다.")
    st.stop()

df_rank = pd.DataFrame(user_ranking_list)

rank_profit = df_rank.sort_values(by='수익률', ascending=False).to_dict('records')
rank_asset = df_rank.sort_values(by='총자산', ascending=False).to_dict('records')
rank_deposit = df_rank.sort_values(by='예금잔액', ascending=False).to_dict('records')
rank_longterm = df_rank.sort_values(by='최장보유일', ascending=False).to_dict('records')

tab1, tab2, tab3, tab4 = st.tabs([
    "📈 최고의 투자자 (1,5,9월)", 
    "👑 월스트리스 큰손 상 (2,6,10월)", 
    "🏛️ 티끌모아 태산 (3,7,11월)", 
    "💎 다이아몬드 핸즈 상 (4,8,12월)"
])

medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]

with tab1:
    st.subheader("📈 최고의 투자자 상")
    st.info("📅 **시상월:** 1월, 5월, 9월 | 🎁 **당첨 상품:** 💵 투자지원금 10,000원")
    st.caption("시장의 흐름을 읽는 안목으로 가장 높은 수익률(%)을 기록한 실력파 투자자에게 수여합니다.")
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
    st.subheader("👑 월스트리스 큰손 상")
    st.info("📅 **시상월:** 2월, 6월, 10월 | 🎁 **당첨 상품:** 💰 보너스 용돈 5,000원 (진짜 용돈!)")
    st.caption("현금, 예금, 주식 평가액을 모두 합쳐 현재 가족 중 가장 많은 자산을 축적한 부자에게 수여합니다.")
    for i, u in enumerate(rank_asset[:5]):
        medal = medals[i] if i < len(medals) else f"{i+1}위"
        with st.container(border=True):
            col_u, col_d = st.columns([1, 2])
            with col_u: st.markdown(f"### {medal} {u['사용자']}")
            with col_d:
                st.markdown(f"**보유 총 자산:** <span style='color:#11B67A; font-weight:bold;'>{u['총자산']:,.0f} 원</span>", unsafe_allow_html=True)
                st.caption(f"예금 잔액: {u['예금잔액']:,.0f} 원 | 주식 및 현금 포함")

with tab3:
    st.subheader("🏛️ 티끌모아 태산 상")
    st.info("📅 **시상월:** 3월, 7월, 11월 | 🎁 **당첨 상품:** 🏛️ 다음 달 특별 우대금리 (기본금리의 2배!)")
    st.caption("투자 유혹을 참고 은행에 자금을 묶어두어 단단한 안전자산을 구축한 인내의 저축왕에게 수여합니다.")
    for i, u in enumerate(rank_deposit[:5]):
        medal = medals[i] if i < len(medals) else f"{i+1}위"
        with st.container(border=True):
            col_u, col_d = st.columns([1, 2])
            with col_u: st.markdown(f"### {medal} {u['사용자']}")
            with col_d:
                st.markdown(f"**은행 예금 통장 잔액:** <span style='color:#0083ff; font-weight:bold;'>{u['예금잔액']:,.0f} 원</span>", unsafe_allow_html=True)
                st.caption(f"안전하게 지켜낸 나만의 든든한 금고!")

with tab4:
    st.subheader("💎 다이아몬드 핸즈 상")
    st.info("📅 **시상월:** 4월, 8월, 12월 | 🎁 **당첨 상품:** 🍕 저녁 메뉴 선택권")
    st.caption("주식의 흔들림에도 팔지 않고 진득하게 가장 오랫동안 주식을 보유한 멘탈 갑(甲) 장기투자자에게 수여합니다.")
    for i, u in enumerate(rank_longterm[:5]):
        medal = medals[i] if i < len(medals) else f"{i+1}위"
        with st.container(border=True):
            col_u, col_d = st.columns([1, 2])
            with col_u: st.markdown(f"### {medal} {u['사용자']}")
            with col_d:
                if u['최장보유일'] == 0 and u['최장보유종목'] == "보유 주식 없음":
                    st.markdown(f"**현재 보유 중인 주식이 없습니다.**")
                else:
                    st.markdown(f"**기다림의 시간:** <span style='color:#8b00ff; font-weight:bold;'>{u['최장보유일']} 일</span>", unsafe_allow_html=True)
                    st.caption(f"효자 종목: [{u['최장보유종목']}] (단 한 주도 다 팔지 않고 끝까지 버틴 기간입니다.)")
