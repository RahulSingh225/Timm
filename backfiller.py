import logging
import subprocess
import time
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [MASTER BACKFILLER] - %(message)s')

def run_script(name):
    logging.info(f"🚀 Running {name}...")
    try:
        subprocess.run([sys.executable, name], check=True)
        logging.info(f"✅ Finished {name}")
    except Exception as e:
        logging.error(f"❌ Failed to run {name}: {e}")

if __name__ == "__main__":
    logging.info("Starting Master Database Backfill...")
    
    # 1. First, build the ISIN map (required for sector tradewise data)
    run_script("build_isin_map.py")
    
    # 2. Daily Price & Technical Alerts (populates market_alerts)
    run_script("yfinance_producer.py")
    
    # 3. Macro Sentiment & Smart Money (FII/DII, Participants, Sectors)
    run_script("seed_historical.py")
    
    # 4. Options Footprint (Smart Money Tracker)
    run_script("option_footprint_producer.py")
    
    # 5. Macro News
    run_script("news_scraper_producer.py")
    
    logging.info("🏆 Database Backfill Complete. Your dashboard should now be populated!")
