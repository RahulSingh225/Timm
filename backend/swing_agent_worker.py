"""
Swing Agent Worker v2.2

RabbitMQ consumer with strict defensive programming:
- Gracefully handles missing keys (like 'data') to avoid KeyError.
- Circuit breaker: Skips flaky symbols after 3 consecutive errors.
- Deduplication: Prevents redundant heavy processing.
- Re-queue=False: Never puts failed messages back on queue.
"""

import pika
import json
import time
import pandas as pd
import logging
import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
from swing_agent_ta import analyze_swing_setups

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SWING AGENT] - %(message)s')

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
EXCHANGE_NAME = os.getenv('RABBITMQ_EXCHANGE', 'market_data_exchange')
QUEUE_NAME = os.getenv('RABBITMQ_SWING_QUEUE', 'swing_analysis_queue')
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'admin')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'supersecretpassword')
DB_URL = os.getenv('DATABASE_URL')

# ─── Guard Rails ───────────────────────────────────────────
_last_processed: dict[str, str] = {}  # symbol -> latest_date_str
_consecutive_failures: dict[str, int] = {}  # symbol -> failure count
MAX_CONSECUTIVE_FAILURES = 3


def _log_run(agent_name, status, duration_ms, symbol=None, error=None):
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
    except Exception:
        pass


def _get_data_date(payload: dict) -> str | None:
    data = payload.get('data', [])
    if not data or not isinstance(data, list):
        return None
    last_entry = data[-1]
    return last_entry.get('Date') or last_entry.get('date') or last_entry.get('timestamp')


def process_message(ch, method, properties, body):
    start_time = time.monotonic()
    symbol = "unknown"

    try:
        # Strict parsing
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logging.error("Failed to decode JSON message body.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # Defensive key access
        symbol = payload.get('symbol', 'unknown')
        data_list = payload.get('data', [])

        # ── Guard 1: Detect payloads from other topics accidentally bound ──
        if not symbol or symbol == "unknown" or not isinstance(data_list, list) or not data_list:
            logging.warning(f"⏭️ {symbol}: Received malformed or non-EOD payload. Discarding.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # ── Guard 2: Circuit breaker check ──
        if _consecutive_failures.get(symbol, 0) >= MAX_CONSECUTIVE_FAILURES:
            logging.warning(f"🛑 {symbol}: Circuit breaker active after {MAX_CONSECUTIVE_FAILURES} failures. Skipping.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # ── Guard 3: Deduplication check ──
        latest_date = _get_data_date(payload)
        if latest_date and _last_processed.get(symbol) == latest_date:
            logging.info(f"⏭️ {symbol}: {latest_date} already analyzed. Skipping.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        logging.info(f"📈 Analyzing {symbol} (EOD batch up to {latest_date})...")

        # Load into DF and normalize
        df = pd.DataFrame(data_list)
        df.columns = [c.title() for c in df.columns] # Ensure title case (Date, Open, etc)
        
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
        df.sort_index(inplace=True)

        if len(df) < 50: # Minimum requirement reduced for safety, but check for 200 inside engine
            logging.info(f"⏭️ {symbol}: Insufficient candle length. Skipping.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # Run Analysis
        report = analyze_swing_setups(df, symbol)
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Track success
        if latest_date: _last_processed[symbol] = latest_date
        _consecutive_failures[symbol] = 0

        if report and report.get('signals'):
            # Forward alert to exchange
            ch.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=f"alert.swing.{symbol}",
                body=json.dumps(report, default=str),
                properties=pika.BasicProperties(delivery_mode=2, content_type='application/json')
            )
            logging.info(f"🚨 ALERT: {symbol} | Confidence: {report['confidence']}%")
            _log_run('swing_agent', 'SUCCESS', elapsed_ms, symbol)
        else:
            _log_run('swing_agent', 'SUCCESS', elapsed_ms, symbol)

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logging.error(f"❌ Critical Failure for {symbol}: {str(e)}")
        _log_run('swing_agent', 'FAILED', elapsed_ms, symbol, str(e)[:500])

        _consecutive_failures[symbol] = _consecutive_failures.get(symbol, 0) + 1
        
        # ACK (remove) faulty message to avoid infinite re-queue loops
        if ch.is_open:
            ch.basic_ack(delivery_tag=method.delivery_tag)


def start_swing_agent():
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
        parameters.heartbeat = 60
        
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='market.eod.*')

        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)

        logging.info("📈 Swing Agent Worker v2.2 started.")
        logging.info(f"   Listening on queue: {QUEUE_NAME} (EOD topics)")
        channel.start_consuming()
    except Exception as e:
        logging.error(f"Worker crashed: {e}")
        time.sleep(10) # Auto-restart delay


if __name__ == "__main__":
    while True:
        try:
            start_swing_agent()
        except KeyboardInterrupt:
            logging.info("Shutting down worker...")
            break
        except Exception:
            logging.info("Worker restarted due to unexpected connection drop.")