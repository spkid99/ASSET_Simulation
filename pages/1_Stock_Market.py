import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go  # ✨ 화려한 캔들 차트를 위한 도구 추가

st.set_page_config(page_title="주식 시장", layout="centered")

# --- 🚀 [속도 최적화 캐시] 차트 데이터 범위 확장 ---
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
        hist = yf.Ticker(ticker).history(period="3mo")
        if not hist.empty:
            # 📊 캔들 차트를 그리기 위해 Open, High, Low, Close 정보를 모두 가져옵니다.
            chart_data = hist[['Open', 'High', 'Low', 'Close']].copy()
            chart_data.index = chart_data.index.tz_localize(None)
            return chart_data
    except: return None
    return None

# --- 구글 시트 연결 ---
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
client = gspread.authorize(creds)
spreadsheet = client.open("ASSET_Simulation")

sheet_balance = spreadsheet.worksheet("잔고")
sheet_stocks = spreadsheet.worksheet("종목관리")
sheet_history = spreadsheet.worksheet("투자내역")

balance_data = sheet_balance.get_all_records()
stock_data = sheet_stocks.get_all_records()
history_data = sheet_history.get_all_records()

current_cash = float(balance_data[0].get('현금잔액', 0)) if balance_data else 0
exchange_rate = get_exchange_rate()

def get_owned_stocks():
    owned = {}
    for row in history_data:
        name = str(row.get('종목명', '')).strip()
        kind = str(row.get('종류(매수/매도)', row.get('종류', ''))).strip()
        try: qty = float(row.get('수량', 0))
        except: qty = 0.0
        if kind == '매수': owned[name] = owned.get(name, 0) + qty
        elif kind == '매도': owned[name] = owned.get(name, 0) - qty
    return {k: round(v, 2) for k, v in owned.items() if round(v, 2) > 0}

owned_stocks = get_owned_stocks()

st.title("🛒 주식 시장 (투자하기)")
st.info(f"💰 현재 투자 가능한 현금: {current_cash:,.0f}원 | 💵 환율: {exchange_rate:,.2f}원")

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
                my_qty = owned_stocks.get(name, 0.0)

                with st.expander(f"📁 {name} ({ticker_symbol}) - {desc}"):
                    st.write(f"📊 **실시간 1주 가격:** {price_text}")
                    st.write(f"📦 **내 보유 수량:** {my_qty}주")
                    
                    sub_chart, sub_buy, sub_sell = st.tabs(["📈 차트", "🛒 매수", "💰 매도"])
                    
                    # --- 📈 캔들 차트 구현 파트 ---
                    with sub_chart:
                        chart_data = get_chart(ticker_symbol)
                        if chart_data is not None:
                            # Plotly를 이용해 빨간/파란 봉 차트 그리기
                            fig = go.Figure(data=[go.Candlestick(
                                x=chart_data.index,
                                open=chart_data['Open'],
                                high=chart_data['High'],
                                low=chart_data['Low'],
                                close=chart_data['Close'],
                                increasing_line_color='red',   # 상승은 빨간색 봉
                                decreasing_line_color='blue'   # 하락은 파란색 봉
                            )])
                            
                            # 차트 레이아웃 깔끔하게 다듬기
                            fig.update_layout(
                                xaxis_rangeslider_visible=False, # 하단 조절 바 숨겨서 깔끔하게
                                margin=dict(l=10, r=10, t=10, b=10), # 여백 줄이기
                                height=300 # 차트 높이 고정
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("최근 차트 데이터가 없습니다.")
                            
                    with sub_buy:
                        buy_qty = st.number_input(f"살 수량", min_value=0.01, step=0.01, format="%.2f", key=f"b_{ticker_symbol}")
                        buy_cost = current_price * buy_qty
                        st.write(f"💸 **총 매수금액:** {buy_cost:,.0f}원") 
                        
                        if st.button(f"'{name}' 사기", key=f"btn_b_{ticker_symbol}"):
                            if current_cash >= buy_cost:
                                sheet_balance.update_acell('A2', current_cash - buy_cost)
                                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                sheet_history.append_row([now, name, "매수", buy_qty, current_price])
                                st.success("매수 완료!")
                                st.rerun()
                            else: st.error("현금이 부족해요!")

                    with sub_sell:
                        sell_qty = st.number_input(f"팔 수량", min_value=0.00, max_value=float(max(my_qty, 0.01)), step=0.01, format="%.2f", key=f"s_{ticker_symbol}")
                        sell_reward = current_price * sell_qty
                        st.write(f"💰 **총 매도금액:** {sell_reward:,.0f}원") 
                        
                        if st.button(f"'{name}' 팔기", key=f"btn_s_{ticker_symbol}"):
                            if my_qty >= sell_qty and sell_qty > 0:
                                sheet_balance.update_acell('A2', current_cash + sell_reward)
                                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                sheet_history.append_row([now, name, "매도", sell_qty, current_price])
                                st.success("매도 완료!")
                                st.rerun()
                            else: st.error("수량을 확인하세요!")
            except Exception as e: 
                st.error(f"{name} 데이터를 불러올 수 없습니다.")
else:
    st.warning("종목관리 시트에 기업을 추가해 주세요.")

st.divider()
if st.button("🔄 실시간 주가 새로고침"):
    st.cache_data.clear()
    st.rerun()
