"""
ETF & Market Indices Historical Dataset Builder with Technical Indicators
Fetches long-term daily price data for Market Indices (NASDAQ, S&P 500, KOSPI) and US/KR ETFs,
computes technical indicators (RSI, Moving Averages, MACD, Bollinger Bands, MDD from ATH, 52W H/L),
and bundles data into data/etf_history.json.
"""

import os
import json
import datetime
import yfinance as yf
import pandas as pd
import numpy as np

MARKET_UNIVERSE = [
    # 1. Major Benchmark Market Indices
    {"ticker": "^NDX", "name": "나스닥 100 지수", "category": "INDEX", "currency": "USD", "isIndex": True},
    {"ticker": "^GSPC", "name": "S&P 500 지수", "category": "INDEX", "currency": "USD", "isIndex": True},
    {"ticker": "^KS11", "name": "코스피 지수", "category": "INDEX", "currency": "KRW", "isIndex": True},
    
    # 2. US Tech & Leverage ETFs
    {"ticker": "QQQ", "name": "Invesco QQQ (나스닥 100 1X)", "category": "US_TECH", "currency": "USD"},
    {"ticker": "QLD", "name": "ProShares Ultra QQQ (2X 레버리지)", "category": "US_TECH_LEV", "currency": "USD"},
    {"ticker": "TQQQ", "name": "ProShares UltraPro QQQ (3X 레버리지)", "category": "US_TECH_LEV", "currency": "USD"},
    {"ticker": "SOXX", "name": "iShares Semiconductor (반도체 1X)", "category": "US_SEMI", "currency": "USD"},
    {"ticker": "SOXL", "name": "Direxion Daily Semiconductor Bull 3X", "category": "US_SEMI_LEV", "currency": "USD"},
    
    # 3. US Broad, Dividend & Fixed Income
    {"ticker": "SPY", "name": "SPDR S&P 500 Trust (1X)", "category": "US_BROAD", "currency": "USD"},
    {"ticker": "SSO", "name": "ProShares Ultra S&P500 (2X)", "category": "US_BROAD_LEV", "currency": "USD"},
    {"ticker": "UPRO", "name": "ProShares UltraPro S&P500 (3X)", "category": "US_BROAD_LEV", "currency": "USD"},
    {"ticker": "SCHD", "name": "Schwab US Dividend Equity (배당다우존스)", "category": "US_DIVIDEND", "currency": "USD"},
    {"ticker": "JEPI", "name": "JPMorgan Equity Premium Income (커버드콜)", "category": "US_INCOME", "currency": "USD"},
    {"ticker": "TLT", "name": "iShares 20+ Year Treasury Bond (미국장기채)", "category": "US_BOND", "currency": "USD"},
    {"ticker": "BIL", "name": "SPDR 1-3 Month T-Bill (단기국채/현금성)", "category": "US_CASH", "currency": "USD"},
    
    # 4. Korean ETFs
    {"ticker": "069500.KS", "name": "KODEX 200", "category": "KR_BROAD", "currency": "KRW"},
    {"ticker": "122630.KS", "name": "KODEX 레버리지 (2X)", "category": "KR_LEV", "currency": "KRW"},
    {"ticker": "379800.KS", "name": "KODEX 미국나스닥100TR", "category": "KR_US_TECH", "currency": "KRW"},
    {"ticker": "379810.KS", "name": "KODEX 미국S&P500TR", "category": "KR_US_BROAD", "currency": "KRW"},
    {"ticker": "448290.KS", "name": "ACE 미국배당다우존스", "category": "KR_US_DIV", "currency": "KRW"},
]

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    sig = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - sig
    return macd, sig, hist

