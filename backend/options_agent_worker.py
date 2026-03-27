import pika
import json
import logging
import os
import yfinance as yf
from py_vollib.black_scholes.implied_volatility import implied_volatility
from py_vollib.black_scholes.greeks.analytical import delta, gamma, theta, vega, rho
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [OPTIONS AGENT] - %(message)s')

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
EXCHANGE_NAME = os.getenv('RABBITMQ_EXCHANGE', 'market_data_exchange')
QUEUE_NAME = os.getenv('RABBITMQ_OPTIONS_QUEUE', 'options_analysis_queue')
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'admin')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'supersecretpassword')

def analyze_option_chain(symbol, current_price):
    """
    Fetches the option chain for the nearest expiry, calculates simple Greeks,
    and looks for anomalous IV spikes.
    """
    yf_symbol = f"{symbol}.NS"
    signals = []
    
    try:
        ticker = yf.Ticker(yf_symbol)
        expirations = ticker.options
        
        if not expirations:
            logging.info(f"No options data available for {symbol}")
            return signals
            
        nearest_expiry = expirations[0]
        opt_chain = ticker.option_chain(nearest_expiry)
        
        calls = opt_chain.calls
        puts = opt_chain.puts
        
        # Analyze ATM Implied Volatility
        # Look for ATM Calls and Puts
        atm_call = calls.iloc[(calls['strike'] - current_price).abs().argsort()[:1]]
        atm_put = puts.iloc[(puts['strike'] - current_price).abs().argsort()[:1]]
        
        if not atm_call.empty and not atm_put.empty:
            call_iv = atm_call.iloc[0]['impliedVolatility']
            put_iv = atm_put.iloc[0]['impliedVolatility']
            
            # Simulated IV spike check (Assuming normal IV is ~20%)
            if call_iv > 0.5:
                signals.append(f"CALL IV SPIKE: ATM Call {nearest_expiry} IV is {round(call_iv*100, 2)}% (High Premium).")
            if put_iv > 0.5:
                signals.append(f"PUT IV SPIKE: ATM Put {nearest_expiry} IV is {round(put_iv*100, 2)}% (Fear/Protection Buying).")
                
            # PCR Check simple Volume based
            if puts['volume'].sum() > 0 and calls['volume'].sum() > 0:
                pcr_vol = puts['volume'].sum() / calls['volume'].sum()
                if pcr_vol > 1.5:
                    signals.append(f"BEARISH SENTIMENT: High Put/Call Volume Ratio ({round(pcr_vol, 2)}).")
                elif pcr_vol < 0.6:
                    signals.append(f"BULLISH SENTIMENT: Low Put/Call Volume Ratio ({round(pcr_vol, 2)}).")

    except Exception as e:
        logging.error(f"Error fetching/analyzing options for {symbol}: {e}")
        
    return signals

def process_message(ch, method, properties, body):
    try:
        payload = json.loads(body)
        symbol = payload['symbol']
        
        # EOD data has a list of 'data' dicts. Get the last close price.
        df_list = payload.get('data', [])
        if not df_list:
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
            
        latest_data = df_list[-1]
        current_price = latest_data['Close']
        
        logging.info(f"Received data for {symbol}. Analyzing Options Chain...")
        
        signals = analyze_option_chain(symbol, current_price)

        if signals:
            alert_payload = {
                "agent": "Options",
                "symbol": symbol,
                "close_price": round(current_price, 2),
                "signals": signals
            }
            
            alert_routing_key = f"alert.options.{symbol}"
            
            ch.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=alert_routing_key,
                body=json.dumps(alert_payload),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logging.info(f"🚨 OPTIONS ALERT GENERATED for {symbol}: {signals}")
        else:
            logging.info(f"No actionable options setups found for {symbol}.")

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logging.error(f"Failed to process message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

def start_options_agent():
    """Connects to RabbitMQ and starts listening to the EOD queue or specific topic."""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(RABBITMQ_HOST, 5672, '/', credentials)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='market.eod.*')

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)

    logging.info("Options Agent is online. To exit press CTRL+C")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logging.info("Agent shutting down...")
        channel.stop_consuming()
        connection.close()

if __name__ == "__main__":
    start_options_agent()
