"""
Vector Analysis Node — Runs 4D candle vector momentum analysis.

Wraps the existing SymbolEngine from candle_vector_agent.py.
Processes historical candles to detect accumulation/distribution patterns.
"""

import os
import json
import pika
import psycopg2
import logging
import yfinance as yf
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:VECTOR] - %(message)s')

DB_URL = os.getenv("DATABASE_URL")
RABBIT_URL = os.getenv("RABBITMQ_URL")

# ... (I'll keep the functions here but I need to replace the loop)

def _get_db_conn():
    return psycopg2.connect(DB_URL)

def _publish_vector_signal(symbol: str, result: dict):
    """Publish the signal to RabbitMQ for real-time dashboard updates."""
    try:
        params = pika.URLParameters(RABBIT_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        
        exchange = 'market_data_exchange'
        channel.exchange_declare(exchange=exchange, exchange_type='topic', durable=True)
        
        # Format for frontend VectorLab consumption
        payload = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "raw_scalar": result.get("raw_scalar"),
            "iv_adjusted_scalar": result.get("iv_adjusted_scalar"),
            "current_atm_iv": result.get("current_atm_iv", 0),
            "signed_accumulation": result.get("signed_accumulation", 0),
            "predicted_next_move": result.get("predicted_next_move_pct", 0),
            "linear_m": result.get("linear_m", 0),
            "linear_b": result.get("linear_b", 0),
            "confidence": result.get("confidence", 0),
            "signal": result.get("signal", "neutral")
        }
        
        channel.basic_publish(
            exchange=exchange,
            routing_key='candle.vector',
            body=json.dumps(payload)
        )
        connection.close()
    except Exception as e:
        logging.warning(f"  [VECTOR:MQ] Failed to publish signal for {symbol}: {e}")

def _persist_vector_signal(symbol: str, result: dict):
    """Save the signal to the vector_signals table for historical explorer."""
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO vector_signals (
                symbol, timestamp, raw_scalar, iv_adjusted_scalar, 
                current_atm_iv, signed_accumulation, predicted_next_move,
                linear_m, linear_b, confidence, signal, created_at
            ) VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (symbol, timestamp) DO UPDATE SET
                raw_scalar = EXCLUDED.raw_scalar,
                confidence = EXCLUDED.confidence,
                signal = EXCLUDED.signal
        """, (
            symbol,
            result.get("raw_scalar"),
            result.get("iv_adjusted_scalar"),
            result.get("current_atm_iv", 0),
            result.get("signed_accumulation", 0),
            result.get("predicted_next_move_pct", 0),
            result.get("linear_m", 0),
            result.get("linear_b", 0),
            result.get("confidence", 0),
            result.get("signal", "neutral")
        ))
        
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.warning(f"  [VECTOR:DB] Failed to persist signal for {symbol}: {e}")

# Import the existing engine
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from candle_vector_agent import SymbolEngine


def vector_analysis_node(state: dict) -> dict:
    """
    Run vector analysis on all watchlist symbols.

    Uses the SymbolEngine to process recent candles and detect
    accumulation/distribution patterns via linear regression.

    Reads:
      - watchlist: list of symbols

    Writes:
      - vector_analyses: {symbol: vector_report}
      - all_evidence: evidence entries from vector analysis
    """
    watchlist = state.get("watchlist", [])
    if not watchlist:
        logging.warning("No watchlist symbols — skipping vector analysis.")
        return {"vector_analyses": {}, "all_evidence": []}

    logging.info(f"📐 Running Vector Analysis on {len(watchlist)} symbols...")

    analyses = {}
    evidence = []

    for i, symbol in enumerate(watchlist):
        try:
            # Handle Yahoo Finance symbol mappings (Indices vs Stocks)
            if symbol == "NIFTY":
                yf_symbol = "^NSEI"
            elif symbol == "BANKNIFTY":
                yf_symbol = "^NSEBANK"
            elif symbol == "SENSEX":
                yf_symbol = "^BSESN"
            else:
                yf_symbol = f"{symbol}.NS"

            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period="3mo", interval="1d")

            if df.empty or len(df) < 20:
                continue

            # Create a fresh engine per symbol and feed candles through it
            engine = SymbolEngine(symbol)
            result = None

            # Feed last 50 candles for regression window
            for _, row in df.tail(50).iterrows():
                ts = str(row.name.date()) if hasattr(row.name, 'date') else str(row.name)
                result = engine.process_candle(
                    timestamp=ts,
                    high=float(row['High']),
                    low=float(row['Low']),
                    open_p=float(row['Open']),
                    close_p=float(row['Close']),
                    volume=int(row['Volume']),
                )

            if result:
                analyses[symbol] = result

                # 💡 REVITALIZE VECTOR LAB: Persist and Publish
                _persist_vector_signal(symbol, result)
                _publish_vector_signal(symbol, result)

                if result.get("signal", "neutral") != "neutral":
                    logging.info(
                        f"  [{i + 1}/{len(watchlist)}] {symbol}: "
                        f"{result['signal'].upper()} | "
                        f"Pred: {result['predicted_next_move_pct']:+.2f}% | "
                        f"Conf: {result['confidence']:.0f}% | "
                        f"{result['classification']}"
                    )

                    evidence.append({
                        "node": "vector",
                        "symbol": symbol,
                        "signal": result["signal"],
                        "classification": result["classification"],
                        "predicted_move_pct": result["predicted_next_move_pct"],
                        "confidence": result["confidence"],
                        "verdict": result.get("verdict", ""),
                        "consecutive_bullish": result.get("consecutive_bullish", 0),
                        "consecutive_bearish": result.get("consecutive_bearish", 0),
                    })

        except Exception as e:
            logging.error(f"  ❌ {symbol}: Vector analysis error: {e}")
            continue

    logging.info(f"  Vector analysis complete: {len(analyses)} symbols processed, "
                 f"{len(evidence)} produced signals")

    return {
        "vector_analyses": analyses,
        "all_evidence": evidence,
    }
