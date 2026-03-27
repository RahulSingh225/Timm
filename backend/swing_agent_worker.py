import pika
import json
import pandas as pd
import pandas_ta as ta
import logging
import os
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SWING AGENT] - %(message)s')

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
EXCHANGE_NAME = os.getenv('RABBITMQ_EXCHANGE', 'market_data_exchange')
QUEUE_NAME = os.getenv('RABBITMQ_SWING_QUEUE', 'swing_analysis_queue')
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'admin')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'supersecretpassword')

def analyze_and_generate_alerts(df, symbol):
    """
    Runs the technical analysis logic on the DataFrame.
    Returns a list of active signals.
    """
    # Ensure data is sorted by date
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    df.sort_index(inplace=True)

    # Calculate Indicators
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)
    df.ta.rsi(length=14, append=True)
    
    # Need at least 200 days of data for the 200 EMA
    if len(df) < 200:
        return []

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    signals = []

    # 1. Golden Cross / Death Cross
    if prev['EMA_50'] <= prev['EMA_200'] and latest['EMA_50'] > latest['EMA_200']:
        signals.append("GOLDEN CROSS: 50 EMA crossed above 200 EMA (Macro Bullish).")
    elif prev['EMA_50'] >= prev['EMA_200'] and latest['EMA_50'] < latest['EMA_200']:
        signals.append("DEATH CROSS: 50 EMA crossed below 200 EMA (Macro Bearish).")

    # 2. RSI Extremes
    if prev['RSI_14'] < 30 and latest['RSI_14'] >= 30:
        signals.append(f"RSI BOUNCE: Recovering from oversold (<30). Current RSI: {round(latest['RSI_14'], 2)}")

    return signals

def process_message(ch, method, properties, body):
    """
    Callback function triggered every time a message hits the queue.
    """
    try:
        # 1. Decode the JSON payload from the Producer
        payload = json.loads(body)
        symbol = payload['symbol']
        logging.info(f"Received EOD data for {symbol}. Analyzing...")

        # 2. Convert the JSON array back into a Pandas DataFrame
        df = pd.DataFrame(payload['data'])
        
        # 3. Run the Technical Analysis
        signals = analyze_and_generate_alerts(df, symbol)

        # 4. If signals are found, publish an Alert back to RabbitMQ
        if signals:
            alert_payload = {
                "agent": "Swing",
                "symbol": symbol,
                "close_price": round(df.iloc[-1]['Close'], 2),
                "signals": signals
            }
            
            # Publish to a new routing key specifically for alerts
            alert_routing_key = f"alert.swing.{symbol}"
            
            ch.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=alert_routing_key,
                body=json.dumps(alert_payload),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logging.info(f"🚨 ALERT GENERATED for {symbol}: {signals}")
        else:
            logging.info(f"No actionable setups found for {symbol} today.")

        # 5. Acknowledge the message (Crucial!)
        # This tells RabbitMQ the message was processed successfully and can be deleted.
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logging.error(f"Failed to process message: {e}")
        # If the code crashes, negatively acknowledge so RabbitMQ requeues it
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

def start_swing_agent():
    """Connects to RabbitMQ and starts listening to the queue."""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    # Ensure the exchange exists
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)

    # Declare the queue for this specific agent
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    # Bind the queue to the exchange using a routing key wildcard
    # 'market.eod.*' means this queue receives EOD data for ANY symbol
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='market.eod.*')

    # Tell RabbitMQ to only send one message at a time to this worker
    channel.basic_qos(prefetch_count=1)

    # Setup the consumer
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)

    logging.info("Swing Agent is online and waiting for market data. To exit press CTRL+C")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logging.info("Agent shutting down...")
        channel.stop_consuming()
        connection.close()

if __name__ == "__main__":
    start_swing_agent()