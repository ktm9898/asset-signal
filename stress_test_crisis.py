"""
Extreme Historical Crisis Stress-Test Engine (2000 Dot-com Bubble & 2008 Global Financial Crisis)
Tests Strategy 1 vs Alternatives under catastrophic market crashes:
1. 2008 Global Financial Crisis (-54% crash & recovery)
2. 2000 Dot-Com Bubble Crash (-83% extreme tech crash)
3. 2000~2026 Long-term (26-year encompassing all 4 historical super-crises)
"""

import os
import json
import datetime
import yfinance as yf
import pandas as pd
import numpy as np

print("[INFO] Fetching historical index data for 2000~2026 stress testing...")

tickers_to_fetch = ["^NDX", "^GSPC", "QQQ", "SPY", "SOXX"]
data = yf.download(
    tickers=tickers_to_fetch,
    start="1999-01-01",
    end=datetime.date.today() + datetime.timedelta(days=1),
    auto_adjust=False,
    progress=False
)

adj_df = data['Adj Close'] if 'Adj Close' in data else data['Close']
close_df = data['Close']

adj_df = adj_df.ffill().bfill()
close_df = close_df.ffill().bfill()

dates = [d.strftime("%Y-%m-%d") for d in close_df.index]
num_days = len(dates)

# Build daily returns
ndx_ret = adj_df['^NDX'].pct_change().fillna(0).values
gspc_ret = adj_df['^GSPC'].pct_change().fillna(0).values
qqq_ret = adj_df['QQQ'].pct_change().fillna(0).values if 'QQQ' in adj_df else ndx_ret
soxx_ret = adj_df['SOXX'].pct_change().fillna(0).values if 'SOXX' in adj_df else ndx_ret

# Synthetic Series Construction:
# 1. QLD: 2X daily return minus 0.95% annual expense
qld_ret = ndx_ret * 2.0 - (0.0095 / 252.0)
qld_prices = np.cumprod(1.0 + qld_ret)

# 2. TQQQ: 3X daily return minus 0.95% annual expense
tqqq_ret = ndx_ret * 3.0 - (0.0095 / 252.0)
tqqq_prices = np.cumprod(1.0 + tqqq_ret)

# 3. SOXL: 3X daily return minus 0.95% annual expense
soxl_ret = soxx_ret * 3.0 - (0.0095 / 252.0)
soxl_prices = np.cumprod(1.0 + soxl_ret)

# 4. SCHD (US Dividend Equity): Value index proxy using S&P 500 Value / Dividend proxy
# SCHD launched in Oct 2011. Pre-2011 SCHD is synthetic Dow Jones US Dividend 100 proxy (0.75 * SPY + 0.25 * Dividend yield boost)
# During 2000-2002 Dot-com crash, Value/Dividend stocks dropped only -20% while Tech dropped -83%.
schd_ret = gspc_ret * 0.85 + 0.0001
schd_prices = np.cumprod(1.0 + schd_ret)

# QQQ Price Series
qqq_prices = np.cumprod(1.0 + qqq_ret)
ndx_prices = adj_df['^NDX'].values

all_asset_prices = {
    "^NDX": ndx_prices,
    "QQQ": qqq_prices,
    "QLD": qld_prices,
    "TQQQ": tqqq_prices,
    "SOXL": soxl_prices,
    "SCHD": schd_prices
}

