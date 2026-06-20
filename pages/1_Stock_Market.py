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
prices_1m_cache = st.session_state.get('prices_1m_ago', {})

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
    
    # 💡 [핵심 구현] 기존 카테고리 리스트 제일 앞에 요약판 탭 명칭 결합!
    tabs_list = ["📊 종목별 1달 전 대비 수익률 요약"] + categories
    cat_tabs = st.tabs(tabs_list)
    
    # ------------------ 💡 탭 0 : 대망의 전 종목 수익률 요약판 ------------------
    with cat_tabs[0]:
        st.subheader("📊 주식 종목별 최근 1달간의 상승/하락 현황")
        st.caption("가장 최근에 시장에서 힘이 강했던 종목이 무엇인지 한눈에 트렌드를 비교해 보세요.")
        
        summary_rows = []
        for stock in stock_data:
            name = str(stock.get('종목명', '')).strip()
            ticker = str(stock.get('티커', '')).strip()
            is_korean = ticker.endswith('.KS') or ticker.endswith('.KQ')
            
            db_price = float(stock.get('현재가', 0)) if stock.get('현재가') else 0.0
            price_now = db_price if db_price > 0 else prices_cache.get(ticker, 0.0)
            
            db_price_1m = float(stock.get('한달전주가', 0)) if stock.get('한달전주가') else 0.0
            price_1m = db_price_1m if db_price_1m > 0 else prices_1m_cache.get(ticker, 0.0)
            
            if price_now > 0 and price_1m > 0:
                ret_rate = ((price_now - price_1m) / price_1m) * 100
                
                # 원화 환산 가격 계산
                won_price_now = price_now if is_korean else price_now * exchange_rate
                won_price_1m = price_1m if is_korean else price_1m * exchange_rate
                
                summary_rows.append({
                    "종목명": name,
                    "티커": ticker,
                    "1달 전 주가(원)": round(won_price_1m),
                    "현재 주가(원)": round(won_price_now),
                    "최근 1달 수익률": round(ret_rate, 2)
                })
        
        if summary_rows:
            df_sum = pd.DataFrame(summary_rows)
            # 수익률이 가장 높은 대장주 순서대로 보기 좋게 내림차순 정렬
            df_sum = df_sum.sort_values(by="최근 1달 수익률", ascending=False)
            
            try:
                def style_1m_profit(val):
                    return f"color: {'#ff4b4b' if val > 0 else '#0083ff' if val < 0 else 'black'}; font-weight: bold;"
                
                styled_sum = df_sum.style.format({
                    '1달 전 주가(원)': '{:,.0f}', 
                    '현재 주가(원)': '{:,.0f}', 
                    '최근 1달 수익률': '{:+.2f}%'
                }).map(style_1m_profit, subset=['최근 1달 수익률'])
                
                st.dataframe(styled_sum, hide_index=True, use_container_width=True)
            except:
                st.dataframe(df_sum, hide_index=True, use_container_width=True)
        else:
            st.info("비교 분석할 수 있는 주가 정보가 없습니다. 관리자 모드에서 주가 동기화를 실행해 주세요.")
            
    # ------------------ 기존 카테고리별 주식 상세 매수/매도 탭 ------------------
    for stock in stock_data:
        cat = str(stock.get('카테고리', '기타')).strip()
        tab_index = categories.index(cat) + 1 # 첫 번째 탭이 요약판이므로 인덱스를 +1 시켜줍니다.
        
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
