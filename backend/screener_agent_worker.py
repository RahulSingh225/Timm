import pika  # type: ignore
import json
import pandas as pd  # type: ignore
import pandas_ta as ta  # type: ignore
import numpy as np  # type: ignore
import yfinance as yf  # type: ignore
import logging
import os
import psycopg2  # type: ignore
from dotenv import load_dotenv  # type: ignore
from datetime import datetime

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SCREENER AGENT] - %(message)s')

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
EXCHANGE_NAME = os.getenv('RABBITMQ_EXCHANGE', 'market_data_exchange')
QUEUE_NAME = os.getenv('RABBITMQ_SCREENER_QUEUE', 'screener_analysis_queue')
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'admin')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'supersecretpassword')
DATABASE_URL = os.getenv('DATABASE_URL')

# =============================================================
# CONFIG — Adjustable screening parameters
# =============================================================
INTRADAY_TARGET_PCT = 2.5   # Target: 2-3% move
INTRADAY_RISK_PCT = 1.0     # Max risk: 1% stoploss
VOLUME_SPIKE_MULTIPLIER = 2.0   # Volume must be 2x 20-day avg
GAP_THRESHOLD_PCT = 1.0     # Gap-up/down must be >= 1%
ATR_EXPANSION_MULTIPLIER = 1.5  # ATR must be 1.5x avg for volatility

# =============================================================
# HELPER: Fetch multi-timeframe data for a symbol
# =============================================================
def fetch_intraday_data(symbol, timeframe='15m', period='5d'):
    """
    Fetches intraday candle data from Yahoo Finance.
    Returns a DataFrame. Also publishes to RabbitMQ for caching.
    """
    yf_symbol = f"{symbol}.NS"
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=period, interval=timeframe)
        
        if df.empty:
            logging.warning(f"No {timeframe} data returned for {symbol}")
            return None
        
        df.reset_index(inplace=True)
        # Rename 'Datetime' column to 'timestamp' for consistency
        if 'Datetime' in df.columns:
            df.rename(columns={'Datetime': 'timestamp'}, inplace=True)
        elif 'Date' in df.columns:
            df.rename(columns={'Date': 'timestamp'}, inplace=True)
        
        logging.info(f"Fetched {len(df)} {timeframe} candles for {symbol}")
        return df
        
    except Exception as e:
        logging.error(f"Failed to fetch {timeframe} data for {symbol}: {e}")
        return None


def publish_candle_cache(channel, symbol, timeframe, df):
    """Publishes fetched candle data to RabbitMQ for the vault worker to cache."""
    if df is None or df.empty:
        return
    try:
        candles = []
        for _, row in df.iterrows():
            candles.append({
                'timestamp': str(row['timestamp']),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row['Volume']),
            })
        
        payload = {
            'symbol': symbol,
            'timeframe': timeframe,
            'data': candles
        }
        
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=f'market.intraday.{symbol}',
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        logging.info(f"📦 Published {len(candles)} {timeframe} candles for {symbol} to cache")
    except Exception as e:
        logging.error(f"Failed to publish candle cache for {symbol}: {e}")


def get_latest_global_cues():
    """Fetches the latest global cues from the database for confidence scoring."""
    if not DATABASE_URL:
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT overall_bias, vix_value, spy_change_pct FROM global_cues ORDER BY captured_at DESC LIMIT 1")
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            return {'bias': row[0], 'vix': row[1], 'spy_pct': row[2]}
    except Exception as e:
        logging.warning(f"Could not fetch global cues: {e}")
    return None


# =============================================================
# SCREENING FILTERS
# =============================================================

def screen_gap(df_daily, symbol):
    """Detect gap-up or gap-down at day open."""
    if df_daily is None or len(df_daily) < 2:
        return None
    
    latest = df_daily.iloc[-1]
    prev = df_daily.iloc[-2]
    
    gap_pct = ((latest['Open'] - prev['Close']) / prev['Close']) * 100
    
    if abs(gap_pct) >= GAP_THRESHOLD_PCT:
        direction = "GAP_UP" if gap_pct > 0 else "GAP_DOWN"
        return {
            'setup_type': direction,
            'signal': f"{direction}: {round(gap_pct, 2)}% gap from prev close ₹{round(prev['Close'], 2)} → open ₹{round(latest['Open'], 2)}",
            'gap_pct': round(gap_pct, 2)
        }
    return None


