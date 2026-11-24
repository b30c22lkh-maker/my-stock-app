import streamlit as st
import yfinance as yf
from yfinance import EquityQuery
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from io import BytesIO
from openai import OpenAI
import requests
import akshare as ak
import time

st.set_page_config(page_title="美股 & 港股 VCP 多源量化交易終端機", page_icon="🏆", layout="wide")
st.title("🏆 美股 & 港股 VCP 實戰交易終端機 (三引擎多源互補版)")
import uuid
from datetime import timezone

@st.cache_resource
def get_traffic_tracker():
    return {"date": "", "daily_views": 0, "active_users": {}}

tracker = get_traffic_tracker()
now_ts = time.time()
today_macau = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

if tracker["date"] != today_macau: tracker["date"], tracker["daily_views"], tracker["active_users"] = today_macau, 0, {}
if "vid" not in st.session_state: st.session_state["vid"] = str(uuid.uuid4()); tracker["daily_views"] += 1

tracker["active_users"][st.session_state["vid"]] = now_ts
tracker["active_users"] = {k: v for k, v in tracker["active_users"].items() if now_ts - v <= 300}

st.sidebar.info(f"👁️ 今日瀏覽：{tracker['daily_views']} 次 ｜ 🟢 目前在線：{len(tracker['active_users'])} 人")


US_CORE_CANDIDATES = [
    'NVDA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'TSLA', 'AVGO', 'ORCL', 'CRM',
    'PLTR', 'APP', 'CELH', 'DUOL', 'CAVA', 'ANET', 'PANW', 'CRWD', 'SNOW', 'DDOG',
    'NET', 'ZS', 'TTD', 'HUBS', 'SHOP', 'COIN', 'HOOD', 'SOFI', 'NU', 'MELI',
    'UBER', 'ABNB', 'BKNG', 'NFLX', 'SPOT', 'LULU', 'DECK', 'ONON', 'ELF', 'SHAK',
    'CMG', 'COST', 'WMT', 'HD', 'TJX', 'LLY', 'NVO', 'UNH', 'ISRG', 'VRTX',
    'DXCM', 'AXON', 'HIMS', 'JPM', 'V', 'MA', 'GS', 'BLK', 'KKR', 'IBKR',
    'SPGI', 'FICO', 'CAT', 'URI', 'PWR', 'ETN', 'VRT', 'GEV', 'GE', 'FIX',
    'XOM', 'COP', 'EOG', 'CEG', 'VST', 'NEE', 'TSM', 'ASML', 'AMD', 'MU'
]

HK_CORE_CANDIDATES = [
    '0700.HK', '9988.HK', '3690.HK', '1810.HK', '1211.HK', '0981.HK', '2318.HK', '0388.HK', '0005.HK', '1299.HK',
    '0941.HK', '0883.HK', '0857.HK', '0386.HK', '1088.HK', '2899.HK', '3968.HK', '0939.HK', '1398.HK', '3988.HK',
    '2628.HK', '2382.HK', '2015.HK', '9868.HK', '9866.HK', '0175.HK', '2269.HK', '1177.HK', '1093.HK', '6160.HK',
    '9999.HK', '9618.HK', '9888.HK', '1024.HK', '6618.HK', '0241.HK', '9961.HK', '6690.HK', '2331.HK', '2020.HK',
    '9633.HK', '2319.HK', '0291.HK', '1929.HK', '1928.HK', '0027.HK', '1109.HK', '0688.HK', '0960.HK', '1997.HK',
    '0016.HK', '0001.HK', '0002.HK', '0003.HK', '0006.HK', '0011.HK', '0012.HK', '0066.HK', '0267.HK', '0288.HK',
    '0669.HK', '0762.HK', '0823.HK', '0914.HK', '0968.HK', '0992.HK', '1038.HK', '1044.HK', '1113.HK', '1209.HK',
    '1347.HK', '1876.HK', '2313.HK', '2333.HK', '2388.HK', '2688.HK', '3328.HK', '3888.HK', '6862.HK', '9992.HK'
]

