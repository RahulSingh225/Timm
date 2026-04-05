"""
Options Analysis Node — Runs options chain analysis on watchlist symbols.

Wraps the existing analyze_option_chain() from options_agent_worker.py.
Supports NIFTY, SENSEX, and individual stock options.
"""

import logging
import yfinance as yf

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:OPTIONS] - %(message)s')

# Import the existing analysis function
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from options_agent_worker import analyze_option_chain


# Symbols that always get options analysis (index options)
INDEX_OPTIONS_SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]


def options_analysis_node(state: dict) -> dict:
    """
    Run options chain analysis on index options + high-confidence stocks.

    Reads:
      - watchlist: list of symbols
      - swing_analyses: to determine which stocks warrant options analysis

    Writes:
      - options_analyses: {symbol: options_report}
      - all_evidence: evidence entries from options analysis
    """
    watchlist = state.get("watchlist", [])
    swing_analyses = state.get("swing_analyses", {})

    logging.info(f"📊 Running Options Analysis...")

    analyses = {}
    evidence = []

    # Build symbols list: index options always + stocks with swing confidence >= 40
    symbols_to_analyze = []

    # Always analyze index options
    for idx_sym in INDEX_OPTIONS_SYMBOLS:
        if idx_sym not in symbols_to_analyze:
            symbols_to_analyze.append(idx_sym)

    # Add stocks that have decent swing signals
    for symbol in watchlist:
        swing = swing_analyses.get(symbol)
        if swing and swing.get("confidence", 0) >= 40:
            if symbol not in symbols_to_analyze:
                symbols_to_analyze.append(symbol)

    logging.info(f"  Analyzing options for {len(symbols_to_analyze)} symbols: {', '.join(symbols_to_analyze[:8])}...")

    for i, symbol in enumerate(symbols_to_analyze):
        logging.info(f"  [{i + 1}/{len(symbols_to_analyze)}] {symbol}...")

        try:
            # Get current price
            swing = swing_analyses.get(symbol)
            if swing and swing.get("close_price"):
                current_price = swing["close_price"]
            else:
                # Fetch price if not in swing analyses (e.g., index symbols)
                if symbol == "NIFTY":
                    yf_symbol = "^NSEI"
                elif symbol == "BANKNIFTY":
                    yf_symbol = "^NSEBANK"
                elif symbol == "SENSEX":
                    yf_symbol = "^BSESN"
                else:
                    yf_symbol = f"{symbol}.NS"

                ticker = yf.Ticker(yf_symbol)
                hist = ticker.history(period="5d")
                if hist.empty:
                    logging.warning(f"    ⚠️ {symbol}: No price data")
                    continue
                current_price = float(hist['Close'].iloc[-1])

            result = analyze_option_chain(symbol, current_price)

            if result and result.get("signals"):
                analyses[symbol] = result
                logging.info(
                    f"    ✅ {symbol}: {result.get('verdict')} | "
                    f"Max Pain: ₹{result.get('max_pain')} | "
                    f"PCR: {result.get('pcr_volume')} | "
                    f"Expected Move: ±{result.get('expected_move_pct')}%"
                )

                evidence.append({
                    "node": "options",
                    "symbol": symbol,
                    "verdict": result.get("verdict"),
                    "max_pain": result.get("max_pain"),
                    "call_wall": result.get("call_wall"),
                    "put_wall": result.get("put_wall"),
                    "pcr_volume": result.get("pcr_volume"),
                    "expected_move_pct": result.get("expected_move_pct"),
                    "signals": result.get("signals", []),
                })
            else:
                logging.info(f"    — {symbol}: No actionable options data")

        except Exception as e:
            logging.error(f"    ❌ {symbol}: Options analysis error: {e}")
            continue

    logging.info(f"  Options analysis complete: {len(analyses)}/{len(symbols_to_analyze)} symbols")

    return {
        "options_analyses": analyses,
        "all_evidence": evidence,
    }
