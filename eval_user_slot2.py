import json
import numpy as np
import datetime
import yfinance as yf

# Load historical data
tickers = ["^NDX", "^GSPC", "QQQ", "SPY", "SOXX"]
data = yf.download(tickers, start="1999-01-01", end=datetime.date.today() + datetime.timedelta(days=1), auto_adjust=False, progress=False)
adj_df = (data['Adj Close'] if 'Adj Close' in data else data['Close']).ffill().bfill()
close_df = data['Close'].ffill().bfill()
dates = [d.strftime("%Y-%m-%d") for d in close_df.index]

ndx_ret = adj_df['^NDX'].pct_change().fillna(0).values
gspc_ret = adj_df['^GSPC'].pct_change().fillna(0).values
qqq_ret = adj_df['QQQ'].pct_change().fillna(0).values if 'QQQ' in adj_df else ndx_ret
soxx_ret = adj_df['SOXX'].pct_change().fillna(0).values if 'SOXX' in adj_df else ndx_ret

qld_ret = ndx_ret * 2.0 - (0.0095 / 252.0)
qld_prices = np.cumprod(1.0 + qld_ret)

tqqq_ret = ndx_ret * 3.0 - (0.0095 / 252.0)
tqqq_prices = np.cumprod(1.0 + tqqq_ret)

schd_ret = gspc_ret * 0.85 + 0.0001
schd_prices = np.cumprod(1.0 + schd_ret)

qqq_prices = np.cumprod(1.0 + qqq_ret)
ndx_prices = adj_df['^NDX'].values

all_asset_prices = {
    "^NDX": ndx_prices,
    "QQQ": qqq_prices,
    "QLD": qld_prices,
    "TQQQ": tqqq_prices,
    "SCHD": schd_prices
}

def simulate_segment(strat, start_date_str, end_date_str):
    s_idx = next((i for i, d in enumerate(dates) if d >= start_date_str), 0)
    e_idx = next((i for i in range(len(dates)-1, -1, -1) if dates[i] <= end_date_str), len(dates)-1)
    seg_dates = dates[s_idx:e_idx+1]
    seg_len = len(seg_dates)
    if seg_len == 0: return None

    seg_prices = {t: all_asset_prices[t][s_idx:e_idx+1] for t in all_asset_prices}
    bm_prices = seg_prices["^NDX"]
    bm_drawdowns = np.zeros(seg_len, dtype=float)
    bm_max = 0.0
    for i in range(seg_len):
        if bm_prices[i] > bm_max: bm_max = bm_prices[i]
        bm_drawdowns[i] = ((bm_prices[i] - bm_max) / bm_max) * 100.0 if bm_max > 0 else 0.0

    initial_cap = 100000000.0
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

    for day in range(seg_len):
        nav = sum(holdings.get(t, 0.0) * seg_prices[t][day] for t in holdings)
        strat_nav[day] = nav
        dd = bm_drawdowns[day]
        tgt_weights = None
        next_stage_idx = current_stage_idx
        days_since = day - last_rebal_day

        if len(stages) > 0:
            if current_stage_idx < 0:
                deepest = -1
                for i, stg in enumerate(stages):
                    if dd <= stg['threshold']: deepest = i
                if deepest >= 0:
                    next_stage_idx = deepest
                    tgt_weights = stages[deepest]['weights']
            else:
                deeper = current_stage_idx
                for i in range(current_stage_idx + 1, len(stages)):
                    if dd <= stages[i]['threshold']: deeper = i
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
            trade_vol = sum(abs(nav * tgt_weights.get(t, 0.0) - holdings.get(t, 0.0) * seg_prices[t][day]) for t in set(list(holdings.keys()) + list(tgt_weights.keys())))
            net_nav = nav - (trade_vol / 2.0) * 0.0015
            holdings = {t: (net_nav * tgt_weights.get(t, 0.0)) / seg_prices[t][day] for t in tgt_weights if tgt_weights.get(t, 0.0) > 0}
            current_stage_idx = next_stage_idx
            last_rebal_day = day
            last_rebal_nav = net_nav
            rebal_count += 1

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
        if strat_nav[i] > peak: peak = strat_nav[i]
        d = ((strat_nav[i] - peak) / peak) * 100.0
        if d < mdd: mdd = d
        if i > 0: daily_rets.append((strat_nav[i] - strat_nav[i-1]) / strat_nav[i-1])

    daily_rets = np.array(daily_rets)
    sharpe = (np.mean(daily_rets) / np.std(daily_rets)) * np.sqrt(252) if np.std(daily_rets) > 0 else 0.0

    return {
        "final_nav": round(final_nav),
        "total_ret_pct": round(total_ret, 1),
        "cagr_pct": round(cagr, 2),
        "mdd_pct": round(mdd, 2),
        "sharpe": round(sharpe, 2),
        "rebal_count": rebal_count
    }

