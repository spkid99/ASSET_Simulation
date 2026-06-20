import streamlit as st
from supabase import create_client, Client
import yfinance as yf
import pandas as pd
from datetime import datetime
import requests
import io

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
    settings_data = supabase.table("system_settings").select("*").execute().data
except Exception as e:
    st.error("DB 접속 에러")
    st.stop()

users_list = [str(r.get('사용자', '')).strip() for r in balance_data if r.get('사용자', '')]
settings_dict = {r.get('key'): r.get('value') for r in settings_data}
current_db_rate = float(settings_dict.get('exchange_rate', '1385.0'))

# 💡 탭 이름을 '종목 마스터 관리'로 더욱 직관적으로 변경했습니다.
tab_money, tab_user, tab_shop, tab_stock_manage, tab_sys = st.tabs([
    "💰 용돈 지급", "👤 유저 관리", "📦 상점 물류", "📦 종목 마스터 관리", "⚙️ 시스템 제어"
])

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
    st.subheader("👤  참가자 이름 변경 및 삭제")
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

# 💡 [집중 구현] 엑셀 대량 붙여넣기 기능 및 단건 편집 통합 제어실
with tab_stock_manage:
    sub_tab1, sub_tab2 = st.tabs(["📋 엑셀 통째로 붙여넣기 (종목 리스트 리셋)", "✏️ 개별 뉴스/태그 간편 수정"])
    
    with sub_tab1:
        st.subheader("🚀 주식 종목 리스트 엑셀 일괄 교체 시스템")
        st.warning("⚠️ 주의: 여기에 데이터를 붙여넣고 실행하면 기존 수파베이스의 종목 리스트가 전체 삭제된 후 새 리스트로 완벽히 교체됩니다! (현재가는 우선 전부 0원으로 초기화됩니다)")
        
        # 안내 가이드 텍스트
        st.markdown("""
        **구글 시트나 엑셀에서 아래 7개 열(헤더 이름 포함)을 드래그하여 복사(Ctrl+C)한 후 아래 상자에 붙여넣으세요(Ctrl+V).**
        `카테고리`	`종목명`	`티커`	`설명`	`최근뉴스`	`핫한뉴스선정`	`뉴스평가`
        """)
        
        pasted_text = st.text_area("엑셀에서 복사한 테이블 데이터를 여기에 붙여넣으세요.", height=250, placeholder="카테고리\t종목명\t티커\t설명\t최근뉴스\t핫한뉴스선정\t뉴스평가\n미국주식\t테슬라\tTSLA\t전기차 제조사\t일론머스크 신제품 발표\tO\t호재")
        
        if st.button("🔥 위 데이터로 수파베이스 종목 전체 리셋 및 교체 실행", type="primary", use_container_width=True):
            if not pasted_text.strip():
                st.error("❌ 붙여넣은 텍스트 데이터가 없습니다.")
            else:
                try:
                    # 엑셀/구글시트의 복사 데이터는 탭(\t)으로 구분된 TSV 문자열입니다.
                    df_pasted = pd.read_csv(io.StringIO(pasted_text.strip()), sep='\t')
                    
                    required_cols = ['카테고리', '종목명', '티커', '설명', '최근뉴스', '핫한뉴스선정', '뉴스평가']
                    missing_cols = [c for c in required_cols if c not in df_pasted.columns]
                    
                    if missing_cols:
                        st.error(f"❌ 헤더(열 이름)가 일치하지 않습니다. 필수 기입 헤더: {missing_cols}")
                    else:
                        with st.spinner("수파베이스 클라우드 금고 비우는 중..."):
                            # 기존 stocks 테이블의 모든 데이터 영구 삭제
                            supabase.table("stocks").delete().neq("id", -1).execute()
                        
                        with st.spinner("새로운 엑셀 종목 대량 주입 중 (현재가 0 세팅)..."):
                            insert_rows = []
                            for _, row in df_pasted.iterrows():
                                insert_rows.append({
                                    "카테고리": str(row['카테고리']).strip(),
                                    "종목명": str(row['종목명']).strip(),
                                    "티커": str(row['티커']).strip(),
                                    "설명": str(row['설명']).strip(),
                                    "최근뉴스": str(row['최근뉴스']).strip() if pd.notna(row['최근뉴스']) else "",
                                    "핫한뉴스선정": str(row['핫한뉴스선정']).strip() if pd.notna(row['핫한뉴스선정']) else "",
                                    "뉴스평가": str(row['뉴스평가']).strip() if pd.notna(row['뉴스평가']) else "",
                                    "현재가": 0.0 # 🎯 요청하신 대로 최초 현재가는 전부 0원으로 깨끗하게 세팅!
                                })
                            
                            if insert_rows:
                                supabase.table("stocks").insert(insert_rows).execute()
                        
                        st.session_state.db_loaded = False
                        st.success("🎉 종목 리스트가 성공적으로 리셋 및 전체 교체되었습니다! 다음 탭에서 실시간 주가를 한 번 동기화해 주세요.")
                        st.rerun()
                except Exception as ex:
                    st.error(f"❌ 데이터 파싱 중 오류가 발생했습니다. 행/열 배치를 확인해 주세요. 오류 내용: {ex}")
                    
    with sub_tab2:
        st.subheader("📰 구글 시트형 뉴스/태그 간편 편집기")
        st.caption("주가를 0원으로 초기화하지 않고, 기존 종목들의 최근 뉴스와 아이콘 태그만 엑셀처럼 빠르게 수정할 때 사용합니다.")
        if stock_data:
            df_stocks = pd.DataFrame(stock_data)
            edit_cols = ['id', '종목명', '티커', '최근뉴스', '뉴스평가', '핫한뉴스선정']
            df_edit = df_stocks[edit_cols].copy()
            
            edited_df = st.data_editor(
                df_edit,
                disabled=['id', '종목명', '티커'],
                hide_index=True,
                use_container_width=True,
                height=300
            )
            
            st.write("")
            if st.button("💾 수정한 뉴스 표 내용만 일괄 덮어쓰기", use_container_width=True):
                with st.spinner("클라우드 금고에 뉴스 업데이트 중..."):
                    for index, row in edited_df.iterrows():
                        sid = row['id']
                        supabase.table("stocks").update({
                            "최근뉴스": str(row['최근뉴스']).strip(),
                            "뉴스평가": str(row['뉴스평가']).strip(),
                            "핫한뉴스선정": str(row['핫한뉴스선정']).strip()
                        }).eq("id", sid).execute()
                    st.session_state.db_loaded = False
                    st.success("🎉 뉴스 내용이 안전하게 저장되었습니다.")
                    st.rerun()

