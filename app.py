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

st.set_page_config(page_title="全美優質潛力股與 VCP 交易終端機 Pro+", page_icon="🏆", layout="wide")

st.title("🏆 全美優質潛力股與 VCP 實戰交易終端機")

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
def get_market_regime():
    spy_3m_ret, vix_val, tnx_val, spy_above_50, spy_above_200 = 0.0, 18.0, 4.2, True, True
    try:
        spy_hist = yf.Ticker("SPY").history(period="1y")
        if len(spy_hist) >= 200:
            spy_close = spy_hist['Close'].iloc[-1]
            spy_3m_ret = ((spy_close - spy_hist['Close'].iloc[-63]) / spy_hist['Close'].iloc[-63]) * 100
            spy_above_50 = spy_close > spy_hist['Close'].rolling(50).mean().iloc[-1]
            spy_above_200 = spy_close > spy_hist['Close'].rolling(200).mean().iloc[-1]
        vix_hist = yf.Ticker("^VIX").history(period="5d")
        if not vix_hist.empty: vix_val = round(vix_hist['Close'].iloc[-1], 2)
        tnx_hist = yf.Ticker("^TNX").history(period="5d")
        if not tnx_hist.empty: tnx_val = round(tnx_hist['Close'].iloc[-1], 2)
    except Exception:
        pass
    return round(spy_3m_ret, 2), vix_val, tnx_val, spy_above_50, spy_above_200

@st.cache_data(ttl=3600, show_spinner=False)
def get_market_candidates(cap_filter):
    conditions = [
        EquityQuery('eq', ['region', 'us']),
        EquityQuery('gt', ['intradayprice', 15]),
        EquityQuery('gt', ['intradaymarketcap', 1_000_000_000]),
        EquityQuery('gt', ['avgdailyvol3m', 300000])
    ]
    if cap_filter == "小型潛力股 (10億 ~ 20億美元)": conditions.append(EquityQuery('btwn', ['intradaymarketcap', 1_000_000_000, 2_000_000_000]))
    elif cap_filter == "中型成長股 (20億 ~ 100億美元)": conditions.append(EquityQuery('btwn', ['intradaymarketcap', 2_000_000_000, 10_000_000_000]))
    elif cap_filter == "大型企業 (100億美元以上)": conditions.append(EquityQuery('gt', ['intradaymarketcap', 10_000_000_000]))
    try:
        res = yf.screen(EquityQuery('and', conditions), size=100, sortField='avgdailyvol3m', sortAsc=False)
        symbols = [item.get('symbol') for item in res.get('quotes', []) if item.get('symbol')]
        if len(symbols) >= 10: return symbols
    except Exception:
        pass
    return FALLBACK_CANDIDATES

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_raw_stock_bundle(symbol):
    for _ in range(2):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
            mcap = info.get('marketCap')
            if not price or price < 15 or not mcap or mcap < 1_000_000_000: return None
            hist = ticker.history(period="1y")
            if len(hist) < 150: return None
            earnings_note = "安全"
            try:
                cal = ticker.calendar
                if isinstance(cal, dict) and 'Earnings Date' in cal and len(cal['Earnings Date']) > 0:
                    days_to_earn = (pd.to_datetime(cal['Earnings Date']).date() - datetime.now().date()).days
                    if 0 <= days_to_earn <= 10: earnings_note = f"⚠️ {days_to_earn}天後財報"
                    elif days_to_earn > 10: earnings_note = f"{days_to_earn}天後"
            except Exception:
                earnings_note = "未公布"
            inst_pct = round(info.get('heldPercentInstitutions', 0) * 100, 1) if info.get('heldPercentInstitutions') else 0.0
            insider_note = "⚪ 正常"
            try:
                insiders = ticker.insider_transactions
                if insiders is not None and not insiders.empty and 'Text' in insiders.columns:
                    recent_text = " ".join(insiders['Text'].head(10).astype(str).tolist()).lower()
                    has_buy = ('purchase' in recent_text) or ('buy' in recent_text)
                    has_sale = ('sale' in recent_text) or ('sell' in recent_text)
                    if has_buy and not has_sale: insider_note = "🟢 高管買進"
                    elif has_buy and has_sale: insider_note = "🟡 買賣互見"
                    elif has_sale: insider_note = "🟠 高管減持"
            except Exception:
                insider_note = "⚪ 正常"
            return {'symbol': symbol, 'info': info, 'price': price, 'mcap': mcap, 'earnings_note': earnings_note, 'inst_pct': inst_pct, 'insider_note': insider_note, 'hist': hist}
        except Exception:
            time.sleep(0.3)
    return None

