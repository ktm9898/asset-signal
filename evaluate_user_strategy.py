import json
import numpy as np
import datetime

with open('data/etf_history.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

dates = data['dates']
num_days = len(dates)
all_prices = {t: np.array(data['universe'][t]['adjClose'], dtype=float) for t in data['universe']}
bm_prices = all_prices['^NDX']

bm_max = 0.0
bm_drawdowns = np.zeros(num_days, dtype=float)
for i in range(num_days):
    if bm_prices[i] > bm_max:
        bm_max = bm_prices[i]
    bm_drawdowns[i] = ((bm_prices[i] - bm_max) / bm_max) * 100.0 if bm_max > 0 else 0.0

def simulate(strat):
    initial_cap = 100000000.0 # 1억원
    holdings = {}
    base_w = strat['baseWeights']
    for t, w in base_w.items():
        holdings[t] = (initial_cap * w) / all_prices[t][0]

    current_stage_idx = -1
    last_rebal_day = 0
    last_rebal_nav = initial_cap
    stages = sorted(strat.get('dropStages', []), key=lambda x: x['threshold'], reverse=True)
    strat_nav = np.zeros(num_days, dtype=float)
    rebal_count = 0
    rebal_events = []
    fee_rate = strat.get('feeRate', 0.0015)

    for day in range(num_days):
        nav = sum(holdings.get(t, 0.0) * all_prices[t][day] for t in holdings)
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
                old_val = holdings.get(t, 0.0) * all_prices[t][day]
                new_val = nav * tgt_weights.get(t, 0.0)
                trade_vol += abs(new_val - old_val)

            net_nav = nav - (trade_vol / 2.0) * fee_rate
            holdings = {t: (net_nav * tgt_weights.get(t, 0.0)) / all_prices[t][day] for t in tgt_weights if tgt_weights.get(t, 0.0) > 0}
            current_stage_idx = next_stage_idx
            last_rebal_day = day
            last_rebal_nav = net_nav
            rebal_count += 1
            rebal_events.append({
                "date": dates[day],
                "reason": trigger_reason,
                "nav": round(net_nav),
                "mdd": round(dd, 1)
            })

    final_nav = strat_nav[-1]
    total_ret = ((final_nav - initial_cap) / initial_cap) * 100.0
    start_dt = datetime.datetime.strptime(dates[0], "%Y-%m-%d")
    end_dt = datetime.datetime.strptime(dates[-1], "%Y-%m-%d")
    years = (end_dt - start_dt).days / 365.25
    cagr = ((final_nav / initial_cap) ** (1.0 / years) - 1.0) * 100.0

    peak = 0.0
    mdd = 0.0
    daily_rets = []
    for i in range(num_days):
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
    neg_rets = daily_rets[daily_rets < 0]
    neg_std = np.std(neg_rets) if len(neg_rets) > 0 else 0.0
    sortino = (mean_ret / neg_std) * np.sqrt(252) if neg_std > 0 else 0.0

    return {
        "name": strat['name'],
        "final_nav": round(final_nav),
        "total_ret_pct": round(total_ret, 1),
        "cagr_pct": round(cagr, 2),
        "mdd_pct": round(mdd, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "rebal_count": rebal_count,
        "events": rebal_events
    }

user_slot_1 = {
    "name": "사용자 실제 전략 1번 (SCHD 60:QQQ 40 기반)",
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

# Optimized Alternatives based on User's SCHD 60:QQQ 40 philosophy:
alt_1 = {
    "name": "대안 A: [SCHD 60 기반 레버리지 조기 투입형] (-15/-25/-35)",
    "baseWeights": {"SCHD": 0.60, "QQQ": 0.40},
    "dropStages": [
        {"threshold": -15.0, "weights": {"SCHD": 0.40, "QQQ": 0.30, "QLD": 0.30}, "name": "1차 하락 (-15%)"},
        {"threshold": -25.0, "weights": {"SCHD": 0.20, "QQQ": 0.30, "QLD": 0.50}, "name": "2차 하락 (-25%)"},
        {"threshold": -35.0, "weights": {"SCHD": 0.10, "QQQ": 0.20, "QLD": 0.40, "TQQQ": 0.30}, "name": "3차 하락 (-35%)"},
        {"threshold": -50.0, "weights": {"SCHD": 0.00, "QQQ": 0.10, "QLD": 0.40, "TQQQ": 0.50}, "name": "4차 하락 (-50%)"}
    ],
    "gainThresholdPct": 20.0
}

alt_2 = {
    "name": "대안 B: [반도체 SOXL 가미 슈퍼 부스트형] (-15/-25/-35)",
    "baseWeights": {"SCHD": 0.60, "QQQ": 0.40},
    "dropStages": [
        {"threshold": -15.0, "weights": {"SCHD": 0.40, "QQQ": 0.40, "SOXL": 0.20}, "name": "1차 하락 (-15%)"},
        {"threshold": -25.0, "weights": {"SCHD": 0.20, "QQQ": 0.30, "QLD": 0.30, "SOXL": 0.20}, "name": "2차 하락 (-25%)"},
        {"threshold": -35.0, "weights": {"SCHD": 0.10, "QQQ": 0.20, "QLD": 0.40, "SOXL": 0.30}, "name": "3차 하락 (-35%)"}
    ],
    "gainThresholdPct": 20.0
}

alt_3 = {
    "name": "대안 C: [배당 극대화 + 2배수 안전 스위칭] (-15/-25)",
    "baseWeights": {"SCHD": 0.60, "QQQ": 0.40},
    "dropStages": [
        {"threshold": -15.0, "weights": {"SCHD": 0.40, "QQQ": 0.30, "QLD": 0.30}, "name": "1차 하락 (-15%)"},
        {"threshold": -25.0, "weights": {"SCHD": 0.20, "QQQ": 0.20, "QLD": 0.60}, "name": "2차 하락 (-25%)"}
    ],
    "gainThresholdPct": 20.0
}

benchmarks = [
    {"name": "벤치마크: QQQ 100% 단순보유", "baseWeights": {"QQQ": 1.0}, "dropStages": [], "gainThresholdPct": 0},
    {"name": "벤치마크: SCHD 60% + QQQ 40% (정적보유)", "baseWeights": {"SCHD": 0.60, "QQQ": 0.40}, "dropStages": [], "gainThresholdPct": 0}
]

strats = [user_slot_1, alt_1, alt_2, alt_3] + benchmarks
results = [simulate(s) for s in strats]

with open('user_strategy_eval.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("EVALUATION COMPLETE")
