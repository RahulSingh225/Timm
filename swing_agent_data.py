import pandas as pd
from datetime import datetime, timedelta
import logging

# Import our authentication function from the previous script
from zerodha_auth import get_kite_session

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_instrument_token(kite, exchange, tradingsymbol):
    """
    Translates a human-readable ticker (e.g., RELIANCE) into Zerodha's internal instrument token.
    Note: In a production environment, you should download kite.instruments() once 
    in the morning and cache it locally (e.g., in a JSON file or Redis) to avoid API rate limits.
    """
    try:
        instruments = kite.instruments(exchange)
        for inst in instruments:
            if inst['tradingsymbol'] == tradingsymbol:
                return inst['instrument_token']
        logging.warning(f"Symbol {tradingsymbol} not found on {exchange}.")
        return None
    except Exception as e:
        logging.error(f"Error fetching instruments: {e}")
        return None

def fetch_swing_data(kite, exchange, symbol, days_back=365, interval='day'):
    """
    Fetches historical OHLCV data and returns a clean Pandas DataFrame.
    Interval options: 'minute', '3minute', '5minute', '15minute', '30minute', '60minute', 'day'
    """
    logging.info(f"Preparing to fetch {interval} data for {symbol}...")
    
    token = get_instrument_token(kite, exchange, symbol)
    if not token:
        return None

    to_date = datetime.now()
    from_date = to_date - timedelta(days=days_back)

    try:
        # Fetch the historical data
        # We set oi=True to pull Open Interest data, which is highly valuable for derivatives analysis
        records = kite.historical_data(
            instrument_token=token,
            from_date=from_date,
            to_date=to_date,
            interval=interval,
            oi=True 
        )
        
        # Convert raw list of dictionaries into a Pandas DataFrame
        df = pd.DataFrame(records)
        
        if not df.empty:
            # Set the date as the index for easier time-series analysis
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            logging.info(f"Successfully fetched {len(df)} records for {symbol}.")
            return df
        else:
            logging.warning(f"No data returned for {symbol} in the given date range.")
            return pd.DataFrame()
            
    except Exception as e:
        logging.error(f"API request failed for {symbol}: {e}")
        return None

# ==========================================
# Testing the Swing Agent Data Pipeline
# ==========================================
if __name__ == "__main__":
    kite_session = get_kite_session()
    
    if kite_session:
        # Let's pull 1 year of daily data for a heavyweight to test our logic
        target_symbol = "RELIANCE"
        
        df_swing = fetch_swing_data(
            kite=kite_session, 
            exchange="NSE", 
            symbol=target_symbol, 
            days_back=365, 
            interval='day'
        )
        
        if df_swing is not None and not df_swing.empty:
            print(f"\n--- {target_symbol} Latest Data ---")
            # Display the last 5 trading days
            print(df_swing[['open', 'high', 'low', 'close', 'volume']].tail())