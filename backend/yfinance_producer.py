import yfinance as yf
import pika
import psycopg2
import json
import logging
import sys
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# RabbitMQ Configuration
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
EXCHANGE_NAME = os.getenv('RABBITMQ_EXCHANGE', 'market_data_exchange')
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'admin')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'supersecretpassword')
DB_URL = os.getenv("DATABASE_URL")

DEFAULT_WATCHLIST = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "ICICIBANK"]

def get_watchlist_from_db():
    if not DB_URL: return DEFAULT_WATCHLIST
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM watchlist WHERE is_active = true")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [r[0] for r in rows] if rows else DEFAULT_WATCHLIST
    except Exception as e:
        logging.error(f"Failed to load watchlist: {e}")
        return DEFAULT_WATCHLIST

def setup_rabbitmq():
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
        return connection, channel
    except Exception as e:
        logging.error(f"RabbitMQ Error: {e}")
        return None, None

def fetch_and_publish_eod_data(channel, symbol, backfill=False):
    yf_symbol = f"{symbol}.NS"
    try:
        ticker = yf.Ticker(yf_symbol)
        period = "5y" if backfill else "1y"
        df = ticker.history(period=period, interval="1d")
        
        if df.empty:
            logging.warning(f"No data for {yf_symbol}")
            return

        df.reset_index(inplace=True)
        # Normalize column names to title case for producer consistency
        df.columns = [c.title() for c in df.columns]
        
        if 'Date' not in df.columns:
            logging.warning(f"Malformed data for {yf_symbol}: No Date column")
            return

        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d') 
        
        # Build strict payload
        data_records = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].to_dict(orient='records')
        
        payload = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "timeframe": "1d",
            "data": data_records
        }
        
        # 1. Individual candle stream (market.candle.SYMBOL)
        for row in data_records:
            candle_payload = {
                "symbol": symbol,
                "timestamp": row["Date"],
                "open": row["Open"],
                "high": row["High"],
                "low": row["Low"],
                "close": row["Close"],
                "volume": row["Volume"]
            }
            channel.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=f"market.candle.{symbol}",
                body=json.dumps(candle_payload),
                properties=pika.BasicProperties(delivery_mode=2, content_type='application/json')
            )
        
        # 2. Complete EOD batch (market.eod.SYMBOL)
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=f"market.eod.{symbol}",
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2, content_type='application/json')
        )
        logging.info(f"✅ Published {symbol} EOD batch ({len(df)} days)")
        
    except Exception as e:
        logging.error(f"Error for {symbol}: {e}")

if __name__ == "__main__":
    backfill = '--backfill' in sys.argv
    connection, channel = setup_rabbitmq()
    if connection and channel:
        watchlist = get_watchlist_from_db()
        for stock in watchlist:
            fetch_and_publish_eod_data(channel, stock, backfill=backfill)
        connection.close()
        logging.info("Pipeline complete.")