HK_LOT_MAP = {
    '0700.HK': 100, '9988.HK': 100, '3690.HK': 100, '1810.HK': 200, '1211.HK': 500, '0981.HK': 500,
    '2318.HK': 500, '0388.HK': 100, '0005.HK': 400, '1299.HK': 200, '0941.HK': 500, '0883.HK': 1000,
    '2899.HK': 2000, '3968.HK': 500, '0939.HK': 1000, '1398.HK': 1000, '2382.HK': 100, '2015.HK': 100,
    '9868.HK': 100, '9866.HK': 10, '0175.HK': 1000, '2269.HK': 500, '6160.HK': 100, '9999.HK': 100,
    '9618.HK': 50, '9888.HK': 50, '1024.HK': 100, '9961.HK': 50, '2331.HK': 500, '2020.HK': 200,
    '9633.HK': 200, '0027.HK': 1000, '1928.HK': 400, '0669.HK': 500, '1347.HK': 1000, '3888.HK': 200, '9992.HK': 200
}

@st.cache_data(ttl=3600, show_spinner=False)
def get_market_regime(is_hk):
    idx_3m_ret, vix_val, tnx_val, idx_above_50, idx_above_200 = 0.0, 18.0, 4.2, True, True
    bench_ticker = "^HSI" if is_hk else "SPY"
    try:
        idx_hist = yf.Ticker(bench_ticker).history(period="1y")
        if len(idx_hist) >= 200:
            idx_close = idx_hist['Close'].iloc[-1]
            idx_3m_ret = ((idx_close - idx_hist['Close'].iloc[-63]) / idx_hist['Close'].iloc[-63]) * 100
            idx_above_50 = idx_close > idx_hist['Close'].rolling(50).mean().iloc[-1]
            idx_above_200 = idx_close > idx_hist['Close'].rolling(200).mean().iloc[-1]
        vix_hist = yf.Ticker("^VHSI" if is_hk else "^VIX").history(period="5d")
        if not vix_hist.empty: vix_val = round(vix_hist['Close'].iloc[-1], 2)
        if not is_hk:
            tnx_hist = yf.Ticker("^TNX").history(period="5d")
            if not tnx_hist.empty: tnx_val = round(tnx_hist['Close'].iloc[-1], 2)
    except Exception:
        pass
    return round(idx_3m_ret, 2), vix_val, tnx_val, idx_above_50, idx_above_200

@st.cache_data(ttl=300, show_spinner=False)
def get_major_indices(hk_mode):
    if hk_mode:
        res = []
        try:
            hk_df = ak.stock_hk_index_spot_sina()
            cn_df = ak.stock_zh_index_spot_sina()
            hk_targets = [("恒生指數", "恒生指数"), ("恒生科技指數", "恒生科技指数"), ("國企指數", "国企指数")]
            for label, kw in hk_targets:
                m = hk_df[hk_df['名称'].str.contains(kw, na=False)]
                if not m.empty:
                    r = m.iloc[0]
                    curr, diff, pct = float(r['最新价']), float(r['涨跌额']), float(r['涨跌幅'])
                    res.append((label, f"{curr:,.0f}", f"{diff:+.0f} ({pct:+.2f}%)"))
                else: res.append((label, "更新中", "0 (0.00%)"))
            cn_targets = [("上證綜指", "上证指数"), ("滬深300", "沪深300")]
            for label, kw in cn_targets:
                m = cn_df[cn_df['名称'] == kw]
                if not m.empty:
                    r = m.iloc[0]
                    curr, diff, pct = float(r['最新价']), float(r['涨跌额']), float(r['涨跌幅'])
                    res.append((label, f"{curr:,.0f}", f"{diff:+.0f} ({pct:+.2f}%)"))
                else: res.append((label, "更新中", "0 (0.00%)"))
            if len(res) == 5 and res[0][1] != "更新中": return res
        except Exception:
            pass
        items = [("恒生指數", "^HSI"), ("恒生科技(換算)", "3033.HK"), ("國企指數", "^HSCE"), ("上證綜指", "000001.SS"), ("滬深300", "000300.SS")]
    else:
        items = [("標普500", "^GSPC"), ("納斯達克100", "^NDX"), ("道瓊工業", "^DJI"), ("羅素2000", "^RUT"), ("費城半導體", "^SOX")]

    res = []
    for name, sym in items:
        try:
            fi = yf.Ticker(sym).fast_info
            mult = 1000 if sym == "3033.HK" else 1
            curr, prev = float(fi['lastPrice']) * mult, float(fi['previousClose']) * mult
            diff = curr - prev
            pct = (diff / prev) * 100 if prev else 0
            res.append((name, f"{curr:,.0f}", f"{diff:+.0f} ({pct:+.2f}%)"))
        except Exception:
            res.append((name, "更新中", "0 (0.00%)"))
    return res

