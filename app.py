import streamlit as st
import yfinance as yf
from yfinance import EquityQuery
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
import time

st.set_page_config(page_title="全美優質潛力股與 VCP 交易決策系統 Pro", page_icon="🏆", layout="wide")

st.title("🏆 全美優質潛力股與 VCP 實戰交易決策系統 (VCP 引擎進化版)")
st.markdown("全市場掃描（**市值 ≥ 1B**、**股價 ≥ $15**），支援**動態調整 VCP 收縮參數**、**距突破點百分比預警**與**自動倉位風控**。")

# 備援優質潛力池（涵蓋大型龍頭 + 中小型高成長黑馬股，市值皆 > 1B）
FALLBACK_CANDIDATES = [
    'NVDA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'TSLA', 'AVGO', 'ORCL', 'CRM',
    'PLTR', 'APP', 'CELH', 'DUOL', 'CAVA', 'ANET', 'PANW', 'CRWD', 'SNOW', 'DDOG',
    'NET', 'ZS', 'TTD', 'HUBS', 'MDB', 'SHOP', 'SQ', 'COIN', 'HOOD', 'SOFI',
    'AFRM', 'UPST', 'NU', 'MELI', 'SE', 'GRAB', 'UBER', 'ABNB', 'BKNG', 'DASH',
    'NFLX', 'SPOT', 'RBLX', 'DKNG', 'LULU', 'DECK', 'ONON', 'ELF', 'BIRK', 'SHAK',
    'CMG', 'TXRH', 'WING', 'COST', 'WMT', 'TGT', 'HD', 'LOW', 'TJX', 'ROST',
    'LLY', 'NVO', 'UNH', 'ISRG', 'VRTX', 'REGN', 'DXCM', 'PODD', 'INSP', 'AXON',
    'TMDX', 'HIMS', 'VKTX', 'ALNY', 'JPM', 'V', 'MA', 'AXP', 'GS', 'MS',
    'BLK', 'KKR', 'APO', 'BX', 'IBKR', 'CBOE', 'NDAQ', 'SPGI', 'MCO', 'FICO',
    'CAT', 'URI', 'PWR', 'ETN', 'VRT', 'GEV', 'GE', 'FIX', 'EME', 'TT',
    'CARR', 'PH', 'IR', 'FTV', 'AME', 'XOM', 'CVX', 'COP', 'EOG', 'FANG',
    'TRGP', 'OKE', 'WMB', 'CEG', 'VST', 'NEE', 'FSLR', 'ENPH', 'TSM', 'ASML',
    'AMD', 'QCOM', 'MU', 'LRCX', 'KLAC', 'AMAT', 'MRVL', 'ARM', 'SMCI', 'DELL'
]

@st.cache_data(ttl=3600, show_spinner=False)
def get_spy_3m_return():
    try:
        spy_hist = yf.Ticker("SPY").history(period="6mo")
        if len(spy_hist) >= 63:
            return ((spy_hist['Close'].iloc[-1] - spy_hist['Close'].iloc[-63]) / spy_hist['Close'].iloc[-63]) * 100
    except Exception:
        pass
    return 0.0

@st.cache_data(ttl=3600, show_spinner=False)
def get_market_candidates(cap_filter):
    conditions = [
        EquityQuery('eq', ['region', 'us']),
        EquityQuery('gt', ['intradayprice', 15]),
        EquityQuery('gt', ['intradaymarketcap', 1_000_000_000]),
        EquityQuery('gt', ['avgdailyvol3m', 300000])
    ]
    if cap_filter == "小型潛力股 (10億 ~ 20億美元)":
        conditions.append(EquityQuery('btwn', ['intradaymarketcap', 1_000_000_000, 2_000_000_000]))
    elif cap_filter == "中型成長股 (20億 ~ 100億美元)":
        conditions.append(EquityQuery('btwn', ['intradaymarketcap', 2_000_000_000, 10_000_000_000]))
    elif cap_filter == "大型企業 (100億美元以上)":
        conditions.append(EquityQuery('gt', ['intradaymarketcap', 10_000_000_000]))
    try:
        q = EquityQuery('and', conditions)
        res = yf.screen(q, size=100, sortField='avgdailyvol3m', sortAsc=False)
        quotes = res.get('quotes', [])
        symbols = [item.get('symbol') for item in quotes if item.get('symbol')]
        if len(symbols) >= 10:
            return symbols
    except Exception:
        pass
    # 若雲端篩選受限，自動啟用內建 130 檔跨市值優質潛力池
    return FALLBACK_CANDIDATES

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_raw_stock_bundle(symbol):
    for _ in range(2):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
            mcap = info.get('marketCap')
            if not price or price < 15 or not mcap or mcap < 1_000_000_000:
                return None
            hist = ticker.history(period="1y")
            if len(hist) < 150:
                return None
            
            earnings_note = "安全"
            try:
                cal = ticker.calendar
                if isinstance(cal, dict) and 'Earnings Date' in cal and len(cal['Earnings Date']) > 0:
                    next_earn = cal['Earnings Date']
                    days_to_earn = (pd.to_datetime(next_earn).date() - datetime.now().date()).days
                    if 0 <= days_to_earn <= 10:
                        earnings_note = f"⚠️ {days_to_earn}天後財報"
                    elif days_to_earn > 10:
                        earnings_note = f"{days_to_earn}天後"
            except Exception:
                earnings_note = "未公布"

            return {'symbol': symbol, 'info': info, 'price': price, 'mcap': mcap, 'earnings_note': earnings_note, 'hist': hist}
        except Exception:
            time.sleep(0.3)
    return None