def run_simulation_segment(strat, start_date_str, end_date_str):
    s_idx = next((i for i, d in enumerate(dates) if d >= start_date_str), 0)
    e_idx = next((i for i in range(len(dates)-1, -1, -1) if dates[i] <= end_date_str), len(dates)-1)
    
    seg_dates = dates[s_idx:e_idx+1]
    seg_len = len(seg_dates)
    if seg_len == 0:
        return None

    # Slice prices & normalize
    seg_prices = {}
    for t in all_asset_prices:
        seg_prices[t] = all_asset_prices[t][s_idx:e_idx+1]
    
    bm_prices = seg_prices["^NDX"]
    bm_drawdowns = np.zeros(seg_len, dtype=float)
    bm_max = 0.0
    for i in range(seg_len):
        if bm_prices[i] > bm_max:
            bm_max = bm_prices[i]
        bm_drawdowns[i] = ((bm_prices[i] - bm_max) / bm_max) * 100.0 if bm_max > 0 else 0.0

    initial_cap = 100000000.0 # 1억원
    holdings = {}
    base_w = strat['baseWeights']
    for t, w in base_w.items():
        holdings[t] = (initial_cap * w) / seg_prices[t][0]

    current_stage_idx = -1
    last_rebal_day = 0
    last_rebal_nav = initial_cap
    stages = sorted(strat.get('dropStages', []), key=lambda x: x['threshold'], reverse=True)
    strat_nav = np.zeros(seg_len, dtype=float)
    rebal_count = 0
    rebal_events = []
    fee_rate = 0.0015

    for day in range(seg_len):
        nav = sum(holdings.get(t, 0.0) * seg_prices[t][day] for t in holdings)
        strat_nav[day] = nav
        dd = bm_drawdowns[day]
        tgt_weights = None
        trigger_reason = None
        next_stage_idx = current_stage_idx
        days_since = day - last_rebal_day

        if len(stages) > 0:
            if current_stage_idx < 0:
                deepest = -1
                for i, stg in enumerate(stages):
                    if dd <= stg['threshold']:
                        deepest = i
                if deepest >= 0:
                    next_stage_idx = deepest
                    tgt_weights = stages[deepest]['weights']
                    trigger_reason = f"[낙폭 도달] {dd:.1f}% ({stages[deepest].get('name', f'{deepest+1}차 하락')} 진입)"
            else:
                deeper = current_stage_idx
                for i in range(current_stage_idx + 1, len(stages)):
                    if dd <= stages[i]['threshold']:
                        deeper = i
                if deeper > current_stage_idx:
                    next_stage_idx = deeper
                    tgt_weights = stages[deeper]['weights']
                    trigger_reason = f"[낙폭 심화] {dd:.1f}% ({stages[deeper].get('name', f'{deeper+1}차 하락')} 진입)"
                else:
                    upper = 0.0 if current_stage_idx == 0 else stages[current_stage_idx - 1]['threshold']
                    if dd >= upper:
                        next_stage_idx = current_stage_idx - 1
                        if next_stage_idx < 0:
                            tgt_weights = base_w
                            trigger_reason = f"[고점 복귀] 0.0% (기본 비중 원복)"
                        else:
                            tgt_weights = stages[next_stage_idx]['weights']
                            trigger_reason = f"[반등 회복] {dd:.1f}% ({stages[next_stage_idx].get('name', f'{next_stage_idx+1}차 하락')} 복귀)"

        if tgt_weights is None and current_stage_idx < 0 and days_since >= 20:
            gain = ((nav - last_rebal_nav) / last_rebal_nav) * 100.0
            if strat.get('gainThresholdPct', 0) > 0 and gain >= strat['gainThresholdPct']:
                tgt_weights = base_w
                trigger_reason = f"[이익실현] +{gain:.1f}%"

        if tgt_weights is not None:
            trade_vol = 0.0
            for t in set(list(holdings.keys()) + list(tgt_weights.keys())):
                old_val = holdings.get(t, 0.0) * seg_prices[t][day]
                new_val = nav * tgt_weights.get(t, 0.0)
                trade_vol += abs(new_val - old_val)

            net_nav = nav - (trade_vol / 2.0) * fee_rate
            holdings = {t: (net_nav * tgt_weights.get(t, 0.0)) / seg_prices[t][day] for t in tgt_weights if tgt_weights.get(t, 0.0) > 0}
            current_stage_idx = next_stage_idx
            last_rebal_day = day
            last_rebal_nav = net_nav
            rebal_count += 1
            rebal_events.append({
                "date": seg_dates[day],
                "reason": trigger_reason,
                "nav": round(net_nav),
                "mdd": round(dd, 1)
            })

    final_nav = strat_nav[-1]
    total_ret = ((final_nav - initial_cap) / initial_cap) * 100.0
    start_dt = datetime.datetime.strptime(seg_dates[0], "%Y-%m-%d")
    end_dt = datetime.datetime.strptime(seg_dates[-1], "%Y-%m-%d")
    years = (end_dt - start_dt).days / 365.25
    cagr = ((final_nav / initial_cap) ** (1.0 / years) - 1.0) * 100.0 if final_nav > 0 else -100.0

    peak = 0.0
    mdd = 0.0
    daily_rets = []
    for i in range(seg_len):
        if strat_nav[i] > peak:
            peak = strat_nav[i]
        d = ((strat_nav[i] - peak) / peak) * 100.0
        if d < mdd:
            mdd = d
        if i > 0:
            daily_rets.append((strat_nav[i] - strat_nav[i-1]) / strat_nav[i-1])

    daily_rets = np.array(daily_rets)
    mean_ret = np.mean(daily_rets)
    std_ret = np.std(daily_rets)
    sharpe = (mean_ret / std_ret) * np.sqrt(252) if std_ret > 0 else 0.0

    return {
        "name": strat['name'],
        "final_nav": round(final_nav),
        "total_ret_pct": round(total_ret, 1),
        "cagr_pct": round(cagr, 2),
        "mdd_pct": round(mdd, 2),
        "sharpe": round(sharpe, 2),
        "rebal_count": rebal_count,
        "events": rebal_events[:10] # sample
    }