def screen_volume_spike(df_daily, symbol):
    """Detect volume spike vs 20-day SMA."""
    if df_daily is None or len(df_daily) < 21:
        return None
    
    df_daily['VOL_SMA_20'] = df_daily['Volume'].rolling(window=20).mean()
    latest = df_daily.iloc[-1]
    vol_ratio = latest['Volume'] / latest['VOL_SMA_20'] if latest['VOL_SMA_20'] > 0 else 0
    
    if vol_ratio >= VOLUME_SPIKE_MULTIPLIER:
        return {
            'setup_type': 'VOLUME_SPIKE',
            'signal': f"VOLUME SPIKE: {round(vol_ratio, 1)}x avg (Today: {int(latest['Volume']):,} vs Avg: {int(latest['VOL_SMA_20']):,})",
            'vol_ratio': round(vol_ratio, 1)
        }
    return None


def screen_atr_expansion(df_daily, symbol):
    """Detect ATR expansion — high volatility = opportunity."""
    if df_daily is None or len(df_daily) < 20:
        return None
    
    df_daily.ta.atr(length=14, append=True)
    
    if 'ATRr_14' not in df_daily.columns:
        return None
    
    atr_avg = df_daily['ATRr_14'].rolling(window=14).mean().iloc[-1]
    current_atr = df_daily['ATRr_14'].iloc[-1]
    
    if pd.isna(atr_avg) or pd.isna(current_atr) or atr_avg == 0:
        return None
    
    atr_ratio = current_atr / atr_avg
    
    if atr_ratio >= ATR_EXPANSION_MULTIPLIER:
        return {
            'setup_type': 'ATR_EXPANSION',
            'signal': f"ATR EXPANSION: {round(atr_ratio, 1)}x avg range (₹{round(current_atr, 2)} vs avg ₹{round(atr_avg, 2)})",
            'atr_ratio': round(atr_ratio, 1)
        }
    return None


def screen_ema_stack_15m(df_15m, symbol):
    """Check EMA alignment on 15-min chart: 9 > 21 > 50 = bullish stack."""
    if df_15m is None or len(df_15m) < 50:
        return None
    
    df_15m.ta.ema(length=9, append=True)
    df_15m.ta.ema(length=21, append=True)
    df_15m.ta.ema(length=50, append=True)
    
    latest = df_15m.iloc[-1]
    
    bullish = latest.get('EMA_9', 0) > latest.get('EMA_21', 0) > latest.get('EMA_50', 0)
    bearish = latest.get('EMA_9', 0) < latest.get('EMA_21', 0) < latest.get('EMA_50', 0)
    
    if bullish:
        return {
            'setup_type': 'EMA_STACK_BULLISH',
            'signal': f"15m EMA STACK: 9>{round(latest.get('EMA_9', 0), 2)} > 21>{round(latest.get('EMA_21', 0), 2)} > 50>{round(latest.get('EMA_50', 0), 2)} (Bullish)",
        }
    elif bearish:
        return {
            'setup_type': 'EMA_STACK_BEARISH',
            'signal': f"15m EMA STACK: 9<{round(latest.get('EMA_9', 0), 2)} < 21<{round(latest.get('EMA_21', 0), 2)} < 50<{round(latest.get('EMA_50', 0), 2)} (Bearish)",
        }
    return None


def screen_vwap_reclaim(df_15m, symbol):
    """Price dipped below VWAP then reclaimed it (mean-reversion setup)."""
    if df_15m is None or len(df_15m) < 10:
        return None
    
    df_15m.ta.vwap(append=True)
    vwap_col = [c for c in df_15m.columns if 'VWAP' in c]
    if not vwap_col:
        return None
    
    vwap_col = vwap_col[0]
    latest = df_15m.iloc[-1]
    prev = df_15m.iloc[-2]
    
    reclaimed = prev['Close'] < prev[vwap_col] and latest['Close'] > latest[vwap_col]
    
    if reclaimed:
        return {
            'setup_type': 'VWAP_RECLAIM',
            'signal': f"VWAP RECLAIM: Price crossed above VWAP ₹{round(latest[vwap_col], 2)} (Close ₹{round(latest['Close'], 2)})",
        }
    return None


