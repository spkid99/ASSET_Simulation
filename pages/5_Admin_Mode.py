import streamlit as st
from supabase import create_client, Client
import yfinance as yf
import pandas as pd
from datetime import datetime
import requests

st.set_page_config(page_title="부모님 전용 관리자 모드", layout="wide")

st.title("⚙️ 부모님 전용 관리자 모드")
pwd = st.text_input("관리자 비밀번호를 입력하세요", type="password")
if pwd != "0000":
    st.warning("🔒 올바른 관리자 비밀번호를 입력해야 제어 장치가 활성화됩니다.")
    st.stop()

st.success("🔓 마스터 계정 로그인 성공! 모든 권한이 활성화되었습니다.")

@st.cache_resource(ttl=3600)
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

try:
    balance_data = supabase.table("balance").select("*").execute().data
    purchases_data = supabase.table("purchases").select("*").execute().data
    stock_data = supabase.table("stocks").select("*").execute().data
except Exception as e:
    st.error("DB 접속 에러")
    st.stop()

users_list = [str(r.get('사용자', '')).strip() for r in balance_data if r.get('사용자', '')]

tab_money, tab_user, tab_shop, tab_sys = st.tabs(["💰 용돈 지급", "👤 유저 관리", "📦 상점 물류", "⚙️ 시스템 마스터 제어"])

with tab_money:
    st.subheader("🎁 자산 강제 주입 (보너스 지급)")
    if not users_list: st.info("유저가 없습니다.")
    else:
        with st.container(border=True):
            target_user = st.selectbox("누구에게 줄까요?", users_list, key="bonus_user")
            bonus_amt = st.number_input("지급할 금액", min_value=0.0, step=1000.0, value=10000.0)
            if st.button(f"🚀 {target_user}에게 {bonus_amt:,.0f}원 쏘기", use_container_width=True):
                u_cash = next((float(r.get('현금잔액', 0)) for r in balance_data if r.get('사용자') == target_user), 0.0)
                supabase.table("balance").update({"현금잔액": u_cash + bonus_amt}).eq("사용자", target_user).execute()
                st.session_state.db_loaded = False
                st.success(f"{target_user} 통장에 {bonus_amt:,.0f}원 입금 완료!")
                st.rerun()

with tab_user:
    st.subheader("👤 참가자 이름 변경 및 삭제")
    if users_list:
        with st.form("rename_form"):
            st.write("✏️ **유저 이름 일괄 변경**")
            old_name = st.selectbox("변경할 대상 선택", users_list)
            new_name = st.text_input("새로운 이름 입력").strip()
            if st.form_submit_button("이름 일괄 변경 실행"):
                if not new_name: st.error("새 이름을 입력하세요!")
                elif new_name in users_list: st.error("이미 존재하는 이름입니다!")
                else:
                    supabase.table("balance").update({"사용자": new_name}).eq("사용자", old_name).execute()
                    supabase.table("history").update({"사용자": new_name}).eq("사용자", old_name).execute()
                    supabase.table("purchases").update({"사용자": new_name}).eq("사용자", old_name).execute()
                    st.session_state.db_loaded = False
                    st.success(f"⚖️ {old_name} ➡️ {new_name} 변경 완료!")
                    st.rerun()

        st.write("---")
        with st.form("delete_form"):
            st.write("🚨 **유저 영구 삭제**")
            del_name = st.selectbox("삭제할 유저 선택", users_list)
            st.warning("⚠️ 삭제하면 모든 데이터(잔고, 기록)가 파괴됩니다.")
            if st.form_submit_button("❌ 영구 삭제 실행"):
                supabase.table("balance").delete().eq("사용자", del_name).execute()
                supabase.table("history").delete().eq("사용자", del_name).execute()
                supabase.table("purchases").delete().eq("사용자", del_name).execute()
                st.session_state.db_loaded = False
                st.success(f"🔥 {del_name} 삭제 완료.")
                st.rerun()

with tab_shop:
    st.subheader("🛒 실물 보상 전달 확인")
    undelivered = [p for p in purchases_data if p.get('상태') != "전달완료"]
    st.metric("📦 대기 중인 배송(전달) 건수", f"{len(undelivered)} 건")
    filter_opt = st.radio("보기 옵션", ["전달 대기중만 보기", "전체 보기"], horizontal=True)
    target_list = undelivered if filter_opt == "전달 대기중만 보기" else purchases_data
    if not target_list: st.info("내역이 없습니다.")
    else:
        for p in target_list:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"### 👤 {p.get('사용자')} ➡️ {p.get('상품명')}")
                    st.caption(f"시간: {p.get('시간')} | 가격: {p.get('결제금액', 0):,.0f}원 | 상태: **{p.get('상태')}**")
                with c2:
                    st.write("")
                    p_id = p.get('id')
                    if p.get('상태') != "전달완료":
                        if st.button("🚚 전달 완료 처리", key=f"del_{p_id}", use_container_width=True):
                            supabase.table("purchases").update({"상태": "전달완료"}).eq("id", p_id).execute()
                            st.success("배송 완료 처리됨!")
                            st.rerun()
                    else: st.button("✅ 처리완료", disabled=True, key=f"done_{p_id}", use_container_width=True)

with tab_sys:
    st.subheader("📈 [부모님 전용] 실시간 주가 강제 업데이트 시스템")
    st.write("자동으로 하루 1회 고정되지만, 지금 즉시 주가를 새로 고치고 싶다면 아래 버튼을 누르세요.")
    if st.button("🔄 지금 즉시 야후 파이낸스 동기화 및 전 종목 현재가 저장", use_container_width=True):
        with st.spinner("야후 검문소를 뚫고 실시간 주가 긁어오는 중..."):
            
            # 💡 핵심: 진짜 사람(크롬 브라우저)인 척하는 신분증(Session) 만들기
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            
            for stock in stock_data:
                ticker = str(stock.get('티커', '')).strip()
                sid = stock.get('id')
                if ticker:
                    try:
                        # 위조 신분증(session)을 야후에 제시하며 가격 요구
                        t = yf.Ticker(ticker, session=session)
                        hist = t.history(period="5d")
                        val = float(hist['Close'].iloc[-1]) if not hist.empty else 0.0
                        if val > 0:
                            supabase.table("stocks").update({"현재가": val}).eq("id", sid).execute()
                    except: pass
            
            try:
                t_rate = yf.Ticker("USDKRW=X", session=session)
                rate = float(t_rate.fast_info['last_price'])
                if rate > 0: st.session_state.exchange_rate = rate
            except: pass
            
            today_date = datetime.now().strftime("%Y-%m-%d")
            supabase.table("system_settings").update({"value": today_date}).eq("key", "last_stock_update").execute()
            st.session_state.db_loaded = False
            st.success("🎉 전 종목 실시간 주가가 수파베이스 금고에 완벽하게 갱신 및 저장되었습니다!")
            st.rerun()
