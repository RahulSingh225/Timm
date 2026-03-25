import pandas as pd
import requests
import pika
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NSDL SECTORS] - %(message)s')

RABBITMQ_HOST = 'localhost'
EXCHANGE_NAME = 'market_data_exchange'

def fetch_fortnightly_sectors(date_code=None):
    if not date_code:
        # Default to a known recent date code format (e.g., 'Mar152026')
        date_code = datetime.now().strftime("%b15%Y") 

    url = f"https://www.fpi.nsdl.co.in/web/StaticReports/Fortnightly_Sector_wise_FII_Investment_Data/FIIInvestSector_{date_code}.html"
    
    headers = {"User-Agent": "Mozilla/5.0"}
    logging.info(f"Attempting to fetch NSDL Sectors: {url}")
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        
        # Pandas magically finds all <table> elements in the HTML
        tables = pd.read_html(io.StringIO(res.text))
        
        # The sector data is usually in the largest table
        df = max(tables, key=len)
        
        # Drop rows where Sector Name is missing or is "Total"
        df = df.dropna(subset=[df.columns[1]])
        df = df[~df.iloc[:, 1].astype(str).str.contains('Total', case=False)]
        
        payloads = []
        for _, row in df.iterrows():
            sector_name = str(row.iloc[1]).strip()
            # Column 27 (index 26) is usually Equity Net INR Cr based on your JS notes
            net_equity = pd.to_numeric(str(row.iloc[26]).replace(',', ''), errors='coerce')
            
            if pd.notna(net_equity) and len(sector_name) > 3:
                payloads.append({
                    "sector": sector_name,
                    "equity_net_inr": float(net_equity)
                })

        if payloads:
            connection = pika.BlockingConnection(pika.ConnectionParameters(RABBITMQ_HOST))
            channel = connection.channel()
            channel.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key='market.sentiment.sectors',
                body=json.dumps({"date_code": date_code, "sectors": payloads}),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logging.info(f"Published {len(payloads)} Sector Flows to Queue.")
            connection.close()

    except Exception as e:
        logging.error(f"Failed to fetch NSDL sectors: {e}")

if __name__ == "__main__":
    fetch_fortnightly_sectors()