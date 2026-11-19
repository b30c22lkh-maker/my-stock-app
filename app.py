import streamlit as st
import yfinance as yf
from yfinance import EquityQuery
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import time

st.set_page_config(page_title="全美優質潛力股與 VCP 型態量化系統", page_icon="🎯", layout="wide")

st.title("🎯 全美優質潛力股與 VCP 型態量化篩選系統")
st.markdown("全市場掃描（不限市值、**股價強制 ≥ $15**），結合**財務穩健度**、**成長潛力**與**量化 VCP 波動率收縮偵測**。")

# 1. 全市場雲端初篩（撈出全美股價 >= $15、流動性充足且有獲利的潛力池）
@st.cache_data(ttl=3600, show_spinner=False)
def get_market_candidates(cap_filter):
    conditions = [
        EquityQuery('eq', ['region', 'us']),
        EquityQuery('gt', ['intradayprice', 15]),         # 強制所有股價 15 元以上
        EquityQuery('gt', ['avgdailyvol3m', 300000]),     # 確保流動性，過濾冷門股
        EquityQuery('gt', ['peratio.lasttwelvemonths', 0])# 確保公司有實質獲利
    ]
    
    if cap_filter == "小型潛力股 (3億 ~ 20億美元)":
        conditions.append(EquityQuery('btwn', ['intradaymarketcap', 300_000_000, 2_000_000_000]))
    elif cap_filter == "中型成長股 (20億 ~ 100億美元)":
        conditions.append(EquityQuery('btwn', ['intradaymarketcap', 2_000_000_000, 10_000_000_000]))
    elif cap_filter == "大型企業 (100億美元以上)":
        conditions.append(EquityQuery('gt', ['intradaymarketcap', 10_000_000_000]))
    else:
        conditions.append(EquityQuery('gt', ['intradaymarketcap', 300_000_000]))

    try:
        q = EquityQuery('and', conditions)
        # 依獲利成長與動能抓取前 100 檔最具潛力候選股進行深度財報與 VCP 運算
        res = yf.screen(q, size=100, sortField='epsgrowth.lasttwelvemonths', sortAsc=False)
        quotes = res.get('quotes', [])
        return [item.get('symbol') for item in quotes if item.get('symbol')]
    except Exception:
        return []

# 2. 單一股票深度體檢 ＋ VCP 型態量化運算
def analyze_stock_and_vcp(symbol):
    for _ in range(2):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            price = info.get('currentPrice') or info.get('regularMarketPrice')
            
            # 再次嚴格確認股價 >= 15 元
            if not price or price < 15:
                return None

            # 財務穩健與潛力指標
            mcap = info.get('marketCap')
            pe = info.get('trailingPE')
            f_pe = info.get('forwardPE')
            roe = info.get('returnOnEquity')
            de = info.get('debtToEquity')
            rev_growth = info.get('revenueGrowth')
            target_price = info.get('targetMeanPrice')
            fcf = info.get('freeCashflow')
            
            # 抓取過去 1 年日線數據計算 VCP 型態
            hist = ticker.history(period="1y")
            if len(hist) < 150:
                return None
                
            close = hist['Close']
            high = hist['High']
            low = hist['Low']
            vol = hist['Volume']
            
            sma50 = close.rolling(50).mean().iloc[-1]
            sma150 = close.rolling(150).mean().iloc[-1]
            sma200 = close.rolling(200).mean().iloc[-1]
            sma200_prev = close.rolling(200).mean().iloc[-20] # 20天前的年線
            high_52w = high.max()
            
            # VCP 條件檢核 (1~5分)
            vcp_score = 0
            # 條件A：多頭排列 (股價 > 50日線 > 150日線 且 股價 > 200日線)
            if price > sma50 and sma50 > sma150 and price > sma200:
                vcp_score += 1
            # 條件B：200日年線處於上升趨勢
            if sma200 > sma200_prev:
                vcp_score += 1
            # 條件C：股價位於強勢區 (距離 52 週高點在 25% 以內)
            dist_from_high = ((high_52w - price) / high_52w) * 100
            if dist_from_high <= 25:
                vcp_score += 1
            # 條件D：波動率收縮 (近10日價格振幅 < 前30日振幅的 70%)
            range_10d = (high.iloc[-10:].max() - low.iloc[-10:].min()) / close.iloc[-10:].mean()
            range_40d = (high.iloc[-40:-10].max() - low.iloc[-40:-10].min()) / close.iloc[-40:-10].mean()
            if range_40d > 0 and range_10d < (range_40d * 0.7):
                vcp_score += 1
            # 條件E：成交量萎縮 (近10日均量 < 50日均量，籌碼沉澱)
            if vol.iloc[-10:].mean() < vol.iloc[-50:].mean():
                vcp_score += 1

            if vcp_score >= 4:
                vcp_status = f"🔥 高度符合 ({vcp_score}/5)"
            elif vcp_score == 3:
                vcp_status = f"👀 觀察中 ({vcp_score}/5)"
            else:
                vcp_status = f"一般 ({vcp_score}/5)"

            upside_pct = round(((target_price - price) / price) * 100, 2) if target_price else None
            
            return {
                '股票代號': symbol,
                '公司名稱': info.get('shortName', symbol),
                '產業': info.get('sector', '其他'),
                'VCP型態評級': vcp_status,
                'VCP分數': vcp_score,
                '市值 (億美元)': round(mcap / 1e9, 2) if mcap else None,
                '目前股價': round(price, 2),
                '華爾街目標價': round(target_price, 2) if target_price else None,
                '潛在上漲空間 (%)': upside_pct,
                '本益比 (P/E)': round(pe, 2) if pe else None,
                '預估本益比': round(f_pe, 2) if f_pe else None,
                'ROE (%)': round(roe * 100, 2) if roe is not None else None,
                '負債比 (D/E)': round(de, 2) if de is not None else 0,
                '營收成長 (%)': round(rev_growth * 100, 2) if rev_growth is not None else None,
                '自由現金流': "正現金流" if (fcf and fcf > 0) else "負/無數據",
                '距52週高點 (%)': round(dist_from_high, 2),
                '樞紐突破價 (Pivot)': round(high.iloc[-15:].max(), 2)
            }
        except Exception:
            time.sleep(0.3)
    return None

