"""
Daily Portfolio Rebalancing & Market Signal Screener
Fetches live ETF prices, tracks Benchmark Rolling ATH / MDD, evaluates Dynamic Allocation state,
and sends actionable rebalancing weights (%) and weight deltas (%p) to Google Apps Script.
"""

import os
import json
import datetime
import requests
import yfinance as yf
import pandas as pd

GAS_WEBAPP_URL = os.environ.get("GAS_WEBAPP_URL", "")
GAS_AUTH_PIN = os.environ.get("GAS_AUTH_PIN", "")
ACTIVE_SLOT_ID = os.environ.get("ACTIVE_SLOT_ID", "1")

KOREAN_ETF_NAMES = {
    "^NDX": "나스닥 100 지수 (^NDX)",
    "^GSPC": "S&P 500 지수 (^GSPC)",
    "^KS11": "코스피 지수 (^KS11)",
    "^IXIC": "나스닥 종합지수 (^IXIC)",
    "069500.KS": "KODEX 200 (069500)",
    "069500": "KODEX 200 (069500)",
    "122630.KS": "KODEX 레버리지 (122630)",
    "122630": "KODEX 레버리지 (122630)",
    "379800.KS": "KODEX 미국나스닥100TR (379800)",
    "379800": "KODEX 미국나스닥100TR (379800)",
    "379810.KS": "KODEX 미국S&P500TR (379810)",
    "379810": "KODEX 미국S&P500TR (379810)",
    "448290.KS": "ACE 미국배당다우존스 (448290)",
    "448290": "ACE 미국배당다우존스 (448290)",
    "453850.KS": "ACE 미국30년국채액티브 (453850)",
    "453850": "ACE 미국30년국채액티브 (453850)",
    "252670.KS": "KODEX 200선물인버스2X (252670)",
    "252670": "KODEX 200선물인버스2X (252670)",
}

def format_ticker_display(ticker):
    t_clean = str(ticker).strip().upper()
    if t_clean in KOREAN_ETF_NAMES:
        return KOREAN_ETF_NAMES[t_clean]
    if t_clean.endswith(".KS"):
        code = t_clean.replace(".KS", "")
        return f"{code} ({code})"
    return t_clean

