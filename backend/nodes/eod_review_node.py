"""
EOD Review Node — Compares today's recommendations vs actual outcomes.

Runs after market close. Fetches actual closing prices and computes
how each recommendation performed.
"""

import os
import logging
import psycopg2
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:EOD_REVIEW] - %(message)s')

DB_URL = os.getenv("DATABASE_URL")


def _get_conn():
    return psycopg2.connect(DB_URL)


def eod_review_node(state: dict) -> dict:
    """
    End-of-day performance review.

    For each accepted trade:
      - Fetch actual closing price
      - Compare vs entry/SL/target
      - Calculate actual P&L
      - Determine if prediction was correct

    For each skipped trade:
      - Fetch actual closing price
      - Determine if the skip was a missed opportunity

    Reads:
      - report_date
      - accepted_trades (from trade_journal DB)
      - skipped_trades

    Writes:
      - eod_results: list of {symbol, predicted, actual_pnl, was_correct, ...}
    """
    report_date = state.get("report_date")
    logging.info(f"📊 Running EOD Review for {report_date}...")

    eod_results = []

    try:
        conn = _get_conn()
        cur = conn.cursor()

        # Fetch today's trades from trade_journal
        cur.execute("""
            SELECT id, symbol, trade_type, entry_price, stoploss, target,
                   predicted_confidence, signals_used, status
            FROM trade_journal
            WHERE trade_date = %s
        """, (report_date,))

        trades = cur.fetchall()
        logging.info(f"  Found {len(trades)} trades for today")

        for trade in trades:
            trade_id = trade[0]
            symbol = trade[1]
            trade_type = trade[2]
            entry_price = trade[3]
            stoploss = trade[4]
            target = trade[5]
            predicted_confidence = trade[6]
            signals_used = trade[7]
            status = trade[8]

            # Get actual closing price
            try:
                yf_symbol = f"{symbol}.NS"
                ticker = yf.Ticker(yf_symbol)
                hist = ticker.history(period="1d")
                if not hist.empty:
                    actual_close = float(hist['Close'].iloc[-1])
                else:
                    logging.warning(f"  ⚠️ No EOD data for {symbol}")
                    continue
            except Exception:
                logging.warning(f"  ⚠️ Failed to fetch EOD price for {symbol}")
                continue

            # Calculate actual P&L
            is_long = "LONG" in trade_type or "CALL" in trade_type
            if is_long:
                actual_pnl_pct = round(((actual_close - entry_price) / entry_price) * 100, 2)
            else:
                actual_pnl_pct = round(((entry_price - actual_close) / entry_price) * 100, 2)

            # Determine predicted direction
            if "LONG" in trade_type or "CALL" in trade_type:
                predicted_direction = "BULLISH"
            else:
                predicted_direction = "BEARISH"

            was_correct = actual_pnl_pct > 0

            # Determine exit status
            if status == "OPEN":
                if stoploss and ((is_long and actual_close <= stoploss) or
                                 (not is_long and actual_close >= stoploss)):
                    exit_status = "SL_HIT"
                elif target and ((is_long and actual_close >= target) or
                                 (not is_long and actual_close <= target)):
                    exit_status = "TARGET_HIT"
                else:
                    exit_status = "SESSION_END"
            else:
                exit_status = status

            result = {
                "trade_id": trade_id,
                "symbol": symbol,
                "trade_type": trade_type,
                "entry_price": entry_price,
                "actual_close": actual_close,
                "actual_pnl_pct": actual_pnl_pct,
                "predicted_direction": predicted_direction,
                "predicted_confidence": predicted_confidence,
                "was_correct": was_correct,
                "exit_status": exit_status,
                "signals_used": signals_used if isinstance(signals_used, list) else [],
            }

            eod_results.append(result)

            status_emoji = "✅" if was_correct else "❌"
            logging.info(
                f"  {status_emoji} {symbol} ({trade_type}): "
                f"Entry ₹{entry_price} → Close ₹{actual_close} "
                f"| P&L: {actual_pnl_pct:+.2f}% | {exit_status}"
            )

            # Update trade_journal with actual results
            cur.execute("""
                UPDATE trade_journal
                SET exit_price = %s, actual_pnl_pct = %s, status = %s, exited_at = NOW()
                WHERE id = %s AND status = 'OPEN'
            """, (actual_close, actual_pnl_pct, exit_status, trade_id))

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        logging.error(f"  EOD review error: {e}")
        return {
            "eod_results": [],
            "errors": [f"eod_review_node: {str(e)}"],
        }

    # Summary
    if eod_results:
        wins = sum(1 for r in eod_results if r["was_correct"])
        total = len(eod_results)
        avg_pnl = sum(r["actual_pnl_pct"] for r in eod_results) / total
        logging.info(f"\n  ── EOD SUMMARY ──")
        logging.info(f"  Win Rate: {wins}/{total} ({wins/total:.0%})")
        logging.info(f"  Avg P&L: {avg_pnl:+.2f}%")
    else:
        logging.info("  No trades to review.")

    return {"eod_results": eod_results}
