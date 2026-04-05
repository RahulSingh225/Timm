"""
Swing Agent — Technical Analysis Engine v2.0

Produces structured, actionable analysis for each stock:
- Multi-indicator scan (EMA, BB, RSI, MACD, ATR)
- Support / Resistance from pivot points + swing highs/lows
- Bollinger Band squeeze and reversal detection
- ATR-based realistic move potential
- Entry / SL / Target calculation
- Trend context (daily + weekly if available)
"""

import pandas as pd
import pandas_ta as ta
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SWING TA] - %(message)s')


def _calc_pivot_levels(high: float, low: float, close: float) -> dict:
    """Classic pivot points: P, R1, R2, R3, S1, S2, S3."""
    pivot = (high + low + close) / 3
    r1 = (2 * pivot) - low
    s1 = (2 * pivot) - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    r3 = high + 2 * (pivot - low)
    s3 = low - 2 * (high - pivot)
    return {
        "pivot": round(pivot, 2),
        "r1": round(r1, 2), "r2": round(r2, 2), "r3": round(r3, 2),
        "s1": round(s1, 2), "s2": round(s2, 2), "s3": round(s3, 2),
    }


def _find_swing_sr(df: pd.DataFrame, lookback: int = 20) -> dict:
    """Find nearest support and resistance from recent swing highs/lows."""
    recent = df.tail(lookback)
    highs = recent['high'].values
    lows = recent['low'].values
    close = df.iloc[-1]['close']

    # Swing highs: local maxima
    resistance_levels = []
    for i in range(1, len(highs) - 1):
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            resistance_levels.append(round(float(highs[i]), 2))

    # Swing lows: local minima
    support_levels = []
    for i in range(1, len(lows) - 1):
        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            support_levels.append(round(float(lows[i]), 2))

    # Find nearest
    resistance_above = [r for r in resistance_levels if r > close]
    support_below = [s for s in support_levels if s < close]

    nearest_resistance = min(resistance_above) if resistance_above else None
    nearest_support = max(support_below) if support_below else None

    return {
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "support_levels": sorted(set(support_below))[-3:] if support_below else [],
        "resistance_levels": sorted(set(resistance_above))[:3] if resistance_above else [],
    }


