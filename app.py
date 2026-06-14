import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="우리 딸의 첫 투자", layout="centered")

@st.cache_data(ttl=600)
def get_exchange_rate():
    try: return float(yf.Ticker("USDKRW=X").fast_info['last_price'])
    except: return 1350.0

# --- 구글 시트 연결 ---
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
client = gspread.authorize(creds)
spreadsheet = client.open("ASSET_Simulation")

sheet_balance = spreadsheet.worksheet("잔고")
sheet_history = spreadsheet.worksheet("투자내역")

balance_data = sheet_balance.get_all_records()
history_data = sheet_history.get_all_records()

current_cash = float(balance_data[0].get('현금잔액', 0)) if balance_data else 0
current_deposit = float(balance_data[0].get('예금잔액', 0)) if balance_data else 0
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

# --- 화면 구성 ---
st.title("우리 딸의 첫 투자 시뮬레이션 🚀")
st.write("가장 안전하고 재미있게 자산을 키워나가는 대시보드입니다.")

st.divider()

# 자산 현황 요약
st.subheader("📋 우리집 자산 요약")
col1, col2, col3 = st.columns(3)
col1.metric(label="💰 내 지갑 현금", value=f"{current_cash:,.0f}원")
col2.metric(label="🏦 은행 예금 잔액", value=f"{current_deposit:,.0f}원")
col3.metric(label="💵 현재 기준 환율", value=f"{exchange_rate:,.2f}원")

st.divider()

# 보유 주식 포트폴리오
st.subheader("📦 내가 보유한 주식 목록")
if owned_stocks:
    df_owned = pd.DataFrame(list(owned_stocks.items()), columns=['종목명', '보유 수량(주)'])
    st.dataframe(df_owned, hide_index=True, use_container_width=True)
else:
    st.write("아직 보유한 주식이 없어요. 왼쪽 메뉴의 'Stock Market'에서 첫 주식을 사보세요!")

st.sidebar.success("원하는 메뉴를 위에서 선택해 주세요!")
