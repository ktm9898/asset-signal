"""
Dynamic Asset Allocation & Portfolio Backtesting Engine
Supports:
- Benchmark Peak & MDD Tracking
- Dynamic State Machine (Escalation Drops, Staircase Hysteresis Recovery, Gain/Drift Rebalancing)
- Multi-benchmark Comparison (Strategy vs Benchmark B&H vs Leveraged B&H vs Static Base B&H)
- Detailed Performance Metrics & Daily Weights Timeline
"""

import os
import json
import numpy as np
import pandas as pd
import datetime

DEFAULT_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "etf_history.json")

def load_etf_data(filepath=DEFAULT_DATA_PATH):
    if not os.path.exists(filepath):
        from build_etf_datasets import build_etf_dataset
        build_etf_dataset()
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def run_portfolio_backtest(
    strategy_config=None,
    start_date="2010-02-11",
    end_date=None,
    initial_capital=100000.0,
    dataset=None
):
    """
    Simulates dynamic asset allocation strategy with conditional rebalancing.
    """
    if dataset is None:
        dataset = load_etf_data()
        
    dates = dataset.get("dates", [])
    universe = dataset.get("universe", {})
    
    if not dates or not universe:
        raise ValueError("Invalid ETF dataset.")
        
    # Filter dates
    date_indices = []
    for i, d in enumerate(dates):
        if d >= start_date and (end_date is None or d <= end_date):
            date_indices.append(i)
            
    if not date_indices:
        raise ValueError(f"No trading dates found in range {start_date} ~ {end_date}")
        
    start_idx = date_indices[0]
    end_idx = date_indices[-1]
    eval_dates = [dates[i] for i in date_indices]
    num_days = len(eval_dates)

    # Strategy Configuration Defaults
    if strategy_config is None:
        strategy_config = get_default_strategy_config()
        
    benchmark_ticker = strategy_config.get("benchmark", "QQQ")
    base_weights = strategy_config.get("baseWeights", {"QQQ": 0.60, "SCHD": 0.40})
    drop_stages = strategy_config.get("dropStages", [
        {"threshold": -20.0, "weights": {"QQQ": 0.40, "QLD": 0.30, "SCHD": 0.30}, "name": "1차 하락 (-20%)"},
        {"threshold": -30.0, "weights": {"QQQ": 0.30, "QLD": 0.30, "TQQQ": 0.20, "SCHD": 0.20}, "name": "2차 하락 (-30%)"},
        {"threshold": -40.0, "weights": {"QQQ": 0.20, "QLD": 0.30, "TQQQ": 0.40, "SCHD": 0.10}, "name": "극단 하락 (-40%)"}
    ])
    # Sort drop stages descending (e.g. -20, -30, -40)
    drop_stages = sorted(drop_stages, key=lambda x: x["threshold"], reverse=True)
    
    recovery_stages = strategy_config.get("recoveryStages", [
        {"fromDrop": -40.0, "recovery": -25.0, "weights": {"QQQ": 0.35, "QLD": 0.30, "TQQQ": 0.15, "SCHD": 0.20}, "name": "반등 1단계 (-25% 회복)"},
        {"fromDrop": -30.0, "recovery": -15.0, "weights": {"QQQ": 0.45, "QLD": 0.25, "TQQQ": 0.00, "SCHD": 0.30}, "name": "반등 2단계 (-15% 회복)"},
        {"fromDrop": -20.0, "recovery": -5.0, "weights": {"QQQ": 0.60, "QLD": 0.00, "TQQQ": 0.00, "SCHD": 0.40}, "name": "반등 3단계 (-5% 정상 복귀)"}
    ])
    recovery_stages = sorted(recovery_stages, key=lambda x: x["recovery"], reverse=False)

    gain_threshold_pct = strategy_config.get("gainThresholdPct", 20.0) # +20% NAV gain rebalance
    tolerance_band_pct = strategy_config.get("toleranceBandPct", 5.0) # 5%p drift tolerance
    cooldown_days = strategy_config.get("cooldownDays", 5) # minimum days between rebalances
    fee_rate = strategy_config.get("feeRate", 0.001) # 0.1% transaction cost

    # Extract price matrices for all active tickers
    all_needed_tickers = set(base_weights.keys())
    all_needed_tickers.add(benchmark_ticker)
    for s in drop_stages:
        all_needed_tickers.update(s.get("weights", {}).keys())
    for s in recovery_stages:
        all_needed_tickers.update(s.get("weights", {}).keys())
    # Add benchmark comparative tickers
    for bm in ["SPY", "TQQQ", "QLD"]:
        if bm in universe:
            all_needed_tickers.add(bm)

    prices = {}
    for t in all_needed_tickers:
        if t in universe and "adjClose" in universe[t]:
            raw_series = universe[t]["adjClose"][start_idx:end_idx+1]
            prices[t] = np.array(raw_series, dtype=np.float64)
        else:
            # Fallback if ticker missing
            prices[t] = np.ones(num_days, dtype=np.float64)

    # Benchmark Drawdown Series
    bm_prices = prices[benchmark_ticker]
    bm_peaks = np.maximum.accumulate(bm_prices)
    bm_drawdowns = np.where(bm_peaks > 0, (bm_prices - bm_peaks) / bm_peaks * 100.0, 0.0)

    # Simulation State
    # Start on Day 0 with base_weights
    curr_weights = normalize_weights(base_weights)
    curr_cash = initial_capital
    holdings = {t: 0.0 for t in all_needed_tickers}
    
    # Initial purchase
    day0_price_sum = sum(curr_weights.get(t, 0) for t in all_needed_tickers)
    for t, w in curr_weights.items():
        if prices[t][0] > 0 and w > 0:
            alloc_val = initial_capital * w * (1.0 - fee_rate)
            holdings[t] = alloc_val / prices[t][0]

    strategy_nav = np.zeros(num_days, dtype=np.float64)
    daily_weights_history = []
    rebalance_events = []
    
    current_state_name = "평시 (Normal)"
    deepest_drop_level = 0.0 # Tracks deepest drop reached in current bear cycle
    last_rebalance_day = 0
    last_rebalance_nav = initial_capital
    
    for day in range(num_days):
        current_date = eval_dates[day]
        current_bm_dd = bm_drawdowns[day]
        
        # 1. Calculate current portfolio NAV
        current_nav = sum(holdings[t] * prices[t][day] for t in all_needed_tickers)
        strategy_nav[day] = current_nav
        
        # Calculate actual live weights
        actual_weights = {}
        for t in all_needed_tickers:
            actual_weights[t] = (holdings[t] * prices[t][day]) / current_nav if current_nav > 0 else 0.0
            
        daily_weights_history.append({t: round(actual_weights.get(t, 0.0), 4) for t in curr_weights.keys()})
        
        # Update deepest drop if in correction
        if current_bm_dd < deepest_drop_level:
            deepest_drop_level = current_bm_dd
            
        # Reset deepest drop if benchmark makes new ATH (DD >= -0.5%)
        if current_bm_dd >= -0.5:
            deepest_drop_level = 0.0
            
        # Check Rebalancing Triggers (if past cooldown or extreme transition)
        days_since_rebalance = day - last_rebalance_day
        target_weights = None
        trigger_reason = None
        new_state_name = current_state_name
        
        # A) Check Drawdown Drop Stages (Escalation)
        matched_drop_stage = None
        for stage in sorted(drop_stages, key=lambda x: x["threshold"]): # Check deepest first (-40, -30, -20)
            if current_bm_dd <= stage["threshold"]:
                matched_drop_stage = stage
                break
                
        if matched_drop_stage is not None:
            # We are in a drop stage
            candidate_state = matched_drop_stage.get("name", f"하락 {matched_drop_stage['threshold']}%")
            if candidate_state != current_state_name and (days_since_rebalance >= cooldown_days or current_state_name == "평시 (Normal)"):
                target_weights = normalize_weights(matched_drop_stage["weights"])
                trigger_reason = f"📉 낙폭 트리거 도달 ({current_bm_dd:.1f}% ≤ {matched_drop_stage['threshold']}%)"
                new_state_name = candidate_state
                
        # B) Check Staircase Recovery Stages (De-escalation / Hysteresis)
        elif deepest_drop_level <= -15.0 and current_state_name != "평시 (Normal)":
            # We previously hit a deep drop and are recovering
            for rec_stage in recovery_stages:
                if current_bm_dd >= rec_stage["recovery"] and deepest_drop_level <= rec_stage.get("fromDrop", -20.0):
                    candidate_state = rec_stage.get("name", f"복귀 ({rec_stage['recovery']}%)")
                    if candidate_state != current_state_name and days_since_rebalance >= cooldown_days:
                        target_weights = normalize_weights(rec_stage["weights"])
                        trigger_reason = f"📈 반등 회복 트리거 도달 ({current_bm_dd:.1f}% ≥ {rec_stage['recovery']}%, 최저 {deepest_drop_level:.1f}%)"
                        new_state_name = candidate_state
                        break
                        
            # If recovered near top (-5% or better), restore normal
            if current_bm_dd >= -5.0 and current_state_name != "평시 (Normal)":
                target_weights = normalize_weights(base_weights)
                trigger_reason = f"✅ 대세 상승 복귀 ({current_bm_dd:.1f}% ≥ -5.0%) -> 평시 비중 원복"
                new_state_name = "평시 (Normal)"
                deepest_drop_level = 0.0

        # C) Check Gain / Tolerance-Drift Rebalancing (in Normal State)
        if target_weights is None and current_state_name == "평시 (Normal)" and days_since_rebalance >= 20:
            nav_gain_pct = (current_nav - last_rebalance_nav) / last_rebalance_nav * 100.0 if last_rebalance_nav > 0 else 0.0
            
            # Check Max Weight Drift
            max_drift_pct = 0.0
            for t, base_w in normalize_weights(base_weights).items():
                act_w = actual_weights.get(t, 0.0)
                drift = abs(act_w - base_w) * 100.0
                if drift > max_drift_pct:
                    max_drift_pct = drift
                    
            if gain_threshold_pct > 0 and nav_gain_pct >= gain_threshold_pct:
                target_weights = normalize_weights(base_weights)
                trigger_reason = f"💰 자산 성장 이익 실현 (총자산 +{nav_gain_pct:.1f}% 상승) -> 목표 비중 재조정"
                new_state_name = "평시 (이익실현 리밸런싱)"
            elif tolerance_band_pct > 0 and max_drift_pct >= tolerance_band_pct:
                target_weights = normalize_weights(base_weights)
                trigger_reason = f"⚖️ 비중 이탈 보정 (최대 괴리율 {max_drift_pct:.1f}%p) -> 기본 비중 환원"
                new_state_name = "평시 (비중보정 리밸런싱)"

        # Execute Rebalance if triggered
        if target_weights is not None:
            # Calculate turnover and costs
            trade_volume = 0.0
            for t in all_needed_tickers:
                old_val = holdings[t] * prices[t][day]
                new_val = current_nav * target_weights.get(t, 0.0)
                trade_volume += abs(new_val - old_val)
                
            fee_cost = (trade_volume / 2.0) * fee_rate
            net_nav = current_nav - fee_cost
            
            # Update holdings
            for t in all_needed_tickers:
                target_val = net_nav * target_weights.get(t, 0.0)
                holdings[t] = target_val / prices[t][day] if prices[t][day] > 0 else 0.0
                
            curr_weights = target_weights
            current_state_name = new_state_name
            last_rebalance_day = day
            last_rebalance_nav = net_nav
            
            rebalance_events.append({
                "date": current_date,
                "dayIndex": day,
                "reason": trigger_reason,
                "state": new_state_name,
                "benchmarkDD": round(float(current_bm_dd), 2),
                "nav": round(float(net_nav), 2),
                "weights": {t: round(target_weights.get(t, 0.0) * 100.0, 1) for t in target_weights.keys()},
                "feeCost": round(float(fee_cost), 2)
            })

    # Benchmark Series Calculation
    benchmarks = {}
    
    # 1. QQQ B&H
    if "QQQ" in prices and prices["QQQ"][0] > 0:
        benchmarks["QQQ_BH"] = (prices["QQQ"] / prices["QQQ"][0]) * initial_capital
        
    # 2. TQQQ B&H
    if "TQQQ" in prices and prices["TQQQ"][0] > 0:
        benchmarks["TQQQ_BH"] = (prices["TQQQ"] / prices["TQQQ"][0]) * initial_capital
        
    # 3. SPY B&H
    if "SPY" in prices and prices["SPY"][0] > 0:
        benchmarks["SPY_BH"] = (prices["SPY"] / prices["SPY"][0]) * initial_capital
        
    # 4. Static Base 60:40 B&H (Buy and Hold without dynamic rebalancing)
    static_nav = np.zeros(num_days, dtype=np.float64)
    norm_base = normalize_weights(base_weights)
    for t, w in norm_base.items():
        if t in prices and prices[t][0] > 0:
            static_nav += (prices[t] / prices[t][0]) * (initial_capital * w)
    benchmarks["STATIC_BASE_BH"] = static_nav

    # Calculate Performance Metrics for Strategy and Benchmarks
    years = (datetime.datetime.strptime(eval_dates[-1], "%Y-%m-%d") - datetime.datetime.strptime(eval_dates[0], "%Y-%m-%d")).days / 365.25
    
    strat_metrics = calculate_metrics(strategy_nav, eval_dates, years, rebalance_events)
    benchmarks_metrics = {}
    for bm_key, bm_nav_series in benchmarks.items():
        benchmarks_metrics[bm_key] = calculate_metrics(bm_nav_series, eval_dates, years, [])

    # Calculate Drawdown Curve for Strategy
    strat_peak = np.maximum.accumulate(strategy_nav)
    strat_dd = np.where(strat_peak > 0, (strategy_nav - strat_peak) / strat_peak * 100.0, 0.0)

    # Prepare downsampled response for fast chart rendering
    step = max(1, num_days // 300)
    chart_dates = eval_dates[::step]
    chart_strat_nav = [round(float(v), 2) for v in strategy_nav[::step]]
    chart_strat_dd = [round(float(v), 2) for v in strat_dd[::step]]
    
    chart_benchmarks = {}
    for bm_key, bm_nav in benchmarks.items():
        chart_benchmarks[bm_key] = [round(float(v), 2) for v in bm_nav[::step]]
        
    return {
        "summary": strat_metrics,
        "benchmarksSummary": benchmarks_metrics,
        "rebalanceEvents": rebalance_events,
        "rebalanceCount": len(rebalance_events),
        "startDate": eval_dates[0],
        "endDate": eval_dates[-1],
        "years": round(years, 2),
        "initialCapital": initial_capital,
        "finalNAV": round(float(strategy_nav[-1]), 2),
        "chartData": {
            "dates": chart_dates,
            "strategyNAV": chart_strat_nav,
            "strategyDD": chart_strat_dd,
            "benchmarksNAV": chart_benchmarks,
            "benchmarkDD": [round(float(v), 2) for v in bm_drawdowns[::step]]
        }
    }

def normalize_weights(w_dict):
    clean = {k: float(v) for k, v in w_dict.items() if float(v) > 0}
    total = sum(clean.values())
    if total <= 0:
        return {"QQQ": 1.0}
    return {k: v / total for k, v in clean.items()}

def calculate_metrics(nav_series, dates, years, events):
    if len(nav_series) < 2 or years <= 0:
        return {}
        
    initial = nav_series[0]
    final = nav_series[-1]
    total_return_pct = (final - initial) / initial * 100.0
    cagr_pct = ((final / initial) ** (1.0 / years) - 1.0) * 100.0 if final > 0 else -100.0
    
    # Daily returns
    daily_rets = np.diff(nav_series) / nav_series[:-1]
    vol_annual_pct = np.std(daily_rets) * np.sqrt(252) * 100.0
    
    # Sharpe Ratio (Rf = 2.0%)
    rf_daily = 0.02 / 252
    excess_rets = daily_rets - rf_daily
    sharpe = (np.mean(excess_rets) / np.std(excess_rets) * np.sqrt(252)) if np.std(excess_rets) > 0 else 0.0
    
    # Sortino Ratio (Downside deviation only)
    neg_rets = daily_rets[daily_rets < 0]
    downside_std = np.std(neg_rets) * np.sqrt(252) if len(neg_rets) > 0 else 0.0
    sortino = (np.mean(excess_rets) * 252 / downside_std) if downside_std > 0 else sharpe
    
    # Max Drawdown & Max DD Duration
    peaks = np.maximum.accumulate(nav_series)
    dds = np.where(peaks > 0, (nav_series - peaks) / peaks * 100.0, 0.0)
    mdd_pct = np.min(dds)
    
    # Calmar Ratio
    calmar = (cagr_pct / abs(mdd_pct)) if abs(mdd_pct) > 0 else 0.0
    
    # Win Rate (Trading Days)
    win_days = np.sum(daily_rets > 0)
    win_rate_pct = (win_days / len(daily_rets)) * 100.0 if len(daily_rets) > 0 else 0.0

    return {
        "totalReturnPct": round(float(total_return_pct), 2),
        "cagrPct": round(float(cagr_pct), 2),
        "mddPct": round(float(mdd_pct), 2),
        "volatilityPct": round(float(vol_annual_pct), 2),
        "sharpe": round(float(sharpe), 2),
        "sortino": round(float(sortino), 2),
        "calmar": round(float(calmar), 2),
        "winRatePct": round(float(win_rate_pct), 1),
        "finalNAV": round(float(final), 2)
    }

def get_default_strategy_config():
    return {
        "name": "나스닥100 동적 계단식 자산배분 (QQQ/QLD/TQQQ/SCHD)",
        "memo": "평시 QQQ 60:SCHD 40 유지, -20%/-30%/-40% 하락 시 2X/3X 레버리지 분할 매수 및 반등 시 계단식 선제 익절",
        "benchmark": "QQQ",
        "baseWeights": {"QQQ": 0.60, "SCHD": 0.40},
        "dropStages": [
            {"threshold": -20.0, "weights": {"QQQ": 0.40, "QLD": 0.30, "SCHD": 0.30}, "name": "1차 하락 (-20%)"},
            {"threshold": -30.0, "weights": {"QQQ": 0.30, "QLD": 0.30, "TQQQ": 0.20, "SCHD": 0.20}, "name": "2차 하락 (-30%)"},
            {"threshold": -40.0, "weights": {"QQQ": 0.20, "QLD": 0.30, "TQQQ": 0.40, "SCHD": 0.10}, "name": "극단 하락 (-40%)"}
        ],
        "recoveryStages": [
            {"fromDrop": -40.0, "recovery": -25.0, "weights": {"QQQ": 0.35, "QLD": 0.30, "TQQQ": 0.15, "SCHD": 0.20}, "name": "반등 1단계 (-25% 회복)"},
            {"fromDrop": -30.0, "recovery": -15.0, "weights": {"QQQ": 0.45, "QLD": 0.25, "TQQQ": 0.00, "SCHD": 0.30}, "name": "반등 2단계 (-15% 회복)"},
            {"fromDrop": -20.0, "recovery": -5.0, "weights": {"QQQ": 0.60, "QLD": 0.00, "TQQQ": 0.00, "SCHD": 0.40}, "name": "반등 3단계 (-5% 원복)"}
        ],
        "gainThresholdPct": 20.0,
        "toleranceBandPct": 5.0,
        "cooldownDays": 5,
        "feeRate": 0.001
    }

if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    print("[INFO] Running Backtest Simulation on Default Strategy...")
    res = run_portfolio_backtest(start_date="2010-02-11")
    print(f"\n=======================================================")
    print(f" 기간: {res['startDate']} ~ {res['endDate']} ({res['years']}년)")
    print(f" 초기 자본: ${res['initialCapital']:,.0f} -> 최종 자산: ${res['finalNAV']:,.0f}")
    print(f" 총 수익률: +{res['summary']['totalReturnPct']}% | CAGR: {res['summary']['cagrPct']}%")
    print(f" 최대 낙폭 (MDD): {res['summary']['mddPct']}% | Sharpe: {res['summary']['sharpe']} | Sortino: {res['summary']['sortino']}")
    print(f" 총 리밸런싱 횟수: {res['rebalanceCount']}회")
    print(f"=======================================================\n")
    print(" 벤치마크 비교:")
    for k, v in res['benchmarksSummary'].items():
        print(f"  - [{k:16s}] 총수익률: {v['totalReturnPct']:+7.1f}% | CAGR: {v['cagrPct']:5.1f}% | MDD: {v['mddPct']:6.1f}% | Sharpe: {v['sharpe']:4.2f}")
    print("\n최근 5건 리밸런싱 이벤트:")
    for ev in res['rebalanceEvents'][-5:]:
        clean_reason = ev['reason'].encode('ascii', 'replace').decode('ascii')
        print(f"  [{ev['date']}] {clean_reason} (NAV: ${ev['nav']:,.0f}) -> {ev['weights']}")
