import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
from datetime import datetime
import pandas as pd

st.set_page_config(page_title="딸아이의 투자 시뮬레이션", layout="centered")

# --- 1. 구글 시트 연결 ---
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('credentials.json', scopes=scopes)
client = gspread.authorize(creds)
spreadsheet = client.open("ASSET_Simulation")

sheet_balance = spreadsheet.worksheet("잔고")
sheet_stocks = spreadsheet.worksheet("종목관리")
sheet_history = spreadsheet.worksheet("투자내역")

balance_data = sheet_balance.get_all_records()
stock_data = sheet_stocks.get_all_records()
history_data = sheet_history.get_all_records()

current_cash = float(balance_data[0].get('현금잔액', 0)) if balance_data else 0
current_deposit = float(balance_data[0].get('예금잔액', 0)) if balance_data else 0

# --- 2. 환율 및 데이터 처리 함수 ---
@st.cache_data(ttl=600)
def get_exchange_rate():
    try:
        return float(yf.Ticker("USDKRW=X").fast_info['last_price'])
    except:
        return 1350.0
exchange_rate = get_exchange_rate()

def get_owned_stocks():
    owned = {}
    for row in history_data:
        name = str(row.get('종목명', '')).strip()
        
        # 🐛 버그 수정: 열 이름이 '종류(매수/매도)' 일 경우와 '종류' 일 경우 모두 대응
        kind = str(row.get('종류(매수/매도)', row.get('종류', ''))).strip()
        
        try:
            qty = float(row.get('수량', 0))
        except:
            qty = 0.0
            
        if kind == '매수':
            owned[name] = owned.get(name, 0) + qty
        elif kind == '매도':
            owned[name] = owned.get(name, 0) - qty
            
    return {k: round(v, 2) for k, v in owned.items() if round(v, 2) > 0}

owned_stocks = get_owned_stocks()

# --- 3. 앱 화면 그리기 ---
st.title("수민이의 첫 투자 시뮬레이션 🚀")

# 상단 자산 현황
col1, col2, col3 = st.columns(3)
col1.info(f"💰 현금: {current_cash:,.0f}원")
col2.success(f"🏦 예금: {current_deposit:,.0f}원")
col3.warning(f"💵 환율: {exchange_rate:,.2f}원")

st.divider()

tab_home, tab_market = st.tabs(["🏠 내 자산 관리", "🛒 주식 시장(투자하기)"])

# ==========================================
# [탭 1] 내 자산 관리 (포트폴리오 + 은행)
# ==========================================
with tab_home:
    st.subheader("📦 내가 보유한 주식")
    if owned_stocks:
        df_owned = pd.DataFrame(list(owned_stocks.items()), columns=['종목명', '보유 수량(주)'])
        st.dataframe(df_owned, hide_index=True, use_container_width=True)
    else:
        st.write("아직 산 주식이 없어요. 주식 시장에서 첫 투자를 시작해 보세요!")
        
    st.divider()
    
    # --- ✨ 은행(예금/출금) 기능 추가 ---
    st.subheader("🏦 우리집 은행 (예금/출금)")
    st.write("안전하게 이자를 받을 수 있는 예금 계좌입니다.")
    
    bank_col1, bank_col2 = st.columns(2)
    
    with bank_col1:
        with st.container(border=True):
            st.write("⬇️ **예금하기** (현금 ➡️ 예금)")
            deposit_amt = st.number_input("넣을 금액", min_value=0, max_value=int(current_cash), step=1000, key="dep_input")
            if st.button("예금 통장에 넣기", use_container_width=True):
                if deposit_amt > 0 and current_cash >= deposit_amt:
                    # 현금은 빼고, 예금은 더해서 시트 업데이트
                    sheet_balance.update_acell('A2', current_cash - deposit_amt)
                    sheet_balance.update_acell('B2', current_deposit + deposit_amt)
                    st.success(f"{deposit_amt:,}원 예금 완료!")
                    st.rerun()
                elif deposit_amt == 0:
                    st.error("금액을 입력해 주세요.")
                else:
                    st.error("현금이 부족해요!")
                    
    with bank_col2:
        with st.container(border=True):
            st.write("⬆️ **출금하기** (예금 ➡️ 현금)")
            withdraw_amt = st.number_input("뺄 금액", min_value=0, max_value=int(current_deposit), step=1000, key="with_input")
            if st.button("현금으로 빼기", use_container_width=True):
                if withdraw_amt > 0 and current_deposit >= withdraw_amt:
                    # 현금은 더하고, 예금은 빼서 시트 업데이트
                    sheet_balance.update_acell('A2', current_cash + withdraw_amt)
                    sheet_balance.update_acell('B2', current_deposit - withdraw_amt)
                    st.success(f"{withdraw_amt:,}원 출금 완료!")
                    st.rerun()
                elif withdraw_amt == 0:
                    st.error("금액을 입력해 주세요.")
                else:
                    st.error("예금 잔액이 부족해요!")

