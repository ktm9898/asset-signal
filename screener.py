"""
Daily Dynamic Asset Allocation & Portfolio Signal Engine
Automated daily execution via GitHub Actions or manual trigger.
Fetches active strategy rules from Google Apps Script, evaluates benchmark drawdown & state machine,
computes target asset weights (%) and adjustment delta (%p), and updates Google Sheets DB.
"""

import os
import sys
import json
import datetime
import requests
import yfinance as yf
import numpy as np
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def post_to_gas(url, action, data, pin=""):
    try:
        payload = {"action": action, "pin": pin, **data}
        resp = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=25
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"[ERROR] GAS response {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[ERROR] Failed to post to GAS ({action}): {e}")
    return None

def fetch_active_strategy(gas_url, pin=""):
    req_url = f"{gas_url}?action=get_strategy_slots"
    if pin:
        req_url += f"&pin={pin}"
    try:
        resp = requests.get(req_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                active_id = data.get("activeSlotId", 1)
                slots = data.get("slots", [])
                active_slot = next((s for s in slots if s.get("id") == active_id), None)
                if active_slot:
                    return active_slot, slots
    except Exception as e:
        print(f"[WARN] Could not fetch strategy from GAS: {e}")
    return None, []

def fetch_user_holdings(gas_url, pin=""):
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
    print("🚀 Running Daily Dynamic Asset Allocation Signal Engine")
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

    print(f"\n📊 [시장 지표 분석]")
    print(f" - 기준 지수 ({benchmark_ticker}) 현재가: ${bm_current_close:,.2f}")
    print(f" - 최고가 (ATH): ${bm_ath:,.2f}")
    print(f" - 고점 대비 하락률 (MDD): {bm_mdd_pct:.2f}%")

    # 4. State Machine Evaluation
    current_state = "평시 (Normal)"
    target_weights = {k: float(v) for k, v in base_weights.items()}
    advice_msg = ""

    # Check Drop Stages
    matched_drop = None
    for stage in sorted(drop_stages, key=lambda x: x["threshold"]): # check deepest first
        if bm_mdd_pct <= stage["threshold"]:
            matched_drop = stage
            break

    if matched_drop is not None:
        current_state = matched_drop.get("name", f"하락 {matched_drop['threshold']}%")
        target_weights = {k: float(v) for k, v in matched_drop.get("weights", {}).items()}
        advice_msg = f"📉 [낙폭 국면 진입] {benchmark_ticker} 고점 대비 {bm_mdd_pct:.1f}% 하락! {current_state} 비중으로 리밸런싱 실행 권장."
    else:
        # Check if recently recovered from deep drop (last 60 days min MDD)
        recent_60d_min_dd = float(bm_series.tail(60).apply(lambda p: (p - bm_ath) / bm_ath * 100.0).min())
        if recent_60d_min_dd <= -15.0 and bm_mdd_pct < -5.0:
            for rec in recovery_stages:
                if bm_mdd_pct >= rec.get("recovery", -10.0) and recent_60d_min_dd <= rec.get("fromDrop", -20.0):
                    current_state = rec.get("name", f"반등 회복 ({rec.get('recovery')}%)")
                    target_weights = {k: float(v) for k, v in rec.get("weights", {}).items()}
                    advice_msg = f"📈 [반등 계단식 복귀] {benchmark_ticker} 낙폭 {bm_mdd_pct:.1f}%로 회복 (최근 저점 {recent_60d_min_dd:.1f}%). 레버리지 비중 선제 축소."
                    break
        
        if not advice_msg:
            current_state = "평시 (Normal)"
            target_weights = {k: float(v) for k, v in base_weights.items()}
            advice_msg = f"✅ [평시 정상 운용] {benchmark_ticker} 고점 대비 {bm_mdd_pct:.1f}%로 안정권 유지. 기본 자산 배분 비중 유지."

    # Normalize target weights to 100%
    tot_w = sum(target_weights.values())
    if tot_w > 0:
        target_weights = {k: round((v / tot_w) * 100.0, 1) for k, v in target_weights.items()}

    # Calculate delta against base weights (or user current holdings if available)
    delta_weights = {}
    for t in all_tickers:
        tgt = target_weights.get(t, 0.0)
        base = base_weights.get(t, 0.0) * 100.0
        delta = tgt - base
        if abs(delta) > 0.01 or tgt > 0:
            delta_weights[t] = round(delta, 1)

    print(f"\n🎯 [금일 권장 포트폴리오 목표 비중]")
    print(f" - 국면 상태: {current_state}")
    for t, w in target_weights.items():
        d_val = delta_weights.get(t, 0.0)
        d_str = f"({d_val:+5.1f}%p)" if d_val != 0 else "(유지)"
        print(f"   • {t:6s}: {w:5.1f}%  {d_str}")
    print(f"\n💡 [운용 조언]\n {advice_msg}")

    # 5. Build Signal Object
    signal_obj = {
        "date": datetime.datetime.now().strftime("%Y-%m-%d"),
        "benchmark": benchmark_ticker,
        "benchmarkPrice": round(bm_current_close, 2),
        "benchmarkATH": round(bm_ath, 2),
        "benchmarkMDD": round(bm_mdd_pct, 2),
        "currentState": current_state,
        "targetWeights": target_weights,
        "deltaWeights": delta_weights,
        "advice": advice_msg
    }

    # 6. Post to Google Sheets if gas_url configured
    if gas_url:
        print(f"\n[INFO] Posting signal to Google Apps Script...")
        res = post_to_gas(gas_url, "update_portfolio_signal", {"signal": signal_obj}, pin=pin)
        if res and res.get("success"):
            print(" -> [SUCCESS] Google Sheets successfully updated!")
        else:
            print(" -> [WARN] Failed to update Google Sheets.")

    return signal_obj

def main():
    gas_url = os.environ.get("GAS_WEBAPP_URL", "https://script.google.com/macros/s/AKfycbwnJXm6B3ZrS0jp5dsoKV6n3ghCOOtjxcSzAVtVlZ3nCk6MwZIKgMVV6e7FJcdM0PaZ4A/exec")
    pin = os.environ.get("AUTH_PIN", "")

    active_slot = None
    if gas_url:
        print("[INFO] Loading active strategy from Google Apps Script...")
        active_slot, _ = fetch_active_strategy(gas_url, pin)

    evaluate_portfolio_signal(strategy_config=active_slot, gas_url=gas_url, pin=pin)

if __name__ == "__main__":
    main()
