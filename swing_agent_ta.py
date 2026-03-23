import pandas as pd
import pandas_ta as ta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def analyze_swing_setups(df, symbol):
    """
    Analyzes daily OHLCV data to detect high-probability swing trading setups.
    Returns a dictionary of active signals formatted for an LLM to digest.
    """
    if df is None or df.empty or len(df) < 200:
        logging.warning(f"Not enough data to calculate structural indicators for {symbol}.")
        return None

    # ==========================================
    # 1. CALCULATE INDICATORS (Appended to DF)
    # ==========================================
    # Trend: 50-day and 200-day Exponential Moving Averages
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)
    
    # Momentum: 14-day RSI
    df.ta.rsi(length=14, append=True)
    
    # Trend Reversal: MACD (Fast 12, Slow 26, Signal 9)
    df.ta.macd(append=True)
    
    # Volume: 20-day Simple Moving Average of Volume
    df['VOL_SMA_20'] = df['volume'].rolling(window=20).mean()

    # Get the last two days of data to check for crossovers and recent momentum
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # Initialize the report dictionary
    report = {
        "symbol": symbol,
        "date": str(latest.name.date()),
        "close_price": round(latest['close'], 2),
        "signals": [],
        "trend_context": "",
        "volume_context": ""
    }

    # ==========================================
    # 2. SCAN FOR SPECIFIC ACTIONABLE SETUPS
    # ==========================================

    # A. The Golden / Death Cross
    if prev['EMA_50'] <= prev['EMA_200'] and latest['EMA_50'] > latest['EMA_200']:
        report["signals"].append("GOLDEN CROSS: 50 EMA crossed above 200 EMA (Macro Bullish).")
    elif prev['EMA_50'] >= prev['EMA_200'] and latest['EMA_50'] < latest['EMA_200']:
        report["signals"].append("DEATH CROSS: 50 EMA crossed below 200 EMA (Macro Bearish).")

    # B. EMA Support Bounce (Pullback Strategy)
    # Price dips below 50 EMA but closes above it, indicating buyers stepped in
    if prev['close'] < prev['EMA_50'] and latest['close'] > latest['EMA_50']:
        report["signals"].append("EMA RECLAIM: Price reclaimed the 50-day EMA support.")
    
    # C. RSI Divergence / Extremes
    if prev['RSI_14'] < 30 and latest['RSI_14'] >= 30:
        report["signals"].append("RSI BOUNCE: Momentum recovering from deep oversold territory (<30).")
    elif latest['RSI_14'] > 70:
        report["signals"].append("RSI OVERBOUGHT: Trading in high-risk overbought zone (>70).")

    # D. MACD Bullish / Bearish Crossover
    # MACD line crosses above the Signal line
    macd_line = latest['MACD_12_26_9']
    signal_line = latest['MACDs_12_26_9']
    prev_macd = prev['MACD_12_26_9']
    prev_signal = prev['MACDs_12_26_9']
    
    if prev_macd <= prev_signal and macd_line > signal_line and macd_line < 0:
        report["signals"].append("MACD CROSS: Bullish crossover below the zero line (Early Reversal).")

    # E. Volume Breakout
    if latest['volume'] > (latest['VOL_SMA_20'] * 2.5):
        report["volume_context"] = "MASSIVE VOLUME SPIKE: Volume is > 2.5x the 20-day average."

    # ==========================================
    # 3. DEFINE BROADER CONTEXT FOR THE LLM
    # ==========================================
    if latest['close'] > latest['EMA_50'] and latest['EMA_50'] > latest['EMA_200']:
        report["trend_context"] = "Strong Uptrend (Price > 50 EMA > 200 EMA)"
    elif latest['close'] < latest['EMA_50'] and latest['EMA_50'] < latest['EMA_200']:
        report["trend_context"] = "Strong Downtrend (Price < 50 EMA < 200 EMA)"
    else:
        report["trend_context"] = "Consolidating / Range-bound"

    # Only return the report if there's actually a signal or extreme volume to act on
    if report["signals"] or "SPIKE" in report["volume_context"]:
        return report
    
    return None

# ==========================================
# Testing the Logic
# ==========================================
if __name__ == "__main__":
    # Assuming `df_swing` is the DataFrame fetched from the previous script
    # For testing, you would pass the df returned from `fetch_swing_data`
    
    # Example usage:
    # report = analyze_swing_setups(df_swing, "RELIANCE")
    # if report:
    #     import json
    #     print(json.dumps(report, indent=4))
    pass