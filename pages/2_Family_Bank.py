import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta # 💡 날짜 계산을 위한 도구 추가

st.set_page_config(page_title="우리집 은행", layout="centered")

# --- 👤 로그인 확인 시스템 ---
if "user_id" not in st.session_state or not st.session_state.user_id:
    st.warning("👤 먼저 메인 홈 화면(app.py)에서 이름을 입력하고 로그인해 주세요!")
    st.stop()

current_user = st.session_state.user_id

# --- 🔌 구글 시트 연결 ---
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
client = gspread.authorize(creds)
spreadsheet = client.open("ASSET_Simulation")

sheet_balance = spreadsheet.worksheet("잔고")
balance_data = sheet_balance.get_all_records()

# --- 🔍 현재 로그인한 사용자의 줄(Row) 위치와 자산, 만기일 찾기 ---
user_row_idx = None
current_cash = 0.0
current_deposit = 0.0
maturity_str = ""

for idx, row in enumerate(balance_data):
    if str(row.get('사용자', '')).strip() == current_user:
        user_row_idx = idx + 2
        current_cash = float(row.get('현금잔액', 0))
        current_deposit = float(row.get('예금잔액', 0))
        maturity_str = str(row.get('예금만기일', '')).strip()
        break

if user_row_idx is None:
    st.error("사용자 정보를 찾을 수 없습니다. 홈 화면에서 다시 로그인해 주세요.")
    st.stop()

# --- ⏳ 예금 만기일 계산 로직 ---
can_withdraw = True
days_left = 0

if current_deposit > 0 and maturity_str:
    try:
        maturity_date = datetime.strptime(maturity_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        if today < maturity_date:
            can_withdraw = False
            days_left = (maturity_date - today).days
    except:
        pass

# --- 🖥️ 화면 구성 ---
st.title("🏦 우리집 은행 (예금/출금)")

ANNUAL_INTEREST_RATE = 0.035
st.info(f"👤 **{current_user}**의 저축 통장 | 📈 **예금 금리: 연 {ANNUAL_INTEREST_RATE*100:.2f}%**")

# 💡 아이들의 눈높이에 맞춘 정기예금 설명
with st.expander("💡 꼭 읽어보세요: 은행과의 새끼손가락 약속! (정기예금이란?)", expanded=True):
    st.write("""
    **'정기예금'**은 은행에 한 달(30일) 동안 돈을 꾹 참고 맡겨두기로 굳게 약속하는 거예요. 
    은행은 이 돈을 안전하게 보관해 주는 대신 **'이자'**라는 용돈을 더 많이 준답니다.
    
    * ⚠️ **주의할 점:** 한 번 통장에 돈을 넣으면, 약속한 날짜(만기일)가 될 때까지는 **절대 돈을 뺄 수 없어요!** * 그러니 당장 주식을 사거나 써야 할 현금은 지갑에 남겨두고, 여유 돈만 저금하는 지혜가 필요해요.
    """)

expected_yearly = current_deposit * ANNUAL_INTEREST_RATE
expected_monthly = expected_yearly / 12

with st.container(border=True):
    st.write(f"✨ **현재 내 예금({current_deposit:,.0f}원)의 예상 이자 보너스**")
    st.write(f"- 🏦 1달 뒤 받게 될 이자: **약 {expected_monthly:,.0f}원**")
    st.write(f"- 📈 1년 뒤 받게 될 이자: **약 {expected_yearly:,.0f}원**")

st.write("")

bank_col1, bank_col2 = st.columns(2)

with bank_col1:
    with st.container(border=True):
        st.write("⬇️ **저금하기** (현금 ➡️ 예금)")
        deposit_amt = st.number_input("넣을 금액", min_value=0, max_value=int(current_cash), step=1000, key="dep_input")
        if st.button("현금을 예금에 넣기", use_container_width=True):
            if deposit_amt > 0 and current_cash >= deposit_amt:
                # 현금 차감 및 예금 증가
                sheet_balance.update_cell(user_row_idx, 2, current_cash - deposit_amt)
                sheet_balance.update_cell(user_row_idx, 3, current_deposit + deposit_amt)
                
                # 💡 통장이 비어있다가 새로 저금하는 경우, 오늘부터 30일 뒤를 만기일로 설정!
                if current_deposit == 0:
                    new_maturity = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                    sheet_balance.update_cell(user_row_idx, 5, new_maturity) # E열(5번째 칸)에 기록
                    st.success(f"✨ {deposit_amt:,}원 저금 완료! 만기일은 30일 뒤인 {new_maturity} 입니다.")
                else:
                    st.success(f"✨ {deposit_amt:,}원 추가 저금 완료! (기존 만기일 유지)")
                
                st.rerun()
            elif deposit_amt == 0: st.error("금액을 입력해 주세요.")
            else: st.error("지갑에 현금이 부족해요!")
                
with bank_col2:
    with st.container(border=True):
        st.write("⬆️ **출금하기** (예금 ➡️ 현금)")
        
        # 💡 만기일이 안 지났으면 강력한 경고창 띄우기
        if not can_withdraw and current_deposit > 0:
            st.warning(f"🔒 은행과의 약속! 만기일({maturity_str})까지 **{days_left}일** 남았습니다. 지금은 돈을 뺄 수 없어요!")
            
        withdraw_amt = st.number_input("뺄 금액", min_value=0, max_value=int(current_deposit), step=1000, key="with_input")
        
        # 💡 만기일이 지나지 않았으면 버튼을 아예 누를 수 없게 잠금 (disabled=True)
        if st.button("예금에서 현금 빼기", use_container_width=True, disabled=not can_withdraw):
            if withdraw_amt > 0 and current_deposit >= withdraw_amt:
                sheet_balance.update_cell(user_row_idx, 2, current_cash + withdraw_amt)
                sheet_balance.update_cell(user_row_idx, 3, current_deposit - withdraw_amt)
                
                # 💡 만약 돈을 전부 다 뺐다면, 만기일 기록을 지워서 다음 저금 시 새로 시작하게 함
                if withdraw_amt == current_deposit:
                    sheet_balance.update_cell(user_row_idx, 5, "")
                    
                st.success(f"✨ {withdraw_amt:,}원 출금 완료! 약속을 잘 지켰어요.")
                st.rerun()
            elif withdraw_amt == 0: st.error("금액을 입력해 주세요.")
            else: st.error("은행 통장에 잔액이 부족해요!")
