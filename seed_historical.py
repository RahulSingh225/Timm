import logging
from datetime import datetime, timedelta
from nse_participant_scraper import fetch_and_parse_participant_data, publish_to_rabbitmq as publish_participant
from nsdl_tradewise_scraper import process_tradewise_month
from nsdl_sector_scraper import fetch_fortnightly_sectors

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SEED HISTORICAL] - %(message)s')

def seed_database():
    logging.info("Starting database seed process...")
    
    # 1. Seed NSDL Tradewise (last 3 months)
    logging.info("Seeding NSDL Tradewise data for the last 3 months...")
    for i in range(1, 4):
        try:
            process_tradewise_month(months_back=i)
        except Exception as e:
            logging.error(f"Failed to seed tradewise for month {i} back: {e}")

    # 2. Seed NSDL Sector Allocation (Current fortnight is default)
    logging.info("Seeding NSDL Fortnightly Sector data...")
    try:
        fetch_fortnightly_sectors()
    except Exception as e:
        logging.error(f"Failed to seed sector data: {e}")

    # 3. Seed Participant Data (Last 5 trade days)
    logging.info("Seeding NSE Participant data for the last 5 days...")
    for i in range(5):
        try:
            target_date = datetime.now() - timedelta(days=i)
            # Exclude weekends
            if target_date.weekday() < 5:
                data = fetch_and_parse_participant_data(target_date)
                if data:
                    publish_participant(data)
        except Exception as e:
            logging.error(f"Failed to seed participant data for {target_date.date()}: {e}")

    logging.info("Database seeding process completed.")

if __name__ == "__main__":
    seed_database()
