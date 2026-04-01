"""
Swing Agent Worker v2.0

RabbitMQ consumer that:
1. Receives EOD market data from yfinance_producer
2. Runs the full swing TA analysis (swing_agent_ta.py)
3. Publishes structured alerts with entry/SL/target
4. Logs every run to the agent_runs table for observability
"""

import pika
import json
import time
import pandas as pd
import logging
import os
import psycopg2
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


def process_message(ch, method, properties, body):
    """Process incoming EOD data and generate swing analysis alerts."""
    start_time = time.monotonic()
    symbol = None

    try:
        payload = json.loads(body)
        symbol = payload['symbol']
        logging.info(f"Received EOD data for {symbol}. Running Swing Analysis...")

        # Convert JSON array back into DataFrame
        df = pd.DataFrame(payload['data'])

        # Normalize column names
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
        df.sort_index(inplace=True)

        # Run the full TA analysis
        report = analyze_swing_setups(df, symbol)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        if report and report.get('signals'):
            # Build alert payload with full structured data
            alert_payload = {
                "agent": "Swing",
                "symbol": symbol,
                "close_price": report['close_price'],
                "signals": report['signals'],
                "signal_type": report['signal_type'],
                "confidence": report['confidence'],
                "trend": report['trend'],
                "support_resistance": report['support_resistance'],
                "bollinger": report['bollinger'],
                "indicators": report['indicators'],
                "move_potential_pct": report['move_potential_pct'],
                "trade_idea": report['trade_idea'],
            }

            alert_routing_key = f"alert.swing.{symbol}"

            ch.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=alert_routing_key,
                body=json.dumps(alert_payload, default=str),
                properties=pika.BasicProperties(delivery_mode=2)
            )

            sig_count = len(report['signals'])
            logging.info(
                f"🚨 ALERT: {symbol} | {report['signal_type']} | "
                f"{sig_count} signals | Confidence: {report['confidence']}% | "
                f"Move potential: {report['move_potential_pct']}%"
            )

            if report.get('trade_idea'):
                idea = report['trade_idea']
                logging.info(
                    f"   💡 Trade Idea: {idea['direction']} | "
                    f"Entry ₹{idea['entry']} → Target ₹{idea['target']} | "
                    f"SL ₹{idea['stoploss']} | R:R {idea['risk_reward']}"
                )

            _log_run('swing_agent', 'SUCCESS', elapsed_ms, symbol)
        else:
            logging.info(f"No actionable setups for {symbol} today.")
            _log_run('swing_agent', 'SUCCESS', elapsed_ms, symbol)

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logging.error(f"Failed to process {symbol or 'unknown'}: {e}")
        _log_run('swing_agent', 'FAILED', elapsed_ms, symbol, str(e)[:500])
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def start_swing_agent():
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

    logging.info("📈 Swing Agent v2.0 is online. Waiting for market data...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logging.info("Agent shutting down...")
        channel.stop_consuming()
        connection.close()


if __name__ == "__main__":
    start_swing_agent()