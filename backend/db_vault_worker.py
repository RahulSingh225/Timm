import os
from datetime import datetime
import pika
import json
import psycopg2
import logging
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [VAULT WORKER] - %(message)s')

# Configuration
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE", "market_data_exchange")
QUEUE_NAME = os.getenv("RABBITMQ_QUEUE", "vault_db_queue")

# Database Connection String
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
        # DB connection failure should requeue so we try when DB is back
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return

    try:
        cursor = conn.cursor()
        payload = json.loads(body)

        if not payload:
            logging.warning(f"Empty payload received on {routing_key}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # ---------------------------------------------------------
        # 1. HANDLE ALERTS (alert.#)
        # ---------------------------------------------------------
        if routing_key.startswith('alert.'):
            signals_list = payload.get('signals', [])
            signals_text = " ".join(signals_list) if isinstance(signals_list, list) else str(signals_list)

            calc_type = 'NEUTRAL'
            if any(kw in signals_text.upper() for kw in ['BULLISH', 'GOLDEN', 'BOUNCE', 'BUY']):
                calc_type = 'BULLISH'
            elif any(kw in signals_text.upper() for kw in ['BEARISH', 'DEATH', 'DROP', 'SELL']):
                calc_type = 'BEARISH'

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
            logging.info(f"💾 Saved Alert: {payload.get('symbol')} [{signal_type}]")

        # ---------------------------------------------------------
        # 2. HANDLE SMART MONEY (market.sentiment.participant)
        # ---------------------------------------------------------
        elif routing_key == 'market.sentiment.participant':
            data_list = payload.get('data', [])
            if data_list:
                insert_query = """
                    INSERT INTO participant_data 
                    (trade_date, participant_type, net_index_call, net_index_put, net_index_futures, net_stock_futures)
                    VALUES %s
                    ON CONFLICT (trade_date, participant_type) DO UPDATE SET
                        net_index_call = EXCLUDED.net_index_call,
                        net_index_put = EXCLUDED.net_index_put,
                        net_index_futures = EXCLUDED.net_index_futures,
                        net_stock_futures = EXCLUDED.net_stock_futures;
                """
                values = [(
                    d['tradeDate'], d['participantType'], d['netIndexCall'], 
                    d['netIndexPut'], d['netIndexFutures'], d['netStockFutures']
                ) for d in data_list]
                
                execute_values(cursor, insert_query, values)
                logging.info(f"💾 Saved/Updated {len(values)} Smart Money footprints.")

        # ---------------------------------------------------------
        # 3. HANDLE NEWS (market.news.macro)
        # ---------------------------------------------------------
        elif routing_key == 'market.news.macro':
            cursor.execute("""
                INSERT INTO news_events (title, content, source, url, published_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING;
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
                    ON CONFLICT (trade_date, index_name, strike_price, option_type) DO UPDATE SET
                        change_in_oi = EXCLUDED.change_in_oi,
                        volume = EXCLUDED.volume,
                        open_interest = EXCLUDED.open_interest;
                """
                values = [(
                    d['tradeDate'], d['indexName'], 'WEEKLY', d['strikePrice'], 
                    d['optionType'], d['closePrice'], d['openInterest'], 
                    d['changeInOI'], d['volume']
                ) for d in payload]
                
                execute_values(cursor, insert_query, values)
                logging.info(f"💾 Saved/Updated {len(values)} Options Footprint rows.")
                
        # ---------------------------------------------------------
        # 4.5 HANDLE VECTOR SIGNALS (candle.vector)
        # ---------------------------------------------------------
        elif routing_key == 'candle.vector':
            timestamp_val = payload.get('timestamp')
            cursor.execute("""
                INSERT INTO vector_signals 
                (symbol, timestamp, raw_scalar, iv_adjusted_scalar, 
                 current_atm_iv, signed_accumulation, predicted_next_move, 
                 linear_m, linear_b, confidence, signal, candle_vector)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, timestamp) DO NOTHING;
            """, (
                payload.get('symbol'),
                timestamp_val,
                payload.get('raw_scalar'),
                payload.get('iv_adjusted_scalar'),
                payload.get('current_atm_iv'),
                payload.get('signed_accumulation'),
                payload.get('predicted_next_move'),
                payload.get('linear_m'),
                payload.get('linear_b'),
                payload.get('confidence'),
                payload.get('signal'),
                json.dumps(payload.get('candle_vector'))
            ))
            logging.info(f"💾 Saved Vector Signal for {payload.get('symbol')}")

        # ---------------------------------------------------------
        # 5. HANDLE FII/DII FLOWS
        # ---------------------------------------------------------
        elif routing_key == 'market.sentiment.flows':
            trade_date = datetime.strptime(payload.get('date'), '%d-%b-%Y').date()
            cursor.execute("""
                INSERT INTO fii_dii_flows 
                (trade_date, fii_net_cash, dii_net_cash, fii_idx_fut_net, pcr, sentiment_score)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (trade_date) DO UPDATE SET
                    fii_net_cash = EXCLUDED.fii_net_cash,
                    dii_net_cash = EXCLUDED.dii_net_cash,
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

        # ---------------------------------------------------------
        # 6. HANDLE NSDL SECTOR ALLOCATIONS
        # ---------------------------------------------------------
        elif routing_key == 'market.sentiment.sectors':
            sectors = payload.get('sectors', [])
            date_code = payload.get('date_code')
            trade_date = datetime.strptime(date_code, '%b%d%Y').date() if date_code else datetime.now().date()

            insert_query = """
                INSERT INTO sector_flows (trade_date, sector_name, net_investment_cr)
                VALUES %s
                ON CONFLICT (trade_date, sector_name) DO UPDATE SET
                    net_investment_cr = EXCLUDED.net_investment_cr;
            """
            values = [(trade_date, s['sector'], s['equity_net_inr']) for s in sectors]
            execute_values(cursor, insert_query, values)
            logging.info(f"💾 Saved {len(values)} NSDL Sector flow records.")

        # ---------------------------------------------------------
        # 7. HANDLE NSDL TRADE-WISE
        # ---------------------------------------------------------
        elif routing_key == 'market.sentiment.tradewise':
            data_list = payload.get('data', [])
            trade_date = datetime.strptime(payload.get('date'), '%d-%b-%Y').date() if payload.get('date') else datetime.now().date()

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

        # ---------------------------------------------------------
        # 8. HANDLE CACHING (INTRADAY CANDLES)
        # ---------------------------------------------------------
        elif routing_key.startswith('market.intraday.'):
            candles = payload.get('data', [])
            symbol = payload.get('symbol')
            timeframe = payload.get('timeframe', '15m')
            
            insert_query = """
                INSERT INTO intraday_candles 
                (symbol, timeframe, candle_time, open, high, low, close, volume)
                VALUES %s
                ON CONFLICT (symbol, timeframe, candle_time) DO UPDATE SET
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    fetched_at = NOW();
            """
            values = [(symbol, timeframe, c['timestamp'], c['open'], c['high'], c['low'], c['close'], c['volume']) for c in candles]
            execute_values(cursor, insert_query, values)
            logging.info(f"💾 Cached {len(values)} {timeframe} candles for {symbol}")

        # ---------------------------------------------------------
        # 9. HANDLE SCREENER RESULTS
        # ---------------------------------------------------------
        elif routing_key.startswith('screener.'):
            cursor.execute("""
                INSERT INTO screened_stocks 
                (symbol, timeframe, trade_type, setup_type, entry_price, target_price, 
                 stoploss_price, target_pct, risk_pct, confidence, signals, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, timeframe, setup_type, created_at) DO NOTHING;
            """, (
                payload.get('symbol'),
                payload.get('timeframe', '15m'),
                payload.get('trade_type', 'INTRADAY'),
                payload.get('setup_type', 'UNKNOWN'),
                payload.get('entry_price'),
                payload.get('target_price'),
                payload.get('stoploss_price'),
                payload.get('target_pct'),
                payload.get('risk_pct'),
                payload.get('confidence', 0),
                json.dumps(payload.get('signals', [])),
                'ACTIVE'
            ))
            logging.info(f"💾 Saved Screener Result for {payload.get('symbol')}")

        conn.commit()
        cursor.close()
        conn.close()
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logging.error(f"Failed to process message on {routing_key}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        # CRITICAL: If the error is with the data content (bogus data), do NOT requeue it.
        # This prevents 100% CPU loops where a bad message is delivered forever.
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def start_vault_worker():
    credentials = pika.PlainCredentials(os.getenv('RABBITMQ_USER', 'admin'), os.getenv('RABBITMQ_PASS', 'supersecretpassword'))
    parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    
    # Bind to all relevant market data keys
    bindings = [
        'alert.#', 'market.sentiment.#', 'market.news.#', 
        'market.footprint.#', 'candle.vector', 'market.intraday.#',
        'screener.#', 'market.global.cues', 'trade.active.#'
    ]
    for key in bindings:
        channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=key)

    channel.basic_qos(prefetch_count=30)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)

    logging.info("🗄️ Vault Worker (Deduplication Enabled) is online.")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        connection.close()

if __name__ == "__main__":
    start_vault_worker()