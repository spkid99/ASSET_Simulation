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
        if 'last_price' in ticker_obj.fast_info: return float(ticker_obj.fast_info['last_price'])
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

# 새로 만든 시트들 연결
try:
    sheet_shop = spreadsheet.worksheet("상점")
    sheet_purchases = spreadsheet.worksheet("구매내역")
    shop_items = sheet_shop.get_all_records()
except:
    st.error("구글 시트에 [상점] 탭과 [구매내역] 탭을 먼저 만들어주세요!")
    st.stop()

balance_data = sheet_balance.get_all_records()
history_data = sheet_history.get_all_records()
stock_data = sheet_stocks.get_all_records()
exchange_rate = get_exchange_rate()
ticker_map = {str(r.get('종목명', '')).replace(" ", ""): str(r.get('티커', '')).strip() for r in stock_data}

# --- 🔍 내 자산과 쓸 수 있는 수익금 계산 ---
user_row_idx = None
current_cash = 0.0
initial_capital = 1000000.0
current_deposit = 0.0

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
# 💡 핵심 로직: 쓸 수 있는 돈은 총 자산에서 원금(100만 원)을 뺀 순수 수익금뿐입니다!
available_profit = max(total_asset - initial_capital, 0)

# --- 🖥️ 화면 구성 ---
st.title("🛒 수익금 포인트 상점")

st.info(f"""
💡 **상점 이용 규칙**
1. 원금({initial_capital:,.0f}원)은 건드릴 수 없어요! 오직 내가 번 **수익금**으로만 쇼핑할 수 있습니다.
2. 쿠폰을 사려면 지갑에 **현금**이 있어야 해요. (수익이 났어도 현금이 없으면 주식을 팔아야 해요!)
""")

col_p, col_c = st.columns(2)
with col_p:
    st.metric(label="🌟 사용 가능한 나의 총 수익금", value=f"{available_profit:,.0f} 원")
with col_c:
    st.metric(label="💰 내 지갑 현금 잔액", value=f"{current_cash:,.0f} 원")

st.divider()

st.subheader("🎁 판매 중인 상품 목록")

if not shop_items:
    st.write("현재 상점에 등록된 상품이 없습니다. 구글 시트의 [상점] 탭에 상품을 추가해 주세요!")
else:
    # 상품을 2개씩 한 줄에 보여주기
    cols = st.columns(2)
    for idx, item in enumerate(shop_items):
        icon = item.get('아이콘', '🎁')
        name = item.get('상품명', '이름 없음')
        price = float(item.get('가격', 0))
        desc = item.get('설명', '')
        
        with cols[idx % 2]:
            with st.container(border=True):
                st.subheader(f"{icon} {name}")
                st.write(f"**가격: {price:,.0f}원**")
                st.caption(desc)
                
                if st.button(f"구매하기", key=f"buy_{idx}"):
                    if available_profit < price:
                        st.error("❌ 쓸 수 있는 수익금이 부족해요! 투자를 더 해서 수익을 늘려보세요.")
                    elif current_cash < price:
                        st.error("❌ 수익은 충분하지만 지갑에 현금이 없어요! 은행에서 출금하거나 주식을 조금 팔아서 현금을 마련해 오세요.")
                    else:
                        # 현금 차감 및 구매 내역 저장
                        sheet_balance.update_cell(user_row_idx, 2, current_cash - price)
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        sheet_purchases.append_row([now, current_user, name, price])
                        
                        st.success(f"🎉 {name} 구매 완료! 부모님께 말씀드려 진짜 상품으로 교환받으세요!")
                        st.rerun()

st.sidebar.success("원하는 메뉴를 위에서 선택해 주세요!")