# ==========================================
# [탭 2] 주식 시장 (기존과 동일)
# ==========================================
with tab_market:
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
                    ticker_info = yf.Ticker(ticker_symbol)
                    raw_price = float(ticker_info.fast_info['last_price'])
                    is_korean = ticker_symbol.endswith('.KS') or ticker_symbol.endswith('.KQ')
                    current_price = raw_price if is_korean else raw_price * exchange_rate
                    price_text = f"{current_price:,.0f}원" if is_korean else f"${raw_price:,.2f} (약 {current_price:,.0f}원)"
                    my_qty = owned_stocks.get(name, 0.0)

                    with st.expander(f"📁 {name} ({ticker_symbol}) - {desc}"):
                        st.write(f"📊 **실시간 1주 가격:** {price_text}")
                        st.write(f"📦 **내 보유 수량:** {my_qty}주")
                        
                        sub_chart, sub_buy, sub_sell = st.tabs(["📈 차트", "🛒 매수", "💰 매도"])
                        
                        with sub_chart:
                            try:
                                hist = ticker_info.history(period="3mo")
                                if not hist.empty:
                                    chart_data = hist[['Close']].copy()
                                    chart_data.index = chart_data.index.tz_localize(None)
                                    st.line_chart(chart_data)
                                else:
                                    st.info("최근 차트 데이터가 없습니다.")
                            except Exception as e:
                                st.warning("차트를 그리는 중 문제가 발생했습니다.")
                                
                        with sub_buy:
                            buy_qty = st.number_input(f"살 수량", min_value=0.01, step=0.01, format="%.2f", key=f"b_{ticker_symbol}")
                            buy_cost = current_price * buy_qty
                            st.write(f"💸 **총 예상 금액:** {buy_cost:,.0f}원")
                            
                            if st.button(f"'{name}' 사기", key=f"btn_b_{ticker_symbol}"):
                                if current_cash >= buy_cost:
                                    sheet_balance.update_acell('A2', current_cash - buy_cost)
                                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    sheet_history.append_row([now, name, "매수", buy_qty, current_price])
                                    st.success("매수 완료!")
                                    st.rerun()
                                else:
                                    st.error("현금이 부족해요!")

                        with sub_sell:
                            sell_qty = st.number_input(f"팔 수량", min_value=0.00, max_value=float(max(my_qty, 0.01)), step=0.01, format="%.2f", key=f"s_{ticker_symbol}")
                            sell_reward = current_price * sell_qty
                            st.write(f"💰 **총 예상 수익:** {sell_reward:,.0f}원")
                            
                            if st.button(f"'{name}' 팔기", key=f"btn_s_{ticker_symbol}"):
                                if my_qty >= sell_qty and sell_qty > 0:
                                    sheet_balance.update_acell('A2', current_cash + sell_reward)
                                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    sheet_history.append_row([now, name, "매도", sell_qty, current_price])
                                    st.success("매도 완료!")
                                    st.rerun()
                                else:
                                    st.error("수량을 확인하세요!")
                except Exception as e:
                    st.error(f"{name} 데이터를 불러올 수 없습니다.")

st.divider()
if st.button("🔄 화면 새로고침"):
    st.rerun()
