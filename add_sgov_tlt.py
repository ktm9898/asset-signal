import json
import yfinance as yf
import pandas as pd
import numpy as np

with open("data/etf_history.json", "r", encoding="utf-8") as f:
    ds = json.load(f)

dates = ds["dates"]
start_date = dates[0]

print(f"Fetching SGOV...")
ticker_data = yf.Ticker("SGOV")
hist = ticker_data.history(start=start_date, auto_adjust=False)

# SGOV started trading in May 2020. Before that, backfill with early price (approx $100.0)
df_close = hist["Close"]
df_close.index = df_close.index.strftime('%Y-%m-%d')
df_reindexed = df_close.reindex(dates)
# Backfill pre-2020 dates with earliest available price (~100.0) and forward fill holidays
df_reindexed = df_reindexed.bfill().ffill()

close_list = [round(float(x), 2) for x in df_reindexed]

ds["universe"]["SGOV"] = {
    "name": "iShares 0-3 Month Treasury Bond",
    "category": "US_CASH",
    "currency": "USD",
    "close": close_list,
    "latestPrice": close_list[-1]
}

print(f"Added SGOV: {len(close_list)} data points, latest price: {close_list[-1]}")

with open("data/etf_history.json", "w", encoding="utf-8") as f:
    json.dump(ds, f, ensure_ascii=False)
print("Updated etf_history.json successfully!")
