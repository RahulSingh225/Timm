import requests
import pandas as pd
import pika
import zipfile
import io
import json
import logging
import os
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
from dateutil.relativedelta import relativedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [TRADEWISE] - %(message)s')

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
EXCHANGE_NAME = os.getenv('RABBITMQ_EXCHANGE', 'market_data_exchange')
ROUTING_KEY = 'market.sentiment.tradewise'

def get_isin_map():
    try:
        with open('data/isin_sector_map.json', 'r') as f:
            return json.load(f)
    except:
        logging.warning("ISIN map not found. Run build_isin_map.py first.")
        return {}

def process_tradewise_month(months_back=1):
    target_date = datetime.now() - relativedelta(months=months_back)
    mon_name = target_date.strftime("%b")
    year = target_date.strftime("%Y")
    
    url = f"https://www.fpi.nsdl.co.in/web/StaticReports/statistics/zip/{mon_name}_{year}.zip"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    logging.info(f"Downloading ZIP: {url}")
    
    try:
        res = requests.get(url, headers=headers, timeout=30)
        res.raise_for_status()
        
        # Read ZIP from memory
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            csv_filename = [f for f in z.namelist() if f.endswith('.csv') or f.endswith('.txt')][0]
            
            with z.open(csv_filename) as f:
                # Use Pandas to parse the messy CSV (handles | or , separators)
                df = pd.read_csv(f, sep=None, engine='python', on_bad_lines='skip')
                
                # Assume columns based on your JS script
                # 7 = ISIN, 9 = BUY/SELL, 14 = Value, 15 = Instrument (EQ)
                df.columns = [str(i) for i in range(len(df.columns))] 
                
                # Filter for Equity only
                df = df[df['15'].str.strip() == 'EQ']
                
                isin_map = get_isin_map()
                
                sector_agg = {}
                for _, row in df.iterrows():
                    isin = str(row['7']).strip()
                    tx_type = str(row['9']).strip().upper()
                    value_cr = pd.to_numeric(row['14'], errors='coerce') / 10000000 # Convert to Cr
                    
                    if pd.isna(value_cr) or tx_type not in ['BUY', 'SELL']: continue
                        
                    sector = isin_map.get(isin, 'Unmapped')
                    
                    if sector not in sector_agg:
                        sector_agg[sector] = {'buy': 0, 'sell': 0, 'net': 0}
                        
                    if tx_type == 'BUY': sector_agg[sector]['buy'] += value_cr
                    else: sector_agg[sector]['sell'] += value_cr
                        
                    sector_agg[sector]['net'] = sector_agg[sector]['buy'] - sector_agg[sector]['sell']

                logging.info(f"Aggregated {len(sector_agg)} sectors for {mon_name} {year}")
                
                # Publish to RabbitMQ
                if sector_agg:
                    payload = {
                        "date": target_date.strftime("%d-%b-%Y"),
                        "data": [{"isin": "SECTOR", "instrument": "EQ", "buy": v['buy'], "sell": v['sell'], "net": v['net'], "sector": k} for k, v in sector_agg.items()]
                    }
                    
                    credentials = pika.PlainCredentials(os.getenv('RABBITMQ_USER', 'admin'), os.getenv('RABBITMQ_PASS', 'supersecretpassword'))
                    connection = pika.BlockingConnection(pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials))
                    channel = connection.channel()
                    
                    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
                    channel.basic_publish(
                        exchange=EXCHANGE_NAME,
                        routing_key=ROUTING_KEY,
                        body=json.dumps(payload),
                        properties=pika.BasicProperties(delivery_mode=2)
                    )
                    logging.info(f"✅ Published Aggregated Tradewise data for {mon_name} {year}")
                    connection.close()
                
    except Exception as e:
        logging.error(f"Failed to process trade-wise data: {e}")

if __name__ == "__main__":
    process_tradewise_month(months_back=1)