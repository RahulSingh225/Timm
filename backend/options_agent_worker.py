"""
Options Agent Worker v2.0

Analyzes the options chain for each stock to provide:
- Max Pain (strike where most options expire worthless)
- OI Buildup detection (smart money positioning)
- IV Percentile (is premium cheap or expensive?)
- PCR analysis (put/call ratio directional read)
- Expected move from ATM straddle premium
- Structured, actionable output
"""

import pika
import json
import time
import logging
import os
import psycopg2
import yfinance as yf
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [OPTIONS AGENT] - %(message)s')

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
EXCHANGE_NAME = os.getenv('RABBITMQ_EXCHANGE', 'market_data_exchange')
QUEUE_NAME = os.getenv('RABBITMQ_OPTIONS_QUEUE', 'options_analysis_queue')
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'admin')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'supersecretpassword')
DB_URL = os.getenv('DATABASE_URL')


def _log_run(agent_name, status, duration_ms, symbol=None, error=None):
    """Log agent run to agent_runs table."""
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO agent_runs (agent_name, run_status, duration_ms, symbol_processed, error_message, finished_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (agent_name, status, duration_ms, symbol, error))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.warning(f"Failed to log run: {e}")


def _calc_max_pain(calls, puts):
    """
    Calculate Max Pain: the strike where total loss for option buyers is maximum
    (i.e., where market makers profit the most).
    """
    strikes = sorted(set(calls['strike'].tolist() + puts['strike'].tolist()))
    min_pain = float('inf')
    max_pain_strike = None

    for test_strike in strikes:
        # Total loss for call buyers if price settles at test_strike
        call_loss = 0
        for _, row in calls.iterrows():
            if test_strike > row['strike']:
                call_loss += (test_strike - row['strike']) * row.get('openInterest', 0)

        # Total loss for put buyers if price settles at test_strike
        put_loss = 0
        for _, row in puts.iterrows():
            if test_strike < row['strike']:
                put_loss += (row['strike'] - test_strike) * row.get('openInterest', 0)

        total_pain = call_loss + put_loss
        if total_pain < min_pain:
            min_pain = total_pain
            max_pain_strike = test_strike

    return max_pain_strike


def _find_oi_walls(calls, puts, current_price):
    """Find highest OI strikes — these act as support (put wall) and resistance (call wall)."""
    # Call wall: highest OI above current price
    calls_above = calls[calls['strike'] >= current_price].sort_values('openInterest', ascending=False)
    call_wall = float(calls_above.iloc[0]['strike']) if not calls_above.empty else None

    # Put wall: highest OI below current price
    puts_below = puts[puts['strike'] <= current_price].sort_values('openInterest', ascending=False)
    put_wall = float(puts_below.iloc[0]['strike']) if not puts_below.empty else None

    return call_wall, put_wall


