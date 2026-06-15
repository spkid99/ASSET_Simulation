import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

st.set_page_config(page_title="부모님 전용 관리자 모드", layout="wide")

st.title("⚙️ 부모님 전용 관리자 모드")
pwd = st.text_input("관리자 비밀번호를 입력하세요", type="password")
if pwd != "0000":
    st.warning("🔒 올바른 관리자 비밀번호를 입력해야 제어 장치가 활성화됩니다.")
    st.stop()

st.success("🔓 마스터 계정 로그인 성공!")

# --- 🔌 구글 시트 연결 ---
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
client = gspread.authorize(creds)
spreadsheet = client.open("ASSET_Simulation")

sheet_balance = spreadsheet.worksheet("잔고")
sheet_history = spreadsheet.worksheet("투자내역")
sheet_purchases = spreadsheet.worksheet("구매내역")

balance_data = sheet_balance.get_all_records()
history_values = sheet_history.get_all_values()
purchase_values = sheet_purchases.get_all_values()

# --- 데이터 매핑 ---
users_list = [str(r.get('사용자', '')).strip() for r in balance_data if r.get('사용자', '')]

tab_u, tab_s = st.tabs(["👤 유저 관리 패널", "📦 Reward Shop 물류 관리"])

with tab_u:
    st.subheader("👤 시뮬레이션 참가자 제어")
    
    if not users_list:
        st.info("등록된 유저가 없습니다.")
    else:
        # 1. 이름 변경 기능
        with st.form("rename_form"):
            st.write("✏️ **유저 이름 변경하기**")
            old_name = st.selectbox("변경할 대상 선택", users_list)
            new_name = st.text_input("새로운 이름 입력").strip()
            rename_submitted = st.form_submit_button("이름 일괄 변경 실행")
            
            if rename_submitted:
                if not new_name:
                    st.error("새 이름을 입력하세요!")
                elif new_name in users_list:
                    st.error("이미 존재하는 이름입니다!")
                else:
                    # 잔고 시트 업데이트
                    for idx, row in enumerate(balance_data):
                        if str(row.get('사용자', '')).strip() == old_name:
                            sheet_balance.update_cell(idx + 2, 1, new_name)
                            break
                    # 투자내역 시트 동기화
                    for idx, row in enumerate(history_values[1:], start=2):
                        if len(row) > 1 and row[1] == old_name:
                            sheet_history.update_cell(idx, 2, new_name)
                    # 구매내역 시트 동기화
                    for idx, row in enumerate(purchase_values[1:], start=2):
                        if len(row) > 1 and row[1] == old_name:
                            sheet_purchases.update_cell(idx, 2, new_name)
                    st.success(f"⚖️ {old_name} ➡️ {new_name} 자산 및 이력 데이터 일괄 변경 완료!")
                    st.rerun()

        # 2. 유저 삭제 기능
        st.write("---")
        with st.form("delete_form"):
            st.write("🚨 **유저 영구 삭제 (오타 대처용)**")
            del_name = st.selectbox("삭제할 유저 선택", users_list, key="del_box")
            st.warning("⚠️ 유저를 삭제하면 해당 금고(잔고 데이터)가 즉시 파괴되며 복구할 수 없습니다.")
            del_submitted = st.form_submit_button("❌ 유저 데이터 계정 삭제")
            
            if del_submitted:
                for idx, row in enumerate(balance_data):
                    if str(row.get('사용자', '')).strip() == del_name:
                        sheet_balance.delete_rows(idx + 2)
                        break
                st.success(f"🔥 {del_name} 유저 계정이 완전 삭제되었습니다.")
                st.rerun()

with tab_s:
    st.subheader("🛒 실물 보상 상품 및 정산 관리")
    
    # 미전달 상품 통계 연산
    undelivered_items = []
    all_purchases = []
    for idx, row in enumerate(purchase_values[1:], start=2):
        while len(row) < 5: row.append("사용전")
        status = row[4] if row[4] else "사용전"
        
        p_info = {
            'row_idx': idx, '시간': row[0], '사용자': row[1], '상품명': row[2], '결제금액': row[3], '상태': status
        }
        all_purchases.append(p_info)
        if status != "전달완료":
            undelivered_items.append(p_info)
            
    st.metric(label="📦 현실에서 아직 아이에게 전달 안 된 상품 총 개수", value=f"{len(undelivered_items)} 개")
    
    filter_opt = st.radio("장부 필터 설정", ["전달 대기중인 내역만 보기", "전체 구매 이력 보기"], horizontal=True)
    st.write("")
    
    target_list = undelivered_items if filter_opt == "전달 대기중인 내역만 보기" else all_purchases
    
    if not target_list:
        st.info("조건에 부합하는 정산 장부 내역이 비어 있습니다.")
    else:
        for idx, p in enumerate(target_list):
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"### 👤 {p['사용자']} ➡️ {p['상품명']}")
                    st.caption(f"구매 시각: {p['시간']} | 결제액: {int(float(p['결제금액'])):,}원 | 현재 상태: **{p['상태']}**")
                with c2:
                    st.write("")
                    if p['상태'] != "전달완료":
                        if st.button("🚚 실물 전달 완료", key=f"del_admin_{idx}", use_container_width=True):
                            sheet_purchases.update_cell(p['row_idx'], 5, "전달완료")
                            st.success("배송 및 지급 상태를 완료 처리했습니다.")
                            st.rerun()
                    else:
                        st.button("✅ 지급 완료됨", disabled=True, key=f"done_admin_{idx}", use_container_width=True)
