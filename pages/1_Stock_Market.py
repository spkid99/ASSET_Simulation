import streamlit as st
from supabase import create_client, Client
import yfinance as yf
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="주식 시장", layout="centered")

if "user_id" not in st.session_state or not st.session_state.user_id:
    st.warning("👤 먼저 메인 홈 화면(app.py)에서 이름을 입력하고 로그인해 주세요!")
    st.stop()

current_user = st.session_state.user_id

if "db_loaded" not in st.session_state or not st.session_state.db_loaded:
    st.warning("💡 먼저 메인 홈 화면(app.py)에서 자산을 한 번 불러와주세요!")
    st.stop()

@st.cache_resource(ttl=3600)
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

balance_data = st.session_state.balance_data
stock_data = st.session_state.stock_data
history_data = st.session_state.history_data
prices_cache = st.session_state.prices

exchange_rate = st.session_state.get('exchange_rate', 1350.0)
if pd.isna(exchange_rate) or exchange_rate <= 0:
    exchange_rate = 1350.0

current_cash = 0.0
for row in balance_data:
    if str(row.get('사용자', '')).strip() == current_user:
        current_cash = float(row.get('현금잔액', 0))
        break

def get_owned_stocks():
    owned = {}
    for row in history_data:
        if str(row.get('사용자', '')).strip() != current_user: continue
        name = str(row.get('종목명', '')).replace(" ", "")
        kind = str(row.get('종류', row.get('종류(매수/매도)', ''))).strip()
        try: qty = float(row.get('수량', 0))
        except: qty = 0.0
        if kind == '매수': owned[name] = owned.get(name, 0) + qty
        elif kind == '매도': owned[name] = owned.get(name, 0) - qty
    return {k: round(v, 4) for k, v in owned.items() if round(v, 4) > 0}

owned_stocks = get_owned_stocks()

st.title("✨ 주식 시장 (투자하기)")
st.info(f"👤 **{current_user}**님 ➡️ 💰 사용 가능한 현금: {current_cash:,.0f}원 | 💱 현재 적용 환율: {exchange_rate:,.2f}원")

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
            news_text = str(stock.get('최근뉴스', '')).strip() 
            news_eval = str(stock.get('뉴스평가', '')).strip()
            
            db_price = float(stock.get('현재가', 0)) if stock.get('현재가') else 0.0
            raw_price = db_price if db_price > 0 else prices_cache.get(ticker_symbol, 0.0)
            
            is_korean = ticker_symbol.endswith('.KS') or ticker_symbol.endswith('.KQ')
            
            if raw_price == 0.0:
                price_text = "⚠️ 주가 데이터 확인 필요 (부모님 모드에서 업데이트 해주세요)"
                current_price = 0.0
            else:
                current_price = raw_price if is_korean else raw_price * exchange_rate
                price_text = f"{current_price:,.0f}원" if is_korean else f"${raw_price:,.2f} (약 {current_price:,.0f}원)"
                
            my_qty = round(owned_stocks.get(name.replace(" ", ""), 0.0), 4)

            with st.expander(f"📦 {name} ({ticker_symbol}) - {desc}"):
                if news_text:
                    icon = "🔴" if news_eval == '호재' else "🔵" if news_eval == '악재' else "🟡" if news_eval == '중립' else "📰"
                    st.success(f"{icon} **최근 뉴스:** {news_text}")
                    
                st.write(f"📊 **실시간 1주 가격:** {price_text}")
                st.write(f"💎 **내가 가진 수량:** {my_qty}주")
                
                sub_buy, sub_sell, sub_chart = st.tabs(["🛒 매수하기", "💰 매도하기", "📈 차트 보기(느림주의)"])
                
                with sub_buy:
                    if raw_price == 0.0:
                        st.error("주가 데이터가 없어 매수 기능이 차단되었습니다.")
                    else:
                        buy_qty = st.number_input(f"살 수량", min_value=0.01, step=0.01, format="%.2f", key=f"b_{ticker_symbol}")
                        buy_cost = current_price * buy_qty
                        st.write(f"💸 **총 매수금액:** {buy_cost:,.0f}원") 
                        
                        if st.button(f"'{name}' 매수하기", key=f"btn_b_{ticker_symbol}"):
                            if current_cash >= buy_cost:
                                supabase = init_connection()
                                supabase.table("balance").update({"현금잔액": current_cash - buy_cost}).eq("사용자", current_user).execute()
                                supabase.table("history").insert({
                                    "시간": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "사용자": current_user, "종목명": name, "종류": "매수", "수량": buy_qty, "가격": current_price
                                }).execute()
                                
                                # 💡 [핵심 해결책] 쫓아내지 않고 그 자리에서 즉시 수파베이스 데이터를 새로고침합니다!
                                st.session_state.balance_data = supabase.table("balance").select("*").execute().data
                                st.session_state.history_data = supabase.table("history").select("*").execute().data
                                
                                st.success("🎉 매수 성공! 현금과 주식 수량이 즉시 업데이트되었습니다.")
                                st.rerun()
                            else: st.error("❌ 현금이 부족해요!")

                with sub_sell:
                    if raw_price == 0.0:
                        st.error("주가 데이터가 없어 매도 기능이 차단되었습니다.")
                    else:
                        sell_qty = st.number_input(f"팔 수량", min_value=0.00, max_value=float(max(my_qty, 0.01)), step=0.01, format="%.2f", key=f"s_{ticker_symbol}")
                        sell_reward = current_price * sell_qty
                        st.write(f"💰 **총 매도금액:** {sell_reward:,.0f}원") 
                        
                        if st.button(f"'{name}' 매도하기", key=f"btn_s_{ticker_symbol}"):
                            if my_qty >= sell_qty and sell_qty > 0:
                                supabase = init_connection()
                                supabase.table("balance").update({"현금잔액": current_cash + sell_reward}).eq("사용자", current_user).execute()
                                supabase.table("history").insert({
                                    "시간": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "사용자": current_user, "종목명": name, "종류": "매도", "수량": sell_qty, "가격": current_price
                                }).execute()
                                
                                # 💡 [핵심 해결책] 쫓아내지 않고 그 자리에서 즉시 수파베이스 데이터를 새로고침합니다!
                                st.session_state.balance_data = supabase.table("balance").select("*").execute().data
                                st.session_state.history_data = supabase.table("history").select("*").execute().data
                                
                                st.success("🎉 매도 성공! 지갑에 현금이 즉시 입금되었습니다.")
                                st.rerun()
                            else: st.error("❌ 주식이 부족합니다.")
                            
                with sub_chart:
                    st.caption("주의: 차트는 인터넷 망 상황에 따라 로딩 속도가 조금 느릴 수 있습니다.")
                    if raw_price == 0.0:
                        st.info("현재 임시 모드 상태이므로 차트를 일시적으로 표시할 수 없습니다.")
                    else:
                        try:
                            hist = yf.Ticker(ticker_symbol).history(period="1y")
                            if not hist.empty:
                                fig = go.Figure()
                                fig.add_trace(go.Scatter(x=hist.index.tz_localize(None), y=hist['Close'], mode='lines', line=dict(color='#00C4FF', width=3), fill='tozeroy', fillcolor='rgba(0, 196, 255, 0.1)'))
                                fig.update_layout(xaxis_rangeslider_visible=False, dragmode="pan", margin=dict(l=0, r=0, t=10, b=0), height=300)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                st.info("차트 데이터가 비어있습니다.")
                        except:
                            st.info("차트를 불러오는 도중 통신 지연이 발생했습니다.")
