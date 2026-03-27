import pandas as pd
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [ISIN MAP] - %(message)s')

NIFTY_500_URL = 'https://archives.nseindia.com/content/indices/ind_nifty500list.csv'
OUT_FILE = 'data/isin_sector_map.json'

DEFAULT_MAP = {
    'INE009A01021': 'Financial Services',
    'INE002A01018': 'Oil, Gas & Consumable Fuels',
    'INE467B01029': 'Information Technology',
    'INE089A01023': 'Healthcare',
    'INE585B01010': 'Automobile and Auto Components'
    # ... add other critical defaults if needed
}

def build_isin_map():
    logging.info("Fetching Nifty 500 list from NSE...")
    try:
        # Pandas reads the CSV directly from the URL
        df = pd.read_csv(NIFTY_500_URL)
        
        # Strip whitespace from column names just in case
        df.columns = df.columns.str.strip()
        
        # Create a dictionary from the DataFrame: { ISIN Code : Industry }
        nifty_map = dict(zip(df['ISIN Code'].str.strip(), df['Industry'].str.strip()))
        
        # Merge with defaults (Nifty 500 overrides defaults if there's a clash)
        final_map = {**DEFAULT_MAP, **nifty_map}
        
        os.makedirs('data', exist_ok=True)
        with open(OUT_FILE, 'w') as f:
            json.dump(final_map, f, indent=4)
            
        logging.info(f"Successfully saved ISIN map. Total entries: {len(final_map)}")
        
    except Exception as e:
        logging.error(f"Failed to build ISIN map: {e}")

if __name__ == "__main__":
    build_isin_map()