user_slot_1 = {
    "name": "전략 1번",
    "baseWeights": {"SCHD": 0.60, "QQQ": 0.40},
    "dropStages": [
        {"threshold": -15.0, "weights": {"SCHD": 0.40, "QQQ": 0.60}},
        {"threshold": -25.0, "weights": {"SCHD": 0.40, "QQQ": 0.40, "QLD": 0.20}},
        {"threshold": -40.0, "weights": {"SCHD": 0.20, "QQQ": 0.40, "QLD": 0.40}},
        {"threshold": -60.0, "weights": {"SCHD": 0.20, "QQQ": 0.20, "QLD": 0.40, "TQQQ": 0.20}},
        {"threshold": -80.0, "weights": {"SCHD": 0.00, "QQQ": 0.20, "QLD": 0.40, "TQQQ": 0.40}}
    ],
    "gainThresholdPct": 20.0
}

user_slot_2 = {
    "name": "전략 2번 (사용자가 새로 짠 레버리지 조기투입)",
    "baseWeights": {"SCHD": 0.60, "QQQ": 0.40},
    "dropStages": [
        {"threshold": -10.0, "weights": {"SCHD": 0.40, "QQQ": 0.40, "QLD": 0.20}},
        {"threshold": -25.0, "weights": {"SCHD": 0.20, "QQQ": 0.40, "QLD": 0.40}},
        {"threshold": -40.0, "weights": {"SCHD": 0.20, "QQQ": 0.00, "QLD": 0.80}},
        {"threshold": -60.0, "weights": {"SCHD": 0.20, "QQQ": 0.00, "QLD": 0.40, "TQQQ": 0.40}},
        {"threshold": -80.0, "weights": {"SCHD": 0.20, "QQQ": 0.00, "QLD": 0.00, "TQQQ": 0.80}}
    ],
    "gainThresholdPct": 20.0
}

res_2012 = {
    "strat1": simulate_segment(user_slot_1, "2012-01-02", "2026-08-28"),
    "strat2": simulate_segment(user_slot_2, "2012-01-02", "2026-08-28")
}

res_2008 = {
    "strat1": simulate_segment(user_slot_1, "2006-01-03", "2013-12-31"),
    "strat2": simulate_segment(user_slot_2, "2006-01-03", "2013-12-31")
}

res_2000 = {
    "strat1": simulate_segment(user_slot_1, "2000-01-03", "2007-12-31"),
    "strat2": simulate_segment(user_slot_2, "2000-01-03", "2007-12-31")
}

res_full = {
    "strat1": simulate_segment(user_slot_1, "2000-01-03", "2026-08-28"),
    "strat2": simulate_segment(user_slot_2, "2000-01-03", "2026-08-28")
}

output = {
    "2012_2026": res_2012,
    "2008_GFC": res_2008,
    "2000_DOTCOM": res_2000,
    "2000_2026_FULL": res_full
}

with open("user_slot2_eval.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("SLOT 2 EVALUATION COMPLETE")
