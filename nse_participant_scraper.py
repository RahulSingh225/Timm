import requests
import pandas as pd
import pika
import json
import logging
from datetime import datetime
import io

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [FII/DII SCRAPER] - %(message)s')

# Configuration
RABBITMQ_HOST = 'localhost'
EXCHANGE_NAME = 'market_data_exchange'
ROUTING_KEY = 'market.sentiment.participant'

# NSE URLs
NSE_BASE_URL = "https://www.nseindia.com"
# The date format in the URL is DDMMYYYY (e.g., 26032026)
NSE_CSV_URL_TEMPLATE = "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{date_str}.csv"

def get_nse_session():
    """Creates a requests session with valid headers and cookies to bypass NSE bot protection."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    })
    
    try:
        # Hit the homepage first to establish cookies
        session.get(NSE_BASE_URL, timeout=10)
        return session
    except Exception as e:
        logging.error(f"Failed to establish NSE session: {e}")
        return None

def fetch_and_parse_participant_data(target_date=None):
    """Downloads the CSV, calculates Net positions, and returns a clean dictionary."""
    if target_date is None:
        target_date = datetime.now()
        
    date_str = target_date.strftime("%d%m%Y")
    csv_url = NSE_CSV_URL_TEMPLATE.format(date_str=date_str)
    
    session = get_nse_session()
    if not session:
        return None

    logging.info(f"Fetching Participant OI data for {date_str}...")
    
    try:
        response = session.get(csv_url, timeout=10)
        
        if response.status_code == 404:
            logging.warning(f"Data not published yet or market closed on {date_str}.")
            return None
            
        response.raise_for_status()
        
        # Read the CSV content directly from memory into a Pandas DataFrame
        # Skip the first row if it contains the "Data as of" header, usually the real headers are on row 1 or 2
        df = pd.read_csv(io.StringIO(response.text), skiprows=1)
        
        # Clean column names (strip trailing/leading spaces)
        df.columns = [col.strip() for col in df.columns]
        
        parsed_data = []
        
        # We care about these 4 participant types
        valid_clients = ['Client', 'DII', 'FII', 'Pro']
        
        for client in valid_clients:
            # Get the row for this specific client type
            row = df[df['Client Type'].str.strip() == client]
            
            if row.empty:
                continue
                
            row = row.iloc[0] # Convert to Series
            
            # Calculate NET positions (Longs - Shorts)
            net_index_call = int(row['Option Index Call Long']) - int(row['Option Index Call Short'])
            net_index_put = int(row['Option Index Put Long']) - int(row['Option Index Put Short'])
            net_index_futures = int(row['Future Index Long']) - int(row['Future Index Short'])
            net_stock_futures = int(row['Future Stock Long']) - int(row['Future Stock Short'])
            
            parsed_data.append({
                "tradeDate": target_date.strftime("%Y-%m-%d"),
                "participantType": client,
                "netIndexCall": net_index_call,
                "netIndexPut": net_index_put,
                "netIndexFutures": net_index_futures,
                "netStockFutures": net_stock_futures
            })
            
        return parsed_data

    except Exception as e:
        logging.error(f"Error processing NSE data: {e}")
        return None

def publish_to_rabbitmq(data):
    """Pushes the parsed JSON payload to your local message queue."""
    if not data:
        return
        
    try:
        credentials = pika.PlainCredentials('admin', 'supersecretpassword')
        parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
        
        payload = {
            "source": "NSE_Participant_OI",
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=ROUTING_KEY,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2, content_type='application/json')
        )
        
        logging.info(f"✅ Successfully published Smart Money positioning to {ROUTING_KEY}")
        connection.close()
        
    except Exception as e:
        logging.error(f"RabbitMQ connection failed: {e}")

if __name__ == "__main__":
    # If testing on a weekend or holiday, pass a specific weekday date:
    # test_date = datetime(2026, 3, 25) # Example weekday
    # parsed_data = fetch_and_parse_participant_data(test_date)
    
    parsed_data = fetch_and_parse_participant_data()
    
    if parsed_data:
        print("\n=== PARSED SMART MONEY DATA ===")
        print(json.dumps(parsed_data, indent=2))
        print("===============================\n")
        publish_to_rabbitmq(parsed_data)