def build_etf_dataset(start_date="2010-01-01", output_file="data/etf_history.json"):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    print(f"[INFO] Fetching historical data for {len(MARKET_UNIVERSE)} assets/indices from {start_date}...")
    
    ticker_list = [item["ticker"] for item in MARKET_UNIVERSE]
    
    try:
        data = yf.download(
            tickers=ticker_list,
            start=start_date,
            end=datetime.date.today() + datetime.timedelta(days=1),
            auto_adjust=False,
            progress=True
        )
    except Exception as e:
        print(f"[ERROR] Failed to download data: {e}")
        return None

    if data.empty:
        print("[ERROR] Downloaded data is empty.")
        return None

    adj_close_df = data['Adj Close'] if 'Adj Close' in data else data['Close']
    close_df = data['Close']
    high_df = data['High'] if 'High' in data else close_df
    low_df = data['Low'] if 'Low' in data else close_df
    volume_df = data['Volume'] if 'Volume' in data else pd.DataFrame(0, index=close_df.index, columns=close_df.columns)

    # Clean date index
    adj_close_df = adj_close_df.ffill().bfill()
    close_df = close_df.ffill().bfill()
    date_strs = [d.strftime("%Y-%m-%d") for d in close_df.index]

    universe_dict = {}
    
    for item in MARKET_UNIVERSE:
        ticker = item["ticker"]
        if ticker not in close_df.columns:
            print(f"[WARN] Ticker {ticker} missing in download, skipping.")
            continue
            
        c_series = close_df[ticker].dropna()
        a_series = adj_close_df[ticker].dropna()
        h_series = high_df[ticker].dropna() if ticker in high_df.columns else c_series
        l_series = low_df[ticker].dropna() if ticker in low_df.columns else c_series
        v_series = volume_df[ticker].dropna() if ticker in volume_df.columns else pd.Series(0, index=c_series.index)

        # Align series to global date index
        aligned_adj = adj_close_df[ticker].values
        aligned_close = close_df[ticker].values
        
        # Technical indicators on latest data
        rsi_series = calculate_rsi(c_series, 14)
        sma20 = c_series.rolling(20).mean()
        sma50 = c_series.rolling(50).mean()
        sma200 = c_series.rolling(200).mean()
        macd_val, macd_sig, macd_hist = calculate_macd(c_series)
        
        # Bollinger Bands (20, 2)
        bb_std = c_series.rolling(20).std()
        bb_upper = sma20 + (bb_std * 2)
        bb_lower = sma20 - (bb_std * 2)

        # ATH & MDD from ATH
        peak_series = c_series.cummax()
        mdd_series = (c_series - peak_series) / peak_series * 100.0
        
        # 52-Week High / Low
        last_252 = c_series.tail(252)
        w52_high = float(last_252.max()) if len(last_252) > 0 else float(c_series.iloc[-1])
        w52_low = float(last_252.min()) if len(last_252) > 0 else float(c_series.iloc[-1])

        latest_close = float(c_series.iloc[-1])
        prev_close = float(c_series.iloc[-2]) if len(c_series) > 1 else latest_close
        chg_1d = ((latest_close - prev_close) / prev_close) * 100.0 if prev_close > 0 else 0.0

        ath_val = float(peak_series.iloc[-1])
        current_mdd = float(mdd_series.iloc[-1])

        universe_dict[ticker] = {
            "ticker": ticker,
            "name": item["name"],
            "category": item["category"],
            "currency": item["currency"],
            "isIndex": item.get("isIndex", False),
            "latestPrice": round(latest_close, 2),
            "change1D": round(chg_1d, 2),
            "ath": round(ath_val, 2),
            "mdd": round(current_mdd, 2),
            "w52High": round(w52_high, 2),
            "w52Low": round(w52_low, 2),
            "rsi14": round(float(rsi_series.iloc[-1]), 1) if len(rsi_series) > 0 else 50.0,
            "sma20": round(float(sma20.iloc[-1]), 2) if not pd.isna(sma20.iloc[-1]) else latest_close,
            "sma50": round(float(sma50.iloc[-1]), 2) if not pd.isna(sma50.iloc[-1]) else latest_close,
            "sma200": round(float(sma200.iloc[-1]), 2) if not pd.isna(sma200.iloc[-1]) else latest_close,
            "macd": round(float(macd_val.iloc[-1]), 2) if not pd.isna(macd_val.iloc[-1]) else 0.0,
            "macdSignal": round(float(macd_sig.iloc[-1]), 2) if not pd.isna(macd_sig.iloc[-1]) else 0.0,
            "bbUpper": round(float(bb_upper.iloc[-1]), 2) if not pd.isna(bb_upper.iloc[-1]) else latest_close,
            "bbLower": round(float(bb_lower.iloc[-1]), 2) if not pd.isna(bb_lower.iloc[-1]) else latest_close,
            "adjClose": [round(float(v), 4) for v in aligned_adj],
            "close": [round(float(v), 4) for v in aligned_close]
        }
        
    dataset = {
        "updatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "startDate": date_strs[0],
        "endDate": date_strs[-1],
        "tradingDays": len(date_strs),
        "dates": date_strs,
        "universe": universe_dict
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False)

    size_kb = os.path.getsize(output_file) / 1024
    print(f"[SUCCESS] Dataset built successfully -> {output_file} ({size_kb:.1f} KB, {len(universe_dict)} tickers, {len(date_strs)} dates)")
    return dataset

if __name__ == "__main__":
    build_etf_dataset()