def fetch_active_strategy_from_gas(gas_url, pin=""):
    if not gas_url:
        return None, 1
    req_url = f"{gas_url}?action=get_strategy_slots"
    if pin:
        req_url += f"&pin={pin}"
    try:
        resp = requests.get(req_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                slots = data.get("slots", [])
                active_id = data.get("activeSlotId", 1)
                for s in slots:
                    if s.get("id") == active_id or s.get("isActive"):
                        return s, active_id
                if slots:
                    return slots[0], active_id
    except Exception as e:
        print(f"[WARN] Failed to fetch strategy slots from GAS: {e}")
    return None, 1

def fetch_user_holdings_from_gas(gas_url, pin=""):
    if not gas_url:
        return []
    req_url = f"{gas_url}?action=holdings"
    if pin:
        req_url += f"&pin={pin}"
    try:
        resp = requests.get(req_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                return data.get("portfolioHoldings", [])
    except Exception as e:
        print(f"[WARN] Failed to fetch holdings: {e}")
    return []

def evaluate_portfolio_signal(strategy_config=None, gas_url=""):
    print("=" * 60)
    print("[INFO] Running Daily Dynamic Asset Allocation Signal Engine")
    print(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. Load Strategy Config
    if strategy_config is None:
        from asset_engine import get_default_strategy_config
        strategy_config = get_default_strategy_config()

    strat_name = strategy_config.get("name", "동적 자산배분 전략")
    benchmark_ticker = strategy_config.get("benchmark", "QQQ")
    base_weights = strategy_config.get("baseWeights", {"QQQ": 0.60, "SCHD": 0.40})
    drop_stages = sorted(strategy_config.get("dropStages", []), key=lambda x: x.get("threshold", 0.0), reverse=True)
    recovery_stages = sorted(strategy_config.get("recoveryStages", []), key=lambda x: x.get("recovery", 0.0))
    gain_threshold_pct = strategy_config.get("gainThresholdPct", 20.0)
    base_recovery_pct = strategy_config.get("baseRecoveryPct", 0.0)
    tolerance_band_pct = strategy_config.get("toleranceBandPct", 5.0)

    print(f"[INFO] Active Strategy: {strat_name}")
    print(f"       Benchmark: {benchmark_ticker}")
    print(f"       Base Weights: {base_weights}")
    print(f"       Drop Stages: {len(drop_stages)} levels | Recovery Stages: {len(recovery_stages)} levels")

    # 2. Collect all required tickers
    all_tickers = set(base_weights.keys())
    all_tickers.add(benchmark_ticker)
    for s in drop_stages:
        all_tickers.update(s.get("weights", {}).keys())
    for s in recovery_stages:
        all_tickers.update(s.get("weights", {}).keys())

    # 3. Fetch Live Daily Prices via yfinance (last 365 days)
    print(f"\n[INFO] Fetching latest price data for: {list(all_tickers)}...")
    start_date = (datetime.date.today() - datetime.timedelta(days=400)).strftime("%Y-%m-%d")
    
    try:
        raw_df = yf.download(
            tickers=list(all_tickers),
            start=start_date,
            auto_adjust=False,
            progress=False
        )
    except Exception as e:
        print(f"[ERROR] Failed to fetch yfinance data: {e}")
        return None

    adj_close = raw_df['Adj Close'] if 'Adj Close' in raw_df else raw_df['Close']
    close_df = raw_df['Close']

    # Get Benchmark Price Series & Calculate Drawdown
    if benchmark_ticker not in adj_close.columns:
        print(f"[ERROR] Benchmark {benchmark_ticker} missing in downloaded data.")
        return None

    bm_series = adj_close[benchmark_ticker].dropna()
    bm_current_close = float(close_df[benchmark_ticker].dropna().iloc[-1])
    bm_current_adj = float(bm_series.iloc[-1])
    bm_ath = float(bm_series.max())
    bm_mdd_pct = ((bm_current_adj - bm_ath) / bm_ath) * 100.0 if bm_ath > 0 else 0.0

    print(f"\n[시장 지표 분석]")
    print(f" - 기준 지수 ({benchmark_ticker}) 현재가: ${bm_current_close:,.2f}")
    print(f" - 최고가 (ATH): ${bm_ath:,.2f}")
    print(f" - 고점 대비 하락률 (MDD): {bm_mdd_pct:.2f}%")

    # 4. Time-Series State Machine Evaluation (Unified Adjustment Stages)
    sorted_drops = sorted(drop_stages, key=lambda x: x.get("threshold", 0.0), reverse=True) # e.g. -10, -20, -30
    norm_base = {k: float(v) for k, v in base_weights.items()}
    tot_b = sum(norm_base.values())
    if tot_b > 0:
        norm_base = {k: v / tot_b for k, v in norm_base.items()}

    current_stage_idx = -1
    drop_entry_peak = 0.0
    current_bm_peak = 0.0
    last_rebalance_nav = 100000000.0
    current_nav = 100000000.0
    holdings = {t: 0.0 for t in all_tickers}
    fee_rate = 0.0015

    # Initialize holdings at day 0
    day0_prices = {t: float(adj_close[t].dropna().iloc[0]) if t in adj_close and len(adj_close[t].dropna()) > 0 else 1.0 for t in all_tickers}
    for t, w in norm_base.items():
        p0 = day0_prices.get(t, 1.0)
        holdings[t] = (current_nav * w * (1.0 - fee_rate)) / p0 if p0 > 0 else 0.0

    eval_dates = list(bm_series.index)
    for d_idx, dt in enumerate(eval_dates):
        current_p = float(bm_series.loc[dt])
        if current_p > current_bm_peak:
            current_bm_peak = current_p
        current_bm_dd = ((current_p - current_bm_peak) / current_bm_peak) * 100.0 if current_bm_peak > 0 else 0.0

        # Calculate current NAV
        day_prices = {t: float(adj_close[t].loc[dt]) if t in adj_close and dt in adj_close[t].index and not pd.isna(adj_close[t].loc[dt]) else 1.0 for t in all_tickers}
        current_nav = sum(holdings[t] * day_prices.get(t, 1.0) for t in all_tickers)

        target_w = None
        next_stage_idx = current_stage_idx

        if len(sorted_drops) > 0:
            if current_stage_idx < 0:
                deepest_idx = -1
                for i, st in enumerate(sorted_drops):
                    if current_bm_dd <= st.get("threshold", 0.0):
                        deepest_idx = i
                if deepest_idx >= 0:
                    next_stage_idx = deepest_idx
                    target_w = sorted_drops[deepest_idx].get("weights", {})
                    drop_entry_peak = current_bm_peak
                elif gain_threshold_pct > 0:
                    gain_pct = ((current_nav - last_rebalance_nav) / last_rebalance_nav) * 100.0
                    if gain_pct >= gain_threshold_pct:
                        target_w = norm_base
                        next_stage_idx = -1
            else:
                deeper_idx = current_stage_idx
                for i in range(current_stage_idx + 1, len(sorted_drops)):
                    if current_bm_dd <= sorted_drops[i].get("threshold", 0.0):
                        deeper_idx = i
                if deeper_idx > current_stage_idx:
                    next_stage_idx = deeper_idx
                    target_w = sorted_drops[deeper_idx].get("weights", {})
                elif current_stage_idx > 0:
                    upper_barrier = sorted_drops[current_stage_idx - 1].get("threshold", 0.0)
                    if current_bm_dd >= upper_barrier:
                        next_stage_idx = current_stage_idx - 1
                        target_w = sorted_drops[next_stage_idx].get("weights", {})
                else:
                    gain_from_peak = ((current_p - drop_entry_peak) / drop_entry_peak) * 100.0 if drop_entry_peak > 0 else current_bm_dd
                    if gain_from_peak >= base_recovery_pct:
                        next_stage_idx = -1
                        target_w = norm_base
                        drop_entry_peak = 0.0
        elif gain_threshold_pct > 0:
            gain_pct = ((current_nav - last_rebalance_nav) / last_rebalance_nav) * 100.0
            if gain_pct >= gain_threshold_pct:
                target_w = norm_base
                next_stage_idx = -1

        if target_w is not None:
            # Rebalance
            tot = sum(target_w.values())
            norm_tw = {k: v / tot for k, v in target_w.items()} if tot > 0 else norm_base
            for t in all_tickers:
                tw = norm_tw.get(t, 0.0)
                p = day_prices.get(t, 1.0)
                if p > 0:
                    t_val = current_nav * tw
                    cur_val = holdings[t] * p
                    fee = abs(t_val - cur_val) * fee_rate
                    holdings[t] = (t_val - fee) / p
                else:
                    holdings[t] = 0.0
            current_nav = sum(holdings[t] * day_prices.get(t, 1.0) for t in all_tickers)
            current_stage_idx = next_stage_idx
            last_rebalance_nav = current_nav

    # Determine final active state name and target weights for today
    if current_stage_idx >= 0 and current_stage_idx < len(sorted_drops):
        st = sorted_drops[current_stage_idx]
        current_state = st.get("name", f"하락 {st.get('threshold', 0.0)}%")
        raw_tw = st.get("weights", {})
        rec_str = f"전고점 +{base_recovery_pct:.0f}% 돌파" if base_recovery_pct > 0 else "전고점(0.0%) 복귀"
        advice_msg = f"[낙폭 국면 유지] {benchmark_ticker} 고점 대비 {bm_mdd_pct:.1f}% 수준. {current_state} 비중 유지하며 {rec_str} 대기."
    else:
        current_state = "기본 (정상 운용)"
        raw_tw = norm_base
        advice_msg = f"[정상 운용] {benchmark_ticker} 정상 범위 (MDD {bm_mdd_pct:.1f}%). 기본 포트폴리오 비중 유지."

    # Normalize target weights to 100%
    tot_w = sum(raw_tw.values())
    if tot_w > 0:
        target_weights = {k: round((v / tot_w) * 100.0, 1) for k, v in raw_tw.items()}
    else:
        target_weights = {k: round(v * 100.0, 1) for k, v in norm_base.items()}

    delta_weights = {}
    for t in all_tickers:
        tgt = target_weights.get(t, 0.0)
        base = norm_base.get(t, 0.0) * 100.0
        delta = tgt - base
        if abs(delta) > 0.01:
            delta_weights[t] = round(delta, 1)

    print(f"\n[최종 산출 신호]")
    print(f" - 현재 국면 상태: {current_state}")
    print(f" - 목표 비중 (%): {target_weights}")
    print(f" - 비중 변동 (%p): {delta_weights}")
    print(f" - 운용 가이드: {advice_msg}")

    signal_payload = {
        "date": datetime.date.today().strftime("%Y-%m-%d"),
        "benchmark": benchmark_ticker,
        "benchmarkPrice": round(bm_current_close, 2),
        "benchmarkATH": round(bm_ath, 2),
        "benchmarkMDD": round(bm_mdd_pct, 2),
        "currentState": current_state,
        "targetWeights": target_weights,
        "deltaWeights": delta_weights,
        "advice": advice_msg
    }

    # 5. Send to Google Apps Script
    if gas_url:
        print(f"\n[INFO] Sending signal payload to GAS WebApp...")
        try:
            resp = requests.post(
                gas_url,
                json={
                    "action": "update_portfolio_signal",
                    "pin": GAS_AUTH_PIN,
                    "signal": signal_payload
                },
                timeout=15
            )
            print(f"[GAS Response] Status {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            print(f"[WARN] Failed to send update to GAS: {e}")

    return signal_payload

def main():
    gas_url = GAS_WEBAPP_URL.strip()
    pin = GAS_AUTH_PIN.strip()
    
    active_strat, active_id = fetch_active_strategy_from_gas(gas_url, pin)
    evaluate_portfolio_signal(active_strat, gas_url)

if __name__ == "__main__":
    main()
