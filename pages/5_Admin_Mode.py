import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="부모님 전용 관리자 모드", layout="wide")

st.title("⚙️ 부모님 전용 관리자 모드")
pwd = st.text_input("관리자 비밀번호를 입력하세요", type="password")
if pwd != "0000":
    st.warning("🔒 올바른 관리자 비밀번호를 입력해야 제어 장치가 활성화됩니다.")
    st.stop()

st.success("🔓 마스터 계정 로그인 성공! 모든 통제 권한이 활성화되었습니다.")

# --- 🚀 속도 최적화 캐시 (총자산 계산용) ---
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

# --- 🔌 구글 시트 연결 (과부하 철통 방어!) ---
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

try:
    sheet_purchases = spreadsheet.worksheet("구매내역")
    purchase_values = sheet_purchases.get_all_values()
except:
    st.error("[구매내역] 탭을 찾을 수 없습니다.")
    st.stop()

balance_data = sheet_balance.get_all_records()
history_data = sheet_history.get_all_records()
history_values = sheet_history.get_all_values()
stock_data = sheet_stocks.get_all_records()

# --- 데이터 가공 ---
users_list = [str(r.get('사용자', '')).strip() for r in balance_data if r.get('사용자', '')]
exchange_rate = get_exchange_rate()
ticker_map = {str(r.get('종목명', '')).replace(" ", ""): str(r.get('티커', '')).strip() for r in stock_data}

# 유저별 총 자산 미리 계산 (월간 초기화를 위함)
users_stats = {}
for idx, row in enumerate(balance_data):
    user = str(row.get('사용자', '')).strip()
    if not user: continue
    users_stats[user] = {
        'row_idx': idx + 2,
        '현금': float(row.get('현금잔액', 0)),
        '예금': float(row.get('예금잔액', 0)),
        '주식가치': 0.0,
        '포트폴리오': {}
    }

for row in history_data:
    user = str(row.get('사용자', '')).strip()
    if user not in users_stats: continue
    name = str(row.get('종목명', '')).replace(" ", "")
    kind = str(row.get('종류', row.get('종류(매수/매도)', ''))).strip()
    try: qty = float(row.get('수량', 0))
    except: qty = 0.0
    
    if name not in users_stats[user]['포트폴리오']:
        users_stats[user]['포트폴리오'][name] = 0.0
    if kind == '매수': users_stats[user]['포트폴리오'][name] += qty
    elif kind == '매도': users_stats[user]['포트폴리오'][name] -= qty

for user, stats in users_stats.items():
    for name, qty in stats['포트폴리오'].items():
        if qty > 0:
            ticker = ticker_map.get(name, "")
            if ticker:
                raw_price = get_price(ticker)
                is_korean = ticker.endswith('.KS') or ticker.endswith('.KQ')
                current_price = raw_price if is_korean else raw_price * exchange_rate
                stats['주식가치'] += current_price * qty
    stats['총자산'] = stats['현금'] + stats['예금'] + stats['주식가치']


# ==========================================
# 🖥️ 관리자 모드 탭 구성
# ==========================================
tab_money, tab_user, tab_shop = st.tabs(["💰 용돈/시상식 관리", "👤 유저 계정 관리", "📦 상점 물류 관리"])

# ------------------------------------------
# 탭 1: 용돈/시상식 관리 (사이드바에서 구출해 온 기능!)
# ------------------------------------------
with tab_money:
    st.subheader("🎁 자산 강제 주입 및 시상식 제어")
    
    if not users_list:
        st.info("등록된 유저가 없습니다.")
    else:
        col1, col2 = st.columns(2)
        
        with col1:
            with st.container(border=True):
                st.write("💸 **투자 지원금 (보너스) 쏴주기**")
                st.caption("랭킹 1위나 미션 달성 시 아이의 지갑에 현금을 꽂아줍니다.")
                
                target_user = st.selectbox("누구에게 줄까요?", users_list, key="bonus_user")
                bonus_amt = st.number_input("지급할 금액", min_value=0, step=1000, value=10000)
                
                if st.button(f"🚀 {target_user}에게 {bonus_amt:,}원 쏘기", use_container_width=True):
                    target_idx = users_stats[target_user]['row_idx']
                    target_cash = users_stats[target_user]['현금']
                    sheet_balance.update_cell(target_idx, 2, target_cash + bonus_amt)
                    st.success(f"{target_user}의 지갑에 {bonus_amt:,}원 입금 완료!")
                    st.rerun()
                    
        with col2:
            with st.container(border=True):
                st.write("🔄 **새로운 달 시작 (수익률 0%로 초기화)**")
                st.caption("시상식이 끝나고 다음 달 레이스를 시작할 때 누릅니다. (자산은 그대로 유지되며 '기준점'만 현재로 바뀝니다.)")
                
                if st.button("🚨 이번 달 결산 끝! 모두 초기화하기", use_container_width=True):
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    for user, stats in users_stats.items():
                        r_idx = stats['row_idx']
                        sheet_balance.update_cell(r_idx, 4, stats['총자산']) # 초기자본금을 현재 자산으로 덮어쓰기
                        sheet_balance.update_cell(r_idx, 6, now_str) # 최근초기화일 업데이트
                    st.success("🎉 모든 유저의 수익률과 매도 횟수가 초기화되었습니다!")
                    st.rerun()

