import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="명예의 전당", layout="wide") # 화면을 넓게 쓰도록 변경

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
@st.cache_resource(ttl=600)
def init_connection():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    return client.open("ASSET_Simulation")

spreadsheet = init_connection()

sheet_balance = spreadsheet.worksheet("잔고")
balance_data = sheet_balance.get_all_records()
history_data = spreadsheet.worksheet("투자내역").get_all_records()
stock_data = spreadsheet.worksheet("종목관리").get_all_records()
exchange_rate = get_exchange_rate()

ticker_map = {str(r.get('종목명', '')).replace(" ", ""): str(r.get('티커', '')).strip() for r in stock_data}

# --- 📊 모든 사용자 자산 계산 ---
users_stats = {}

for idx, row in enumerate(balance_data):
    user = str(row.get('사용자', '')).strip()
    if not user: continue
    users_stats[user] = {
        'row_idx': idx + 2, # 시트 업데이트용 위치
        '현금': float(row.get('현금잔액', 0)),
        '예금': float(row.get('예금잔액', 0)),
        '초기자본': float(row.get('초기자본금', 1000000)),
        '최근초기화일': str(row.get('최근초기화일', '')),
        '주식가치': 0.0, '총자산': 0.0, '수익률': 0.0,
        '매도횟수': 0, '보유종목수': 0, '포트폴리오': {}
    }

for row in history_data:
    user = str(row.get('사용자', '')).strip()
    if user not in users_stats: continue
    
    name = str(row.get('종목명', '')).replace(" ", "")
    kind = str(row.get('종류', row.get('종류(매수/매도)', ''))).strip()
    try: qty = float(row.get('수량', 0))
    except: qty = 0.0
    
    # 시간 파싱 (이번 달 매도 횟수만 계산하기 위함)
    time_str = str(row.get('시간', ''))
    try: trade_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except: trade_time = datetime.min
    
    reset_str = users_stats[user]['최근초기화일']
    try: reset_time = datetime.strptime(reset_str, "%Y-%m-%d %H:%M:%S")
    except: reset_time = datetime.min
    
    if name not in users_stats[user]['포트폴리오']:
        users_stats[user]['포트폴리오'][name] = 0.0
        
    if kind == '매수': 
        users_stats[user]['포트폴리오'][name] += qty
    elif kind == '매도': 
        users_stats[user]['포트폴리오'][name] -= qty
        # 💡 초기화 이후에 발생한 매도만 카운트!
        if trade_time > reset_time:
            users_stats[user]['매도횟수'] += 1

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
ranking_hold = sorted(users_stats.items(), key=lambda x: x[1]['매도횟수']) 
ranking_diverse = sorted(users_stats.items(), key=lambda x: x[1]['보유종목수'], reverse=True)


# ==========================================
# --- 🖥️ 화면 구성 ---
# ==========================================
st.title("🏆 실시간 랭킹 및 명예의 전당")
st.write("우리 가족 중 이번 달 최고의 자산가는 누구일까요?")

# --- ⚙️ 부모님 전용 관리자 모드 (사이드바) ---
with st.sidebar.expander("⚙️ 부모님 전용 관리자 모드"):
    admin_pwd = st.text_input("비밀번호를 입력하세요", type="password")
    if admin_pwd == "0000":
        st.success("✅ 관리자 권한 확인됨")
        
        # 기능 1: 보너스 지급
        st.write("🎁 **투자 지원금 쏘기**")
        target_user = st.selectbox("누구에게 줄까요?", list(users_stats.keys()))
        if st.button(f"{target_user}에게 10,000원 쏘기"):
            target_idx = users_stats[target_user]['row_idx']
            target_cash = users_stats[target_user]['현금']
            sheet_balance.update_cell(target_idx, 2, target_cash + 10000)
            st.success("지급 완료! (새로고침을 눌러주세요)")
            
        st.divider()
        
        # 기능 2: 월간 초기화
        st.write("🔄 **새로운 달 시작 (초기화)**")
        st.caption("모든 사용자의 '초기자본'을 현재 총자산으로 맞추어 수익률을 0%로 리셋하고, 매도 횟수도 새로 카운트합니다.")
        if st.button("🚨 이번 달 시상식 끝! 다음 달 리셋하기"):
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for user, stats in users_stats.items():
                r_idx = stats['row_idx']
                # 초기자본금(D열, 4번째 칸)을 현재 총자산으로 업데이트
                sheet_balance.update_cell(r_idx, 4, stats['총자산'])
                # 최근초기화일(F열, 6번째 칸)을 지금 시간으로 업데이트
                sheet_balance.update_cell(r_idx, 6, now_str)
            st.success("모든 데이터가 새로운 달에 맞게 초기화되었습니다! (새로고침 해주세요)")