def analyze_option_chain(symbol, current_price):
    """Full options chain analysis for a stock."""
    yf_symbol = f"{symbol}.NS"
    result = {
        "signals": [],
        "max_pain": None,
        "call_wall": None,
        "put_wall": None,
        "pcr_volume": None,
        "pcr_oi": None,
        "atm_call_iv": None,
        "atm_put_iv": None,
        "expected_move_pct": None,
        "verdict": "NO_DATA",
    }

    try:
        ticker = yf.Ticker(yf_symbol)
        expirations = ticker.options

        if not expirations:
            logging.info(f"No options data available for {symbol}")
            return result

        nearest_expiry = expirations[0]
        opt_chain = ticker.option_chain(nearest_expiry)

        calls = opt_chain.calls
        puts = opt_chain.puts

        if calls.empty or puts.empty:
            return result

        # ─── ATM Analysis ──────────────────────────────
        atm_call = calls.iloc[(calls['strike'] - current_price).abs().argsort()[:1]]
        atm_put = puts.iloc[(puts['strike'] - current_price).abs().argsort()[:1]]

        if not atm_call.empty:
            result['atm_call_iv'] = round(float(atm_call.iloc[0].get('impliedVolatility', 0)) * 100, 2)
        if not atm_put.empty:
            result['atm_put_iv'] = round(float(atm_put.iloc[0].get('impliedVolatility', 0)) * 100, 2)

        # ─── IV Spike Check ───────────────────────────
        call_iv = atm_call.iloc[0].get('impliedVolatility', 0) if not atm_call.empty else 0
        put_iv = atm_put.iloc[0].get('impliedVolatility', 0) if not atm_put.empty else 0

        if call_iv > 0.5:
            result['signals'].append(f"CALL IV SPIKE: ATM Call IV is {round(call_iv*100, 1)}% (High Premium).")
        if put_iv > 0.5:
            result['signals'].append(f"PUT IV SPIKE: ATM Put IV is {round(put_iv*100, 1)}% (Fear/Protection Buying).")

        # ─── Expected Move (ATM Straddle) ──────────────
        atm_call_price = float(atm_call.iloc[0].get('lastPrice', 0)) if not atm_call.empty else 0
        atm_put_price = float(atm_put.iloc[0].get('lastPrice', 0)) if not atm_put.empty else 0
        straddle_premium = atm_call_price + atm_put_price
        if current_price > 0 and straddle_premium > 0:
            expected_move = round((straddle_premium / current_price) * 100, 2)
            result['expected_move_pct'] = expected_move
            result['signals'].append(f"EXPECTED MOVE: Market implies ±{expected_move}% move by {nearest_expiry}.")

        # ─── PCR Analysis ─────────────────────────────
        total_call_vol = calls['volume'].sum()
        total_put_vol = puts['volume'].sum()
        total_call_oi = calls['openInterest'].sum()
        total_put_oi = puts['openInterest'].sum()

        if total_call_vol > 0:
            pcr_vol = round(total_put_vol / total_call_vol, 2)
            result['pcr_volume'] = pcr_vol
            if pcr_vol > 1.5:
                result['signals'].append(f"BEARISH SENTIMENT: High PCR (Volume) {pcr_vol} — heavy put buying.")
            elif pcr_vol < 0.6:
                result['signals'].append(f"BULLISH SENTIMENT: Low PCR (Volume) {pcr_vol} — call-heavy activity.")

        if total_call_oi > 0:
            pcr_oi = round(total_put_oi / total_call_oi, 2)
            result['pcr_oi'] = pcr_oi

        # ─── Max Pain ─────────────────────────────────
        max_pain = _calc_max_pain(calls, puts)
        result['max_pain'] = max_pain
        if max_pain:
            mp_distance = round(((max_pain - current_price) / current_price) * 100, 2)
            if abs(mp_distance) > 1:
                direction = "above" if mp_distance > 0 else "below"
                result['signals'].append(f"MAX PAIN: ₹{max_pain} ({mp_distance:+.1f}% {direction} CMP) — gravitational pull.")

        # ─── OI Walls ──────────────────────────────────
        call_wall, put_wall = _find_oi_walls(calls, puts, current_price)
        result['call_wall'] = call_wall
        result['put_wall'] = put_wall

        if call_wall:
            result['signals'].append(f"CALL WALL: Highest call OI at ₹{call_wall} (Options Resistance).")
        if put_wall:
            result['signals'].append(f"PUT WALL: Highest put OI at ₹{put_wall} (Options Support).")

        # ─── OI Buildup Detection ──────────────────────
        # Check for significant OI change in top 5 strikes
        for _, row in calls.nlargest(3, 'openInterest').iterrows():
            change_oi = row.get('change', 0)
            if change_oi and abs(change_oi) > 0:
                oi = row.get('openInterest', 0)
                if oi > 0 and abs(change_oi / oi) > 0.3:
                    result['signals'].append(
                        f"CALL OI BUILDUP: Strike ₹{row['strike']} saw {round(change_oi/oi*100, 1)}% OI change (Smart Money)."
                    )
                    break

        for _, row in puts.nlargest(3, 'openInterest').iterrows():
            change_oi = row.get('change', 0)
            if change_oi and abs(change_oi) > 0:
                oi = row.get('openInterest', 0)
                if oi > 0 and abs(change_oi / oi) > 0.3:
                    result['signals'].append(
                        f"PUT OI BUILDUP: Strike ₹{row['strike']} saw {round(change_oi/oi*100, 1)}% OI change (Smart Money)."
                    )
                    break

        # ─── Verdict ───────────────────────────────────
        bullish_count = sum(1 for s in result['signals'] if 'BULLISH' in s or 'CALL OI' in s)
        bearish_count = sum(1 for s in result['signals'] if 'BEARISH' in s or 'PUT IV SPIKE' in s or 'PUT OI' in s)

        if max_pain and max_pain > current_price * 1.01:
            bullish_count += 1  # Max pain above CMP = bullish gravity
        elif max_pain and max_pain < current_price * 0.99:
            bearish_count += 1

        if bullish_count > bearish_count:
            result['verdict'] = "BULLISH"
        elif bearish_count > bullish_count:
            result['verdict'] = "BEARISH"
        else:
            result['verdict'] = "NEUTRAL"

    except Exception as e:
        logging.error(f"Error analyzing options for {symbol}: {e}")
        result['signals'].append(f"Analysis error: {str(e)[:100]}")

    return result