def screen_rsi_reversal_15m(df_15m, symbol):
    """RSI crossing above 40 from below on 15m chart."""
    if df_15m is None or len(df_15m) < 20:
        return None
    
    df_15m.ta.rsi(length=14, append=True)
    
    if 'RSI_14' not in df_15m.columns:
        return None
    
    latest = df_15m.iloc[-1]
    prev = df_15m.iloc[-2]
    
    if pd.isna(latest['RSI_14']) or pd.isna(prev['RSI_14']):
        return None
    
    if prev['RSI_14'] < 40 and latest['RSI_14'] >= 40:
        return {
            'setup_type': 'RSI_REVERSAL',
            'signal': f"RSI REVERSAL: 15m RSI crossed above 40 ({round(prev['RSI_14'], 1)} → {round(latest['RSI_14'], 1)})",
        }
    return None


# =============================================================
# MAIN SCREENING PIPELINE
# =============================================================

def run_full_screen(symbol, df_daily, channel):
    """
    Run all screening filters on a single stock.
    Returns a screener result payload if the stock passes, else None.
    """
    signals = []
    
    # --- Daily Timeframe Filters ---
    gap = screen_gap(df_daily, symbol)
    if gap:
        signals.append(gap)
    
    vol = screen_volume_spike(df_daily, symbol)
    if vol:
        signals.append(vol)
    
    atr = screen_atr_expansion(df_daily, symbol)
    if atr:
        signals.append(atr)
    
    # --- 15m Timeframe Filters (fetch on-demand, will be cached) ---
    df_15m = fetch_intraday_data(symbol, timeframe='15m', period='5d')
    if df_15m is not None:
        # Cache the data
        publish_candle_cache(channel, symbol, '15m', df_15m)
        
        ema_stack = screen_ema_stack_15m(df_15m, symbol)
        if ema_stack:
            signals.append(ema_stack)
        
        vwap = screen_vwap_reclaim(df_15m, symbol)
        if vwap:
            signals.append(vwap)
        
        rsi_rev = screen_rsi_reversal_15m(df_15m, symbol)
        if rsi_rev:
            signals.append(rsi_rev)
    
    # --- DECISION: Need at least 2 signals to pass screen ---
    if len(signals) < 2:
        return None
    
    # Calculate entry, target, SL
    latest = df_daily.iloc[-1]
    close_price = float(latest['Close'])
    
    # Determine direction from signal mix
    bullish_count = sum(1 for s in signals if 'BULLISH' in s.get('setup_type', '') or s.get('setup_type', '') in ['GAP_UP', 'VWAP_RECLAIM', 'RSI_REVERSAL'])
    bearish_count = sum(1 for s in signals if 'BEARISH' in s.get('setup_type', '') or s.get('setup_type', '') == 'GAP_DOWN')
    
    is_bullish = bullish_count >= bearish_count
    
    entry_price = close_price
    if is_bullish:
        target_price = round(entry_price * (1 + INTRADAY_TARGET_PCT / 100), 2)
        stoploss_price = round(entry_price * (1 - INTRADAY_RISK_PCT / 100), 2)
    else:
        target_price = round(entry_price * (1 - INTRADAY_TARGET_PCT / 100), 2)
        stoploss_price = round(entry_price * (1 + INTRADAY_RISK_PCT / 100), 2)
    
    # --- Confidence Score ---
    base_confidence = min(len(signals) * 20, 60)  # 20 per signal, max 60
    
    # Global cues bonus
    global_cues = get_latest_global_cues()
    if global_cues:
        bias = global_cues.get('bias', 'NEUTRAL')
        if (is_bullish and bias == 'RISK_ON') or (not is_bullish and bias == 'RISK_OFF'):
            base_confidence += 20  # Aligned with global
        elif (is_bullish and bias == 'RISK_OFF') or (not is_bullish and bias == 'RISK_ON'):
            base_confidence -= 10  # Contradicted by global
        
        vix = global_cues.get('vix')
        if vix and vix < 18:
            base_confidence += 10  # Low VIX = stable environment
    
    confidence = max(10, min(100, base_confidence))
    
    primary_setup = signals[0]['setup_type']
    
    result = {
        'symbol': symbol,
        'timeframe': '15m' if df_15m is not None else '1d',
        'trade_type': 'INTRADAY',
        'setup_type': primary_setup,
        'entry_price': entry_price,
        'target_price': target_price,
        'stoploss_price': stoploss_price,
        'target_pct': INTRADAY_TARGET_PCT,
        'risk_pct': INTRADAY_RISK_PCT,
        'confidence': confidence,
        'signals': [s['signal'] for s in signals],
        'direction': 'BULLISH' if is_bullish else 'BEARISH'
    }
    
    return result


