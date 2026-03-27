import os
import json
import time
import logging
import numpy as np
import requests
import pika
from collections import deque
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# CONFIGURATION & ENVIRONMENT VARIABLES
# ==========================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format='%(asctime)s - [VECTOR AGENT] - %(message)s')

# RabbitMQ Config (matches platform conventions)
RMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RMQ_USER = os.getenv("RABBITMQ_USER", "admin")
RMQ_PASS = os.getenv("RABBITMQ_PASS", "supersecretpassword")
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE", "market_data_exchange")
ROUTING_KEY_IN = os.getenv("VECTOR_ROUTING_KEY_IN", "market.candle.#")
QUEUE_IN = os.getenv("VECTOR_QUEUE_IN", "candle_vector_queue")
ROUTING_KEY_OUT = "candle.vector"

# Math/Vector Config
HISTORY_WINDOW = int(os.getenv("HISTORY_WINDOW", "100"))
IV_SCALING_FACTOR = float(os.getenv("IV_SCALING_FACTOR", "1.0"))
SIGNAL_THRESHOLD = float(os.getenv("SIGNAL_THRESHOLD", "5.0"))

# ==========================================
# NSE OPTIONS CHAIN API HANDLER
# ==========================================
class NSEOptionsAPI:
    """Handles fetching and caching the Implied Volatility from the NSE Options Chain."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        self.base_url = "https://www.nseindia.com"
        self.api_url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
        self.cached_iv = 15.0
        self.last_fetch_time = 0
        self.cache_ttl = 60

    def _refresh_cookies(self):
        try:
            self.session.get(self.base_url, timeout=5)
        except Exception as e:
            logging.warning(f"Failed to refresh NSE cookies: {e}")

    def get_atm_iv(self, current_spot: float) -> float:
        """Fetches the options chain, finds the ATM strike, and returns average IV of CE and PE."""
        if time.time() - self.last_fetch_time < self.cache_ttl:
            return self.cached_iv

        try:
            response = self.session.get(self.api_url, timeout=5)
            if response.status_code == 401:
                self._refresh_cookies()
                response = self.session.get(self.api_url, timeout=5)
            
            response.raise_for_status()
            data = response.json()
            
            records = data.get('records', {}).get('data', [])
            if not records:
                return self.cached_iv
                
            closest_strike_record = min(records, key=lambda x: abs(x.get('strikePrice', 0) - current_spot))
            
            ce_iv = closest_strike_record.get('CE', {}).get('impliedVolatility', 0)
            pe_iv = closest_strike_record.get('PE', {}).get('impliedVolatility', 0)
            
            valid_ivs = [iv for iv in (ce_iv, pe_iv) if iv > 0]
            avg_iv = sum(valid_ivs) / len(valid_ivs) if valid_ivs else self.cached_iv
            
            self.cached_iv = avg_iv
            self.last_fetch_time = time.time()
            logging.info(f"Fetched new ATM IV from NSE: {avg_iv:.2f}")
            return avg_iv

        except Exception as e:
            logging.error(f"Error fetching NSE Option Chain: {e}. Using cached IV: {self.cached_iv}")
            return self.cached_iv

# ==========================================
# VECTOR & REGRESSION ENGINE
# ==========================================
class VectorEngine:
    """Processes 4D candle vectors, maintains running accumulations, and fits Linear Regression."""
    
    def __init__(self):
        self.nse_api = NSEOptionsAPI()
        
        self.signed_accumulation = 0.0
        self.prev_candle: Optional[Dict[str, float]] = None
        self.prev_raw_scalar = 0.0
        self.prev_iv_adjusted = 0.0
        
        # Regression History: X = IV Adjusted Scalar, Y = Next Candle Nifty Point Move
        self.history_x = deque(maxlen=HISTORY_WINDOW)
        self.history_y = deque(maxlen=HISTORY_WINDOW)

    def process_candle(self, timestamp: str, high: float, low: float, open_p: float, close_p: float) -> Dict[str, Any]:
        vector = [high, low, open_p, close_p]
        
        # 1. Derive scalar: (Close - Open) / (High - Low)
        spread = high - low
        raw_scalar = (close_p - open_p) / spread if spread > 0 else 0.0
        
        # 2. IV Adjustment
        current_iv = self.nse_api.get_atm_iv(close_p)
        iv_adjusted_scalar = (raw_scalar / current_iv) * IV_SCALING_FACTOR

        m, b, predicted_move, confidence = 0.0, 0.0, 0.0, 0.0
        
        # 3. Process Logic based on "Next Candle" rule (Requires 1-step lag)
        is_green = close_p > open_p
        
        if self.prev_candle is not None:
            sign = 1.0 if is_green else -1.0
            self.signed_accumulation += (self.prev_raw_scalar * sign)
            
            actual_point_move = close_p - self.prev_candle['close']
            
            self.history_x.append(self.prev_iv_adjusted)
            self.history_y.append(actual_point_move)
            
            # 4. Fit Linear Regression (Y = MX + B) if we have enough data
            if len(self.history_x) >= 10:
                x_array = np.array(self.history_x)
                y_array = np.array(self.history_y)
                
                m, b = np.polyfit(x_array, y_array, 1)
                
                predicted_move = (m * iv_adjusted_scalar) + b
                
                correlation = np.corrcoef(x_array, y_array)[0, 1]
                confidence = round(abs(correlation) * 100, 2) if not np.isnan(correlation) else 0.0

        # Update state for next iteration
        self.prev_candle = {'open': open_p, 'high': high, 'low': low, 'close': close_p}
        self.prev_raw_scalar = raw_scalar
        self.prev_iv_adjusted = iv_adjusted_scalar

        # Determine Signal
        signal = "neutral"
        if predicted_move > SIGNAL_THRESHOLD:
            signal = "bullish"
        elif predicted_move < -SIGNAL_THRESHOLD:
            signal = "bearish"

        return {
            "timestamp": timestamp,
            "symbol": "NIFTY",
            "candle_vector": vector,
            "raw_scalar": round(raw_scalar, 4),
            "iv_adjusted_scalar": round(iv_adjusted_scalar, 6),
            "current_atm_iv": round(current_iv, 2),
            "signed_accumulation": round(self.signed_accumulation, 2),
            "predicted_next_move": round(predicted_move, 2),
            "linear_m": round(m, 4),
            "linear_b": round(b, 4),
            "confidence": confidence,
            "signal": signal
        }

# ==========================================
# RABBITMQ WORKER & LIFECYCLE
# ==========================================
class VectorMQWorker:
    def __init__(self):
        self.engine = VectorEngine()
        self.connection = None
        self.channel = None

    def connect(self):
        credentials = pika.PlainCredentials(RMQ_USER, RMQ_PASS)
        parameters = pika.ConnectionParameters(
            host=RMQ_HOST,
            credentials=credentials,
            heartbeat=60,
            blocked_connection_timeout=300
        )
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()

        # Use the platform's shared exchange
        self.channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)

        # Setup input queue
        self.channel.queue_declare(queue=QUEUE_IN, durable=True)
        self.channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_IN, routing_key=ROUTING_KEY_IN)
        self.channel.basic_qos(prefetch_count=1)

    def process_message(self, ch, method, properties, body):
        try:
            payload = json.loads(body)
            symbol = payload.get('symbol', 'UNKNOWN')
            
            # Only process NIFTY candles
            if symbol != 'NIFTY':
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            timestamp = payload.get('timestamp') or payload.get('Date')
            open_p = float(payload['open'] if 'open' in payload else payload['Open'])
            high = float(payload['high'] if 'high' in payload else payload['High'])
            low = float(payload['low'] if 'low' in payload else payload['Low'])
            close_p = float(payload['close'] if 'close' in payload else payload['Close'])

            # Run Vector Math & ML Model
            alert_data = self.engine.process_candle(timestamp, high, low, open_p, close_p)
            
            # Publish Vector Alert back to the shared exchange
            ch.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=ROUTING_KEY_OUT,
                body=json.dumps(alert_data),
                properties=pika.BasicProperties(delivery_mode=2, content_type='application/json')
            )
            
            logging.info(f"📐 Vector Alert: Signal={alert_data['signal']} | Pred_Move={alert_data['predicted_next_move']} | Confidence={alert_data['confidence']}%")
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logging.error(f"Error processing candle message: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def run(self):
        while True:
            try:
                logging.info("Connecting to RabbitMQ...")
                self.connect()
                logging.info(f"Connected. Listening on {QUEUE_IN} for candle data...")
                
                self.channel.basic_consume(queue=QUEUE_IN, on_message_callback=self.process_message)
                self.channel.start_consuming()
                
            except pika.exceptions.AMQPConnectionError as e:
                logging.warning(f"Connection lost, reconnecting in 5s... ({e})")
                time.sleep(5)
            except KeyboardInterrupt:
                logging.info("Shutting down Vector Agent gracefully...")
                if self.connection:
                    self.connection.close()
                break
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                time.sleep(5)

if __name__ == "__main__":
    worker = VectorMQWorker()
    worker.run()
