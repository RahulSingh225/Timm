"""
Candle Vector Agent v2.0

Processes 4D candle vectors for individual stocks (not just NIFTY).
- Derives scalar momentum from (Close-Open)/(High-Low)
- Tracks signed accumulation over time
- Fits linear regression for predictive move estimation
- Classifies vectors as accumulation/distribution
- Produces human-readable verdicts
"""

import os
import json
import time
import logging
import numpy as np
import pika
from collections import deque
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# CONFIGURATION
# ==========================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format='%(asctime)s - [VECTOR AGENT] - %(message)s')

RMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RMQ_USER = os.getenv("RABBITMQ_USER", "admin")
RMQ_PASS = os.getenv("RABBITMQ_PASS", "supersecretpassword")
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE", "market_data_exchange")
ROUTING_KEY_IN = "market.eod.*"
QUEUE_IN = os.getenv("VECTOR_QUEUE_IN", "candle_vector_queue")
ROUTING_KEY_OUT = "alert.vector"

HISTORY_WINDOW = int(os.getenv("HISTORY_WINDOW", "100"))
SIGNAL_THRESHOLD = float(os.getenv("SIGNAL_THRESHOLD", "2.0"))


# ==========================================
# MULTI-SYMBOL VECTOR ENGINE
# ==========================================
class MultiSymbolVectorEngine:
    """Maintains separate vector state per symbol."""

    def __init__(self):
        self.engines: Dict[str, SymbolEngine] = {}

    def get_engine(self, symbol: str) -> 'SymbolEngine':
        if symbol not in self.engines:
            self.engines[symbol] = SymbolEngine(symbol)
        return self.engines[symbol]