@st.cache_data(ttl=3600, show_spinner=False)
def get_finnhub_consensus(symbol, fh_key):
    if not fh_key or ".HK" in symbol: return "", 0.0
    try:
        base = "https" + "://finnhub.io/api/v1"
        r1 = requests.get(f"{base}/stock/recommendation?symbol={symbol}&token={fh_key}", timeout=4).json()
        r2 = requests.get(f"{base}/stock/price-target?symbol={symbol}&token={fh_key}", timeout=4).json()
        rec_label = ""
        if isinstance(r1, list) and len(r1) > 0:
            latest = r1[0]
            sb, b, h, s, ss = latest.get('strongBuy', 0), latest.get('buy', 0), latest.get('hold', 0), latest.get('sell', 0), latest.get('strongSell', 0)
            tot = sb + b + h + s + ss
            if tot > 0:
                score = (sb*1 + b*2 + h*3 + s*4 + ss*5) / tot
                tag = "🟢 強力買入" if score <= 1.8 else ("🟢 買入" if score <= 2.4 else ("🟡 持有" if score <= 3.2 else "🔴 減持"))
                rec_label = f"{tag} ({tot}家)"
        target_mean = float(r2.get('targetMean', 0.0)) if isinstance(r2, dict) else 0.0
        return rec_label, target_mean
    except Exception:
        return "", 0.0

@st.cache_data(ttl=1800, show_spinner=False)
def get_finnhub_news(symbol, fh_key):
    if not fh_key or ".HK" in symbol: return []
    try:
        base = "https" + "://finnhub.io/api/v1"
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        data = requests.get(f"{base}/company-news?symbol={symbol}&from={week_ago}&to={today}&token={fh_key}", timeout=5).json()
        if isinstance(data, list): return data[:3]
    except Exception:
        pass
    return []

@st.cache_data(ttl=3600, show_spinner=False)
def get_expanded_candidates(is_hk, extra_tickers):
    if is_hk:
        hk_strong = []
        try:
            q_hk = EquityQuery('and', [EquityQuery('eq', ['region', 'hk']), EquityQuery('gt', ['intradayprice', 2]), EquityQuery('gt', ['intradaymarketcap', 5_000_000_000]), EquityQuery('gt', ['avgdailyvol3m', 500000])])
            res_hk = yf.screen(q_hk, size=120, sortField='avgdailyvol3m', sortAsc=False)
            hk_strong = [item.get('symbol') for item in res_hk.get('quotes', []) if item.get('symbol')]
        except Exception:
            hk_strong = []
        return list(dict.fromkeys(extra_tickers + hk_strong + HK_CORE_CANDIDATES))[:180]
    
    dark_horses, leaders, active_backup = [], [], []
    try:
        q_horse = EquityQuery('and', [EquityQuery('eq', ['region', 'us']), EquityQuery('gt', ['intradayprice', 15]), EquityQuery('btwn', ['intradaymarketcap', 1_500_000_000, 20_000_000_000]), EquityQuery('gt', ['avgdailyvol3m', 350000]), EquityQuery('gt', ['quarterlyrevenuegrowth', 0.15])])
        res1 = yf.screen(q_horse, size=100, sortField='avgdailyvol3m', sortAsc=False)
        dark_horses = [item.get('symbol') for item in res1.get('quotes', []) if item.get('symbol')]
    except Exception: pass
    try:
        q_lead = EquityQuery('and', [EquityQuery('eq', ['region', 'us']), EquityQuery('gt', ['intradayprice', 15]), EquityQuery('gt', ['intradaymarketcap', 20_000_000_000]), EquityQuery('gt', ['avgdailyvol3m', 400000])])
        res2 = yf.screen(q_lead, size=100, sortField='percentchange', sortAsc=False)
        leaders = [item.get('symbol') for item in res2.get('quotes', []) if item.get('symbol')]
    except Exception: pass
    try:
        q_act = EquityQuery('and', [EquityQuery('eq', ['region', 'us']), EquityQuery('gt', ['intradayprice', 15]), EquityQuery('gt', ['intradaymarketcap', 1_000_000_000]), EquityQuery('gt', ['avgdailyvol3m', 300000])])
        res3 = yf.screen(q_act, size=100, sortField='avgdailyvol3m', sortAsc=False)
        active_backup = [item.get('symbol') for item in res3.get('quotes', []) if item.get('symbol')]
    except Exception: pass
    return list(dict.fromkeys(extra_tickers + dark_horses + leaders + active_backup + US_CORE_CANDIDATES))[:180]

