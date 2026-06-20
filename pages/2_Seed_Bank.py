import streamlit as st
from supabase import create_client, Client
from datetime import datetime
import pandas as pd

st.set_page_config(page_title="가족 은행", layout="centered")

if "user_id" not in st.session_state or not st.session_state.user_id:
    st.warning("👤 먼저 메인 홈 화면(app.py)에서 로그인해 주세요!")
    st.stop()

current_user = st.session_state.user_id

@st.cache_resource(ttl=3600)
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

try:
    user_res = supabase.table("balance").select("*").eq("사용자", current_user).execute()
    if not user_res.data:
        st.error("사용자 정보를 찾을 수 없습니다.")
        st.stop()
        
    user_data = user_res.data[0]
    current_cash = float(user_data.get('현금잔액', 0))
    current_deposit = float(user_data.get('예금잔액', 0))
    maturity_date_str = str(user_data.get('만기일', '')).strip()
    
except Exception as e:
    st.error("데이터베이스 연결 오류가 발생했습니다.")
    st.stop()

# --- 🔒 만기일 잠금 로직 ---
is_locked = False
today = datetime.now().date()

if maturity_date_str and maturity_date_str.lower() != 'nan':
    try:
        maturity_date = datetime.strptime(maturity_date_str, "%Y-%m-%d").date()
        if today < maturity_date:
            is_locked = True
    except:
        pass 

# 💡 현실 은행 방식 적용: 연이율 12% 및 1달(1개월) 만기 기준 이자 계산
base_annual_rate = 12.0
monthly_rate = base_annual_rate / 12.0
expected_interest = current_deposit * (monthly_rate / 100)
expected_total = current_deposit + expected_interest

# --- 🖥️ 화면 UI 구성 ---
st.title("🏦 시드 뱅크 (1달 만기 예금)")
st.info("안전하게 돈을 보관하고 실제 은행처럼 1달 뒤에 이자를 받아보세요! (만기일 전 출금 불가)")

# 📊 자산 현황판
col_top1, col_top2 = st.columns(2)
with col_top1:
    with st.container(border=True): 
        st.write("💵 **내 지갑 (가용 현금)**")
        st.subheader(f"{current_cash:,.0f} 원")
with col_top2:
    with st.container(border=True): 
        st.write("🏛️ **은행 통장 (예금)**")
        st.subheader(f"{current_deposit:,.0f} 원")
        
        if maturity_date_str and maturity_date_str.lower() != 'nan':
            if is_locked:
                st.markdown(f"🔒 **만기일:** <span style='color:#ff4b4b;'>{maturity_date_str} (출금 불가)</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"🔓 **만기일:** <span style='color:#11B67A;'>{maturity_date_str} (출금 가능)</span>", unsafe_allow_html=True)
        else:
            st.caption("만기일 미지정 (현재 입출금 자유)")

# 💡 연이율 및 월 적용 이자 안내판
with st.container(border=True):
    st.write(f"📈 **가족 은행 예금 금리:** 연이율 **{base_annual_rate}%** (1달 만기 시 실적용 이자율: **{monthly_rate:.0f}%**)")
    st.markdown(f"🎁 **1달 만기 시 예상 수령액:** <span style='color:#0083ff; font-weight:bold;'>총 {expected_total:,.0f} 원</span> (원금 + 이자 {expected_interest:,.0f}원)", unsafe_allow_html=True)
    st.caption("※ 🏆 시상식에서 '티끌모아 태산 상'을 받으면 특별 우대 금리가 추가될 수 있습니다!")

st.divider()

# 🎛️ 예금/출금 UI
col_in, col_out = st.columns(2)

with col_in:
    st.subheader("💰 예금하기")
    st.write("지갑의 현금을 은행에 넣습니다.")
    in_amt = st.number_input("예금할 금액 (원)", min_value=0.0, step=1000.0, format="%.0f", key="in_amt")
    
    if st.button("입금 확정", use_container_width=True, type="primary"):
        if current_cash >= in_amt and in_amt > 0:
            supabase.table("balance").update({"현금잔액": current_cash - in_amt, "예금잔액": current_deposit + in_amt}).eq("사용자", current_user).execute()
            st.session_state.db_loaded = False
            st.success(f"🎉 {in_amt:,.0f}원 예금 완료! 만기 시 받을 이자가 늘어났습니다.")
            st.rerun()
        elif in_amt <= 0:
            st.warning("금액을 1원 이상 입력해주세요.")
        else: 
            st.error("❌ 지갑에 현금이 부족합니다.")

with col_out:
    st.subheader("💸 출금하기")
    st.write("은행의 예금을 지갑으로 뺍니다.")
    out_amt = st.number_input("출금할 금액 (원)", min_value=0.0, step=1000.0, format="%.0f", key="out_amt")
    
    if is_locked:
        st.error(f"🔒 약속한 만기일({maturity_date_str})까지 꾹 참아야 합니다!")
        st.button("출금 확정", disabled=True, use_container_width=True, key="btn_out_locked")
    else:
        if st.button("출금 확정", use_container_width=True, type="primary", key="btn_out_free"):
            if current_deposit >= out_amt and out_amt > 0:
                supabase.table("balance").update({"현금잔액": current_cash + out_amt, "예금잔액": current_deposit - out_amt}).eq("사용자", current_user).execute()
                st.session_state.db_loaded = False
                st.success(f"🎉 {out_amt:,.0f}원 출금 완료!")
                st.rerun()
            elif out_amt <= 0:
                st.warning("금액을 1원 이상 입력해주세요.")
            else: 
                st.error("❌ 은행 예금이 부족합니다.")
