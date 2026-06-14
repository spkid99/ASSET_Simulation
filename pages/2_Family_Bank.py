import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="우리집 은행", layout="centered")

scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
client = gspread.authorize(creds)
spreadsheet = client.open("ASSET_Simulation")

sheet_balance = spreadsheet.worksheet("잔고")
balance_data = sheet_balance.get_all_records()

current_cash = float(balance_data[0].get('현금잔액', 0)) if balance_data else 0
current_deposit = float(balance_data[0].get('예금잔액', 0)) if balance_data else 0

st.title("🏦 우리집 은행 (예금/출금)")

ANNUAL_INTEREST_RATE = 0.035
st.write(f"안전하게 원금과 이자를 모을 수 있는 곳이에요. (📈 **적용 금리: 연 {ANNUAL_INTEREST_RATE*100}%**)")

expected_yearly = current_deposit * ANNUAL_INTEREST_RATE
expected_monthly = expected_yearly / 12

with st.container(border=True):
    st.write(f"💡 **현재 내 예금({current_deposit:,.0f}원)의 예상 이자**")
    st.write(f"- 1달을 넣어두면: **약 {expected_monthly:,.0f}원**이 붙어요!")
    st.write(f"- 1년을 넣어두면: **약 {expected_yearly:,.0f}원**이 붙어요!")
    
    if st.button("🎁 [시뮬레이션] 한 달 치 이자 예금으로 받기 ⏳", use_container_width=True):
        if current_deposit > 0:
            interest_amt = int(expected_monthly)
            if interest_amt > 0:
                sheet_balance.update_acell('B2', current_deposit + interest_amt)
                st.success(f"야호! 한 달이 지났다고 가정하고 {interest_amt:,}원의 이자가 예금에 추가되었어요!")
                st.rerun()
            else: st.warning("이자가 1원 미만이라 아직 받을 수 없어요. 예금을 더 넣어보세요!")
        else: st.warning("통장이 텅 비었어요. 현금을 먼저 예금해주세요!")

bank_col1, bank_col2 = st.columns(2)

with bank_col1:
    with st.container(border=True):
        st.write("⬇️ **예금하기** (현금 ➡️ 예금)")
        deposit_amt = st.number_input("넣을 금액", min_value=0, max_value=int(current_cash), step=1000, key="dep_input")
        if st.button("예금 통장에 넣기", use_container_width=True):
            if deposit_amt > 0 and current_cash >= deposit_amt:
                sheet_balance.update_acell('A2', current_cash - deposit_amt)
                sheet_balance.update_acell('B2', current_deposit + deposit_amt)
                st.success(f"{deposit_amt:,}원 예금 완료!")
                st.rerun()
            elif deposit_amt == 0: st.error("금액을 입력해 주세요.")
            else: st.error("현금이 부족해요!")
                
with bank_col2:
    with st.container(border=True):
        st.write("⬆️ **출금하기** (예금 ➡️ 현금)")
        withdraw_amt = st.number_input("뺄 금액", min_value=0, max_value=int(current_deposit), step=1000, key="with_input")
        if st.button("현금으로 빼기", use_container_width=True):
            if withdraw_amt > 0 and current_deposit >= withdraw_amt:
                sheet_balance.update_acell('A2', current_cash + withdraw_amt)
                sheet_balance.update_acell('B2', current_deposit - withdraw_amt)
                st.success(f"{withdraw_amt:,}원 출금 완료!")
                st.rerun()
            elif withdraw_amt == 0: st.error("금액을 입력해 주세요.")
            else: st.error("예금 잔액이 부족해요!")
