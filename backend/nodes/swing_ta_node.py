"""
Swing TA Node — Runs swing technical analysis on every watchlist symbol.

Wraps the existing analyze_swing_setups() from swing_agent_ta.py.
Fetches 1-year daily data via yfinance and produces structured reports.
"""

import logging
import yfinance as yf

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:SWING_TA] - %(message)s')

# Import the existing analysis function (preserved, not rewritten)
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from swing_agent_ta import analyze_swing_setups


def swing_ta_node(state: dict) -> dict:
    """
    Run swing technical analysis on all watchlist symbols.

    Reads:
      - watchlist: list of symbol strings

    Writes:
      - swing_analyses: {symbol: analysis_report}
      - all_evidence: evidence entries from swing analysis
    """
    watchlist = state.get("watchlist", [])
    if not watchlist:
        logging.warning("No watchlist symbols — skipping swing analysis.")
        return {"swing_analyses": {}, "all_evidence": []}

    logging.info(f"📊 Running Swing TA on {len(watchlist)} symbols...")

    analyses = {}
    evidence = []

    for i, symbol in enumerate(watchlist):
        logging.info(f"  [{i + 1}/{len(watchlist)}] {symbol}...")

        try:
            yf_symbol = f"{symbol}.NS"
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period="1y", interval="1d")

            if df.empty or len(df) < 200:
                logging.warning(f"    ⚠️ {symbol}: Insufficient data ({len(df)} candles, need 200+)")
                continue

            report = analyze_swing_setups(df, symbol)

            if report:
                analyses[symbol] = report
                sig_count = len(report.get("signals", []))
                confidence = report.get("confidence", 0)

                logging.info(
                    f"    ✅ {symbol}: {report.get('signal_type', 'NEUTRAL')} | "
                    f"{sig_count} signals | confidence={confidence}%"
                )

                # Add evidence for this symbol
                evidence.append({
                    "node": "swing_ta",
                    "symbol": symbol,
                    "signal_type": report.get("signal_type"),
                    "confidence": confidence,
                    "signals": report.get("signals", []),
                    "trend": report.get("trend", {}),
                    "trade_idea": report.get("trade_idea"),
                })
            else:
                logging.info(f"    — {symbol}: No actionable signals")

        except Exception as e:
            logging.error(f"    ❌ {symbol}: Swing analysis error: {e}")
            continue

    logging.info(f"  Swing TA complete: {len(analyses)}/{len(watchlist)} symbols produced signals")

    return {
        "swing_analyses": analyses,
        "all_evidence": evidence,
    }