st.divider()

# --- 🥇 시상식 안내 보드 ---
col1, col2 = st.columns(2)

with col1:
    with st.container(border=True):
        st.subheader("👑 최고의 투자가 상")
        st.write("**의미:** 시장의 흐름을 잘 읽고 자산을 훌륭하게 불린 투자 실력자입니다.")
        st.caption("📌 **선정 기준:** 이번 달 시작 대비 '수익률' 1위")
        st.success("🎁 **보상:** 투자 지원금 10,000원 앱 내 즉시 지급!")
        if ranking_yield:
            st.info(f"🏆 현재 1위: **{ranking_yield[0][0]}** ({ranking_yield[0][1]['수익률']:.2f}%)")
        
    with st.container(border=True):
        st.subheader("🐜 성실한 개미 상")
        st.write("**의미:** 꾹 참고 은행에 돈을 가장 많이 저축한 인내의 아이콘입니다.")
        st.caption("📌 **선정 기준:** '은행 예금 통장 잔액' 1위")
        st.success("🎁 **보상:** 부모님이 좋아하는 간식(탕후루/버블티 등) 사주기!")
        if ranking_deposit:
            st.info(f"🏆 현재 1위: **{ranking_deposit[0][0]}** (예금 {ranking_deposit[0][1]['예금']:,.0f}원)")

with col2:
    with st.container(border=True):
        st.subheader("🧘 버핏의 인내심 상")
        st.write("**의미:** 흔들리는 주가에도 당황하지 않고 엉덩이 무겁게 버틴 진정한 투자가입니다.")
        st.caption("📌 **선정 기준:** 이번 달 주식 '매도 횟수'가 가장 적은 사람")
        st.success("🎁 **보상:** 오늘 하루 집안일 완전 면제권!")
        if ranking_hold:
            st.info(f"🏆 현재 1위: **{ranking_hold[0][0]}** (매도 단 {ranking_hold[0][1]['매도횟수']}회)")
            
    with st.container(border=True):
        st.subheader("🥚 바구니 마스터 상")
        st.write("**의미:** 한 곳에 몰빵하지 않고 여러 회사에 골고루 투자한 똑똑한 전략가입니다.")
        st.caption("📌 **선정 기준:** 보유하고 있는 '주식 종목 수' 1위")
        st.success("🎁 **보상:** 이번 주말 배달/외식 메뉴 결정권!")
        if ranking_diverse:
            st.info(f"🏆 현재 1위: **{ranking_diverse[0][0]}** (총 {ranking_diverse[0][1]['보유종목수']}개 기업 분산)")

st.divider()

st.subheader("📊 가족 전체 수익률 랭킹 보드")
df_board = []
for idx, (user, stats) in enumerate(ranking_yield):
    df_board.append({
        "순위": f"{idx+1}위",
        "이름": user,
        "현재 총 자산": f"{stats['총자산']:,.0f}원",
        "이번 달 수익률": f"{stats['수익률']:.2f}%"
    })
st.dataframe(pd.DataFrame(df_board), hide_index=True, use_container_width=True)