def enrich_single_stock(symbol, hist, is_hk, fh_key):
    price = float(hist['Close'].iloc[-1])
    if (not is_hk and price < 15) or (is_hk and price < 1.0): return None
    info = {}
    try: info = yf.Ticker(symbol).info or {}
    except Exception: info = {}
    
    mcap = info.get('marketCap') or (5_000_000_000 if is_hk else 15_000_000_000)
    if not is_hk and mcap < 1_000_000_000: return None

    lot_size = HK_LOT_MAP.get(symbol, info.get('lotSize') or 100) if is_hk else 1
    roe_val = round(info.get('returnOnEquity') * 100, 2) if info.get('returnOnEquity') is not None else 0.0
    pe_val = round(info.get('trailingPE'), 2) if info.get('trailingPE') else 0.0
    de_val = round(info.get('debtToEquity'), 2) if info.get('debtToEquity') is not None else 0.0

    if roe_val == 0 or pe_val == 0 or de_val == 0:
        try:
            t = yf.Ticker(symbol)
            inc, bal = t.income_stmt, t.balance_sheet
            if inc is not None and not inc.empty and bal is not None and not bal.empty:
                ni_rows = [r for r in inc.index if 'Net Income' in str(r)]
                eps_rows = [r for r in inc.index if 'Diluted EPS' in str(r) or 'Basic EPS' in str(r)]
                eq_rows = [r for r in bal.index if 'Stockholders Equity' in str(r) or 'Total Equity' in str(r)]
                debt_rows = [r for r in bal.index if 'Total Debt' in str(r)]
                eq = float(bal.loc[eq_rows.pop(0)].dropna().iloc[-1]) if eq_rows else 0
                if roe_val == 0 and ni_rows and eq > 0: roe_val = round((float(inc.loc[ni_rows.pop(0)].dropna().iloc[-1]) / eq) * 100, 2)
                if pe_val == 0 and eps_rows:
                    eps = float(inc.loc[eps_rows.pop(0)].dropna().iloc[-1])
                    if eps > 0: pe_val = round(price / eps, 2)
                if de_val == 0 and debt_rows and eq > 0: de_val = round((float(bal.loc[debt_rows.pop(0)].dropna().iloc[-1]) / eq) * 100, 2)
        except Exception:
            pass

    rec_str, target_p = get_finnhub_consensus(symbol, fh_key)
    if not rec_str:
        rec_map = {'strong_buy': '🟢 強力買入', 'buy': '🟢 買入', 'hold': '🟡 持有', 'underperform': '🟠 減持', 'sell': '🔴 賣出'}
        rec_str = rec_map.get(str(info.get('recommendationKey', '')).lower(), '⚪ 暫無評級')
    if target_p == 0.0 and info.get('targetMeanPrice'):
        target_p = float(info.get('targetMeanPrice'))
    upside_pct = round(((target_p - price) / price) * 100, 1) if target_p > 0 else 0.0

    return {'symbol': symbol, 'info': info, 'price': price, 'mcap': mcap, 'lot_size': lot_size, 'lot_cost': round(price * lot_size, 0), 'roe_val': roe_val, 'pe_val': pe_val, 'de_val': de_val, 'rec_str': rec_str, 'target_p': round(target_p, 2), 'upside_pct': upside_pct, 'hist': hist}