@st.cache_data(ttl=3600, show_spinner=False)
def load_full_analysis(cap_filter, extra_tickers):
    candidates = get_market_candidates(cap_filter)
    all_symbols = list(dict.fromkeys(extra_tickers + candidates))
    
    with st.spinner(f"⚡ 正在深度掃描全市場 {len(all_symbols)} 檔股價 ≥ $15 潛力股並運算 VCP 型態（約需 15～25 秒）..."):
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(analyze_stock_and_vcp, all_symbols))
    return pd.DataFrame([r for r in results if r is not None])

# 3. 側邊欄控制台
with st.sidebar:
    st.header("🎛️ 優質潛力股 ＋ VCP 控制台")
    
    cap_choice = st.selectbox(
        "🏢 企業規模範圍（不限龍頭）",
        ["全市場不限規模 (3億美元以上)", "小型潛力股 (3億 ~ 20億美元)", "中型成長股 (20億 ~ 100億美元)", "大型企業 (100億美元以上)"]
    )
    
    custom_input = st.text_input("🔍 額外加入自選代號（逗號分隔）", placeholder="例如: PLTR, CELH, NVDA")
    custom_list = [t.strip().upper() for t in custom_input.split(",") if t.strip()]
    
    if st.button("🔄 強制刷新最新行情", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
        
    st.divider()
    st.subheader("1️⃣ 財務穩健度門檻")
    min_roe = st.slider("最低 ROE 要求 (%)", 0, 50, 12)
    max_de = st.slider("負債比上限 (D/E %)", 0, 300, 150)
    only_pos_fcf = st.checkbox("僅顯示「正自由現金流」企業", value=True)
    
    st.subheader("2️⃣ 估值與成長潛力")
    max_pe = st.slider("本益比上限 (P/E)", 5, 80, 35)
    min_upside = st.slider("分析師目標價最低空間 (%)", -20, 50, 5)
    
    st.subheader("3️⃣ VCP 型態過濾")
    vcp_filter = st.radio(
        "VCP 型態符合程度",
        ["全部顯示 (依 VCP 分數排序)", "僅顯示 🔥 高度符合 VCP (4~5分)", "顯示 👀 觀察中以上 (3~5分)"]
    )

# 載入數據
df = load_full_analysis(cap_choice, custom_list)

if df.empty:
    st.warning("⚠️ 暫時未取得數據，請點擊左側「🔄 強制刷新最新行情」重試。")
    st.stop()

with st.sidebar:
    all_sectors = sorted(df['產業'].dropna().unique().tolist())
    selected_sectors = st.multiselect("篩選產業類別", all_sectors, default=all_sectors)

# 4. 執行多維度篩選
filtered_df = df[
    (df['目前股價'] >= 15) &
    (df['本益比 (P/E)'].notna()) &
    (df['本益比 (P/E)'] <= max_pe) &
    (df['ROE (%)'].notna()) &
    (df['ROE (%)'] >= min_roe) &
    (df['負債比 (D/E)'] <= max_de) &
    (df['產業'].isin(selected_sectors))
]

if only_pos_fcf:
    filtered_df = filtered_df[filtered_df['自由現金流'] == "正現金流"]
if min_upside > -20:
    filtered_df = filtered_df[filtered_df['潛在上漲空間 (%)'].notna() & (filtered_df['潛在上漲空間 (%)'] >= min_upside)]

if "高度符合" in vcp_filter:
    filtered_df = filtered_df[filtered_df['VCP分數'] >= 4]
elif "觀察中" in vcp_filter:
    filtered_df = filtered_df[filtered_df['VCP分數'] >= 3]

# 優先依 VCP 分數、其次依潛在上漲空間排序
filtered_df = filtered_df.sort_values(by=['VCP分數', '潛在上漲空間 (%)'], ascending=[False, False])

# 5. 主畫面儀表板
c1, c2, c3, c4 = st.columns(4)
c1.metric("掃描優質池 ($15+)", f"{len(df)} 檔")
c2.metric("符合條件潛力股", f"{len(filtered_df)} 檔")
vcp_count = len(filtered_df[filtered_df['VCP分數'] >= 4])
c3.metric("🔥 高度符合 VCP 標的", f"{vcp_count} 檔")
avg_roe = round(filtered_df['ROE (%)'].mean(), 1) if len(filtered_df) > 0 else 0
c4.metric("精選平均 ROE", f"{avg_roe} %")

st.subheader("📋 優質潛力股與 VCP 型態篩選名單")
# 隱藏內部計算用的 VCP分數 數字欄，保留漂亮的文字評級欄
display_df = filtered_df.drop(columns=['VCP分數'])
st.dataframe(display_df, use_container_width=True, hide_index=True)

# 一鍵下載 Excel
output = BytesIO()
with pd.ExcelWriter(output, engine='openpyxl') as writer:
    display_df.to_excel(writer, sheet_name='精選潛力VCP股', index=False)
    df.drop(columns=['VCP分數']).to_excel(writer, sheet_name='全市場掃描總表', index=False)

st.download_button(
    label="📥 下載 Excel 量化與 VCP 分析報表",
    data=output.getvalue(),
    file_name=f"美股優質潛力VCP選股_ROE{min_roe}_PE{max_pe}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary"
)

# 6. VCP 型態視覺化確認圖表（標示樞紐突破價、收縮區間、三均線與量縮）
st.divider()
st.subheader("📊 VCP 型態視覺化確認（樞紐突破線、收縮區間、多頭均線與成交量萎縮）")

chart_options = display_df['股票代號'].tolist() if len(display_df) > 0 else df['股票代號'].tolist()
selected_symbol = st.selectbox("請選擇要檢視 VCP 型態的股票代號：", chart_options)

if selected_symbol:
    hist = yf.Ticker(selected_symbol).history(period="1y")
    if not hist.empty:
        hist['SMA50'] = hist['Close'].rolling(window=50).mean()
        hist['SMA150'] = hist['Close'].rolling(window=150).mean()
        hist['SMA200'] = hist['Close'].rolling(window=200).mean()
        hist['Vol_MA50'] = hist['Volume'].rolling(window=50).mean()
        
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
hist['RSI'] = 100 - (100 / (1 + (gain / loss)))
# 計算近 15 日樞紐壓力價 (Pivot) 與支撐價
pivot_high = hist['High'].iloc[-15:].max()
pivot_low = hist['Low'].iloc[-15:].min()
fig = make_subplots(
rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
row_heights=[0.65, 0.18, 0.17],
subplot_titles=(f"{selected_symbol} VCP 均線排列與近期收縮樞紐區間 (Pivot: ${round(pivot_high, 2)})", "成交量與 50 日均量（觀察量縮沉澱）", "RSI (14日) 動能指標")
)
# 第一層：K線 + VCP 核心三均線 (50/150/200) + 近期收縮樞紐區間
fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='日K線'), row=1, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA50'], mode='lines', name='50日均線', line=dict(color='orange', width=1.5)), row=1, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA150'], mode='lines', name='150日均線', line=dict(color='green', width=1.5)), row=1, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA200'], mode='lines', name='200日年線', line=dict(color='blue', width=2)), row=1, col=1)
# 在近 15 個交易日畫出 VCP 樞紐突破線（紅色虛線）與底部支撐線（綠色虛線）
recent_dates = hist.index[-15:]
fig.add_trace(go.Scatter(x=recent_dates, y=[pivot_high]*len(recent_dates), mode='lines', name=f'樞紐突破線 (${round(pivot_high,2)})', line=dict(color='red', width=2, dash='dash')), row=1, col=1)
fig.add_trace(go.Scatter(x=recent_dates, y=[pivot_low]*len(recent_dates), mode='lines', name=f'近期收縮底線 (${round(pivot_low,2)})', line=dict(color='teal', width=1.5, dash='dot')), row=1, col=1)
# 第二層：成交量 + 50日均量線（方便肉眼看出量縮）
fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], name='每日成交量', marker_color='rgba(100, 149, 237, 0.5)'), row=2, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['Vol_MA50'], mode='lines', name='50日均量線', line=dict(color='darkblue', width=1.5)), row=2, col=1)
# 第三層：RSI
fig.add_trace(go.Scatter(x=hist.index, y=hist['RSI'], mode='lines', name='RSI (14)', line=dict(color='purple', width=1.5)), row=3, col=1)
fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
fig.update_layout(xaxis_rangeslider_visible=False, height=780, template="plotly_white", showlegend=True)
st.plotly_chart(fig, use_container_width=True)


