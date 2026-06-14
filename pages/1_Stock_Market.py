import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="주식 시장", layout="centered")

# --- 👤 로그인 확인 시스템 ---
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
    try: return float(yf.Ticker(ticker).fast_info['last_price'])
    except: return 0.0

@st.cache_data(ttl=3600)
def get_chart(ticker):
    try:
        hist = yf.Ticker(ticker).history(period="1y")
        if not hist.empty:
            chart_data = hist[['Close']].copy()
            chart_data.index = chart_data.index.tz_localize(None)
            return chart_data
    except: return None
    return None

# --- 🔌 구글 시트 연결 (⚡ 과부하 방어력 추가!) ---
# 구글 시트에 매번 로그인하지 않고, 한 번 연결하면 10분(600초) 동안 유지합니다.
@st.cache_resource(ttl=600)
def init_google_sheet():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    return client.open("ASSET_Simulation")

spreadsheet = init_google_sheet()
sheet_balance = spreadsheet.worksheet("잔고")
sheet_stocks = spreadsheet.worksheet("종목관리")
sheet_history = spreadsheet.worksheet("투자내역")

balance_data = sheet_balance.get_all_records()
stock_data = sheet_stocks.get_all_records()
history_data = sheet_history.get_all_records()
exchange_rate = get_exchange_rate()

# --- 🔍 현재 로그인한 사용자의 줄(Row) 위치와 현금 찾기 ---
user_row_idx = None
current_cash = 0.0

for idx, row in enumerate(balance_data):
    if str(row.get('사용자', '')).strip() == current_user:
        user_row_idx = idx + 2
        current_cash = float(row.get('현금잔액', 0))
        break

if user_row_idx is None:
    st.error("사용자 정보를 찾을 수 없습니다. 홈 화면에서 다시 로그인해 주세요.")
    st.stop()

# --- 📊 내 보유 주식만 계산 ---
def get_owned_stocks():
    owned = {}
    for row in history_data:
        if str(row.get('사용자', '')).strip() != current_user: continue # 내 것만!
        name = str(row.get('종목명', '')).replace(" ", "")
        kind = str(row.get('종류', row.get('종류(매수/매도)', ''))).strip()
        try: qty = float(row.get('수량', 0))
        except: qty = 0.0
        if kind == '매수': owned[name] = owned.get(name, 0) + qty
        elif kind == '매도': owned[name] = owned.get(name, 0) - qty
    return {k: round(v, 2) for k, v in owned.items() if round(v, 2) > 0}

owned_stocks = get_owned_stocks()

# --- 🖥️ 화면 그리기 ---
st.title("✨ 주식 시장 (투자하기)")
st.info(f"👤 **{current_user}**님 자산 상태 ➡️ 💰 사용 가능한 현금: {current_cash:,.0f}원 | 💵 환율: {exchange_rate:,.2f}원")

if stock_data:
    categories = list(set([str(stock.get('카테고리', '기타')).strip() for stock in stock_data]))
    categories.sort() 
    cat_tabs = st.tabs(categories)
    
    for stock in stock_data:
        cat = str(stock.get('카테고리', '기타')).strip()
        tab_index = categories.index(cat)
        
        with cat_tabs[tab_index]:
            ticker_symbol = str(stock.get('티커', '')).strip()
            name = str(stock.get('종목명', '')).strip()
            desc = str(stock.get('설명', '')).strip()
            
            try:
                raw_price = get_price(ticker_symbol)
                if raw_price == 0.0: continue
                    
                is_korean = ticker_symbol.endswith('.KS') or ticker_symbol.endswith('.KQ')
                current_price = raw_price if is_korean else raw_price * exchange_rate
                price_text = f"{current_price:,.0f}원" if is_korean else f"${raw_price:,.2f} (약 {current_price:,.0f}원)"
                my_qty = owned_stocks.get(name.replace(" ", ""), 0.0)

                with st.expander(f"📦 {name} ({ticker_symbol}) - {desc}"):
                    st.write(f"📊 **실시간 1주 가격:** {price_text}")
                    st.write(f"💎 **내가 가진 수량:** {my_qty}주")
                    
                    sub_chart, sub_buy, sub_sell = st.tabs(["📈 차트 보기", "🛒 매수하기", "💰 매도하기"])
                    
                    with sub_chart:
                        chart_data = get_chart(ticker_symbol)
                        if chart_data is not None:
                            fig = go.Figure()
                            fig.add_trace(go.Scatter(
                                x=chart_data.index, y=chart_data['Close'], mode='lines',
                                line=dict(color='#00C4FF', width=3),
                                fill='tozeroy', fillcolor='rgba(0, 196, 255, 0.1)', name='주가'
                            ))
                            fig.update_layout(
                                xaxis_rangeslider_visible=False, dragmode="pan",
                                margin=dict(l=0, r=0, t=10, b=0), height=300, hovermode="x unified"
                            )
                            st.plotly_chart(fig, use_container_width=True, theme="streamlit")
                        else:
                            st.info("최근 차트 데이터가 없습니다.")
                            
                    with sub_buy:
                        buy_qty = st.number_input(f"살 수량", min_value=0.01, step=0.01, format="%.2f", key=f"b_{ticker_symbol}")
                        buy_cost = current_price * buy_qty
                        st.write(f"💸 **총 매수금액:** {buy_cost:,.0f}원") 
                        
                        if st.button(f"'{name}' 매수하기", key=f"btn_b_{ticker_symbol}"):
                            if current_cash >= buy_cost:
                                sheet_balance.update_cell(user_row_idx, 2, current_cash - buy_cost)
                                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                sheet_history.append_row([now, current_user, name, "매수", buy_qty, current_price])
                                st.success("🎉 매수 성공! 홈 화면에서 자산을 확인해 보세요.")
                                st.rerun()
                            else: st.error("❌ 현금이 부족해요!")

                    with sub_sell:
                        sell_qty = st.number_input(f"팔 수량", min_value=0.00, max_value=float(max(my_qty, 0.01)), step=0.01, format="%.2f", key=f"s_{ticker_symbol}")
                        sell_reward = current_price * sell_qty
                        st.write(f"💰 **총 매도금액:** {sell_reward:,.0f}원") 
                        
                        if st.button(f"'{name}' 매도하기", key=f"btn_s_{ticker_symbol}"):
                            if my_qty >= sell_qty and sell_qty > 0:
                                sheet_balance.update_cell(user_row_idx, 2, current_cash + sell_reward)
                                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                sheet_history.append_row([now, current_user, name, "매도", sell_qty, current_price])
                                st.success("🎉 매도 성공! 돈이 지갑으로 들어왔습니다.")
                                st.rerun()
                            else: st.error("❌ 팔 수 있는 주식이 부족하거나 수량이 잘못되었습니다.")
            except Exception as e: 
                st.error(f"{name} 데이터를 불러올 수 없습니다.")
else:
    st.warning("종목관리 시트에 기업을 추가해 주세요.")

st.divider()
if st.button("🔄 실시간 주가 새로고침", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
