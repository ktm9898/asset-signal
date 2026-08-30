import json

with open("data/etf_history.json", "r", encoding="utf-8") as f:
    ds = json.load(f)

dates = ds["dates"]
print("Total dates:", len(dates))

sDate = "2026-05-19"
# find closest date >= sDate
try:
    sIdx = next(i for i, d in enumerate(dates) if d >= sDate)
    print("Found sIdx:", sIdx, "Date:", dates[sIdx])
    
    for t in ["SCHD", "QQQ", "^NDX"]:
        asset = ds["universe"][t]
        start_p = asset["close"][sIdx]
        end_p = asset["close"][-1]
        ret = ((end_p - start_p) / start_p) * 100.0
        print(f"{t}: start={start_p}, end={end_p}, return={ret:.2f}%")
except Exception as e:
    print("Error:", e)
