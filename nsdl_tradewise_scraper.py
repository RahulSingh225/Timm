import requests
import pandas as pd
import zipfile
import io
import json
import logging
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [TRADEWISE] - %(message)s')

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
                # You can now save this to DB or publish to RabbitMQ here
                
    except Exception as e:
        logging.error(f"Failed to process trade-wise data: {e}")

if __name__ == "__main__":
    process_tradewise_month(months_back=1)