@st.cache_data(ttl=3600, show_spinner=False)
def load_raw_market_data(is_hk, extra_tickers, fh_key):
    regime = get_market_regime(is_hk)
    all_symbols = get_expanded_candidates(is_hk, extra_tickers)
    mkt_name = "港股通與恒指成分" if is_hk else "全美高成長黑馬 + 領頭羊 + 核心池"
    with st.spinner(f"⚡ 正在多源同步【{mkt_name}】共 {len(all_symbols)} 檔 K 線、財報與投行評級（約 15 秒）..."):
        raw_data = yf.download(all_symbols, period="1y", group_by="ticker", threads=True, progress=False)
        valid_hists = {}
        for sym in all_symbols:
            try:
                df_sym = raw_data[sym].dropna(subset=['Close']) if len(all_symbols) > 1 else raw_data.dropna(subset=['Close'])
                if len(df_sym) >= 150: valid_hists[sym] = df_sym
            except Exception: pass
        with ThreadPoolExecutor(max_workers=3) as executor:
            bundles = list(executor.map(lambda s: enrich_single_stock(s, valid_hists.get(s), is_hk, fh_key), list(valid_hists.keys())))
    return [b for b in bundles if b is not None], regime

def evaluate_vcp_dynamic(bundles, bench_ret, max_risk_amt, pivot_days, contraction_ratio, max_high_dist, is_hk):
    rows = []
    for b in bundles:
        symbol, info, price, mcap, hist = b['symbol'], b['info'], b['price'], b['mcap'], b['hist']
        close, high, low, vol = hist['Close'], hist['High'], hist['Low'], hist['Volume']
        rs_vs_idx = round(((close.iloc[-1] - close.iloc[-63]) / close.iloc[-63]) * 100 - bench_ret, 2)
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
        risk_per_share = max(pivot_price - stop_loss, 0.05)
        stop_loss_pct = round((risk_per_share / pivot_price) * 100, 1)
        suggested_shares = max((int(max_risk_amt // risk_per_share) // b['lot_size']) * b['lot_size'], b['lot_size']) if (is_hk and pivot_price * b['lot_size'] <= max_risk_amt * 15) else (0 if is_hk else int(max_risk_amt // risk_per_share))
        row_dict = {'股票代號': symbol, 'VCP評級': vcp_status, 'VCP分數': vcp_score, '目前股價': round(price, 2), '樞紐買點': pivot_price, '距買點(%)': dist_to_pivot, '建議停損': stop_loss, '停損幅度(%)': stop_loss_pct, '建議股數': suggested_shares}
        if is_hk: row_dict['每手股數'], row_dict['每手入場費(HK$)'] = b['lot_size'], round(pivot_price * b['lot_size'], 0)
        row_dict.update({'投行共識': b['rec_str'], '目標價': b['target_p'], '目標空間(%)': b['upside_pct'], 'ROE (%)': b['roe_val'], '本益比': b['pe_val'], '負債比(%)': b['de_val'], '量能比(%)': int(vol_ratio), '跑贏大盤(%)': rs_vs_idx, '公司名稱': info.get('shortName', symbol)})
        rows.append(row_dict)
    return pd.DataFrame(rows)

st.sidebar.header("🌎 選擇交易市場")
market_choice = st.sidebar.radio("切換掃描市場", ["🇺🇸 美股市場 (USD)", "🇭🇰 港股市場 (HKD)"], horizontal=True)
is_hk = "港股" in market_choice
curr_sym = "HK$" if is_hk else "$"
st.sidebar.divider()
st.sidebar.header("🎛️ VCP 交易決策控制台")
custom_input = st.sidebar.text_input("🔍 額外港股代號（直接輸入數字如 700, 9988）" if is_hk else "🔍 額外美股代號（逗號分隔）", placeholder="例如: 700, 9988, 1211" if is_hk else "例如: ADPT, TSM, AMD")
custom_list = [f"{t.strip().replace('.HK','').replace('.hk','').zfill(4)}.HK" for t in custom_input.split(",") if t.strip()] if is_hk else [t.strip().upper() for t in custom_input.split(",") if t.strip()]
max_lot_fee = st.sidebar.number_input("💰 港股每手入場費上限 (HK$)", min_value=1000, max_value=200000, value=30000, step=1000) if is_hk else 999999999
if st.sidebar.button("🔄 強制刷新最新行情", use_container_width=True): st.cache_data.clear(); st.rerun()
or_key = st.secrets.get("OPENROUTER_API_KEY", "")
gh_key = st.secrets.get("GITHUB_API_KEY", "")
fh_key = "".join(c for c in str(st.secrets.get("FINNHUB_API_KEY", "")) if ord(c) < 128).strip()
ai_mode = st.sidebar.selectbox("🤖 AI 極速分析師模式", ["⚡ 雙引擎極速接力 (GitHub GPT-4o-mini 優先 ➔ OpenRouter)", "僅使用 OpenRouter", "僅使用 GitHub Models (GPT-4o-mini)"])
exp_vcp = st.sidebar.expander("🎯 VCP 型態引擎參數（即時重算）", expanded=False)
pivot_days = exp_vcp.slider("樞紐突破與停損觀察天數", 10, 30, 15, step=5)
contraction_ratio = exp_vcp.slider("波動收縮嚴格度 (越小越緊縮)", 0.50, 0.95, 0.75, step=0.05)
max_high_dist = exp_vcp.slider("距 52 週高點最大距離 (%)", 15, 45, 25, step=5)
vcp_filter = exp_vcp.radio("VCP 型態篩選", ["全部顯示 (依 VCP 分數排序)", "僅顯示 🔥 高度符合 VCP (4~5分)", "顯示 👀 觀察中以上 (3~5分)"])
exp_risk = st.sidebar.expander(f"🛡️ 資金風控設定 ({curr_sym})", expanded=False)
default_risk = 4000 if is_hk else 500
max_risk_amt = exp_risk.number_input(f"單筆最大可承受虧損 ({curr_sym})", min_value=50, max_value=500000, value=default_risk, step=100)
max_stop_pct = exp_risk.slider("最大可接受停損幅度上限 (%)", 3, 25, 15, step=1)
exp_fund = st.sidebar.expander("📊 財報與強勢股門檻", expanded=False)
min_roe = exp_fund.slider("最低 ROE 要求 (%)", 0, 50, 0)
max_de = exp_fund.slider("負債比上限 (D/E %)", 0, 500, 300)
max_pe = exp_fund.slider("本益比上限 (0=不限)", 0, 150, 0)
only_beat_spy = exp_fund.checkbox("僅顯示「近3個月跑贏大盤」強勢股", value=False)
bundles, regime = load_raw_market_data(is_hk, custom_list, fh_key)
if not bundles: st.warning("⚠️ 連線暫時繁忙，請點擊左側「🔄 強制刷新最新行情」重試。"); st.stop()
bench_3m, vix_val, tnx_val, idx_above_50, idx_above_200 = regime
idx_label = "恒生指數 (HSI)" if is_hk else "標普500 (SPY)"
vix_label = "VHSI 恒指波幅" if is_hk else f"VIX：{vix_val} ｜ 10年美債：{tnx_val}%"
if vix_val < 22 and idx_above_50: market_banner = f"🟢 {idx_label}紅綠燈：多頭安全區 ｜ {vix_label} ｜ 大盤站穩50日線"; st.success(market_banner)
elif vix_val > 28 and not idx_above_200: market_banner = f"🔴 {idx_label}紅綠燈：高風險警戒區 ｜ {vix_label} ｜ 大盤跌破200日年線"; st.error(market_banner)
else: market_banner = f"🟡 {idx_label}紅綠燈：震盪觀察區 ｜ {vix_label} ｜ 市場處於震盪整理期"; st.warning(market_banner)
idx_cols = st.columns(5)
for col, (i_name, i_val, i_delta) in zip(idx_cols, get_major_indices(is_hk)): col.metric(i_name, i_val, i_delta)
df = evaluate_vcp_dynamic(bundles, bench_3m, max_risk_amt, pivot_days, contraction_ratio, max_high_dist, is_hk)
filtered_df = df[df['股票代號'].isin(custom_list) | ((df['停損幅度(%)'] <= max_stop_pct) & (df['ROE (%)'] >= min_roe) & (df['負債比(%)'] <= max_de))]
if is_hk: filtered_df = filtered_df[filtered_df['股票代號'].isin(custom_list) | (filtered_df['每手入場費(HK$)'] <= max_lot_fee)]
if max_pe > 0: filtered_df = filtered_df[filtered_df['股票代號'].isin(custom_list) | (filtered_df['本益比'] <= max_pe)]
if only_beat_spy: filtered_df = filtered_df[filtered_df['股票代號'].isin(custom_list) | (filtered_df['跑贏大盤(%)'] > 0)]
if "高度符合" in vcp_filter: filtered_df = filtered_df[filtered_df['VCP分數'] >= 4]
if "觀察中" in vcp_filter: filtered_df = filtered_df[filtered_df['VCP分數'] >= 3]
filtered_df = filtered_df.sort_values(by=['VCP分數', '距買點(%)'], ascending=[False, True]).reset_index(drop=True)
c1, c2, c3, c4 = st.columns(4)
c1.metric("掃描優質池（上限180檔）", f"{len(df)} 檔")
c2.metric("符合風控與手數門檻", f"{len(filtered_df)} 檔")
vcp_count = len(filtered_df[filtered_df['VCP分數'] >= 4])
c3.metric("🔥 高度符合 VCP 標的", f"{vcp_count} 檔")
c4.metric(f"{idx_label} 近3月基準", f"{bench_3m} %")
st.divider()
col_left, col_right = st.columns([1.08, 0.92])
display_df = filtered_df.drop(columns=['VCP分數'])
col_left.subheader("📋 精選名單（👆 點擊任何一列，右側圖表與 AI 同步切換）")
styled_df = display_df.style.apply(lambda r: ['background-color: #d4edda; color: #155724; font-weight: bold;' if (c == '距買點(%)' and r[c] <= 2.5) else ('background-color: #f8d7da; color: #721c24; font-weight: bold;' if (c == '停損幅度(%)' and r[c] > 10.0) else '') for c in r.index], axis=1).format(precision=2)
col_cfg = {
"ROE (%)": st.column_config.ProgressColumn("ROE (%)", format="%.1f%%", min_value=0, max_value=50),
"目前股價": st.column_config.NumberColumn("目前股價", format=f"{curr_sym}%.2f"),
"樞紐買點": st.column_config.NumberColumn("樞紐買點", format=f"{curr_sym}%.2f"),
"建議停損": st.column_config.NumberColumn("建議停損", format=f"{curr_sym}%.2f"),
"目標價": st.column_config.NumberColumn("目標價", format=f"{curr_sym}%.2f")
}
table_event = col_left.dataframe(styled_df, use_container_width=True, hide_index=True, height=620, on_select="rerun", selection_mode="single-row", column_config=col_cfg)
output = BytesIO()
writer = pd.ExcelWriter(output, engine='openpyxl')
display_df.to_excel(writer, sheet_name='VCP交易決策名單', index=False)
df.drop(columns=['VCP分數']).to_excel(writer, sheet_name='全市場掃描總表', index=False)
writer.close()
col_left.download_button(label="📥 下載 Excel 交易風控報表", data=output.getvalue(), file_name=f"{'港股' if is_hk else '美股'}VCP交易決策_{pivot_days}日樞紐.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
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
m1.metric("突破買進價", f"{curr_sym}{p_buy}")
m2.metric("防守停損價", f"{curr_sym}{p_stop}", f"-{active_row['停損幅度(%)']}%", delta_color="inverse")
m3.metric("建議買進股數", f"{s_shares} 股")
m4.metric("預計投入本金", f"{curr_sym}{total_capital:,.0f}")
hist = yf.Ticker(selected_symbol).history(period="1y")
hist['SMA50'] = hist['Close'].rolling(window=50).mean()
hist['SMA150'] = hist['Close'].rolling(window=150).mean()
hist['SMA200'] = hist['Close'].rolling(window=200).mean()
hist['Vol_MA50'] = hist['Volume'].rolling(window=50).mean()
delta = hist['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
hist['RSI'] = 100 - (100 / (1 + (gain / loss)))
fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.65, 0.18, 0.17], subplot_titles=(f"{selected_symbol} 近{pivot_days}日樞紐突破 ({curr_sym}{p_buy}) 與停損 ({curr_sym}{p_stop})", "成交量與 50 日均量", "RSI (14日)"))
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
fig.update_layout(xaxis_rangeslider_visible=False, height=560, template="plotly_white", showlegend=False, margin=dict(l=10, r=10, t=35, b=10))
col_right.plotly_chart(fig, use_container_width=True)
news_list = get_finnhub_news(selected_symbol, fh_key)
exp_news = col_right.expander(f"📰 {selected_symbol} 最新華爾街頭條新聞（Finnhub 即時情報）", expanded=False)
for n in news_list: exp_news.markdown(f"- **[{n.get('headline', '')}]({n.get('url', '#')})** *({n.get('source', '')})*")

st.divider()
st.subheader(f"🤖 AI 量化投資分析師（已自動讀取 {selected_symbol} 財報、投行評級與新聞）")

if "chat_history" not in st.session_state: st.session_state.chat_history = []

q_col1, q_col2, q_col3 = st.columns(3)
quick_prompt = None
if q_col1.button(f"🔍 深度健檢 {selected_symbol} 的 VCP 勝率與風險", use_container_width=True): quick_prompt = f"請根據目前數據，深度評估 {selected_symbol} ({active_row['公司名稱']}) 的 VCP 型態、投行共識目標價、ROE、本益比與大盤環境，分析它現在突破的勝率與最大風險點。"
if q_col2.button(f"📋 幫我寫 {selected_symbol} 的分批進場與停利計畫", use_container_width=True): quick_prompt = f"假設我準備在 {curr_sym}{p_buy} 突破時買進 {s_shares} 股 {selected_symbol}，停損設在 {curr_sym}{p_stop}，請幫我設計一份具體的買進確認條件、分批停利目標與移動停損計畫。"
if q_col3.button("🗑️ 清除對話紀錄", use_container_width=True): st.session_state.chat_history = []; st.rerun()

user_typed = st.chat_input(f"輸入任何關於 {selected_symbol} 或{'港股' if is_hk else '美股'}投資的問題...")
active_prompt = quick_prompt if quick_prompt else user_typed

for msg in st.session_state.chat_history: st.chat_message(msg["role"]).markdown(msg["content"])

if not active_prompt: st.stop()

or_clean = "".join(c for c in str(or_key) if ord(c) < 128).strip()
gh_clean = "".join(c for c in str(gh_key) if ord(c) < 128).strip()

if not or_clean and not gh_clean: st.warning("⚠️ 請先在 Streamlit 後台 Settings -> Secrets 設定 AI 金鑰！"); st.stop()

st.session_state.chat_history.append({"role": "user", "content": active_prompt})
st.chat_message("user").markdown(active_prompt)
news_summary = "；".join([n.get('headline', '') for n in news_list]) if news_list else "無近期突發新聞"
stock_context = f"你是專業{'港股通與' if is_hk else '華爾街'}VCP量化交易分析師，請用繁體中文條理分明回答，不要只重複股票代號。市場環境：{market_banner}。標的：{selected_symbol} ({active_row['公司名稱']})。VCP評級：{active_row['VCP評級']}，量能比：{active_row['量能比(%)']}%，跑贏大盤3M：{active_row['跑贏大盤(%)']}%。現價{curr_sym}{active_row['目前股價']}，樞紐買點{curr_sym}{p_buy}（距買點{active_row['距買點(%)']}%），建議停損{curr_sym}{p_stop}（風險{active_row['停損幅度(%)']}%），建議買進{s_shares}股。投行共識：{active_row['投行共識']}，目標價{curr_sym}{active_row['目標價']}（空間{active_row['目標空間(%)']}%）。ROE {active_row['ROE (%)']}%，本益比 {active_row['本益比']}，負債比{active_row['負債比(%)']}%。近期新聞：{news_summary}。"
msgs = [{"role": "system", "content": stock_context}] + st.session_state.chat_history[-6:]

gh_url = "https" + "://models.github.ai/inference"
or_url = "https" + "://openrouter.ai/api/v1"
reply_text = ""

if "僅使用 OpenRouter" not in ai_mode and gh_clean:
    try:
        stream = OpenAI(api_key=gh_clean, base_url=gh_url, timeout=8.0).chat.completions.create(model="gpt-4o-mini", messages=msgs, stream=True)
        reply_text = st.chat_message("assistant").write_stream(c.delta.content for chunk in stream for c in chunk.choices if c.delta.content)
    except Exception: reply_text = ""

if not reply_text and "僅使用 GitHub" not in ai_mode and or_clean:
    try:
        stream = OpenAI(api_key=or_clean, base_url=or_url, timeout=15.0).chat.completions.create(model="openrouter/free", messages=msgs, stream=True)
        reply_text = st.chat_message("assistant").write_stream(c.delta.content for chunk in stream for c in chunk.choices if c.delta.content)
    except Exception as e: reply_text = f"❌ AI 引擎暫時繁忙，請稍後再試（{e}）"; st.chat_message("assistant").markdown(reply_text)

st.session_state.chat_history.append({"role": "assistant", "content": reply_text})