def analyze_swing_setups(df: pd.DataFrame, symbol: str, weekly_df: pd.DataFrame = None) -> dict | None:
    """
    Full structural analysis on daily OHLCV data.
    Returns a rich, structured report for downstream consumers.
    """
    if df is None or df.empty or len(df) < 200:
        logging.warning(f"Not enough data for {symbol} (need 200+, got {len(df) if df is not None else 0}).")
        return None

    # Normalize column names to lowercase
    df.columns = [c.lower() for c in df.columns]

    # ──────────────────────────────────────────────────
    # 1. CALCULATE ALL INDICATORS
    # ──────────────────────────────────────────────────

    # EMAs
    df.ta.ema(length=9, append=True)
    df.ta.ema(length=21, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)

    # RSI
    df.ta.rsi(length=14, append=True)

    # MACD
    df.ta.macd(append=True)

    # Bollinger Bands (20, 2)
    df.ta.bbands(length=20, std=2, append=True)

    # ATR (14-day)
    df.ta.atr(length=14, append=True)

    # ADX (14-day)
    # pandas-ta adx returns ADX_14, DMP_14, DMN_14
    df.ta.adx(length=14, append=True)

    # OBV (On-Balance Volume)
    df.ta.obv(append=True)

    # VWAP
    df.ta.vwap(append=True)

    # Volume SMA
    df['VOL_SMA_20'] = df['volume'].rolling(window=20).mean()

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    close = float(latest['close'])
    signals = []

    # ──────────────────────────────────────────────────
    # 2. TREND CONTEXT
    # ──────────────────────────────────────────────────
    ema9 = latest.get('EMA_9', close)
    ema21 = latest.get('EMA_21', close)
    ema50 = latest.get('EMA_50', close)
    ema200 = latest.get('EMA_200', close)

    if close > ema50 and ema50 > ema200:
        daily_trend = "BULLISH"
    elif close < ema50 and ema50 < ema200:
        daily_trend = "BEARISH"
    else:
        daily_trend = "NEUTRAL"

    adx = latest.get('ADX_14', 0)
    if adx > 25:
        daily_trend_strength = "STRONG"
    elif adx < 20:
        daily_trend_strength = "CHOPPY"
    else:
        daily_trend_strength = "WEAK"

    # Short-term micro-trend from 9/21 EMA
    if ema9 > ema21:
        micro_trend = "BULLISH"
    elif ema9 < ema21:
        micro_trend = "BEARISH"
    else:
        micro_trend = "NEUTRAL"

    # Multi-Timeframe Confluence (MTFC): Weekly Trend
    weekly_trend = "NEUTRAL"
    if weekly_df is not None and not weekly_df.empty and len(weekly_df) >= 50:
        weekly_df.columns = [c.lower() for c in weekly_df.columns]
        weekly_df.ta.ema(length=10, append=True)
        weekly_df.ta.ema(length=40, append=True)
        w_latest = weekly_df.iloc[-1]
        w_ema10 = w_latest.get('EMA_10', w_latest['close'])
        w_ema40 = w_latest.get('EMA_40', w_latest['close'])
        
        if w_latest['close'] > w_ema10 and w_ema10 > w_ema40:
            weekly_trend = "BULLISH"
        elif w_latest['close'] < w_ema10 and w_ema10 < w_ema40:
            weekly_trend = "BEARISH"
    
    if weekly_trend != "NEUTRAL":
        if weekly_trend == daily_trend:
            signals.append(f"MTFC ALIGNMENT: Both Weekly and Daily are {weekly_trend}.")
        else:
            signals.append(f"MTFC CONFLICT: Weekly is {weekly_trend} but Daily is {daily_trend}.")

    # ──────────────────────────────────────────────────
    # 3. SIGNAL DETECTION
    # ──────────────────────────────────────────────────

    # A. EMA Crossovers
    if prev.get('EMA_50', 0) <= prev.get('EMA_200', 0) and ema50 > ema200:
        signals.append("GOLDEN CROSS: 50 EMA crossed above 200 EMA (Macro Bullish).")
    elif prev.get('EMA_50', 0) >= prev.get('EMA_200', 0) and ema50 < ema200:
        signals.append("DEATH CROSS: 50 EMA crossed below 200 EMA (Macro Bearish).")

    # 9/21 EMA cross (fast)
    if prev.get('EMA_9', 0) <= prev.get('EMA_21', 0) and ema9 > ema21:
        signals.append("FAST EMA CROSS: 9 EMA crossed above 21 EMA (Short-term Bullish).")
    elif prev.get('EMA_9', 0) >= prev.get('EMA_21', 0) and ema9 < ema21:
        signals.append("FAST EMA CROSS: 9 EMA crossed below 21 EMA (Short-term Bearish).")

    # B. EMA Support Bounce
    if prev['close'] < prev.get('EMA_50', 0) and close > ema50:
        signals.append("EMA RECLAIM: Price reclaimed 50-day EMA support.")

    # C. RSI
    rsi = latest.get('RSI_14', 50)
    prev_rsi = prev.get('RSI_14', 50)
    if not pd.isna(rsi) and not pd.isna(prev_rsi):
        if prev_rsi < 30 and rsi >= 30:
            signals.append(f"RSI BOUNCE: Recovering from oversold (RSI {round(rsi, 1)}).")
        elif prev_rsi < 40 and rsi >= 40:
            signals.append(f"RSI MOMENTUM: Crossed above 40 (RSI {round(rsi, 1)}).")
        elif rsi > 70:
            signals.append(f"RSI OVERBOUGHT: In high-risk zone (RSI {round(rsi, 1)}).")

    # D. MACD
    macd_val = latest.get('MACD_12_26_9', 0)
    signal_val = latest.get('MACDs_12_26_9', 0)
    prev_macd = prev.get('MACD_12_26_9', 0)
    prev_signal = prev.get('MACDs_12_26_9', 0)

    if not any(pd.isna(v) for v in [macd_val, signal_val, prev_macd, prev_signal]):
        if prev_macd <= prev_signal and macd_val > signal_val:
            if macd_val < 0:
                signals.append("MACD BULLISH CROSS: Below zero line (Early reversal).")
            else:
                signals.append("MACD BULLISH CROSS: Above zero line (Trend continuation).")
        elif prev_macd >= prev_signal and macd_val < signal_val:
            signals.append("MACD BEARISH CROSS: Momentum shifting down.")

    # E. Bollinger Band Signals
    bb_upper = latest.get('BBU_20_2.0', None)
    bb_lower = latest.get('BBL_20_2.0', None)
    bb_mid = latest.get('BBM_20_2.0', None)
    bb_width = latest.get('BBB_20_2.0', None)
    prev_bb_lower = prev.get('BBL_20_2.0', None)

    if bb_upper and bb_lower and bb_mid:
        # BB Squeeze: width narrowing
        if bb_width is not None and not pd.isna(bb_width):
            bb_width_sma = df['BBB_20_2.0'].rolling(20).mean().iloc[-1] if 'BBB_20_2.0' in df.columns else None
            if bb_width_sma and not pd.isna(bb_width_sma) and bb_width < bb_width_sma * 0.6:
                signals.append(f"BB SQUEEZE: Bandwidth is {round(bb_width, 2)} vs avg {round(bb_width_sma, 2)} — breakout imminent.")

        # BB Reversal: touched lower band then closed inside
        if prev_bb_lower and not pd.isna(prev_bb_lower):
            if prev['close'] <= prev_bb_lower and close > bb_lower:
                signals.append(f"BB REVERSAL: Price bounced off lower band ₹{round(bb_lower, 2)} (Mean reversion).")

        # BB Upper breakout
        if close > bb_upper and not pd.isna(bb_upper):
            signals.append(f"BB BREAKOUT: Price closed above upper band ₹{round(bb_upper, 2)} (Momentum).")

    # F. Volume & OBV
    vol_sma = latest.get('VOL_SMA_20', 0)
    if vol_sma and not pd.isna(vol_sma) and vol_sma > 0:
        vol_ratio = latest['volume'] / vol_sma
        if vol_ratio >= 2.5:
            signals.append(f"MASSIVE VOLUME: {round(vol_ratio, 1)}x average ({int(latest['volume']):,} vs avg {int(vol_sma):,}).")
        elif vol_ratio >= 1.5:
            signals.append(f"VOLUME SPIKE: {round(vol_ratio, 1)}x average.")

    obv = latest.get('OBV', None)
    if obv is not None:
        # Simple OBV trend vs Price trend
        obv_sma = df['OBV'].rolling(20).mean().iloc[-1]
        if close > ema50 and obv < obv_sma:
            signals.append("BEARISH DIVERGENCE: Price is bullish but OBV is declining (Smart money exiting).")
        elif close < ema50 and obv > obv_sma:
            signals.append("BULLISH DIVERGENCE: Price is bearish but OBV is rising (Smart money accumulating).")

    vwap = latest.get('VWAP_D', None)
    if vwap is not None and not pd.isna(vwap):
        if prev['close'] < vwap and close > vwap:
            signals.append(f"VWAP RECLAIM: Price crossed above VWAP {round(vwap, 2)}.")

    # ──────────────────────────────────────────────────
    # 4. SUPPORT / RESISTANCE
    # ──────────────────────────────────────────────────
    prev_day_high = float(prev['high'])
    prev_day_low = float(prev['low'])
    prev_day_close = float(prev['close'])

    pivots = _calc_pivot_levels(prev_day_high, prev_day_low, prev_day_close)
    swing_sr = _find_swing_sr(df, lookback=30)

    # ──────────────────────────────────────────────────
    # 5. MOVE POTENTIAL (ATR-based)
    # ──────────────────────────────────────────────────
    atr = latest.get('ATRr_14', None)
    move_potential_pct = 0.0
    if atr and not pd.isna(atr) and close > 0:
        move_potential_pct = round((atr / close) * 100, 2)

    # ──────────────────────────────────────────────────
    # 6. ENTRY / SL / TARGET (only if signals found)
    # ──────────────────────────────────────────────────
    entry = None
    stoploss = None
    target = None
    risk_reward = None

    if signals:
        bullish_score = sum(1 for s in signals if any(kw in s for kw in ['BULLISH', 'GOLDEN', 'BOUNCE', 'RECLAIM', 'REVERSAL', 'MOMENTUM']))
        bearish_score = sum(1 for s in signals if any(kw in s for kw in ['BEARISH', 'DEATH', 'OVERBOUGHT']))
        is_bullish = bullish_score >= bearish_score

        entry = close
        if atr and not pd.isna(atr):
            if is_bullish:
                stoploss = round(close - (1.5 * atr), 2)
                target = round(close + (2.5 * atr), 2)
            else:
                stoploss = round(close + (1.5 * atr), 2)
                target = round(close - (2.5 * atr), 2)

            sl_dist = abs(close - stoploss)
            tgt_dist = abs(target - close)
            risk_reward = round(tgt_dist / sl_dist, 2) if sl_dist > 0 else 0

    # ──────────────────────────────────────────────────
    # 7. CONFIDENCE SCORE
    # ──────────────────────────────────────────────────
    confidence = 0
    if signals:
        confidence = min(len(signals) * 15, 60)  # Base: 15 per signal, cap 60
        if daily_trend == micro_trend and daily_trend != "NEUTRAL":
            confidence += 20  # Trend alignment bonus
        if move_potential_pct >= 2.0:
            confidence += 10  # High ATR = high opportunity
        if vol_sma and not pd.isna(vol_sma) and vol_sma > 0 and latest['volume'] / vol_sma >= 1.5:
            confidence += 10  # Volume confirmation
        confidence = min(confidence, 100)

    # Signal type
    bullish_count = sum(1 for s in signals if any(kw in s for kw in ['BULLISH', 'GOLDEN', 'BOUNCE', 'RECLAIM', 'REVERSAL', 'MOMENTUM', 'BREAKOUT']))
    bearish_count = sum(1 for s in signals if any(kw in s for kw in ['BEARISH', 'DEATH', 'OVERBOUGHT']))
    if bullish_count > bearish_count:
        signal_type = "BULLISH"
    elif bearish_count > bullish_count:
        signal_type = "BEARISH"
    else:
        signal_type = "NEUTRAL"

    # Only return if we have signals or extreme conditions
    if not signals:
        return None

    return {
        "symbol": symbol,
        "date": str(latest.name.date()) if hasattr(latest.name, 'date') else str(latest.name),
        "close_price": round(close, 2),
        "trend": {
            "daily": daily_trend,
            "micro": micro_trend,
            "weekly": weekly_trend,
            "strength": daily_trend_strength,
            "alignment": "STRONG" if daily_trend == micro_trend and daily_trend == weekly_trend else "WEAK" if daily_trend != micro_trend else "FLAT",
        },
        "support_resistance": {
            **swing_sr,
            **pivots,
        },
        "bollinger": {
            "upper": round(bb_upper, 2) if bb_upper and not pd.isna(bb_upper) else None,
            "mid": round(bb_mid, 2) if bb_mid and not pd.isna(bb_mid) else None,
            "lower": round(bb_lower, 2) if bb_lower and not pd.isna(bb_lower) else None,
        },
        "indicators": {
            "rsi": round(rsi, 2) if not pd.isna(rsi) else None,
            "macd": round(macd_val, 4) if not pd.isna(macd_val) else None,
            "atr": round(atr, 2) if atr and not pd.isna(atr) else None,
            "adx": round(adx, 2) if not pd.isna(adx) else None,
            "obv": round(obv, 2) if obv and not pd.isna(obv) else None,
            "vwap": round(vwap, 2) if vwap and not pd.isna(vwap) else None,
            "ema9": round(ema9, 2) if not pd.isna(ema9) else None,
            "ema21": round(ema21, 2) if not pd.isna(ema21) else None,
            "ema50": round(ema50, 2) if not pd.isna(ema50) else None,
            "ema200": round(ema200, 2) if not pd.isna(ema200) else None,
        },
        "signals": signals,
        "signal_type": signal_type,
        "move_potential_pct": move_potential_pct,
        "trade_idea": {
            "direction": signal_type,
            "entry": entry,
            "stoploss": stoploss,
            "target": target,
            "risk_reward": risk_reward,
        } if entry else None,
        "confidence": confidence,
    }


# ──────────────────────────────────────────────────
# DRY RUN MODE
# ──────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import json
    import yfinance as yf

    symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    yf_symbol = f"{symbol}.NS"

    logging.info(f"Fetching daily data for {yf_symbol}...")
    ticker = yf.Ticker(yf_symbol)
    df = ticker.history(period="1y", interval="1d")

    if df.empty:
        logging.error(f"No data for {yf_symbol}")
        sys.exit(1)

    report = analyze_swing_setups(df, symbol)

    if report:
        print(f"\n{'='*60}")
        print(f"📊 SWING ANALYSIS: {symbol}")
        print(f"{'='*60}")
        print(json.dumps(report, indent=2, default=str))
        print(f"{'='*60}\n")
    else:
        print(f"No actionable setups for {symbol}.")