with tab_sys:
    st.subheader("⚙️ 시스템 마스터 제어실")
    
    with st.container(border=True):
        st.write("💵 **[부모님 전용] 현재 고정 환율 제어**")
        st.write(f"현재 데이터베이스에 기록된 기준 환율: **{current_db_rate:,.2f} 원**")
        custom_rate = st.number_input("아이들 앱에 수동으로 강제 지정할 환율 입력 (원)", min_value=1000.0, max_value=2000.0, value=current_db_rate, step=1.0)
        
        if st.button("💱 입력한 환율로 금고 강제 세팅", use_container_width=True):
            supabase.table("system_settings").update({"value": str(custom_rate)}).eq("key", "exchange_rate").execute()
            st.session_state.db_loaded = False
            st.success(f"🎯 환율이 {custom_rate:,.1f}원으로 강제 고정되었습니다. 홈 화면을 새로고침 하세요!")
            st.rerun()

    st.write("---")
    st.write("📈 **인터넷 실시간 주가 및 환율 강제 수집기**")
    if st.button("🔄 지금 즉시 인터넷 동기화 및 전 종목 현재가/환율 저장", use_container_width=True):
        with st.spinner("보안 검문소를 우회하여 최신 자산 데이터 수집 중..."):
            
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            })
            
            success_logs = []
            fail_logs = []
            
            for stock in stock_data:
                ticker = str(stock.get('티커', '')).strip()
                sid = stock.get('id')
                name = str(stock.get('종목명', ''))
                
                if ticker:
                    try:
                        t = yf.Ticker(ticker, session=session)
                        val = 0.0
                        try: val = float(t.fast_info['last_price'])
                        except:
                            hist = t.history(period="1d")
                            if not hist.empty: val = float(hist['Close'].iloc[-1])
                                
                        if val > 0:
                            supabase.table("stocks").update({"현재가": val}).eq("id", sid).execute()
                            success_logs.append(f"✅ {name} ({ticker}): {val:,.2f} 원격 저장 완료")
                        else: fail_logs.append(f"❌ {name} ({ticker}): 주가 데이터 수신 실패")
                    except Exception as e: fail_logs.append(f"❌ {name} ({ticker}): 통신 지연 ({str(e)})")
            
            try:
                response = requests.get("https://open.er-api.com/v6/latest/USD")
                if response.status_code == 200:
                    exchange_data = response.json()
                    rate = float(exchange_data["rates"]["KRW"])
                    if rate > 1000:
                        supabase.table("system_settings").update({"value": str(rate)}).eq("key", "exchange_rate").execute()
                        success_logs.append(f"✅ 환율 공인 오픈 API 실시간 수집 성공: {rate:,.2f}원")
            except Exception as e: 
                fail_logs.append(f"❌ 환율 수집 통신 오류 (기존 금고 환율 유지)")
            
            today_date = datetime.now().strftime("%Y-%m-%d")
            supabase.table("system_settings").update({"value": today_date}).eq("key", "last_stock_update").execute()
            st.session_state.db_loaded = False
            
            if success_logs:
                st.success("🎉 실시간 자산 정보 동기화가 완료되었습니다!")
                for log in success_logs: st.write(log)
            if fail_logs:
                st.error("🚨 아래 항목들은 가져오지 못했습니다.")
                for log in fail_logs: st.write(log)
