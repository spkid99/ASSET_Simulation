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

# 💡 탭 이름 변경 및 '특별 우대금리 지급' 탭 추가
tab_money, tab_interest, tab_user, tab_shop, tab_stock_manage, tab_sys = st.tabs([
    "💰 투자 지원금 지급", "📈 특별 우대금리 지급", "👤 유저 관리", "📦 상점 물류", "📦 종목 마스터 관리", "⚙️ 시스템 제어"
])

with tab_money:
    st.subheader("🎁 투자 지원금 지급 (시드머니 주입)")
    if not users_list: st.info("유저가 없습니다.")
    else:
