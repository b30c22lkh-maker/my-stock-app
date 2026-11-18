import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import time

st.set_page_config(page_title="美股價值選股與量化看盤系統 Ultimate", page_icon="🚀", layout="wide")

st.title("🚀 美股龍頭深度價值選股與量化看盤系統 (Ultimate 版)")
st.markdown("採用**抗封鎖穩定引擎**，結合**華爾街目標價空間**、**自由現金流防雷**與**三層技術指標圖表**。")

DEFAULT_TICKERS = [
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'AMZN', 'TSLA', 'AVGO', 'ORCL', 'CRM',
    'ADBE', 'AMD', 'QCOM', 'TXN', 'INTC', 'IBM', 'CSCO', 'NOW', 'INTU', 'AMAT',
    'MU', 'LRCX', 'KLAC', 'ADI', 'PANW', 'SNPS', 'CDNS', 'NFLX', 'DIS', 'CMCSA',
    'VZ', 'T', 'TMUS', 'BRK-B', 'JPM', 'V', 'MA', 'BAC', 'WFC', 'GS', 'MS', 'BLK',
    'C', 'AXP', 'SPGI', 'CB', 'MMC', 'PGR', 'SCHW', 'PYPL', 'COF', 'USB', 'PNC',
    'LLY', 'UNH', 'JNJ', 'ABBV', 'MRK', 'TMO', 'ABT', 'DHR', 'PFE', 'AMGN',
    'ISRG', 'SYK', 'BSX', 'VRTX', 'REGN', 'GILD', 'BMY', 'CVS', 'CI', 'ELV',
    'WMT', 'PG', 'COST', 'KO', 'PEP', 'MCD', 'NKE', 'SBUX', 'HD', 'LOW',
    'TGT', 'PM', 'MO', 'CL', 'MDLZ', 'KMB', 'GIS', 'EL', 'LULU', 'BKNG',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'CAT', 'DE', 'UNP', 'UPS', 'HON',
    'GE', 'RTX', 'LMT', 'BA', 'MMM', 'ETN', 'NEE', 'DUK', 'SO', 'PLD'
]

def fetch_single_stock(symbol):
    for attempt in range(2):
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
            if not price:
                time.sleep(0.5)
                continue
            pe = info.get('trailingPE')
            f_pe = info.get('forwardPE')
            peg = info.get('pegRatio')
            roe = info.get('returnOnEquity')
            de = info.get('debtToEquity')
            high_52w = info.get('fiftyTwoWeekHigh')
            sma_200 = info.get('twoHundredDayAverage')
            div_yield = info.get('dividendYield')
            target_price = info.get('targetMeanPrice')
            fcf = info.get('freeCashflow')
            
            roe_pct = round(roe * 100, 2) if roe is not None else None
            drop_from_high = round(((high_52w - price) / high_52w) * 100, 2) if (high_52w and price) else None
            upside_pct = round(((target_price - price) / price) * 100, 2) if (target_price and price) else None
            above_sma200 = "是" if (price and sma_200 and price > sma_200) else "否"
            fcf_positive = "正現金流" if (fcf and fcf > 0) else "負/無數據"
            
            return {
                '股票代號': symbol,
                '公司名稱': info.get('shortName', symbol),
                '產業': info.get('sector', '其他'),
                '目前股價': round(price, 2),
                '華爾街目標價': round(target_price, 2) if target_price else None,
                '潛在上漲空間 (%)': upside_pct,
                '本益比 (P/E)': round(pe, 2) if pe else None,
                '預估本益比': round(f_pe, 2) if f_pe else None,
                'PEG': round(peg, 2) if peg else None,
                'ROE (%)': roe_pct,
                '負債比 (D/E)': round(de, 2) if de is not None else 0,
                '自由現金流': fcf_positive,
                '殖利率 (%)': round(div_yield, 2) if div_yield is not None else 0,
                '距52週高點跌幅 (%)': drop_from_high,
                '站上200日年線': above_sma200
            }
        except Exception:
            time.sleep(0.5)
    return None

@st.cache_data(ttl=3600, show_spinner=False)
def load_all_stocks(ticker_list):
    with st.spinner("⚡ 正在從市場安全載入 113 檔龍頭財報數據（首次載入約需 15～20 秒）..."):
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(fetch_single_stock, ticker_list))
    valid_results = [r for r in results if r is not None]
    return pd.DataFrame(valid_results)

with st.sidebar:
    st.header("🎛️ 選股控制台")
    custom_input = st.text_input("🔍 額外加入觀察代號（用逗號分隔）", placeholder="例如: TSM, PLTR, KO")
    custom_tickers = [t.strip().upper() for t in custom_input.split(",") if t.strip()]
    all_tickers = list(dict.fromkeys(DEFAULT_TICKERS + custom_tickers))
    
    if st.button("🔄 強制刷新最新報價", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
        
    st.divider()
    st.subheader("1️⃣ 估值與成長門檻")
    max_pe = st.slider("本益比上限 (P/E)", 5, 60, 25)
    min_upside = st.slider("分析師目標價最低上漲空間 (%)", -20, 50, 5)
    
    st.subheader("2️⃣ 體質與安全邊際")
    min_roe = st.slider("最低 ROE 要求 (%)", 0, 50, 15)
    max_de = st.slider("負債比上限 (D/E %)", 0, 300, 150)
    min_drop = st.slider("距 52 週高點至少回檔 (%)", 0, 50, 5)
    min_yield = st.slider("最低股息殖利率 (%)", 0.0, 8.0, 0.0, step=0.5)
    
    st.subheader("3️⃣ 進階過濾")
    only_pos_fcf = st.checkbox("僅顯示「正自由現金流」企業", value=False)
    only_above_sma200 = st.checkbox("僅顯示「站上 200 日年線」企業", value=False)

df = load_all_stocks(all_tickers)

if df.empty or '產業' not in df.columns:
    st.error("⚠️ Yahoo Finance 暫時限制了雲端伺服器的數據請求，請點擊左側「🔄 強制刷新最新報價」或稍等 1 分鐘後重新整理網頁。")
    st.stop()

with st.sidebar:
    all_sectors = sorted(df['產業'].dropna().unique().tolist())
    selected_sectors = st.multiselect("篩選產業類別", all_sectors, default=all_sectors)

filtered_df = df[
    (df['本益比 (P/E)'].notna()) &
    (df['本益比 (P/E)'] > 0) &
    (df['本益比 (P/E)'] <= max_pe) &
    (df['ROE (%)'].notna()) &
    (df['ROE (%)'] >= min_roe) &
    (df['負債比 (D/E)'] <= max_de) &
    (df['距52週高點跌幅 (%)'].notna()) &
    (df['距52週高點跌幅 (%)'] >= min_drop) &
    (df['殖利率 (%)'] >= min_yield) &
    (df['產業'].isin(selected_sectors))
]

if min_upside > -20:
    filtered_df = filtered_df[filtered_df['潛在上漲空間 (%)'].notna() & (filtered_df['潛在上漲空間 (%)'] >= min_upside)]
if only_pos_fcf:
    filtered_df = filtered_df[filtered_df['自由現金流'] == "正現金流"]
if only_above_sma200:
    filtered_df = filtered_df[filtered_df['站上200日年線'] == "是"]

filtered_df = filtered_df.sort_values(by='潛在上漲空間 (%)', ascending=False)

c1, c2, c3, c4 = st.columns(4)
c1.metric("掃描企業總數", f"{len(df)} 檔")
c2.metric("符合條件精選股", f"{len(filtered_df)} 檔")
avg_roe = round(filtered_df['ROE (%)'].mean(), 1) if len(filtered_df) > 0 else 0
c3.metric("平均 ROE", f"{avg_roe} %")
avg_upside = round(filtered_df['潛在上漲空間 (%)'].mean(), 1) if len(filtered_df) > 0 else 0
c4.metric("平均目標價空間", f"+{avg_upside} %")

st.subheader("📋 精選價值候選股名單（預設依華爾街目標價上漲空間排序）")
st.dataframe(filtered_df, use_container_width=True, hide_index=True)

output = BytesIO()
with pd.ExcelWriter(output, engine='openpyxl') as writer:
    filtered_df.to_excel(writer, sheet_name='精選價值股', index=False)
    df.to_excel(writer, sheet_name='全市場掃描數據', index=False)

st.download_button(
    label="📥 下載 Excel 量化分析報表",
    data=output.getvalue(),
    file_name=f"美股量化價值選股_PE{max_pe}_ROE{min_roe}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary"
)

st.divider()
st.subheader("📊 專業技術面買點確認（布林通道、雙均線、成交量與 RSI 曲線）")

chart_options = filtered_df['股票代號'].tolist() if len(filtered_df) > 0 else sorted(df['股票代號'].tolist())
selected_symbol = st.selectbox("請選擇要深度分析走勢的股票代號：", chart_options)

if selected_symbol:
    hist = yf.Ticker(selected_symbol).history(period="1y")
    if not hist.empty:
        hist['SMA20'] = hist['Close'].rolling(window=20).mean()
        hist['STD20'] = hist['Close'].rolling(window=20).std()
        hist['BB_Upper'] = hist['SMA20'] + (hist['STD20'] * 2)
        hist['BB_Lower'] = hist['SMA20'] - (hist['STD20'] * 2)
        hist['SMA50'] = hist['Close'].rolling(window=50).mean()
        hist['SMA200'] = hist['Close'].rolling(window=200).mean()
        
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        hist['RSI'] = 100 - (100 / (1 + rs))
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.65, 0.17, 0.18], subplot_titles=(f"{selected_symbol} 股價、均線與布林通道", "每日成交量", "RSI (14日) 相對強弱指標"))
        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='日K線'), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist.index, y=hist['BB_Upper'], mode='lines', name='布林上軌', line=dict(color='rgba(150, 150, 150, 0.5)', dash='dot')), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist.index, y=hist['BB_Lower'], mode='lines', name='布林下軌', line=dict(color='rgba(150, 150, 150, 0.5)', dash='dot'), fill='tonexty', fillcolor='rgba(150, 150, 150, 0.08)'), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA50'], mode='lines', name='50日季線', line=dict(color='orange', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA200'], mode='lines', name='200日年線', line=dict(color='blue', width=2)), row=1, col=1)
        fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], name='成交量', marker_color='rgba(100, 149, 237, 0.6)'), row=2, col=1)
        fig.add_trace(go.Scatter(x=hist.index, y=hist['RSI'], mode='lines', name='RSI (14)', line=dict(color='purple', width=1.5)), row=3, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
        fig.update_layout(xaxis_rangeslider_visible=False, height=750, template="plotly_white", showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

# END OF APP
