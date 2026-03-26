import pika  # type: ignore
import json
import psycopg2  # type: ignore
import logging
import time
import os
import yfinance as yf  # type: ignore
from dotenv import load_dotenv  # type: ignore

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [PRICE MONITOR] - %(message)s')

# Configuration
load_dotenv()
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "admin")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "supersecretpassword")
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE", "market_data_exchange")
DB_URL = os.getenv("DATABASE_URL")

POLL_INTERVAL = 60  # seconds

def get_db_connection():
    try:
        return psycopg2.connect(DB_URL)
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return None

def publish_alert(trade, alert_type, current_price, pnl_pct):
    """
    Publishes a stoploss or target alert to RabbitMQ.
    """
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
        
        routing_key = f'alert.{alert_type}.{trade["symbol"]}'
        
        payload = {
            'symbol': trade['symbol'],
            'agent': 'PriceMonitor',
            'signal_type': 'BEARISH' if alert_type == 'stoploss' else 'BULLISH',
            'trade_id': trade['id'],
            'entry_price': trade['entry_price'],
            'current_price': current_price,
            'pnl_pct': pnl_pct,
            'signals': [f'{alert_type.upper()} HIT! Entry: {trade["entry_price"]}, Exit: {current_price}, PnL: {pnl_pct}%'],
            'summary': f"{trade['symbol']} has hit your {alert_type}. Exiting trade."
        }
        
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=routing_key,
            body=json.dumps(payload)
        )
        
        # Also publish an active trade status update to update the DB
        update_payload = {
            'action': 'update',
            'trade_id': trade['id'],
            'status': f'{alert_type.upper()}_HIT',
            'current_price': current_price,
            'pnl_pct': pnl_pct
        }
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=f'trade.active.{trade["symbol"]}',
            body=json.dumps(update_payload)
        )

        logging.info(f"🚨 Published {alert_type.upper()} alert for {trade['symbol']}")
        connection.close()

    except Exception as e:
        logging.error(f"RabbitMQ Connection Error publishing alert: {e}")

def monitor_active_trades():
    """
    Polls active trades and checks against yfinance real-time prices.
    """
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        # Fetch all open trades
        cursor.execute("SELECT id, symbol, entry_price, stoploss, target FROM active_trades WHERE status = 'OPEN'")
        open_trades = cursor.fetchall()

        if not open_trades:
            return  # No active trades to monitor
            
        logging.info(f"🔍 Monitoring {len(open_trades)} active trades...")
        
        # Batch fetch prices for all symbols
        symbols = [str(row[1]) + ".NS" if not str(row[1]).endswith(".NS") else str(row[1]) for row in open_trades]
        
        # yf.download is faster for bulk, but Tickers is fine for few
        tickers = yf.Tickers(" ".join(symbols))
        
        updates_needed = []

        for row in open_trades:
            trade = {
                'id': row[0],
                'symbol': str(row[1]),
                'entry_price': float(row[2]),
                'stoploss': float(row[3]),
                'target': float(row[4])
            }
            
            trade_symbol = str(trade['symbol'])
            ticker_sym = trade_symbol + ".NS" if not trade_symbol.endswith(".NS") else trade_symbol
            
            try:
                hist = tickers.tickers[ticker_sym].history(period="1d", interval="1m")
                if len(hist) > 0:
                    current_price = round(float(hist['Close'].iloc[-1]), 2)
                    pnl_pct = round(((current_price - trade['entry_price']) / trade['entry_price']) * 100, 2)
                    
                    if current_price <= trade['stoploss']:
                        logging.warning(f"🛑 STOPLOSS HIT for {trade['symbol']} @ {current_price}")
                        publish_alert(trade, 'stoploss', current_price, pnl_pct)
                        
                    elif current_price >= trade['target']:
                        logging.warning(f"🎯 TARGET HIT for {trade['symbol']} @ {current_price}")
                        publish_alert(trade, 'target', current_price, pnl_pct)
                        
                    else:
                        updates_needed.append((current_price, pnl_pct, trade['id']))
                        
            except Exception as e:
                logging.error(f"Error fetching price for {trade['symbol']}: {e}")

        # Bulk update just the current price and PnL for trades still OPEN
        if updates_needed:
            execute_query = "UPDATE active_trades SET current_price = %s, pnl_pct = %s WHERE id = %s"
            cursor.executemany(execute_query, updates_needed)
            conn.commit()

        cursor.close()
        
    except Exception as e:
        logging.error(f"Database error while monitoring trades: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    logging.info("🛡️ Price Monitor Worker is online. Tracking active trades...")
    while True:
        try:
            monitor_active_trades()
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            logging.info("Shutting down Price Monitor Worker...")
            break
        except Exception as e:
            logging.error(f"Worker crashed! Restarting in 60s. Error: {e}")
            time.sleep(60)
