import json

with open("data/etf_history.json", "r", encoding="utf-8") as f:
    ds = f.read()

data = json.loads(ds)
print("Available Benchmark Tickers in data:", list(data.get("universe", {}).keys()))
if "^NDX" in data["universe"]:
    print("^NDX data points:", len(data["universe"]["^NDX"]["close"]))
if "^IXIC" in data["universe"]:
    print("^IXIC data points:", len(data["universe"]["^IXIC"]["close"]))