@st.cache_data(ttl=3600, show_spinner=False)
def load_raw_market_data(cap_filter, extra_tickers):
    spy_ret = get_spy_3m_return()
    candidates = get_market_candidates(cap_filter)
    all_symbols = list(dict.fromkeys(extra_tickers + candidates))
    with st.spinner(f"⚡ 正在載入全市場 {len(all_symbols)} 檔市值 ≥ 1B 企業數據（首次載入約 20 秒）..."):
        with ThreadPoolExecutor(max_workers=4) as executor:
            bundles = list(executor.map(fetch_raw_stock_bundle, all_symbols))
    return [b for b in bundles if b is not None], round(spy_ret, 2)

def evaluate_vcp_dynamic(bundles, spy_ret, max_risk_usd, pivot_days, contraction_ratio, max_high_dist):
    rows = []
    for b in bundles:
        symbol = b['symbol']
        info = b['info']
        price = b['price']
        mcap = b['mcap']
        hist = b['hist']
        
        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        vol = hist['Volume']
        
        stock_3m_ret = ((close.iloc[-1] - close.iloc[-63]) / close.iloc[-63]) * 100
        rs_vs_spy = round(stock_3m_ret - spy_ret, 2)
        
        sma50 = close.rolling(50).mean().iloc[-1]
        sma150 = close.rolling(150).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        sma200_prev = close.rolling(200).mean().iloc[-20]
        high_52w = high.max()
        dist_from_high = ((high_52w - price) / high_52w) * 100
        
        range_t1 = (high.iloc[-60:-30].max() - low.iloc[-60:-30].min()) / close.iloc[-60:-30].mean()
        range_t2 = (high.iloc[-30:-10].max() - low.iloc[-30:-10].min()) / close.iloc[-30:-10].mean()
        range_t3 = (high.iloc[-10:].max() - low.iloc[-10:].min()) / close.iloc[-10:].mean()
        
        vcp_score = 0
        if price > sma50 and sma50 > sma150 and price > sma200:
            vcp_score += 1
        if sma200 > sma200_prev:
            vcp_score += 1
        if dist_from_high <= max_high_dist:
            vcp_score += 1
        if range_t2 > 0 and range_t3 < (range_t2 * contraction_ratio) and range_t2 <= (range_t1 * 1.1):
            vcp_score += 1
        vol_ratio = round((vol.iloc[-5:].mean() / vol.iloc[-50:].mean()) * 100, 0)
        if vol_ratio <= 90:
            vcp_score += 1

        if vcp_score >= 4:
            vcp_status = f"🔥 高度符合 ({vcp_score}/5)"
        elif vcp_score == 3:
            vcp_status = f"👀 觀察中 ({vcp_score}/5)"
        else:
            vcp_status = f"一般 ({vcp_score}/5)"

        pivot_price = round(high.iloc[-pivot_days:].max(), 2)
        stop_loss = round(low.iloc[-pivot_days:].min() * 0.99, 2)
        dist_to_pivot = round(((pivot_price - price) / price) * 100, 2)
        
        risk_per_share = max(pivot_price - stop_loss, 0.1)
        stop_loss_pct = round((risk_per_share / pivot_price) * 100, 1)
        suggested_shares = int(max_risk_usd // risk_per_share)
        
        pe = info.get('trailingPE')
        roe = info.get('returnOnEquity')
        de = info.get('debtToEquity')
        target_price = info.get('targetMeanPrice')
        fcf = info.get('freeCashflow')
        upside_pct = round(((target_price - price) / price) * 100, 2) if target_price else None
        
        rows.append({
            '股票代號': symbol,
            'VCP型態評級': vcp_status,
            'VCP分數': vcp_score,
            '目前股價': round(price, 2),
            '樞紐突破價': pivot_price,
            '距突破點(%)': dist_to_pivot,
            '建議停損價': stop_loss,
            '停損幅度(%)': stop_loss_pct,
            '建議買進股數': suggested_shares,
            '近期量能比(%)': int(vol_ratio),
            '跑贏大盤3M(%)': rs_vs_spy,
            '財報防雷': b['earnings_note'],
            'ROE (%)': round(roe * 100, 2) if roe is not None else 0,
            '本益比 (P/E)': round(pe, 2) if pe else 0,
            '負債比 (D/E)': round(de, 2) if de is not None else 0,
            '潛在上漲空間(%)': upside_pct,
            '市值 (億美元)': round(mcap / 1e9, 2),
            '公司名稱': info.get('shortName', symbol),
            '產業': info.get('sector', '其他'),
            '自由現金流': "正現金流" if (fcf and fcf > 0) else "負/無數據",
            '距52週高點(%)': round(dist_from_high, 2)
        })
    return pd.DataFrame(rows)

with st.sidebar:
    st.header("🎛️ VCP 交易決策控制台")
    cap_choice = st.selectbox("🏢 企業規模範圍（全部 ≥ 1B）", ["全市場不限規模 (1B / 10億美元以上)", "小型潛力股 (10億 ~ 20億美元)", "中型成長股 (20億 ~ 100億美元)", "大型企業 (100億美元以上)"])
    custom_input = st.text_input("🔍 額外加入自選代號（逗號分隔）", placeholder="例如: PLTR, CELH, NVDA")
    custom_list = [t.strip().upper() for t in custom_input.split(",") if t.strip()]
    
    if st.button("🔄 強制刷新最新行情", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
        
    st.divider()
    st.subheader("🎯 VCP 型態引擎微調（即時重算）")
    pivot_days = st.slider("樞紐突破與停損觀察天數", 10, 30, 15, step=5)
    contraction_ratio = st.slider("波動收縮嚴格度 (越小越緊縮)", 0.50, 0.95, 0.75, step=0.05)
    max_high_dist = st.slider("距 52 週高點最大距離 (%)", 15, 45, 25, step=5)
    vcp_filter = st.radio("VCP 型態篩選", ["全部顯示 (依 VCP 分數排序)", "僅顯示 🔥 高度符合 VCP (4~5分)", "顯示 👀 觀察中以上 (3~5分)"])

    st.divider()
    st.subheader("🛡️ 倉位風控與基本面門檻")
    max_risk_usd = st.number_input("單筆最大可承受虧損 (美元)", min_value=50, max_value=50000, value=500, step=50)
    min_roe = st.slider("最低 ROE 要求 (%)", 0, 50, 0)
    max_de = st.slider("負債比上限 (D/E %)", 0, 500, 250)
    max_pe = st.slider("本益比上限 (0=不限)", 0, 150, 0)
    only_pos_fcf = st.checkbox("僅顯示「正自由現金流」企業", value=False)
    only_beat_spy = st.checkbox("僅顯示「近3個月跑贏大盤」強勢股", value=False)
bundles, spy_3m = load_raw_market_data(cap_choice, custom_list)
if not bundles:
st.warning("⚠️ 暫時未取得數據，請點擊左側「🔄 強制刷新最新行情」重試。")
st.stop()
df = evaluate_vcp_dynamic(bundles, spy_3m, max_risk_usd, pivot_days, contraction_ratio, max_high_dist)
with st.sidebar:
all_sectors = sorted(df['產業'].dropna().unique().tolist())
selected_sectors = st.multiselect("篩選產業類別", all_sectors, default=all_sectors)
filtered_df = df[
(df['目前股價'] >= 15) &
(df['市值 (億美元)'] >= 10) &
(df['ROE (%)'] >= min_roe) &
(df['負債比 (D/E)'] <= max_de) &
(df['產業'].isin(selected_sectors))
]
if max_pe > 0:
filtered_df = filtered_df[filtered_df['本益比 (P/E)'] <= max_pe]
if only_pos_fcf:
filtered_df = filtered_df[filtered_df['自由現金流'] == "正現金流"]
if only_beat_spy:
filtered_df = filtered_df[filtered_df['跑贏大盤3M(%)'] > 0]
if "高度符合" in vcp_filter:
filtered_df = filtered_df[filtered_df['VCP分數'] >= 4]
elif "觀察中" in vcp_filter:
filtered_df = filtered_df[filtered_df['VCP分數'] >= 3]
filtered_df = filtered_df.sort_values(by=['VCP分數', '距突破點(%)'], ascending=[False, True])
c1, c2, c3, c4 = st.columns(4)
c1.metric("掃描優質池 (≥1B / $15+)", f"{len(df)} 檔")
c2.metric("符合條件強勢股", f"{len(filtered_df)} 檔")
vcp_count = len(filtered_df[filtered_df['VCP分數'] >= 4])
c3.metric("🔥 高度符合 VCP 標的", f"{vcp_count} 檔")
c4.metric("標普500 (SPY) 近3月基準", f"{spy_3m} %")
st.subheader("📋 VCP 交易決策與倉位風控名單（依 VCP 分數與接近突破程度排序）")
display_df = filtered_df.drop(columns=['VCP分數'])
st.dataframe(display_df, use_container_width=True, hide_index=True)
output = BytesIO()
writer = pd.ExcelWriter(output, engine='openpyxl')
display_df.to_excel(writer, sheet_name='VCP交易決策名單', index=False)
df.drop(columns=['VCP分數']).to_excel(writer, sheet_name='全市場掃描總表', index=False)
writer.close()
st.download_button(label="📥 下載 Excel 交易風控報表", data=output.getvalue(), file_name=f"美股VCP交易決策_{pivot_days}日樞紐.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
st.divider()
st.subheader("📊 VCP 突破買點與停損防守線圖表")
chart_options = display_df['股票代號'].tolist() if len(display_df) > 0 else df['股票代號'].tolist()
selected_symbol = st.selectbox("請選擇要檢視買賣點位的股票代號：", chart_options)
hist = yf.Ticker(selected_symbol).history(period="1y")
hist['SMA50'] = hist['Close'].rolling(window=50).mean()
hist['SMA150'] = hist['Close'].rolling(window=150).mean()
hist['SMA200'] = hist['Close'].rolling(window=200).mean()
hist['Vol_MA50'] = hist['Volume'].rolling(window=50).mean()
delta = hist['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
hist['RSI'] = 100 - (100 / (1 + (gain / loss)))
pivot_high = round(hist['High'].iloc[-pivot_days:].max(), 2)
stop_loss = round(hist['Low'].iloc[-pivot_days:].min() * 0.99, 2)
fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.65, 0.18, 0.17], subplot_titles=(f"{selected_symbol} 近{pivot_days}日樞紐突破買點 (${pivot_high}) 與防守停損線 (${stop_loss})", "成交量與 50 日均量（觀察量縮沉澱）", "RSI (14日) 動能指標"))
fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='日K線'), row=1, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA50'], mode='lines', name='50日均線', line=dict(color='orange', width=1.5)), row=1, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA150'], mode='lines', name='150日均線', line=dict(color='green', width=1.5)), row=1, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA200'], mode='lines', name='200日年線', line=dict(color='blue', width=2)), row=1, col=1)
recent_dates = hist.index[-pivot_days:]
fig.add_trace(go.Scatter(x=recent_dates, y=[pivot_high]*len(recent_dates), mode='lines', name=f'樞紐突破買點 (${pivot_high})', line=dict(color='red', width=2, dash='dash')), row=1, col=1)
fig.add_trace(go.Scatter(x=recent_dates, y=[stop_loss]*len(recent_dates), mode='lines', name=f'防守停損線 (${stop_loss})', line=dict(color='teal', width=2, dash='dot')), row=1, col=1)
fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], name='每日成交量', marker_color='rgba(100, 149, 237, 0.5)'), row=2, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['Vol_MA50'], mode='lines', name='50日均量線', line=dict(color='darkblue', width=1.5)), row=2, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['RSI'], mode='lines', name='RSI (14)', line=dict(color='purple', width=1.5)), row=3, col=1)
fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
fig.update_layout(xaxis_rangeslider_visible=False, height=780, template="plotly_white", showlegend=True)
st.plotly_chart(fig, use_container_width=True)
