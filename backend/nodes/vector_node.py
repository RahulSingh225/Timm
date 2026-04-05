"""
Vector Analysis Node — Runs 4D candle vector momentum analysis.

Wraps the existing SymbolEngine from candle_vector_agent.py.
Processes historical candles to detect accumulation/distribution patterns.
"""

import logging
import yfinance as yf

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:VECTOR] - %(message)s')

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
