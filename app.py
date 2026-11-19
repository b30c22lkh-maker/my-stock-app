import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from openai import OpenAI
import time

st.set_page_config(page_title="全美優質潛力股與 VCP 交易終端機 AI版", page_icon="🏆", layout="wide")
st.title("🏆 全美優質潛力股與 VCP 實戰交易終端機 (極速 AI + 財報精算版)")

CORE_CANDIDATES = [
    'NVDA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'TSLA', 'AVGO', 'ORCL', 'CRM',
    'PLTR', 'APP', 'CELH', 'DUOL', 'CAVA', 'ANET', 'PANW', 'CRWD', 'SNOW', 'DDOG',
    'NET', 'ZS', 'TTD', 'HUBS', 'SHOP', 'COIN', 'HOOD', 'SOFI', 'NU', 'MELI',
    'UBER', 'ABNB', 'BKNG', 'NFLX', 'SPOT', 'LULU', 'DECK', 'ONON', 'ELF', 'SHAK',
    'CMG', 'COST', 'WMT', 'HD', 'TJX', 'LLY', 'NVO', 'UNH', 'ISRG', 'VRTX',
    'DXCM', 'AXON', 'HIMS', 'JPM', 'V', 'MA', 'GS', 'BLK', 'KKR', 'IBKR',
    'SPGI', 'FICO', 'CAT', 'URI', 'PWR', 'ETN', 'VRT', 'GEV', 'GE', 'FIX',
    'XOM', 'COP', 'EOG', 'CEG', 'VST', 'NEE', 'TSM', 'ASML', 'AMD', 'MU'
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
def fetch_raw_stock_bundle(symbol):
    for _ in range(2):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1y")
            if len(hist) < 150: return None
            info = {}
            try: info = ticker.info or {}
            except Exception: info = {}
            
            price = info.get('currentPrice') or info.get('regularMarketPrice') or float(hist['Close'].iloc[-1])
            mcap = info.get('marketCap') or 15_000_000_000
            if price < 15 or mcap < 1_000_000_000: return None

            roe_val = round(info.get('returnOnEquity') * 100, 2) if info.get('returnOnEquity') is not None else 0.0
            pe_val = round(info.get('trailingPE'), 2) if info.get('trailingPE') else 0.0
            de_val = round(info.get('debtToEquity'), 2) if info.get('debtToEquity') is not None else 0.0
            fcf_str = "正現金流" if (info.get('freeCashflow') and info.get('freeCashflow') > 0) else "待確認"

            # 直接從三大財報精算 ROE、本益比(P/E) 與 負債比(D/E %)
            try:
                inc = ticker.income_stmt
                bal = ticker.balance_sheet
                if inc is not None and not inc.empty and bal is not None and not bal.empty:
                    ni_rows = [r for r in inc.index if 'Net Income' in str(r)]
                    eps_rows = [r for r in inc.index if 'Diluted EPS' in str(r) or 'Basic EPS' in str(r)]
                    eq_rows = [r for r in bal.index if 'Stockholders Equity' in str(r) or 'Total Equity' in str(r)]
                    debt_rows = [r for r in bal.index if 'Total Debt' in str(r)]
                    
                    eq = float(bal.loc[eq_rows.pop(0)].dropna().iloc[-1]) if eq_rows else 0
                    if roe_val == 0 and ni_rows and eq > 0:
                        ni = float(inc.loc[ni_rows.pop(0)].dropna().iloc[-1])
                        roe_val = round((ni / eq) * 100, 2)
                    if pe_val == 0 and eps_rows:
                        eps = float(inc.loc[eps_rows.pop(0)].dropna().iloc[-1])
                        if eps > 0: pe_val = round(price / eps, 2)
                    if de_val == 0 and debt_rows and eq > 0:
                        debt = float(bal.loc[debt_rows.pop(0)].dropna().iloc[-1])
                        de_val = round((debt / eq) * 100, 2)
                    if ni_rows and float(inc.loc[ni_rows[0]].dropna().iloc[-1]) > 0:
                        fcf_str = "正獲利"
            except Exception:
                pass

            return {
                'symbol': symbol,
                'info': info,
                'price': price,
                'mcap': mcap,
                'roe_val': roe_val,
                'pe_val': pe_val,
                'de_val': de_val,
                'fcf_str': fcf_str,
                'hist': hist
            }
        except Exception:
            time.sleep(0.4)
    return None

@st.cache_data(ttl=3600, show_spinner=False)
def load_raw_market_data(extra_tickers):
    regime = get_market_regime()
    all_symbols = list(dict.fromkeys(extra_tickers + CORE_CANDIDATES))
    with st.spinner(f"⚡ 正在高速掃描 {len(all_symbols)} 檔市值 ≥ 1B 潛力股與三大財報（約 10～15 秒）..."):
        with ThreadPoolExecutor(max_workers=3) as executor:
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
        rows.append({'股票代號': symbol, 'VCP評級': vcp_status, 'VCP分數': vcp_score, '目前股價': round(price, 2), '樞紐買點': pivot_price, '距買點(%)': dist_to_pivot, '建議停損': stop_loss, '停損幅度(%)': stop_loss_pct, '建議股數': suggested_shares, 'ROE (%)': b['roe_val'], '本益比': b['pe_val'], '負債比(%)': b['de_val'], '量能比(%)': int(vol_ratio), '跑贏大盤(%)': rs_vs_spy, '獲利狀態': b['fcf_str'], '公司名稱': info.get('shortName', symbol)})
    return pd.DataFrame(rows)

st.sidebar.header("🎛️ VCP 交易決策控制台")
custom_input = st.sidebar.text_input("🔍 額外自選代號（逗號分隔）", placeholder="例如: SOXL, TSM, AMD")
custom_list = [t.strip().upper() for t in custom_input.split(",") if t.strip()]

if st.sidebar.button("🔄 強制刷新最新行情", use_container_width=True): st.cache_data.clear(); st.rerun()

or_key = st.secrets.get("OPENROUTER_API_KEY", "")
gh_key = st.secrets.get("GITHUB_API_KEY", "")
ai_mode = st.sidebar.selectbox("🤖 AI 極速分析師模式", ["⚡ 雙引擎極速接力 (GitHub GPT-4o-mini 優先 ➔ OpenRouter)", "僅使用 OpenRouter (Llama-3.3-70B)", "僅使用 GitHub Models (GPT-4o-mini)"])

exp_vcp = st.sidebar.expander("🎯 VCP 型態引擎參數（即時重算）", expanded=False)
pivot_days = exp_vcp.slider("樞紐突破與停損觀察天數", 10, 30, 15, step=5)
contraction_ratio = exp_vcp.slider("波動收縮嚴格度 (越小越緊縮)", 0.50, 0.95, 0.75, step=0.05)
max_high_dist = exp_vcp.slider("距 52 週高點最大距離 (%)", 15, 45, 25, step=5)
vcp_filter = exp_vcp.radio("VCP 型態篩選", ["全部顯示 (依 VCP 分數排序)", "僅顯示 🔥 高度符合 VCP (4~5分)", "顯示 👀 觀察中以上 (3~5分)"])

exp_risk = st.sidebar.expander("🛡️ 資金風控設定", expanded=False)
max_risk_usd = exp_risk.number_input("單筆最大可承受虧損 (美元)", min_value=50, max_value=50000, value=500, step=50)
max_stop_pct = exp_risk.slider("最大可接受停損幅度上限 (%)", 3, 25, 15, step=1)

exp_fund = st.sidebar.expander("📊 財報與強勢股門檻", expanded=False)
min_roe = exp_fund.slider("最低 ROE 要求 (%)", 0, 50, 0)
max_de = exp_fund.slider("負債比上限 (D/E %)", 0, 500, 300)
max_pe = exp_fund.slider("本益比上限 (0=不限)", 0, 150, 0)
only_beat_spy = exp_fund.checkbox("僅顯示「近3個月跑贏大盤」強勢股", value=False)

bundles, regime = load_raw_market_data(custom_list)
if not bundles: st.warning("⚠️ 連線暫時繁忙，請點擊左側「🔄 強制刷新最新行情」重試。"); st.stop()

spy_3m, vix_val, tnx_val, spy_above_50, spy_above_200 = regime

if vix_val < 20 and spy_above_50: market_banner = f"🟢 大盤環境紅綠燈：多頭安全區 ｜ VIX：{vix_val} ｜ 10年美債：{tnx_val}% ｜ SPY站穩50日線"; st.success(market_banner)
elif vix_val > 26 and not spy_above_200: market_banner = f"🔴 大盤環境紅綠燈：高風險警戒區 ｜ VIX：{vix_val} ｜ 10年美債：{tnx_val}% ｜ SPY跌破200日年線"; st.error(market_banner)
else: market_banner = f"🟡 大盤環境紅綠燈：震盪觀察區 ｜ VIX：{vix_val} ｜ 10年美債：{tnx_val}% ｜ 市場處於震盪期"; st.warning(market_banner)

df = evaluate_vcp_dynamic(bundles, spy_3m, max_risk_usd, pivot_days, contraction_ratio, max_high_dist)
filtered_df = df[(df['目前股價'] >= 15) & (df['停損幅度(%)'] <= max_stop_pct) & (df['ROE (%)'] >= min_roe) & (df['負債比(%)'] <= max_de)]
if max_pe > 0: filtered_df = filtered_df[filtered_df['本益比'] <= max_pe]
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
col_left.subheader("📋 精選名單（👆 點擊任何一列，右側圖表與 AI 同步切換）")
styled_df = display_df.style.apply(lambda r: ['background-color: #d4edda; color: #155724; font-weight: bold;' if (c == '距買點(%)' and r[c] <= 2.5) else ('background-color: #f8d7da; color: #721c24; font-weight: bold;' if (c == '停損幅度(%)' and r[c] > 10.0) else '') for c in r.index], axis=1)
col_cfg = {
"ROE (%)": st.column_config.ProgressColumn("ROE (%)", format="%.1f%%", min_value=0, max_value=50),
"目前股價": st.column_config.NumberColumn("目前股價", format="$%.2f"),
"樞紐買點": st.column_config.NumberColumn("樞紐買點", format="$%.2f"),
"建議停損": st.column_config.NumberColumn("建議停損", format="$%.2f")
}
table_event = col_left.dataframe(styled_df, use_container_width=True, hide_index=True, height=620, on_select="rerun", selection_mode="single-row", column_config=col_cfg)
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
fig.update_layout(xaxis_rangeslider_visible=False, height=580, template="plotly_white", showlegend=False, margin=dict(l=10, r=10, t=35, b=10))
col_right.plotly_chart(fig, use_container_width=True)
st.divider()
st.subheader(f"🤖 AI 量化投資分析師（已自動讀取 {selected_symbol} 最新數據）")
if "chat_history" not in st.session_state: st.session_state.chat_history = []
q_col1, q_col2, q_col3 = st.columns(3)
quick_prompt = None
if q_col1.button(f"🔍 深度健檢 {selected_symbol} 的 VCP 勝率與風險", use_container_width=True): quick_prompt = f"請根據目前數據，深度評估 {selected_symbol} ({active_row['公司名稱']}) 的 VCP 型態、ROE、本益比、負債比與大盤環境，分析它現在突破的勝率與最大風險點。"
if q_col2.button(f"📋 幫我寫 {selected_symbol} 的分批進場與停利計畫", use_container_width=True): quick_prompt = f"假設我準備在 ${p_buy} 突破時買進 {s_shares} 股 {selected_symbol}，停損設在 ${p_stop}，請幫我設計一份具體的買進確認條件、分批停利目標與移動停損計畫。"
if q_col3.button("🗑️ 清除對話紀錄", use_container_width=True): st.session_state.chat_history = []; st.rerun()
user_typed = st.chat_input(f"輸入任何關於 {selected_symbol} 或美股投資的問題...")
active_prompt = quick_prompt if quick_prompt else user_typed
for msg in st.session_state.chat_history: st.chat_message(msg["role"]).markdown(msg["content"])
if not active_prompt: st.stop()
or_clean = "".join(c for c in str(or_key) if ord(c) < 128).strip()
gh_clean = "".join(c for c in str(gh_key) if ord(c) < 128).strip()
if not or_clean and not gh_clean: st.warning("⚠️ 請先在 Streamlit 後台 Settings -> Secrets 設定金鑰！"); st.stop()
st.session_state.chat_history.append({"role": "user", "content": active_prompt})
st.chat_message("user").markdown(active_prompt)
stock_context = f"你是專業華爾街VCP量化交易分析師，請用繁體中文條理分明回答，不要只重複股票代號。市場環境：{market_banner}。標的：{selected_symbol} ({active_row['公司名稱']})。VCP評級：{active_row['VCP評級']}，量能比：{active_row['量能比(%)']}%，跑贏大盤3M：{active_row['跑贏大盤(%)']}%。現價${active_row['目前股價']}，樞紐買點${p_buy}（距買點{active_row['距買點(%)']}%），建議停損${p_stop}（風險{active_row['停損幅度(%)']}%），建議買進{s_shares}股。ROE {active_row['ROE (%)']}%，本益比 {active_row['本益比']}，負債比{active_row['負債比(%)']}%。"
msgs = [{"role": "system", "content": stock_context}] + st.session_state.chat_history[-6:]
reply_text = ""
gh_url = "https://models.inference" + ".ai.azure.com"
or_url = "https://openrouter.ai" + "/api/v1"

if "僅使用 OpenRouter" not in ai_mode and gh_clean: reply_text = OpenAI(api_key=gh_clean, base_url=gh_url).chat.completions.create(model="gpt-4o-mini", messages=msgs).choices.pop(0).message.content
if not reply_text and "僅使用 GitHub" not in ai_mode and or_clean: reply_text = OpenAI(api_key=or_clean, base_url=or_url).chat.completions.create(model="meta-llama/llama-3.3-70b-instruct:free", messages=msgs).choices.pop(0).message.content

st.chat_message("assistant").markdown(reply_text)
st.session_state.chat_history.append({"role": "assistant", "content": reply_text})
