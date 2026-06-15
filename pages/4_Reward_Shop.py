import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="포인트 상점", layout="centered")

if "user_id" not in st.session_state or not st.session_state.user_id:
    st.warning("👤 먼저 메인 홈 화면(app.py)에서 이름을 입력하고 로그인해 주세요!")
    st.stop()

current_user = st.session_state.user_id

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
        return 0.0
    except: return 0.0

# --- 🔌 구글 시트 연결 ---
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
client = gspread.authorize(creds)
spreadsheet = client.open("ASSET_Simulation")

sheet_balance = spreadsheet.worksheet("잔고")
sheet_history = spreadsheet.worksheet("투자내역")
sheet_stocks = spreadsheet.worksheet("종목관리")
sheet_shop = spreadsheet.worksheet("상점")
sheet_purchases = spreadsheet.worksheet("구매내역")

balance_data = sheet_balance.get_all_records()
history_data = sheet_history.get_all_records()
stock_data = sheet_stocks.get_all_records()
shop_items = sheet_shop.get_all_records()
purchase_values = sheet_purchases.get_all_values() # 행 인덱스 추적용
exchange_rate = get_exchange_rate()
ticker_map = {str(r.get('종목명', '')).replace(" ", ""): str(r.get('티커', '')).strip() for r in stock_data}

# --- 🔍 자산 및 가용 수익금 계산 ---
user_row_idx, current_cash, current_deposit, initial_capital = None, 0.0, 0.0, 1000000.0
for idx, row in enumerate(balance_data):
    if str(row.get('사용자', '')).strip() == current_user:
        user_row_idx = idx + 2
        current_cash = float(row.get('현금잔액', 0))
        current_deposit = float(row.get('예금잔액', 0))
        initial_capital = float(row.get('초기자본금', 1000000))
        break

portfolio = {}
for row in history_data:
    if str(row.get('사용자', '')).strip() != current_user: continue
    name = str(row.get('종목명', '')).replace(" ", "")
    kind = str(row.get('종류', row.get('종류(매수/매도)', ''))).strip()
    try: qty = float(row.get('수량', 0))
    except: qty = 0.0
    if kind == '매수': portfolio[name] = portfolio.get(name, 0) + qty
    elif kind == '매도': portfolio[name] = portfolio.get(name, 0) - qty

total_stock_value = 0.0
for name, qty in portfolio.items():
    if qty <= 0: continue
    ticker = ticker_map.get(name, "")
    if ticker:
        raw_price = get_price(ticker)
        is_korean = ticker.endswith('.KS') or ticker.endswith('.KQ')
        total_stock_value += (raw_price if is_korean else raw_price * exchange_rate) * qty

total_asset = current_cash + current_deposit + total_stock_value
available_profit = max(total_asset - initial_capital, 0)

# --- 🎟️ 내 쿠폰지갑 데이터 추출 ---
user_coupons = []
for r_idx, row in enumerate(purchase_values[1:], start=2):
    while len(row) < 5: row.append("사용전")
    if str(row[1]).strip() == current_user:
        user_coupons.append({
            'row_idx': r_idx, '시간': row[0], '상품명': row[2], '결제금액': row[3], '상태': row[4] if row[4] else "사용전"
        })

# --- 🖥️ 화면 구성 ---
st.title("🛒 수익금 포인트 상점 & 지갑")
st.info(f"💡 원금({initial_capital:,.0f}원) 제외 순수 투자 수익금으로만 이용 가능합니다.")

col_p, col_c = st.columns(2)
with col_p: st.metric(label="🌟 사용 가능한 나의 총 수익금", value=f"{available_profit:,.0f} 원")
with col_c: st.metric(label="💰 내 지갑 현금 잔액", value=f"{current_cash:,.0f} 원")

tab_shop, tab_wallet = st.tabs(["🛍️ 상품 상점 구경", "🎟️ 내 쿠폰지갑"])

with tab_shop:
    if not shop_items:
        st.write("현재 상점에 등록된 상품이 없습니다.")
    else:
        cols = st.columns(2)
        for idx, item in enumerate(shop_items):
            img_url = str(item.get('이미지URL', '')).strip()
            name = item.get('상품명', '이름 없음')
            price = float(item.get('가격', 0))
            desc = item.get('설명', '')
            
            with cols[idx % 2]:
                with st.container(border=True):
                    if img_url:
                        try: st.image(img_url, use_container_width=True)
                        except: st.caption("🖼️ 이미지를 불러올 수 없습니다.")
                    st.subheader(name)
                    st.write(f"**가격: {price:,.0f}원**")
                    st.caption(desc)
                    
                    if st.button(f"구매하기", key=f"buy_{idx}", use_container_width=True):
                        if available_profit < price: st.error("❌ 쓸 수 있는 수익금이 부족해요!")
                        elif current_cash < price: st.error("❌ 지갑에 실물 현금이 부족합니다. 주식을 일부 매도해 주세요.")
                        else:
                            sheet_balance.update_cell(user_row_idx, 2, current_cash - price)
                            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            # 상태 칸에 '사용전' 기입
                            sheet_purchases.append_row([now_str, current_user, name, price, "사용전"])
                            st.success(f"🎉 {name} 구매 완료! '내 쿠폰지갑'으로 전송되었습니다.")
                            st.rerun()

with tab_wallet:
    st.subheader("🎟️ 보유 중인 모바일 쿠폰")
    if not user_coupons:
        st.info("아직 구매한 쿠폰이 없습니다.")
    else:
        for c_idx, cp in enumerate(user_coupons):
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"### {cp['상품명']}")
                    st.caption(f"구매일시: {cp['시간']} | 상태: **{cp['상태']}**")
                with c2:
                    st.write("")
                    if cp['상태'] == "사용전":
                        if st.button("🎟️ 사용하기", key=f"use_btn_{c_idx}", use_container_width=True):
                            sheet_purchases.update_cell(cp['row_idx'], 5, "사용완료")
                            st.success("쿠폰을 사용 처리했습니다! 부모님께 선물을 요청하세요.")
                            st.rerun()
                    elif cp['상태'] == "사용완료":
                        st.button("✅ 사용 완료", disabled=True, key=f"used_{c_idx}", use_container_width=True)
                    elif cp['상태'] == "전달완료":
                        st.button("📦 전달 완료", disabled=True, key=f"del_user_{c_idx}", use_container_width=True)
