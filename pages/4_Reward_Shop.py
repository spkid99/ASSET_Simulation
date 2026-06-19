import streamlit as st
from supabase import create_client, Client
import yfinance as yf
from datetime import datetime
import pandas as pd

st.set_page_config(page_title="포인트 상점", layout="centered")

if "user_id" not in st.session_state or not st.session_state.user_id:
    st.warning("👤 먼저 메인 홈 화면(app.py)에서 로그인해 주세요!")
    st.stop()

current_user = st.session_state.user_id

# --- 🚀 철통 방어 캐시 ---
@st.cache_data(ttl=600)
def get_exchange_rate():
    try: 
        rate = float(yf.Ticker("USDKRW=X").fast_info['last_price'])
        return 1350.0 if pd.isna(rate) else rate
    except: return 1350.0

@st.cache_data(ttl=300)
def get_price(ticker):
    if not ticker: return 0.0
    try: 
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if not hist.empty: 
            val = float(hist['Close'].iloc[-1])
            if not pd.isna(val) and val > 0: return val
        if hasattr(t, 'fast_info') and 'last_price' in t.fast_info: 
            val = float(t.fast_info['last_price'])
            if not pd.isna(val) and val > 0: return val
        return 0.0
    except: return 0.0

@st.cache_resource(ttl=3600)
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- 📊 Supabase에서 실시간 데이터 로드 ---
try:
    balance_data = supabase.table("balance").select("*").execute().data
    history_data = supabase.table("history").select("*").execute().data
    stock_data = supabase.table("stocks").select("*").execute().data
    shop_items = supabase.table("shop_items").select("*").execute().data
    purchase_values = supabase.table("purchases").select("*").execute().data
except Exception as e:
    st.error("데이터베이스 연결에 문제가 발생했습니다. 잠시 후 다시 시도해주세요.")
    st.stop()

exchange_rate = get_exchange_rate()
ticker_map = {str(r.get('종목명', r.get('종목명', ''))).replace(" ", ""): str(r.get('티커', r.get('티커', ''))).strip() for r in stock_data}

# --- 🔍 자산 및 가용 수익금 계산 ---
current_cash, current_deposit, initial_capital = 0.0, 0.0, 1000000.0
for row in balance_data:
    u_name = str(row.get('사용자', row.get('사용자', ''))).strip()
    if u_name == current_user:
        current_cash = float(row.get('현금잔액', row.get('현금잔액', 0)))
        current_deposit = float(row.get('예금잔액', row.get('예금잔액', 0)))
        initial_capital = float(row.get('초기자본금', row.get('초기자본금', 1000000)))
        break

portfolio = {}
for row in history_data:
    u_name = str(row.get('사용자', row.get('사용자', ''))).strip()
    if u_name != current_user: continue
    name = str(row.get('종목명', row.get('종목명', ''))).replace(" ", "")
    kind = str(row.get('종류', row.get('종류', '매수'))).strip()
    try: qty = float(row.get('수량', row.get('수량', 0)))
    except: qty = 0.0
    if kind == '매수': portfolio[name] = portfolio.get(name, 0) + qty
    elif kind == '매도': portfolio[name] = portfolio.get(name, 0) - qty

total_stock_value = 0.0
for name, qty in portfolio.items():
    if qty <= 0: continue
    ticker = ticker_map.get(name, "")
    if ticker:
        raw_price = get_price(ticker)
        if raw_price == 0.0 and 'prices' in st.session_state:
            raw_price = st.session_state.prices.get(ticker, 0.0)
            
        is_korean = ticker.endswith('.KS') or ticker.endswith('.KQ')
        total_stock_value += (raw_price if is_korean else raw_price * exchange_rate) * qty

total_asset = current_cash + current_deposit + total_stock_value
available_profit = max(total_asset - initial_capital, 0)

# --- 🎟️ 내 쿠폰지갑 데이터 가공 ---
user_coupons = []
for row in purchase_values:
    u_name = str(row.get('사용자', row.get('사용자', ''))).strip()
    if u_name == current_user:
        user_coupons.append({
            'id': row.get('id'),
            '시간': row.get('시간', row.get('시간', '')),
            '상품명': row.get('상품명', row.get('상품명', '')),
            '결제금액': row.get('결제금액', row.get('결제금액', 0)),
            '상태': row.get('상태', row.get('상태', '사용전'))
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
            # 💡 [핵심 해결책] 대문자든 소문자든 이름표를 다 찾아오도록 보완!
            img_url = item.get('이미지URL', item.get('이미지url', ''))
            img_url = str(img_url).strip() if img_url else ""
            
            name = str(item.get('상품명', item.get('상품명', '이름 없음'))).strip()
            
            price_val = item.get('가격', item.get('가격', 0))
            try: price = float(price_val)
            except: price = 0.0
                
            desc = str(item.get('설명', item.get('설명', ''))).strip()
            
            with cols[idx % 2]:
                with st.container(border=True):
                    if img_url and img_url.lower() != 'nan':
                        try: st.image(img_url, use_container_width=True)
                        except: st.caption("🖼️ 이미지를 불러올 수 없습니다.")
                    else:
                        st.caption("🖼️ 등록된 이미지가 없습니다.")
                        
                    st.subheader(name)
                    st.write(f"**가격: {price:,.0f}원**")
                    st.caption(desc)
                    
                    if st.button(f"구매하기", key=f"buy_{idx}", use_container_width=True):
                        if available_profit < price: 
                            st.error("❌ 쓸 수 있는 수익금이 부족해요!")
                        elif current_cash < price: 
                            st.error("❌ 지갑에 실물 현금이 부족합니다. 주식을 일부 매도해 주세요.")
                        else:
                            supabase.table("balance").update({"현금잔액": current_cash - price}).eq("사용자", current_user).execute()
                            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            supabase.table("purchases").insert({
                                "시간": now_str, "사용자": current_user, "상품명": name, "결제금액": price, "상태": "사용전"
                            }).execute()
                            
                            st.session_state.db_loaded = False
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
                            supabase.table("purchases").update({"상태": "사용완료"}).eq("id", cp['id']).execute()
                            st.success("쿠폰을 사용 처리했습니다! 부모님께 선물을 요청하세요.")
                            st.rerun()
                    else:
                        st.button(f"✅ {cp['상태']}", disabled=True, key=f"done_{c_idx}", use_container_width=True)
