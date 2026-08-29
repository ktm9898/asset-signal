"""
ETF Historical Dataset Builder
Fetches long-term Total Return (Adjusted Close) daily price data for major US & Korean ETFs,
and generates compact data/etf_history.json for fast client-side backtesting and signal processing.
"""

import os
import json
import datetime
import yfinance as yf
import pandas as pd
import numpy as np

ETF_UNIVERSE = [
    # US Nasdaq / Tech
    {"ticker": "QQQ", "name": "Invesco QQQ (나스닥 100)", "category": "US_TECH", "currency": "USD"},
    {"ticker": "QLD", "name": "ProShares Ultra QQQ (2X 레버리지)", "category": "US_TECH_LEV", "currency": "USD"},
    {"ticker": "TQQQ", "name": "ProShares UltraPro QQQ (3X 레버리지)", "category": "US_TECH_LEV", "currency": "USD"},
    
    # US Broad / Dividend / Value
    {"ticker": "SPY", "name": "SPDR S&P 500 Trust", "category": "US_BROAD", "currency": "USD"},
    {"ticker": "SSO", "name": "ProShares Ultra S&P500 (2X)", "category": "US_BROAD_LEV", "currency": "USD"},
    {"ticker": "UPRO", "name": "ProShares UltraPro S&P500 (3X)", "category": "US_BROAD_LEV", "currency": "USD"},
    {"ticker": "SCHD", "name": "Schwab US Dividend Equity (배당성장)", "category": "US_DIVIDEND", "currency": "USD"},
    {"ticker": "JEPI", "name": "JPMorgan Equity Premium Income", "category": "US_INCOME", "currency": "USD"},
    
    # US Fixed Income / Semiconductor / Cash
    {"ticker": "TLT", "name": "iShares 20+ Year Treasury Bond", "category": "US_BOND", "currency": "USD"},
    {"ticker": "SOXX", "name": "iShares Semiconductor ETF", "category": "US_SEMI", "currency": "USD"},
    {"ticker": "SOXL", "name": "Direxion Daily Semiconductor Bull 3X", "category": "US_SEMI_LEV", "currency": "USD"},
    {"ticker": "BIL", "name": "SPDR 1-3 Month T-Bill (현금성)", "category": "US_CASH", "currency": "USD"},
    
    # Korean ETFs
    {"ticker": "069500.KS", "name": "KODEX 200", "category": "KR_BROAD", "currency": "KRW"},
    {"ticker": "122630.KS", "name": "KODEX 레버리지 (2X)", "category": "KR_LEV", "currency": "KRW"},
    {"ticker": "379800.KS", "name": "KODEX 미국나스닥100TR", "category": "KR_US_TECH", "currency": "KRW"},
    {"ticker": "379810.KS", "name": "KODEX 미국S&P500TR", "category": "KR_US_BROAD", "currency": "KRW"},
    {"ticker": "448290.KS", "name": "ACE 미국배당다우존스", "category": "KR_US_DIV", "currency": "KRW"},
]

def build_etf_dataset(start_date="2010-01-01", output_file="data/etf_history.json"):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    print(f"[INFO] Fetching historical data for {len(ETF_UNIVERSE)} ETFs from {start_date}...")
    
    ticker_list = [item["ticker"] for item in ETF_UNIVERSE]
    
    # Fetch from yfinance
    try:
        data = yf.download(
            tickers=ticker_list,
            start=start_date,
            end=datetime.date.today() + datetime.timedelta(days=1),
            auto_adjust=False,
            progress=True
        )
    except Exception as e:
        print(f"[ERROR] Failed to download ETF data: {e}")
        return None

    if data.empty:
        print("[ERROR] Downloaded data is empty.")
        return None

    # Handle multi-index columns
    adj_close_df = data['Adj Close'] if 'Adj Close' in data else data['Close']
    close_df = data['Close']
    
    # We will build US trading day aligned dates as primary reference
    us_dates = [d.strftime("%Y-%m-%d") for d in data.index]
    
    result = {
        "updatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "startDate": start_date,
        "endDate": us_dates[-1] if us_dates else "",
        "dates": us_dates,
        "universe": {}
    }
    
    for item in ETF_UNIVERSE:
        t = item["ticker"]
        name = item["name"]
        cat = item["category"]
        curr = item["currency"]
        
        if t in adj_close_df.columns:
            # Map to all dates (forward fill for missing days / holidays)
            aligned_adj = adj_close_df[t].ffill().bfill()
            aligned_close = close_df[t].ffill().bfill()
            
            # If still has NaN, fill 0
            adj_values = [round(float(v), 4) if pd.notna(v) else None for v in aligned_adj]
            close_values = [round(float(v), 4) if pd.notna(v) else None for v in aligned_close]
            
            # Calculate Rolling Peak and Drawdown for benchmark purposes
            valid_adj = np.array([v if v is not None else 0 for v in adj_values])
            running_max = np.maximum.accumulate(valid_adj)
            # Avoid division by zero
            with np.errstate(divide='ignore', invalid='ignore'):
                dd = np.where(running_max > 0, (valid_adj - running_max) / running_max * 100.0, 0.0)
            dd_values = [round(float(v), 2) for v in dd]
            
            result["universe"][t] = {
                "ticker": t,
                "name": name,
                "category": cat,
                "currency": curr,
                "adjClose": adj_values,
                "close": close_values,
                "drawdown": dd_values,
                "latestPrice": close_values[-1] if close_values else 0,
                "latestAdjClose": adj_values[-1] if adj_values else 0,
                "latestDrawdown": dd_values[-1] if dd_values else 0.0,
                "allTimeHigh": round(float(np.max(valid_adj)), 4) if len(valid_adj) > 0 else 0
            }
            print(f" -> Processed {t}: {len(adj_values)} days (Latest Price: {close_values[-1]}, MDD: {dd_values[-1]}%)")
        else:
            print(f"[WARN] Ticker {t} not found in downloaded columns.")
            
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        
    file_size_kb = os.path.getsize(output_file) / 1024
    print(f"[SUCCESS] Saved ETF dataset to {output_file} ({file_size_kb:.1f} KB)")
    return result

if __name__ == "__main__":
    build_etf_dataset(start_date="2010-01-01")