class SymbolEngine:
    """Processes 4D candle vectors for a single symbol."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.signed_accumulation = 0.0
        self.prev_candle: Optional[Dict[str, float]] = None
        self.prev_raw_scalar = 0.0

        # Regression History
        self.history_x = deque(maxlen=HISTORY_WINDOW)
        self.history_y = deque(maxlen=HISTORY_WINDOW)

        # Accumulation tracking
        self.consecutive_bullish = 0
        self.consecutive_bearish = 0

    def process_candle(self, timestamp: str, high: float, low: float,
                       open_p: float, close_p: float, volume: int = 0) -> Dict[str, Any]:

        vector = [high, low, open_p, close_p]

        # 1. Derive scalar: (Close - Open) / (High - Low)
        spread = high - low
        raw_scalar = (close_p - open_p) / spread if spread > 0 else 0.0

        # 2. Classify candle
        is_green = close_p > open_p
        body_pct = abs(close_p - open_p) / spread * 100 if spread > 0 else 0

        # 3. Track accumulation/distribution
        if is_green:
            self.consecutive_bullish += 1
            self.consecutive_bearish = 0
        else:
            self.consecutive_bearish += 1
            self.consecutive_bullish = 0

        m, b, predicted_move, confidence = 0.0, 0.0, 0.0, 0.0

        if self.prev_candle is not None:
            sign = 1.0 if is_green else -1.0
            self.signed_accumulation += (self.prev_raw_scalar * sign)

            actual_point_move = close_p - self.prev_candle['close']
            actual_pct_move = (actual_point_move / self.prev_candle['close'] * 100) if self.prev_candle['close'] > 0 else 0

            self.history_x.append(self.prev_raw_scalar)
            self.history_y.append(actual_pct_move)

            # 4. Fit Linear Regression
            if len(self.history_x) >= 10:
                x_array = np.array(self.history_x)
                y_array = np.array(self.history_y)

                m, b = np.polyfit(x_array, y_array, 1)
                predicted_move = (m * raw_scalar) + b

                correlation = np.corrcoef(x_array, y_array)[0, 1]
                confidence = round(abs(correlation) * 100, 2) if not np.isnan(correlation) else 0.0

        # Update state
        self.prev_candle = {'open': open_p, 'high': high, 'low': low, 'close': close_p}
        self.prev_raw_scalar = raw_scalar

        # 5. Determine Signal
        signal = "neutral"
        if predicted_move > SIGNAL_THRESHOLD:
            signal = "bullish"
        elif predicted_move < -SIGNAL_THRESHOLD:
            signal = "bearish"

        # 6. Classification
        if self.signed_accumulation > 5:
            classification = "ACCUMULATION"
        elif self.signed_accumulation < -5:
            classification = "DISTRIBUTION"
        else:
            classification = "NEUTRAL"

        # 7. Human-readable verdict
        verdict = self._build_verdict(signal, predicted_move, confidence, classification)

        return {
            "timestamp": timestamp,
            "symbol": self.symbol,
            "candle_vector": vector,
            "raw_scalar": round(raw_scalar, 4),
            "body_pct": round(body_pct, 1),
            "signed_accumulation": round(self.signed_accumulation, 2),
            "predicted_next_move_pct": round(predicted_move, 3),
            "linear_m": round(m, 4),
            "linear_b": round(b, 4),
            "confidence": confidence,
            "signal": signal,
            "classification": classification,
            "consecutive_bullish": self.consecutive_bullish,
            "consecutive_bearish": self.consecutive_bearish,
            "verdict": verdict,
        }

    def _build_verdict(self, signal: str, predicted_move: float, confidence: float, classification: str) -> str:
        """Generate a human-readable analysis verdict."""
        parts = []

        # Classification
        if classification == "ACCUMULATION":
            parts.append(f"Accumulation phase detected (score: {self.signed_accumulation:.1f})")
        elif classification == "DISTRIBUTION":
            parts.append(f"Distribution phase detected (score: {self.signed_accumulation:.1f})")

        # Consecutive candles
        if self.consecutive_bullish >= 3:
            parts.append(f"{self.consecutive_bullish} consecutive bullish candles")
        elif self.consecutive_bearish >= 3:
            parts.append(f"{self.consecutive_bearish} consecutive bearish candles")

        # Prediction
        if confidence >= 30:
            direction = "upside" if predicted_move > 0 else "downside"
            parts.append(f"Regression predicts {abs(predicted_move):.2f}% {direction} (confidence: {confidence:.0f}%)")

        if not parts:
            parts.append("No strong vector pattern detected")

        return ". ".join(parts) + "."


# ==========================================
# RABBITMQ WORKER
# ==========================================
class VectorMQWorker:
    def __init__(self):
        self.engine = MultiSymbolVectorEngine()
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

        self.channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=QUEUE_IN, durable=True)
        self.channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_IN, routing_key=ROUTING_KEY_IN)
        self.channel.basic_qos(prefetch_count=1)

    def process_message(self, ch, method, properties, body):
        try:
            payload = json.loads(body)
            symbol = payload.get('symbol', 'UNKNOWN')
            data_list = payload.get('data', [])

            if not data_list:
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            # Process the LAST candle in the batch (most recent)
            # But feed all candles through the engine for history
            sym_engine = self.engine.get_engine(symbol)
            alert_data = None

            for candle in data_list[-50:]:  # Last 50 candles for regression window
                ts = candle.get('Date') or candle.get('timestamp', '')
                open_p = float(candle.get('Open', candle.get('open', 0)))
                high = float(candle.get('High', candle.get('high', 0)))
                low = float(candle.get('Low', candle.get('low', 0)))
                close_p = float(candle.get('Close', candle.get('close', 0)))
                vol = int(candle.get('Volume', candle.get('volume', 0)))

                alert_data = sym_engine.process_candle(ts, high, low, open_p, close_p, vol)

            if alert_data and alert_data['signal'] != 'neutral':
                # Publish vector alert
                ch.basic_publish(
                    exchange=EXCHANGE_NAME,
                    routing_key=f"{ROUTING_KEY_OUT}.{symbol}",
                    body=json.dumps(alert_data, default=str),
                    properties=pika.BasicProperties(delivery_mode=2, content_type='application/json')
                )
                logging.info(
                    f"📐 {symbol}: {alert_data['signal'].upper()} | "
                    f"Pred: {alert_data['predicted_next_move_pct']:+.2f}% | "
                    f"Conf: {alert_data['confidence']:.0f}% | "
                    f"{alert_data['classification']}"
                )
            else:
                if alert_data:
                    logging.info(f"   {symbol}: {alert_data['classification']} | Pred: {alert_data['predicted_next_move_pct']:+.2f}% (below threshold)")

            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logging.error(f"Error processing vector for {payload.get('symbol', '???')}: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def run(self):
        while True:
            try:
                logging.info("Connecting to RabbitMQ...")
                self.connect()
                logging.info(f"📐 Vector Agent v2.0 online. Listening on {QUEUE_IN} for ALL symbols...")

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
