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

# Backfill mode flag
BACKFILL_MODE = '--backfill' in sys.argv if 'sys' in dir() else False
BACKFILL_START = '2020-01-01'

# RabbitMQ Configuration
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
EXCHANGE_NAME = os.getenv('RABBITMQ_EXCHANGE', 'market_data_exchange')
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'admin')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'supersecretpassword')

# Database Configuration
DB_URL = os.getenv("DATABASE_URL")

DEFAULT_WATCHLIST = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "ICICIBANK", "NIFTY"]

def get_watchlist_from_db():
    """Fetch active symbols from the watchlist table. Falls back to hardcoded defaults."""
    if not DB_URL:
        logging.warning("DATABASE_URL not set, using default watchlist.")
        return DEFAULT_WATCHLIST
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM watchlist WHERE is_active = true")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        if rows:
            symbols = [r[0] for r in rows]
            logging.info(f"Loaded {len(symbols)} symbols from watchlist DB: {symbols}")
            return symbols
        else:
            logging.warning("Watchlist table is empty, using default watchlist.")
            return DEFAULT_WATCHLIST
    except Exception as e:
        logging.error(f"Failed to load watchlist from DB: {e}. Using defaults.")
        return DEFAULT_WATCHLIST

def setup_rabbitmq():
    """Establishes connection to RabbitMQ and sets up the Topic Exchange."""
    try:
        # Connect to the local Docker RabbitMQ instance
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        # Declare a 'topic' exchange so we can route messages specifically (e.g., market.eod.RELIANCE)
        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
        return connection, channel
    except Exception as e:
        logging.error(f"Failed to connect to RabbitMQ: {e}")
        return None, None

def fetch_and_publish_eod_data(channel, symbol, backfill=False):
    """Fetches daily data from yfinance and publishes it to the queue."""
    # Note: Yahoo Finance uses '.NS' suffix for NSE stocks
    yf_symbol = f"{symbol}.NS"
    routing_key = f"market.eod.{symbol}"
    
    if backfill:
        logging.info(f"Fetching FULL HISTORY for {yf_symbol} since {BACKFILL_START}...")
    else:
        logging.info(f"Fetching data for {yf_symbol}...")
    
    try:
        ticker = yf.Ticker(yf_symbol)
        if backfill:
            df = ticker.history(start=BACKFILL_START, interval="1d")
        else:
            df = ticker.history(period="1y", interval="1d")
        
        if df.empty:
            logging.warning(f"No data found for {yf_symbol}")
            return
            
        # Clean up the DataFrame for JSON serialization
        df.reset_index(inplace=True)
        # Convert datetime to string format
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d') 
        
        # Convert DataFrame to a dictionary payload complete with dates
        payload = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "timeframe": "1d",
            # Orient='records' creates a clean list of dictionaries for each day
            "data": df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].to_dict(orient='records')
        }
        
        # Publish individual candles to the vector agent
        for row in payload["data"]:
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
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type='application/json'
                )
            )
            
        
        # Publish the payload to RabbitMQ
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=routing_key,
            body=json.dumps(payload),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent (survives server restarts)
                content_type='application/json'
            )
        )
        logging.info(f"Successfully published {len(df)} days of data to queue with keys: {routing_key} & market.candle.{symbol}")
        
    except Exception as e:
        logging.error(f"Error fetching/publishing data for {symbol}: {e}")

def fetch_and_publish_intraday_data(channel, symbol, timeframes=None):
    """Fetches intraday candle data and publishes it for caching in the database."""
    if timeframes is None:
        timeframes = ['15m', '1h']
    
    yf_symbol = f"{symbol}.NS"
    
    for tf in timeframes:
        try:
            logging.info(f"Fetching {tf} data for {symbol}...")
            ticker = yf.Ticker(yf_symbol)
            # 5m/15m → last 5 days max, 1h → last 60 days
            period = '5d' if tf in ['5m', '15m'] else '60d'
            df = ticker.history(period=period, interval=tf)
            
            if df.empty:
                logging.warning(f"No {tf} data for {symbol}")
                continue
            
            df.reset_index(inplace=True)
            
            # Normalize column name
            time_col = 'Datetime' if 'Datetime' in df.columns else 'Date'
            
            candles = []
            for _, row in df.iterrows():
                candles.append({
                    'timestamp': str(row[time_col]),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': int(row['Volume']),
                })
            
            payload = {
                'symbol': symbol,
                'timeframe': tf,
                'data': candles
            }
            
            channel.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=f'market.intraday.{symbol}',
                body=json.dumps(payload),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logging.info(f"📦 Published {len(candles)} {tf} candles for {symbol} to cache")
            
        except Exception as e:
            logging.error(f"Error fetching {tf} data for {symbol}: {e}")

if __name__ == "__main__":
    backfill = '--backfill' in sys.argv
    
    connection, channel = setup_rabbitmq()
    
    if connection and channel:
        # Dynamically fetch watchlist from the database
        watchlist = get_watchlist_from_db()
        
        if backfill:
            logging.info(f"Starting BACKFILL Data Ingestion (since {BACKFILL_START})...")
        else:
            logging.info("Starting EOD Data Ingestion Pipeline...")
        
        for stock in watchlist:
            fetch_and_publish_eod_data(channel, stock, backfill=backfill)
        
        # Also fetch and cache intraday data for screener (not affected by backfill)
        if not backfill:
            logging.info("Starting Intraday Data Cache Pipeline...")
            for stock in watchlist:
                fetch_and_publish_intraday_data(channel, stock)
            
        # Close connection cleanly
        connection.close()
        logging.info("Data ingestion complete. Connection closed.")