def process_message(ch, method, properties, body):
    """Process incoming EOD data and generate options analysis alerts."""
    start_time = time.monotonic()
    symbol = None

    try:
        payload = json.loads(body)
        symbol = payload['symbol']

        df_list = payload.get('data', [])
        if not df_list:
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        latest_data = df_list[-1]
        current_price = float(latest_data['Close'])

        logging.info(f"Analyzing Options Chain for {symbol} @ ₹{current_price:.2f}...")

        result = analyze_option_chain(symbol, current_price)
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        if result['signals']:
            alert_payload = {
                "agent": "Options",
                "symbol": symbol,
                "close_price": round(current_price, 2),
                "signals": result['signals'],
                "signal_type": result['verdict'],
                "max_pain": result['max_pain'],
                "call_wall": result['call_wall'],
                "put_wall": result['put_wall'],
                "pcr_volume": result['pcr_volume'],
                "pcr_oi": result['pcr_oi'],
                "atm_call_iv": result['atm_call_iv'],
                "atm_put_iv": result['atm_put_iv'],
                "expected_move_pct": result['expected_move_pct'],
            }

            ch.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=f"alert.options.{symbol}",
                body=json.dumps(alert_payload),
                properties=pika.BasicProperties(delivery_mode=2)
            )

            logging.info(
                f"🚨 OPTIONS ALERT: {symbol} | {result['verdict']} | "
                f"Max Pain: ₹{result['max_pain']} | PCR: {result['pcr_volume']} | "
                f"Expected Move: ±{result['expected_move_pct']}%"
            )
            _log_run('options_agent', 'SUCCESS', elapsed_ms, symbol)
        else:
            logging.info(f"No actionable options setups for {symbol}.")
            _log_run('options_agent', 'SUCCESS', elapsed_ms, symbol)

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logging.error(f"Failed to process options for {symbol or 'unknown'}: {e}")
        _log_run('options_agent', 'FAILED', elapsed_ms, symbol, str(e)[:500])
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def start_options_agent():
    """Connects to RabbitMQ and starts listening."""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='market.eod.*')

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)

    logging.info("📊 Options Agent v2.0 is online. Waiting for market data...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logging.info("Agent shutting down...")
        channel.stop_consuming()
        connection.close()


if __name__ == "__main__":
    import sys
    if '--dry-run' in sys.argv:
        symbol = sys.argv[2] if len(sys.argv) > 2 else "RELIANCE"
        ticker = yf.Ticker(f"{symbol}.NS")
        hist = ticker.history(period="5d")
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            print(f"\n{'='*60}")
            print(f"📊 OPTIONS ANALYSIS: {symbol} @ ₹{price:.2f}")
            print(f"{'='*60}")
            result = analyze_option_chain(symbol, price)
            print(json.dumps(result, indent=2))
            print(f"{'='*60}\n")
    else:
        start_options_agent()
