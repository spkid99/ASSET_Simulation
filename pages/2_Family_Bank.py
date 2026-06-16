import streamlit as st
from supabase import create_client, Client

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
    # 💡 Supabase에서 내 지갑 정보만 0.01초 만에 쏙 뽑아옵니다!
    user_res = supabase.table("balance").select("*").eq("사용자", current_user).execute()
    if not user_res.data:
        st.error("사용자 정보를 찾을 수 없습니다.")
        st.stop()
    user_data = user_res.data[0]
    current_cash = float(user_data.get('현금잔액', 0))
    current_deposit = float(user_data.get('예금잔액', 0))
except Exception as e:
    st.error("데이터베이스 연결 오류가 발생했습니다.")
    st.stop()

st.title("🏦 가족 은행")
st.info("안전하게 돈을 보관하고 이자를 받아보세요!")

col1, col2 = st.columns(2)
with col1:
    with st.container(border=True): 
        st.write("💵 **내 지갑 (현금)**")
        st.subheader(f"{current_cash:,.0f} 원")
with col2:
    with st.container(border=True): 
        st.write("🏛️ **은행 통장 (예금)**")
        st.subheader(f"{current_deposit:,.0f} 원")

tab_in, tab_out = st.tabs(["💰 예금하기 (통장에 돈 넣기)", "💸 출금하기 (지갑으로 돈 빼기)"])

with tab_in:
    in_amt = st.number_input("예금할 금액 (원)", min_value=0.0, step=1000.0, format="%.0f")
    if st.button("입금 확인", use_container_width=True):
        if current_cash >= in_amt and in_amt > 0:
            # 💡 잔고 업데이트 (현금 빼고, 예금 더하기)
            supabase.table("balance").update({
                "현금잔액": current_cash - in_amt, 
                "예금잔액": current_deposit + in_amt
            }).eq("사용자", current_user).execute()
            
            st.session_state.db_loaded = False # 메인 화면 메모리 동기화 신호
            st.success(f"🎉 {in_amt:,.0f}원 예금 완료!")
            st.rerun()
        else: st.error("❌ 지갑에 현금이 부족합니다.")

with tab_out:
    out_amt = st.number_input("출금할 금액 (원)", min_value=0.0, step=1000.0, format="%.0f")
    if st.button("출금 확인", use_container_width=True):
        if current_deposit >= out_amt and out_amt > 0:
            # 💡 잔고 업데이트 (현금 더하고, 예금 빼기)
            supabase.table("balance").update({
                "현금잔액": current_cash + out_amt, 
                "예금잔액": current_deposit - out_amt
            }).eq("사용자", current_user).execute()
            
            st.session_state.db_loaded = False
            st.success(f"🎉 {out_amt:,.0f}원 출금 완료!")
            st.rerun()
        else: st.error("❌ 은행 예금이 부족합니다.")
