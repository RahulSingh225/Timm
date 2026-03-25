import requests
import pandas as pd
import pika
import json
import logging
import io
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NSE FLOWS] - %(message)s')

RABBITMQ_HOST = 'localhost'
EXCHANGE_NAME = 'market_data_exchange'

def get_nse_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive"
    })
    # Hit homepage to get cookies
    session.get("https://www.nseindia.com", timeout=10)
    return session

def fetch_flows():
    session = get_nse_session()
    
    # 1. Fetch Cash Data
    try:
        cash_res = session.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=15)
        cash_data = cash_res.json()
    except Exception as e:
        logging.error(f"Cash API failed: {e}")
        return

    # Extract FII and DII Net Cash
    payload = {"date": None, "fii_net_cash": 0, "dii_net_cash": 0}
    for row in cash_data:
        cat = row.get('category', '').upper()
        if 'FII' in cat or 'FPI' in cat:
            payload['fii_net_cash'] = float(row.get('netValue', 0))
            payload['date'] = row.get('date')
        elif 'DII' in cat:
            payload['dii_net_cash'] = float(row.get('netValue', 0))

    if not payload['date']:
        return

    # 2. Fetch F&O CSV for that exact date
    date_obj = datetime.strptime(payload['date'], '%d-%b-%Y')
    fao_url = f"https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{date_obj.strftime('%d%m%Y')}.csv"
    
    try:
        fao_res = session.get(fao_url, timeout=15)
        # Use Pandas to read the CSV directly from memory
        df = pd.read_csv(io.StringIO(fao_res.text), skiprows=1)
        df.columns = df.columns.str.strip()
        
        # Get FII Row
        fii_row = df[df['Client Type'].str.strip() == 'FII'].iloc[0]
        
        idx_call_short = int(fii_row['Option Index Call Short'])
        idx_put_short = int(fii_row['Option Index Put Short'])
        
        payload['fii_idx_fut_net'] = int(fii_row['Future Index Long']) - int(fii_row['Future Index Short'])
        
        # Calculate PCR
        payload['pcr'] = round(idx_put_short / idx_call_short, 2) if idx_call_short > 0 else 1.0
        
        # Calculate Sentiment Score (Your custom logic)
        sentiment = 50 + (payload['fii_net_cash'] / 200) + (payload['fii_idx_fut_net'] / 5000)
        if payload['pcr'] > 1.3: sentiment -= 10
        if payload['pcr'] < 0.7: sentiment += 10
        payload['sentiment_score'] = max(0, min(100, round(sentiment, 1)))

    except Exception as e:
        logging.warning(f"F&O CSV not found or failed: {e}")
        payload['pcr'] = 1.0
        payload['sentiment_score'] = 50

    # 3. Publish to RabbitMQ
    connection = pika.BlockingConnection(pika.ConnectionParameters(RABBITMQ_HOST))
    channel = connection.channel()
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    
    channel.basic_publish(
        exchange=EXCHANGE_NAME,
        routing_key='market.sentiment.flows',
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    logging.info(f"Published FII Flows to Queue: {payload}")
    connection.close()

if __name__ == "__main__":
    fetch_flows()