# ------------------------------------------
# 탭 2: 유저 계정 관리
# ------------------------------------------
with tab_user:
    st.subheader("👤 시뮬레이션 참가자 제어")
    
    if not users_list:
        st.info("등록된 유저가 없습니다.")
    else:
        with st.form("rename_form"):
            st.write("✏️ **유저 이름 변경하기**")
            old_name = st.selectbox("변경할 대상 선택", users_list)
            new_name = st.text_input("새로운 이름 입력").strip()
            rename_submitted = st.form_submit_button("이름 일괄 변경 실행")
            
            if rename_submitted:
                if not new_name: st.error("새 이름을 입력하세요!")
                elif new_name in users_list: st.error("이미 존재하는 이름입니다!")
                else:
                    for idx, row in enumerate(balance_data):
                        if str(row.get('사용자', '')).strip() == old_name:
                            sheet_balance.update_cell(idx + 2, 1, new_name)
                            break
                    for idx, row in enumerate(history_values[1:], start=2):
                        if len(row) > 1 and row[1] == old_name:
                            sheet_history.update_cell(idx, 2, new_name)
                    for idx, row in enumerate(purchase_values[1:], start=2):
                        if len(row) > 1 and row[1] == old_name:
                            sheet_purchases.update_cell(idx, 2, new_name)
                    st.success(f"⚖️ {old_name} ➡️ {new_name} 변경 완료!")
                    st.rerun()

        st.write("---")
        with st.form("delete_form"):
            st.write("🚨 **유저 영구 삭제 (오타 대처용)**")
            del_name = st.selectbox("삭제할 유저 선택", users_list, key="del_box")
            st.warning("⚠️ 유저를 삭제하면 해당 금고(잔고 데이터)가 즉시 파괴되며 복구할 수 없습니다.")
            del_submitted = st.form_submit_button("❌ 유저 데이터 영구 삭제")
            
            if del_submitted:
                for idx, row in enumerate(balance_data):
                    if str(row.get('사용자', '')).strip() == del_name:
                        sheet_balance.delete_rows(idx + 2)
                        break
                st.success(f"🔥 {del_name} 계정 삭제 완료.")
                st.rerun()

# ------------------------------------------
# 탭 3: 상점 물류 관리
# ------------------------------------------
with tab_shop:
    st.subheader("🛒 실물 보상 상품 및 정산 관리")
    
    undelivered_items = []
    all_purchases = []
    for idx, row in enumerate(purchase_values[1:], start=2):
        while len(row) < 5: row.append("사용전")
        status = row[4] if row[4] else "사용전"
        p_info = {'row_idx': idx, '시간': row[0], '사용자': row[1], '상품명': row[2], '결제금액': row[3], '상태': status}
        all_purchases.append(p_info)
        if status != "전달완료":
            undelivered_items.append(p_info)
            
    st.metric(label="📦 현실에서 아직 아이에게 전달 안 된 상품 총 개수", value=f"{len(undelivered_items)} 개")
    filter_opt = st.radio("장부 필터 설정", ["전달 대기중인 내역만 보기", "전체 구매 이력 보기"], horizontal=True)
    st.write("")
    
    target_list = undelivered_items if filter_opt == "전달 대기중인 내역만 보기" else all_purchases
    
    if not target_list:
        st.info("조건에 부합하는 정산 장부 내역이 없습니다.")
    else:
        for idx, p in enumerate(target_list):
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"### 👤 {p['사용자']} ➡️ {p['상품명']}")
                    st.caption(f"구매 시각: {p['시간']} | 결제액: {int(float(p['결제금액'])):,}원 | 상태: **{p['상태']}**")
                with c2:
                    st.write("")
                    if p['상태'] != "전달완료":
                        if st.button("🚚 실물 전달 완료", key=f"del_admin_{idx}", use_container_width=True):
                            sheet_purchases.update_cell(p['row_idx'], 5, "전달완료")
                            st.success("배송 및 지급 상태를 완료 처리했습니다.")
                            st.rerun()
                    else:
                        st.button("✅ 지급 완료됨", disabled=True, key=f"done_admin_{idx}", use_container_width=True)
