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
    fee_rate = strat.get('feeRate', 0.0015)

    for day in range(num_days):
        nav = sum(holdings.get(t, 0.0) * all_prices[t][day] for t in holdings)
        strat_nav[day] = nav
        dd = bm_drawdowns[day]
        tgt_weights = None
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
            else:
                deeper = current_stage_idx
                for i in range(current_stage_idx + 1, len(stages)):
                    if dd <= stages[i]['threshold']:
                        deeper = i
                if deeper > current_stage_idx:
                    next_stage_idx = deeper
                    tgt_weights = stages[deeper]['weights']
                else:
                    upper = 0.0 if current_stage_idx == 0 else stages[current_stage_idx - 1]['threshold']
                    if dd >= upper:
                        next_stage_idx = current_stage_idx - 1
                        tgt_weights = base_w if next_stage_idx < 0 else stages[next_stage_idx]['weights']

        if tgt_weights is None and current_stage_idx < 0 and days_since >= 20:
            gain = ((nav - last_rebal_nav) / last_rebal_nav) * 100.0
            if strat.get('gainThresholdPct', 0) > 0 and gain >= strat['gainThresholdPct']:
                tgt_weights = base_w

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
        "rebal_count": rebal_count
    }

strats = [
    {
        "name": "현재 전략 1번 (기존 -20/-30/-40)",
        "baseWeights": {"QQQ": 0.60, "SCHD": 0.40},
        "dropStages": [
            {"threshold": -20.0, "weights": {"QQQ": 0.40, "QLD": 0.30, "SCHD": 0.30}},
            {"threshold": -30.0, "weights": {"QQQ": 0.30, "QLD": 0.30, "TQQQ": 0.20, "SCHD": 0.20}},
            {"threshold": -40.0, "weights": {"QQQ": 0.20, "QLD": 0.30, "TQQQ": 0.40, "SCHD": 0.10}}
        ],
        "gainThresholdPct": 20.0
    },
    {
        "name": "대안 1: [황금 밸런스 3단형] (-15/-25/-35)",
        "baseWeights": {"QQQ": 0.60, "SCHD": 0.40},
        "dropStages": [
            {"threshold": -15.0, "weights": {"QQQ": 0.40, "QLD": 0.40, "SCHD": 0.20}},
            {"threshold": -25.0, "weights": {"QQQ": 0.20, "QLD": 0.50, "TQQQ": 0.20, "SCHD": 0.10}},
            {"threshold": -35.0, "weights": {"QQQ": 0.10, "QLD": 0.40, "TQQQ": 0.40, "SCHD": 0.10}}
        ],
        "gainThresholdPct": 20.0
    },
    {
        "name": "대안 2: [2배수 QLD 특화 안전형] (-15/-25)",
        "baseWeights": {"QQQ": 0.60, "SCHD": 0.40},
        "dropStages": [
            {"threshold": -15.0, "weights": {"QQQ": 0.40, "QLD": 0.40, "SCHD": 0.20}},
            {"threshold": -25.0, "weights": {"QQQ": 0.20, "QLD": 0.60, "SCHD": 0.20}}
        ],
        "gainThresholdPct": 20.0
    },
    {
        "name": "대안 3: [반도체 SOXL 슈퍼알파형] (-15/-25/-35)",
        "baseWeights": {"QQQ": 0.50, "SCHD": 0.50},
        "dropStages": [
            {"threshold": -15.0, "weights": {"QQQ": 0.30, "QLD": 0.40, "SOXL": 0.10, "SCHD": 0.20}},
            {"threshold": -25.0, "weights": {"QQQ": 0.20, "QLD": 0.40, "SOXL": 0.30, "SCHD": 0.10}},
            {"threshold": -35.0, "weights": {"QQQ": 0.10, "QLD": 0.30, "TQQQ": 0.30, "SOXL": 0.20, "SCHD": 0.10}}
        ],
        "gainThresholdPct": 20.0
    },
    {
        "name": "대안 4: [고수익 집중 레버리지형] (-12/-22/-32)",
        "baseWeights": {"QQQ": 0.70, "SCHD": 0.30},
        "dropStages": [
            {"threshold": -12.0, "weights": {"QQQ": 0.30, "QLD": 0.50, "SCHD": 0.20}},
            {"threshold": -22.0, "weights": {"QQQ": 0.10, "QLD": 0.40, "TQQQ": 0.40, "SCHD": 0.10}},
            {"threshold": -32.0, "weights": {"QLD": 0.30, "TQQQ": 0.60, "SCHD": 0.10}}
        ],
        "gainThresholdPct": 20.0
    },
    {
        "name": "벤치마크: QQQ 100% (나스닥 단순보유)",
        "baseWeights": {"QQQ": 1.0},
        "dropStages": [],
        "gainThresholdPct": 0
    },
    {
        "name": "벤치마크: SPY 100% (S&P500 단순보유)",
        "baseWeights": {"SPY": 1.0},
        "dropStages": [],
        "gainThresholdPct": 0
    },
    {
        "name": "벤치마크: QQQ 60% + SCHD 40% (정적배분)",
        "baseWeights": {"QQQ": 0.60, "SCHD": 0.40},
        "dropStages": [],
        "gainThresholdPct": 0
    }
]

results = [simulate(s) for s in strats]
with open('eval_output.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("SUCCESS")