@st.cache_data(ttl=3600, show_spinner=False)
def load_raw_market_data(cap_filter, extra_tickers):
    regime = get_market_regime()
    candidates = get_market_candidates(cap_filter)
    all_symbols = list(dict.fromkeys(extra_tickers + candidates))
    with st.spinner(f"⚡ 正在掃描大盤紅綠燈與 {len(all_symbols)} 檔市值 ≥ 1B 企業數據（約 20 秒）..."):
        with ThreadPoolExecutor(max_workers=4) as executor:
            bundles = list(executor.map(fetch_raw_stock_bundle, all_symbols))
    return [b for b in bundles if b is not None], regime

def evaluate_vcp_dynamic(bundles, spy_ret, max_risk_usd, pivot_days, contraction_ratio, max_high_dist):
    rows = []
    for b in bundles:
        symbol, info, price, mcap, hist = b['symbol'], b['info'], b['price'], b['mcap'], b['hist']
        close, high, low, vol = hist['Close'], hist['High'], hist['Low'], hist['Volume']
        rs_vs_spy = round(((close.iloc[-1] - close.iloc[-63]) / close.iloc[-63]) * 100 - spy_ret, 2)
        sma50, sma150, sma200 = close.rolling(50).mean().iloc[-1], close.rolling(150).mean().iloc[-1], close.rolling(200).mean().iloc[-1]
        sma200_prev = close.rolling(200).mean().iloc[-20]
        high_52w = high.max()
        dist_from_high = ((high_52w - price) / high_52w) * 100
        range_t1 = (high.iloc[-60:-30].max() - low.iloc[-60:-30].min()) / close.iloc[-60:-30].mean()
        range_t2 = (high.iloc[-30:-10].max() - low.iloc[-30:-10].min()) / close.iloc[-30:-10].mean()
        range_t3 = (high.iloc[-10:].max() - low.iloc[-10:].min()) / close.iloc[-10:].mean()
        vcp_score = 0
        if price > sma50 and sma50 > sma150 and price > sma200: vcp_score += 1
        if sma200 > sma200_prev: vcp_score += 1
        if dist_from_high <= max_high_dist: vcp_score += 1
        if range_t2 > 0 and range_t3 < (range_t2 * contraction_ratio) and range_t2 <= (range_t1 * 1.1): vcp_score += 1
        vol_ratio = round((vol.iloc[-5:].mean() / vol.iloc[-50:].mean()) * 100, 0)
        if vol_ratio <= 90: vcp_score += 1
        vcp_status = f"🔥 高度 ({vcp_score}/5)" if vcp_score >= 4 else (f"👀 觀察 ({vcp_score}/5)" if vcp_score == 3 else f"一般 ({vcp_score}/5)")
        pivot_price = round(high.iloc[-pivot_days:].max(), 2)
        stop_loss = round(low.iloc[-pivot_days:].min() * 0.99, 2)
        dist_to_pivot = round(((pivot_price - price) / price) * 100, 2)
        risk_per_share = max(pivot_price - stop_loss, 0.1)
        stop_loss_pct = round((risk_per_share / pivot_price) * 100, 1)
        suggested_shares = int(max_risk_usd // risk_per_share)
        pe, roe, de, target_price, fcf = info.get('trailingPE'), info.get('returnOnEquity'), info.get('debtToEquity'), info.get('targetMeanPrice'), info.get('freeCashflow')
        upside_pct = round(((target_price - price) / price) * 100, 2) if target_price else None
        rows.append({'股票代號': symbol, 'VCP評級': vcp_status, 'VCP分數': vcp_score, '目前股價': round(price, 2), '樞紐買點': pivot_price, '距買點(%)': dist_to_pivot, '建議停損': stop_loss, '停損幅度(%)': stop_loss_pct, '建議股數': suggested_shares, '機構持股(%)': b['inst_pct'], '內部人動向': b['insider_note'], '量能比(%)': int(vol_ratio), '跑贏大盤(%)': rs_vs_spy, '財報防雷': b['earnings_note'], 'ROE (%)': round(roe * 100, 2) if roe is not None else 0, '本益比': round(pe, 2) if pe else 0, '負債比': round(de, 2) if de is not None else 0, '目標空間(%)': upside_pct, '市值(億)': round(mcap / 1e9, 2), '公司名稱': info.get('shortName', symbol), '產業': info.get('sector', '其他'), '自由現金流': "正現金流" if (fcf and fcf > 0) else "負/無數據"})
    return pd.DataFrame(rows)

st.sidebar.header("🎛️ VCP 交易決策控制台")
cap_choice = st.sidebar.selectbox("🏢 企業規模範圍（≥ 1B）", ["全市場不限規模 (1B / 10億美元以上)", "小型潛力股 (10億 ~ 20億美元)", "中型成長股 (20億 ~ 100億美元)", "大型企業 (100億美元以上)"])
custom_input = st.sidebar.text_input("🔍 額外自選代號（逗號分隔）", placeholder="例如: PLTR, CELH, NVDA")
custom_list = [t.strip().upper() for t in custom_input.split(",") if t.strip()]

if st.sidebar.button("🔄 強制刷新最新行情", use_container_width=True): st.cache_data.clear(); st.rerun()

exp_vcp = st.sidebar.expander("🎯 VCP 型態引擎參數（即時重算）", expanded=True)
pivot_days = exp_vcp.slider("樞紐突破與停損觀察天數", 10, 30, 15, step=5)
contraction_ratio = exp_vcp.slider("波動收縮嚴格度 (越小越緊縮)", 0.50, 0.95, 0.75, step=0.05)
max_high_dist = exp_vcp.slider("距 52 週高點最大距離 (%)", 15, 45, 25, step=5)
vcp_filter = exp_vcp.radio("VCP 型態篩選", ["全部顯示 (依 VCP 分數排序)", "僅顯示 🔥 高度符合 VCP (4~5分)", "顯示 👀 觀察中以上 (3~5分)"])
exp_risk = st.sidebar.expander("🛡️ 資金風控設定", expanded=True)
max_risk_usd = exp_risk.number_input("單筆最大可承受虧損 (美元)", min_value=50, max_value=50000, value=500, step=50)
max_stop_pct = exp_risk.slider("最大可接受停損幅度上限 (%)", 3, 25, 15, step=1)
exp_fund = st.sidebar.expander("📊 籌碼與基本面門檻", expanded=False)
min_inst = exp_fund.slider("最低機構持股比例 (%)", 0, 90, 0, step=10)
min_roe = exp_fund.slider("最低 ROE 要求 (%)", 0, 50, 0)
max_de = exp_fund.slider("負債比上限 (D/E %)", 0, 500, 250)
max_pe = exp_fund.slider("本益比上限 (0=不限)", 0, 150, 0)
only_pos_fcf = exp_fund.checkbox("僅顯示「正自由現金流」企業", value=False)
only_beat_spy = exp_fund.checkbox("僅顯示「近3個月跑贏大盤」強勢股", value=False)
bundles, regime = load_raw_market_data(cap_choice, custom_list)
if not bundles: st.warning("⚠️ 暫時未取得數據，請點擊左側刷新重試。"); st.stop()
spy_3m, vix_val, tnx_val, spy_above_50, spy_above_200 = regime
if vix_val < 20 and spy_above_50: st.success(f"🟢 大盤環境紅綠燈：多頭安全區 ｜ VIX：{vix_val} ｜ 10年美債：{tnx_val}% ｜ SPY站穩50日線（適合按標準風控執行 VCP 突破）")
elif vix_val > 26 and not spy_above_200: st.error(f"🔴 大盤環境紅綠燈：高風險警戒區 ｜ VIX：{vix_val} ｜ 10年美債：{tnx_val}% ｜ SPY跌破200日年線（假突破風險高，建議觀望）")
else: st.warning(f"🟡 大盤環境紅綠燈：震盪觀察區 ｜ VIX：{vix_val} ｜ 10年美債：{tnx_val}% ｜ 市場處於震盪或修正期（建議減半倉位操作）")
df = evaluate_vcp_dynamic(bundles, spy_3m, max_risk_usd, pivot_days, contraction_ratio, max_high_dist)
all_sectors = sorted(df['產業'].dropna().unique().tolist())
selected_sectors = exp_fund.multiselect("篩選產業類別", all_sectors, default=all_sectors)
filtered_df = df[(df['目前股價'] >= 15) & (df['市值(億)'] >= 10) & (df['停損幅度(%)'] <= max_stop_pct) & (pd.to_numeric(df['機構持股(%)'], errors='coerce').fillna(0) >= min_inst) & (pd.to_numeric(df['ROE (%)'], errors='coerce').fillna(0) >= min_roe) & (pd.to_numeric(df['負債比'], errors='coerce').fillna(0) <= max_de)]
if max_pe > 0: filtered_df = filtered_df[filtered_df['本益比'] <= max_pe]
if only_pos_fcf: filtered_df = filtered_df[filtered_df['自由現金流'] == "正現金流"]
if only_beat_spy: filtered_df = filtered_df[filtered_df['跑贏大盤(%)'] > 0]
if "高度符合" in vcp_filter: filtered_df = filtered_df[filtered_df['VCP分數'] >= 4]
if "觀察中" in vcp_filter: filtered_df = filtered_df[filtered_df['VCP分數'] >= 3]
filtered_df = filtered_df.sort_values(by=['VCP分數', '距買點(%)'], ascending=[False, True]).reset_index(drop=True)
c1, c2, c3, c4 = st.columns(4)
c1.metric("掃描優質池 (≥1B / $15+)", f"{len(df)} 檔")
c2.metric("符合風控強勢股", f"{len(filtered_df)} 檔")
vcp_count = len(filtered_df[filtered_df['VCP分數'] >= 4])
c3.metric("🔥 高度符合 VCP 標的", f"{vcp_count} 檔")
c4.metric("標普500 (SPY) 近3月基準", f"{spy_3m} %")
st.divider()
col_left, col_right = st.columns([1.08, 0.92])
display_df = filtered_df.drop(columns=['VCP分數'])
styled_df = display_df.style.apply(lambda r: ['background-color: #d4edda; color: #155724; font-weight: bold;' if (c == '距買點(%)' and r[c] <= 2.5) else ('background-color: #f8d7da; color: #721c24; font-weight: bold;' if (c == '停損幅度(%)' and r[c] > 10.0) else '') for c in r.index], axis=1)
col_cfg = {
"機構持股(%)": st.column_config.ProgressColumn("機構持股(%)", format="%.1f%%", min_value=0, max_value=100),
"ROE (%)": st.column_config.ProgressColumn("ROE (%)", format="%.1f%%", min_value=0, max_value=50),
"目前股價": st.column_config.NumberColumn("目前股價", format="$%.2f"),
"樞紐買點": st.column_config.NumberColumn("樞紐買點", format="$%.2f"),
"建議停損": st.column_config.NumberColumn("建議停損", format="$%.2f")
}
table_event = col_left.dataframe(styled_df, use_container_width=True, hide_index=True, height=680, on_select="rerun", selection_mode="single-row", column_config=col_cfg)
output = BytesIO()
writer = pd.ExcelWriter(output, engine='openpyxl')
display_df.to_excel(writer, sheet_name='VCP交易決策名單', index=False)
df.drop(columns=['VCP分數']).to_excel(writer, sheet_name='全市場掃描總表', index=False)
writer.close()
col_left.download_button(label="📥 下載 Excel 交易風控報表", data=output.getvalue(), file_name=f"美股VCP交易決策_{pivot_days}日樞紐.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
selected_rows = table_event.selection.rows if (table_event and hasattr(table_event, "selection")) else []
if len(selected_rows) > 0 and len(display_df) > next(iter(selected_rows)): active_row = display_df.iloc[next(iter(selected_rows))]
elif len(display_df) > 0: active_row = display_df.head(1).squeeze()
else: active_row = df.head(1).squeeze()
selected_symbol = active_row['股票代號']
p_buy = float(active_row['樞紐買點'])
p_stop = float(active_row['建議停損'])
s_shares = int(active_row['建議股數'])
total_capital = round(p_buy * s_shares, 2)
col_right.subheader(f"🎯 {selected_symbol} ({active_row['公司名稱']}) 交易計畫")
m1, m2, m3, m4 = col_right.columns(4)
m1.metric("突破買進價", f"${p_buy}")
m2.metric("防守停損價", f"${p_stop}", f"-{active_row['停損幅度(%)']}%", delta_color="inverse")
m3.metric("建議買進股數", f"{s_shares} 股")
m4.metric("預計投入本金", f"${total_capital:,.0f}")
hist = yf.Ticker(selected_symbol).history(period="1y")
hist['SMA50'] = hist['Close'].rolling(window=50).mean()
hist['SMA150'] = hist['Close'].rolling(window=150).mean()
hist['SMA200'] = hist['Close'].rolling(window=200).mean()
hist['Vol_MA50'] = hist['Volume'].rolling(window=50).mean()
delta = hist['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
hist['RSI'] = 100 - (100 / (1 + (gain / loss)))
fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.65, 0.18, 0.17], subplot_titles=(f"{selected_symbol} 近{pivot_days}日樞紐突破 (${p_buy}) 與停損 (${p_stop})", "成交量與 50 日均量", "RSI (14日)"))
fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='日K線'), row=1, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA50'], mode='lines', name='50日線', line=dict(color='orange', width=1.5)), row=1, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA150'], mode='lines', name='150日線', line=dict(color='green', width=1.5)), row=1, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA200'], mode='lines', name='200日年線', line=dict(color='blue', width=2)), row=1, col=1)
recent_dates = hist.index[-pivot_days:]
fig.add_trace(go.Scatter(x=recent_dates, y=[p_buy]*len(recent_dates), mode='lines', name='突破買點', line=dict(color='red', width=2, dash='dash')), row=1, col=1)
fig.add_trace(go.Scatter(x=recent_dates, y=[p_stop]*len(recent_dates), mode='lines', name='停損底線', line=dict(color='teal', width=2, dash='dot')), row=1, col=1)
fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], name='成交量', marker_color='rgba(100, 149, 237, 0.5)'), row=2, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['Vol_MA50'], mode='lines', name='50日均量', line=dict(color='darkblue', width=1.5)), row=2, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist['RSI'], mode='lines', name='RSI', line=dict(color='purple', width=1.5)), row=3, col=1)
fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
fig.update_layout(xaxis_rangeslider_visible=False, height=620, template="plotly_white", showlegend=False, margin=dict(l=10, r=10, t=35, b=10))
col_right.plotly_chart(fig, use_container_width=True)
