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
    # 💡 내 지갑 정보와 함께 '만기일' 데이터도 쏙 뽑아옵니다.
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

# --- 🔒 만기일 잠금 로직 계산 ---
is_locked = False
today = datetime.now().date()

# 데이터베이스에 만기일이 적혀있다면 날짜를 비교합니다.
if maturity_date_str and maturity_date_str.lower() != 'nan':
    try:
        maturity_date = datetime.strptime(maturity_date_str, "%Y-%m-%d").date()
        if today < maturity_date:
            is_locked = True # 아직 만기일이 안 지났으면 자물쇠 철칵!
    except:
        pass 

# --- 🖥️ 화면 UI 구성 ---
st.title("🏦 가족 은행")
st.info("안전하게 돈을 보관하고 이자를 받아보세요! (약속한 만기일 전에는 뺄 수 없습니다)")

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
        
        # 만기일 상태 표시기
        if maturity_date_str and maturity_date_str.lower() != 'nan':
            if is_locked:
                st.markdown(f"🔒 **만기일:** <span style='color:#ff4b4b;'>{maturity_date_str} (출금 불가)</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"🔓 **만기일:** <span style='color:#11B67A;'>{maturity_date_str} (출금 가능)</span>", unsafe_allow_html=True)
        else:
            st.caption("만기일 미지정 (자유 입출금 가능)")

st.divider()

# 🎛️ 예금/출금 UI (탭이 아닌 원래의 직관적인 좌우 나란히 배치)
col_in, col_out = st.columns(2)

with col_in:
    st.subheader("💰 예금하기")
    st.write("지갑의 현금을 은행에 넣습니다.")
    
    in_amt = st.number_input("예금할 금액 (원)", min_value=0.0, step=1000.0, format="%.0f", key="in_amt")
    
    if st.button("입금 확정", use_container_width=True, type="primary"):
        if current_cash >= in_amt and in_amt > 0:
            supabase.table("balance").update({
                "현금잔액": current_cash - in_amt, 
                "예금잔액": current_deposit + in_amt
            }).eq("사용자", current_user).execute()
            
            st.session_state.db_loaded = False # 메인 화면 메모리 동기화 신호
            st.success(f"🎉 {in_amt:,.0f}원 예금 완료!")
            st.rerun()
        elif in_amt <= 0:
            st.warning("금액을 1원 이상 입력해주세요.")
        else: 
            st.error("❌ 지갑에 현금이 부족합니다.")

with col_out:
    st.subheader("💸 출금하기")
    st.write("은행의 예금을 지갑으로 뺍니다.")
    
    out_amt = st.number_input("출금할 금액 (원)", min_value=0.0, step=1000.0, format="%.0f", key="out_amt")
    
    # 💡 만기일이 지나지 않았다면 버튼 자체를 아예 비활성화(막아버림) 시킵니다!
    if is_locked:
        st.error(f"🔒 약속한 만기일({maturity_date_str})까지 꾹 참아야 합니다!")
        st.button("출금 확정", disabled=True, use_container_width=True, key="btn_out_locked")
    else:
        if st.button("출금 확정", use_container_width=True, type="primary", key="btn_out_free"):
            if current_deposit >= out_amt and out_amt > 0:
                supabase.table("balance").update({
                    "현금잔액": current_cash + out_amt, 
                    "예금잔액": current_deposit - out_amt
                }).eq("사용자", current_user).execute()
                
                st.session_state.db_loaded = False
                st.success(f"
