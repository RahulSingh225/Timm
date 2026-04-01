import yfinance as yf  # type: ignore
import pika  # type: ignore
import json
import logging
import os
import schedule  # type: ignore
import time
from dotenv import load_dotenv  # type: ignore

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [GLOBAL CUES PRODUCER] - %(message)s')

load_dotenv()
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "admin")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "supersecretpassword")
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE", "market_data_exchange")

# Market Tickers to fetch
# ^GSPC = S&P 500, ^IXIC = NASDAQ, ^DJI = Dow Jones, ^VIX = Volatility Index, ^NSEI = Nifty 50, INR=X = USD/INR
TICKERS = {
    'SPY': '^GSPC',
    'QQQ': '^IXIC',
    'DJI': '^DJI',
    'VIX': '^VIX',
    'NIFTY': '^NSEI',
    'USDINR': 'INR=X'
}

def fetch_global_cues():
    """
    Fetches the latest data for major global indices to determine market bias.
    """
    logging.info("🌍 Fetching Global Macro Cues...")
    cues_data = {
        'spy_change_pct': 0.0,
        'qqq_change_pct': 0.0,
        'dji_change_pct': 0.0,
        'vix_value': 0.0,
        'vix_change_pct': 0.0,
        'sgx_nifty': 0.0, # Using NIFTY as proxy if GIFT NIFTY isn't available easily on Yahoo
        'sgx_change_pct': 0.0,
        'usd_inr': 0.0,
        'gift_nifty': 0.0,
        'overall_bias': 'NEUTRAL'
    }

    try:
        # Fetch data in bulk
        symbols = list(TICKERS.values())
        tickers = yf.Tickers(" ".join(symbols))
        
        # Calculate changes
        calc_change = lambda current, prev: round(((current - prev) / prev) * 100, 2) if prev else 0.0

        for name, ticker_sym in TICKERS.items():
            hist = tickers.tickers[ticker_sym].history(period="5d")
            if len(hist) >= 2:
                current_close = float(hist['Close'].iloc[-1])
                prev_close = float(hist['Close'].iloc[-2])
                change_pct = calc_change(current_close, prev_close)

                if name == 'SPY':
                    cues_data['spy_change_pct'] = change_pct
                elif name == 'QQQ':
                    cues_data['qqq_change_pct'] = change_pct
                elif name == 'DJI':
                    cues_data['dji_change_pct'] = change_pct
                elif name == 'VIX':
                    cues_data['vix_value'] = round(current_close, 2)
                    cues_data['vix_change_pct'] = change_pct
                elif name == 'NIFTY':
                    # Using current NIFTY level as proxy for GIFT
                    cues_data['sgx_nifty'] = round(current_close, 2)
                    cues_data['gift_nifty'] = round(current_close, 2)
                    cues_data['sgx_change_pct'] = change_pct
                elif name == 'USDINR':
                    cues_data['usd_inr'] = round(current_close, 2)

        # Determine Overall Bias
        # Simple Logic: If SPY/QQQ green and VIX dropping -> RISK_ON
        # If SPY/QQQ red and VIX rising > 18 -> RISK_OFF
        avg_us_change = (cues_data['spy_change_pct'] + cues_data['qqq_change_pct']) / 2
        
        if avg_us_change > 0.3 and cues_data['vix_value'] < 18 and cues_data['vix_change_pct'] < 0:
            cues_data['overall_bias'] = 'RISK_ON'
        elif avg_us_change < -0.3 or (cues_data['vix_value'] > 20 and cues_data['vix_change_pct'] > 5):
            cues_data['overall_bias'] = 'RISK_OFF'
        else:
            cues_data['overall_bias'] = 'NEUTRAL'

        logging.info(f"📊 Global Market Bias: {cues_data['overall_bias']} | VIX: {cues_data['vix_value']} | SPY: {cues_data['spy_change_pct']}%")
        return cues_data

    except Exception as e:
        logging.error(f"Failed to fetch global cues from Yahoo Finance: {e}")
        return None

def publish_cues(cues_data):
    """
    Publishes global cues to the market.global.cues routing key.
    """
    if not cues_data:
        return
        
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
        
        routing_key = 'market.global.cues'
        
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=routing_key,
            body=json.dumps(cues_data)
        )
        
        logging.info(f"🚀 Published Global Cues to {routing_key}")
        connection.close()

    except Exception as e:
        logging.error(f"RabbitMQ Connection Error: {e}")

def run_job():
    cues = fetch_global_cues()
    if cues:
        publish_cues(cues)

if __name__ == "__main__":
    import sys
    
    if '--dry-run' in sys.argv:
        cues = fetch_global_cues()
        logging.info("🌵 Dry Run Mode. Payload:")
        print(json.dumps(cues, indent=2))
        sys.exit(0)

    if '--single-run' in sys.argv:
        # Scheduler-managed mode: run once and exit
        run_job()
        logging.info("Single run complete. Exiting.")
        sys.exit(0)
        
    logging.info("⏰ Global Cues Producer starting up (standalone scheduler mode)...")
    
    # Run once immediately on startup to populate the DB
    run_job()
    
    # Schedule to run every day pre-market (8:30 AM local server time)
    schedule.every().day.at("08:30").do(run_job)
    
    # Also run mid-day for US futures updates (optional but helpful)
    schedule.every().day.at("13:30").do(run_job)
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except KeyboardInterrupt:
            logging.info("Shutting down Global Cues Producer...")
            break