# =============================================================
# RABBITMQ MESSAGE HANDLER
# =============================================================

def process_message(ch, method, properties, body):
    """
    Triggered when EOD market data arrives from yfinance_producer.
    Runs the full screening pipeline on the received symbol.
    """
    try:
        payload = json.loads(body)
        symbol = payload.get('symbol')
        data_list = payload.get('data', [])
        
        if not symbol or not data_list:
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
        
        logging.info(f"Screening {symbol}...")
        
        # Convert to DataFrame
        df_daily = pd.DataFrame(data_list)
        if 'Date' in df_daily.columns:
            df_daily['Date'] = pd.to_datetime(df_daily['Date'])
            df_daily.set_index('Date', inplace=True)
        df_daily.sort_index(inplace=True)
        
        # Run screener
        result = run_full_screen(symbol, df_daily, ch)
        
        if result:
            # Publish screener result
            ch.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=f'screener.intraday.{symbol}',
                body=json.dumps(result),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logging.info(f"🎯 SCREENED IN: {symbol} ({result['setup_type']}) | "
                        f"Entry: ₹{result['entry_price']} → Target: ₹{result['target_price']} "
                        f"| Confidence: {result['confidence']}%")
        else:
            logging.info(f"❌ {symbol}: Did not pass screening (< 2 signals)")
        
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logging.error(f"Screening failed for message: {e}")
        ch.basic_ack(delivery_tag=method.delivery_tag)  # Don't requeue — prevents infinite loops


def start_screener_agent():
    """Connects to RabbitMQ and starts listening for EOD data."""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    
    # Listen for EOD data from yfinance producer
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='market.eod.*')
    
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)

    logging.info("🔍 Screener Agent is online. Waiting for market data to screen...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logging.info("Screener Agent shutting down...")
        channel.stop_consuming()
        connection.close()


# =============================================================
# DRY RUN MODE (for testing without RabbitMQ)
# =============================================================
if __name__ == "__main__":
    import sys
    
    if '--dry-run' in sys.argv:
        logging.info("=== DRY RUN MODE ===")
        test_symbol = sys.argv[2] if len(sys.argv) > 2 else "RELIANCE"
        
        logging.info(f"Fetching daily data for {test_symbol} ...")
        yf_symbol = f"{test_symbol}.NS"
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period="1y")
        
        if df.empty:
            logging.error(f"No data for {test_symbol}")
            sys.exit(1)
        
        df.reset_index(inplace=True)
        
        # Run screening (without RabbitMQ publish for cache)
        signals = []
        gap = screen_gap(df, test_symbol)
        if gap: signals.append(gap)
        vol = screen_volume_spike(df, test_symbol)
        if vol: signals.append(vol)
        atr = screen_atr_expansion(df, test_symbol)
        if atr: signals.append(atr)
        
        df_15m = fetch_intraday_data(test_symbol, '15m', '5d')
        if df_15m is not None:
            ema = screen_ema_stack_15m(df_15m, test_symbol)
            if ema: signals.append(ema)
            vwap = screen_vwap_reclaim(df_15m, test_symbol)
            if vwap: signals.append(vwap)
            rsi = screen_rsi_reversal_15m(df_15m, test_symbol)
            if rsi: signals.append(rsi)
        
        print(f"\n{'='*60}")
        print(f"📊 SCREENING REPORT: {test_symbol}")
        print(f"{'='*60}")
        
        if signals:
            for s in signals:
                print(f"  ✅ [{s['setup_type']}] {s['signal']}")
            print(f"\n  Total Signals: {len(signals)}")
            print(f"  Verdict: {'PASS (>=2 signals)' if len(signals) >= 2 else 'FAIL (<2 signals)'}")
        else:
            print("  ❌ No signals detected.")
        
        print(f"{'='*60}\n")
    else:
        start_screener_agent()