# Define strategies
user_slot_1 = {
    "name": "전략 1번 (사용자 현재 전략)",
    "baseWeights": {"SCHD": 0.60, "QQQ": 0.40},
    "dropStages": [
        {"threshold": -15.0, "weights": {"SCHD": 0.40, "QQQ": 0.60}, "name": "1차 하락 (-15%)"},
        {"threshold": -25.0, "weights": {"SCHD": 0.40, "QQQ": 0.40, "QLD": 0.20}, "name": "2차 하락 (-25%)"},
        {"threshold": -40.0, "weights": {"SCHD": 0.20, "QQQ": 0.40, "QLD": 0.40}, "name": "3차 하락 (-40%)"},
        {"threshold": -60.0, "weights": {"SCHD": 0.20, "QQQ": 0.20, "QLD": 0.40, "TQQQ": 0.20}, "name": "4차 하락 (-60%)"},
        {"threshold": -80.0, "weights": {"SCHD": 0.00, "QQQ": 0.20, "QLD": 0.40, "TQQQ": 0.40}, "name": "5차 하락 (-80%)"}
    ],
    "gainThresholdPct": 20.0
}

alt_A = {
    "name": "대안 A (레버리지 조기 투입형)",
    "baseWeights": {"SCHD": 0.60, "QQQ": 0.40},
    "dropStages": [
        {"threshold": -15.0, "weights": {"SCHD": 0.40, "QQQ": 0.30, "QLD": 0.30}, "name": "1차 하락 (-15%)"},
        {"threshold": -25.0, "weights": {"SCHD": 0.20, "QQQ": 0.30, "QLD": 0.50}, "name": "2차 하락 (-25%)"},
        {"threshold": -35.0, "weights": {"SCHD": 0.10, "QQQ": 0.20, "QLD": 0.40, "TQQQ": 0.30}, "name": "3차 하락 (-35%)"},
        {"threshold": -50.0, "weights": {"SCHD": 0.00, "QQQ": 0.10, "QLD": 0.40, "TQQQ": 0.50}, "name": "4차 하락 (-50%)"}
    ],
    "gainThresholdPct": 20.0
}

alt_B = {
    "name": "대안 B (반도체 SOXL 가미형)",
    "baseWeights": {"SCHD": 0.60, "QQQ": 0.40},
    "dropStages": [
        {"threshold": -15.0, "weights": {"SCHD": 0.40, "QQQ": 0.40, "SOXL": 0.20}, "name": "1차 하락 (-15%)"},
        {"threshold": -25.0, "weights": {"SCHD": 0.20, "QQQ": 0.30, "QLD": 0.30, "SOXL": 0.20}, "name": "2차 하락 (-25%)"},
        {"threshold": -35.0, "weights": {"SCHD": 0.10, "QQQ": 0.20, "QLD": 0.40, "SOXL": 0.30}, "name": "3차 하락 (-35%)"}
    ],
    "gainThresholdPct": 20.0
}

alt_C = {
    "name": "대안 C (2배수 QLD 안전 스위칭)",
    "baseWeights": {"SCHD": 0.60, "QQQ": 0.40},
    "dropStages": [
        {"threshold": -15.0, "weights": {"SCHD": 0.40, "QQQ": 0.30, "QLD": 0.30}, "name": "1차 하락 (-15%)"},
        {"threshold": -25.0, "weights": {"SCHD": 0.20, "QQQ": 0.20, "QLD": 0.60}, "name": "2차 하락 (-25%)"}
    ],
    "gainThresholdPct": 20.0
}

bench_qqq = {"name": "QQQ 100% (단순보유)", "baseWeights": {"QQQ": 1.0}, "dropStages": []}
bench_schd_qqq = {"name": "SCHD 60% + QQQ 40% (정적보유)", "baseWeights": {"SCHD": 0.60, "QQQ": 0.40}, "dropStages": []}

test_strats = [user_slot_1, alt_A, alt_B, alt_C, bench_schd_qqq, bench_qqq]

# Scenarios to test:
scenarios = [
    {
        "title": "시나리오 1: 2008년 글로벌 금융위기 구간 (2006-01-03 ~ 2013-12-31, 8년)",
        "start": "2006-01-03",
        "end": "2013-12-31"
    },
    {
        "title": "시나리오 2: 2000년 닷컴버블 붕괴 구간 (2000-01-03 ~ 2007-12-31, 8년)",
        "start": "2000-01-03",
        "end": "2007-12-31"
    },
    {
        "title": "시나리오 3: 2000년 ~ 2026년 26년 초장기 풀 스트레스 (닷컴+금융위기+코로나+2022 모두 관통)",
        "start": "2000-01-03",
        "end": dates[-1]
    }
]

output_report = {}
for sc in scenarios:
    res = [run_simulation_segment(s, sc['start'], sc['end']) for s in test_strats]
    output_report[sc['title']] = res

with open('crisis_stress_results.json', 'w', encoding='utf-8') as f:
    json.dump(output_report, f, ensure_ascii=False, indent=2)

print("[SUCCESS] Stress test completed -> crisis_stress_results.json")
