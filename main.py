import logging
from kite import get_kite_session

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    logging.info("Initializing Agent Timm...")
    
    try:
        kite = get_kite_session()
        if kite:
            logging.info("Agent Timm is connected and ready for operations.")
            # Add further logic here for data analysis, trading, etc.
            
            # Example: Fetch profile data
            profile = kite.profile()
            print(f"User: {profile['user_name']}")
            print(f"Email: {profile['email']}")
            
        else:
            logging.error("Failed to initialize Kite session.")
            
    except Exception as e:
        logging.error(f"An error occurred during initialization: {e}")

if __name__ == "__main__":
    main()
