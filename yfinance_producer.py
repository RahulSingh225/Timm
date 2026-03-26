import yfinance as yf
import pika
import json
import logging
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

def fetch_and_publish_eod_data(channel, symbol):
    """Fetches 1 year of daily data from yfinance and publishes it to the queue."""
    # Note: Yahoo Finance uses '.NS' suffix for NSE stocks
    yf_symbol = f"{symbol}.NS"
    routing_key = f"market.eod.{symbol}"
    
    logging.info(f"Fetching data for {yf_symbol}...")
    
    try:
        ticker = yf.Ticker(yf_symbol)
        # Fetch 1 year of daily data
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

if __name__ == "__main__":
    connection, channel = setup_rabbitmq()
    
    if connection and channel:
        # Let's test it with a mini-watchlist of heavyweights
        watchlist = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "ICICIBANK","NIFTY"]
        
        logging.info("Starting EOD Data Ingestion Pipeline...")
        for stock in watchlist:
            fetch_and_publish_eod_data(channel, stock)
            
        # Close connection cleanly
        connection.close()
        logging.info("Data ingestion complete. Connection closed.")