import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
import pika
import json
import psycopg2
import logging
from psycopg2.extras import execute_values

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [VAULT WORKER] - %(message)s')

# Configuration
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE", "market_data_exchange")
QUEUE_NAME = os.getenv("RABBITMQ_QUEUE", "vault_db_queue")

# Database Connection String (Matches Docker Compose)
DB_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    try:
        conn = psycopg2.connect(DB_URL)
        return conn
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return None

def process_message(ch, method, properties, body):
    routing_key = method.routing_key
    conn = get_db_connection()
    
    if not conn:
        # Requeue message if DB is down
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return

    try:
        cursor = conn.cursor()
        payload = json.loads(body)

        # ---------------------------------------------------------
        # 1. HANDLE ALERTS (alert.#)
        # ---------------------------------------------------------
        if routing_key.startswith('alert.'):
            # Smart signal type detection (mirrors db_worker.ts logic)
            signals_list = payload.get('signals', [])
            signals_text = " ".join(signals_list) if isinstance(signals_list, list) else str(signals_list)

            calc_type = 'NEUTRAL'
            if any(kw in signals_text.upper() for kw in ['BULLISH', 'GOLDEN', 'BOUNCE', 'BUY']):
                calc_type = 'BULLISH'
            elif any(kw in signals_text.upper() for kw in ['BEARISH', 'DEATH', 'DROP', 'SELL']):
                calc_type = 'BEARISH'

            # Honor explicit type from agent payload if provided, else use calculated
            signal_type = payload.get('signal_type') or payload.get('signalType') or calc_type

            cursor.execute("""
                INSERT INTO market_alerts (symbol, agent_source, signal_type, close_price, signals, summary)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                payload.get('symbol'),
                payload.get('agent', 'Unknown'),
                signal_type,
                round(float(payload.get('close_price'))) if payload.get('close_price') else None,
                json.dumps(signals_list),
                payload.get('summary') or payload.get('brief')
            ))
            logging.info(f"💾 Saved Alert for {payload.get('symbol')} [{signal_type}]")

        # ---------------------------------------------------------
        # 2. HANDLE SMART MONEY (market.sentiment.participant)
        # ---------------------------------------------------------
        elif routing_key == 'market.sentiment.participant':
            data_list = payload.get('data', [])
            if data_list:
                # Use execute_values for fast bulk inserts
                insert_query = """
                    INSERT INTO participant_data 
                    (trade_date, participant_type, net_index_call, net_index_put, net_index_futures, net_stock_futures)
                    VALUES %s
                """
                values = [(
                    d['tradeDate'], d['participantType'], d['netIndexCall'], 
                    d['netIndexPut'], d['netIndexFutures'], d['netStockFutures']
                ) for d in data_list]
                
                execute_values(cursor, insert_query, values)
                logging.info(f"💾 Saved {len(values)} Smart Money footprints.")

        # ---------------------------------------------------------
        # 3. HANDLE NEWS (market.news.macro)
        # ---------------------------------------------------------
        elif routing_key == 'market.news.macro':
            cursor.execute("""
                INSERT INTO news_events (title, content, source, url, published_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING; -- Prevents duplicate news articles
            """, (
                payload.get('title'),
                payload.get('content'),
                payload.get('source'),
                payload.get('url'),
                payload.get('publishedAt')
            ))
            logging.info(f"💾 Saved News: {payload.get('title')[:30]}...")

        # ---------------------------------------------------------
        # 4. HANDLE OPTIONS FOOTPRINT (market.footprint.options)
        # ---------------------------------------------------------
        elif routing_key == 'market.footprint.options':
            if isinstance(payload, list):
                insert_query = """
                    INSERT INTO options_footprint 
                    (trade_date, index_name, expiry_type, strike_price, option_type, close_price, open_interest, change_in_oi, volume)
                    VALUES %s
                """
                
                # Simple logic to guess Weekly vs Monthly (can be refined later)
                values = [(
                    d['tradeDate'], d['indexName'], 'WEEKLY', d['strikePrice'], 
                    d['optionType'], d['closePrice'], d['openInterest'], 
                    d['changeInOI'], d['volume']
                ) for d in payload]
                
                execute_values(cursor, insert_query, values)
                logging.info(f"💾 Saved {len(values)} Options Footprint rows.")
        # ---------------------------------------------------------
        # 5. HANDLE FII/DII FLOWS (from Node.js producer)
        # ---------------------------------------------------------
        elif routing_key == 'market.sentiment.flows':
            try:
                # Convert DD-MMM-YYYY to standard datetime
                trade_date = datetime.strptime(payload.get('date'), '%d-%b-%Y').date()
                
                cursor.execute("""
                    INSERT INTO fii_dii_flows 
                    (trade_date, fii_net_cash, dii_net_cash, fii_idx_fut_net, pcr, sentiment_score)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (trade_date) DO UPDATE SET
                        fii_net_cash = EXCLUDED.fii_net_cash,
                        pcr = EXCLUDED.pcr,
                        sentiment_score = EXCLUDED.sentiment_score;
                """, (
                    trade_date,
                    payload.get('fii_net_cash', 0),
                    payload.get('dii_net_cash', 0),
                    payload.get('fii_idx_fut_net', 0),
                    payload.get('pcr', 1.0),
                    payload.get('sentiment_score', 50)
                ))
                logging.info(f"💾 Saved FII/DII Flows for {trade_date}")
            except Exception as e:
                logging.error(f"Error parsing date or saving flows: {e}")

        # ---------------------------------------------------------
        # 6. HANDLE NSDL SECTOR ALLOCATIONS (from Node.js producer)
        # ---------------------------------------------------------
        elif routing_key == 'market.sentiment.sectors':
            sectors = payload.get('sectors', [])
            if sectors:
                # Try to parse the NSDL date_code (e.g., 'Mar152026')
                try:
                    date_code = payload.get('date_code')
                    trade_date = datetime.strptime(date_code, '%b%d%Y').date()
                except:
                    trade_date = datetime.now().date()

                insert_query = """
                    INSERT INTO sector_flows (trade_date, sector_name, net_investment_cr)
                    VALUES %s
                """
                values = [(
                    trade_date,
                    s['sector'],
                    s['equity_net_inr']
                ) for s in sectors]
                
                execute_values(cursor, insert_query, values)
                logging.info(f"💾 Saved {len(values)} NSDL Sector flow records.")

        # ---------------------------------------------------------
        # 7. HANDLE NSDL TRADE-WISE (from Node.js producer)
        # ---------------------------------------------------------
        elif routing_key == 'market.sentiment.tradewise':
            data_list = payload.get('data', [])
            if data_list:
                # Try to parse date
                try:
                    trade_date = datetime.strptime(payload.get('date'), '%d-%b-%Y').date()
                except:
                    trade_date = datetime.now().date()

                insert_query = """
                    INSERT INTO tradewise_flows 
                    (trade_date, isin, buy_value, sell_value, net_value, instrument_type)
                    VALUES %s
                    ON CONFLICT (trade_date, isin) DO UPDATE SET
                        buy_value = EXCLUDED.buy_value,
                        sell_value = EXCLUDED.sell_value,
                        net_value = EXCLUDED.net_value;
                """
                values = [(trade_date, d['isin'], d['buy'], d['sell'], d['net'], d['instrument']) for d in data_list]
                
                execute_values(cursor, insert_query, values)
                logging.info(f"💾 Saved {len(values)} Trade-wise records.")
        # Commit transaction and acknowledge message
        conn.commit()
        cursor.close()
        conn.close()
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logging.error(f"Failed to save to database: {e}")
        if conn:
            conn.rollback() # Rollback the bad transaction
            conn.close()
        # NACK the message so RabbitMQ doesn't delete it; we can try again later
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

def start_vault_worker():
    credentials = pika.PlainCredentials(os.getenv('RABBITMQ_USER', 'admin'), os.getenv('RABBITMQ_PASS', 'supersecretpassword'))
    parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    
    # This queue is exclusively for the database
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    
    # Bind to EVERYTHING we want to save
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='alert.#')
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='market.sentiment.participant')
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='market.news.macro')
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='market.footprint.options')
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='market.sentiment.flows')
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='market.sentiment.sectors')
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='market.sentiment.tradewise')

    # Prefetch count = 50 for faster bulk writing
    channel.basic_qos(prefetch_count=50)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)

    logging.info("🗄️ Vault Worker is online. Listening for all market data to persist to PostgreSQL...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logging.info("Vault Worker shutting down...")
        channel.stop_consuming()
        connection.close()

if __name__ == "__main__":
    start_vault_worker()