import os
from dotenv import load_dotenv
load_dotenv()
import requests
import pandas as pd
import pika
import json
import logging
import zipfile
import io
import io
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [FOOTPRINT AGENT] - %(message)s')

def get_nse_bhavcopy(date_obj):
    """Downloads and extracts the NSE F&O Bhavcopy for a given date."""
    # Format: 26Mar2026 -> 26MAR2026
    date_str = date_obj.strftime("%d%b%Y").upper()
    month_str = date_obj.strftime("%b").upper()
    year_str = date_obj.strftime("%Y")
    
    # URL format: https://nsearchives.nseindia.com/content/historical/DERIVATIVES/2026/MAR/fo26MAR2026bhav.csv.zip
    url = f"https://nsearchives.nseindia.com/content/historical/DERIVATIVES/{year_str}/{month_str}/fo{date_str}bhav.csv.zip"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                filename = z.namelist()[0]
                with z.open(filename) as f:
                    df = pd.read_csv(f)
                    return df
        else:
            logging.warning(f"Bhavcopy not found for {date_str}. (Weekend/Holiday?)")
            return None
    except Exception as e:
        logging.error(f"Failed to fetch Bhavcopy: {e}")
        return None

def process_and_publish_footprint():
    # Try the last 5 days to find the latest published bhavcopy
    df = None
    target_date = datetime.now()
    
    for i in range(5):
        current_attempt = target_date - timedelta(days=i)
        df = get_nse_bhavcopy(current_attempt)
        if df is not None and not df.empty:
            logging.info(f"Using Bhavcopy from {current_attempt.strftime('%d-%b-%Y')}")
            break
    
    if df is None or df.empty:
        logging.error("Could not find any recent Bhavcopy files.")
        return

    # Filter for NIFTY Options only
    nifty_opts = df[(df['SYMBOL'] == 'NIFTY') & (df['INSTRUMENT'].isin(['OPTIDX']))].copy()
    
    # Data cleaning & Formatting
    payloads = []
    for _, row in nifty_opts.iterrows():
        # Determine if weekly or monthly based on EXPIRY_DT vs current date (simplified logic)
        payload = {
            "tradeDate": current_attempt.strftime("%Y-%m-%d"),
            "indexName": "NIFTY",
            "expiryDate": row['EXPIRY_DT'],
            "strikePrice": float(row['STRIKE_PR']),
            "optionType": row['OPTION_TYP'], # CE or PE
            "closePrice": float(row['CLOSE']),
            "openInterest": int(row['OPEN_INT']),
            "changeInOI": int(row['CHG_IN_OI']),
            "volume": int(row['CONTRACTS'])
        }
        payloads.append(payload)

    # Publish to RabbitMQ
    credentials = pika.PlainCredentials(os.getenv('RABBITMQ_USER', 'admin'), os.getenv('RABBITMQ_PASS', 'supersecretpassword'))
    connection = pika.BlockingConnection(pika.ConnectionParameters(os.getenv('RABBITMQ_HOST', 'localhost'), 5672, '/', credentials))
    channel = connection.channel()
    channel.exchange_declare(exchange='market_data_exchange', exchange_type='topic', durable=True)

    # Publish in bulk or row by row
    channel.basic_publish(
        exchange='market_data_exchange',
        routing_key='market.footprint.options',
        body=json.dumps(payloads),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    
    logging.info(f"✅ Published {len(payloads)} Nifty Option Footprints to Queue.")
    connection.close()

if __name__ == "__main__":
    process_and_publish_footprint()