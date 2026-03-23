import os
import logging
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Setup basic logging for our system
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_kite_session():
    """
    Handles the Zerodha Kite Connect authentication flow.
    Returns an authenticated KiteConnect instance.
    """
    # Load credentials securely from .env file
    load_dotenv()
    api_key = os.getenv("KITE_API_KEY")
    api_secret = os.getenv("KITE_API_SECRET")

    if not api_key or not api_secret:
        raise ValueError("API Key or Secret missing. Check your .env file.")

    kite = KiteConnect(api_key=api_key)

    # Check if we already have a valid access token for today
    token_file = "access_token.txt"
    
    if os.path.exists(token_file):
        with open(token_file, 'r') as file:
            access_token = file.read().strip()
        
        # Try to use the existing token
        kite.set_access_token(access_token)
        try:
            # Ping the profile endpoint to verify the token is still active
            profile = kite.profile()
            logging.info(f"Successfully connected using existing token. Welcome, {profile['user_name']}!")
            return kite
        except Exception as e:
            logging.warning("Existing token expired or invalid. Generating a new one.")

    # If no valid token exists, initiate the manual login flow
    logging.info("=== ACTION REQUIRED ===")
    logging.info(f"1. Please click this URL to login: {kite.login_url()}")
    logging.info("2. After login, you will be redirected to a URL.")
    logging.info("3. Copy the 'request_token' parameter from that URL.")
    
    request_token = input("Enter the Request Token here: ").strip()

    try:
        # Exchange the request token for an access token
        data = kite.generate_session(request_token, api_secret=api_secret)
        access_token = data["access_token"]
        
        # Save the token for the rest of the day so other agents can use it
        kite.set_access_token(access_token)
        with open(token_file, 'w') as file:
            file.write(access_token)
            
        logging.info("New access token generated and saved successfully!")
        return kite

    except Exception as e:
        logging.error(f"Authentication failed: {e}")
        return None

# Test the connection when running this script directly
if __name__ == "__main__":
    kite_session = get_kite_session()
    if kite_session:
        print("Kite Session is ready to pull data.")