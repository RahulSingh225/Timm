"""
Self-Learning Node — Updates strategy weights based on trade outcomes.

After the EOD review scores each trade, this node:
  1. Tracks per-signal accuracy in learning_history
  2. Adjusts confidence multipliers in strategy_weights
  3. Learns which signals work in which market regime

Weight adjustment rules:
  - Win rate > 60% → increase weight by 0.05 (max 2.0)
  - Win rate < 40% → decrease weight by 0.05 (min 0.3)
  - User overrides always take priority over learned weights
"""

import os
import re
import logging
import psycopg2
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:SELF_LEARN] - %(message)s')

DB_URL = os.getenv("DATABASE_URL")

# Same patterns as screener_node
SIGNAL_TYPE_PATTERNS = {
    "GOLDEN_CROSS": r"GOLDEN CROSS",
    "DEATH_CROSS": r"DEATH CROSS",
    "EMA_RECLAIM": r"EMA RECLAIM",
    "FAST_EMA_CROSS_BULL": r"FAST EMA CROSS.*Bullish",
    "FAST_EMA_CROSS_BEAR": r"FAST EMA CROSS.*Bearish",
    "RSI_BOUNCE": r"RSI BOUNCE",
    "RSI_MOMENTUM": r"RSI MOMENTUM",
    "RSI_OVERBOUGHT": r"RSI OVERBOUGHT",
    "MACD_BULLISH": r"MACD BULLISH",
    "MACD_BEARISH": r"MACD BEARISH",
    "BB_SQUEEZE": r"BB SQUEEZE",
    "BB_REVERSAL": r"BB REVERSAL",
    "BB_BREAKOUT": r"BB BREAKOUT",
    "VOLUME_SPIKE": r"VOLUME SPIKE|MASSIVE VOLUME",
}


def _extract_signal_type(signal_text: str) -> str:
    """Extract canonical signal type from a signal description."""
    for sig_type, pattern in SIGNAL_TYPE_PATTERNS.items():
        if re.search(pattern, signal_text, re.IGNORECASE):
            return sig_type
    return "OTHER"


def _get_conn():
    return psycopg2.connect(DB_URL)


def self_learning_node(state: dict) -> dict:
    """
    Update strategy weights based on today's trade outcomes.

    Reads:
      - eod_results: from eod_review_node
      - report_date, market_regime, vix

    Writes:
      - learning_updates: list of weight adjustments made
    """
    eod_results = state.get("eod_results", [])
    report_date = state.get("report_date")
    market_regime = state.get("market_regime", "NEUTRAL")
    vix = state.get("vix")

    if not eod_results:
        logging.info("No EOD results to learn from. Skipping.")
        return {"learning_updates": []}

    logging.info(f"🧠 Self-learning from {len(eod_results)} trade outcomes...")

    learnings = []

    try:
        conn = _get_conn()
        cur = conn.cursor()

        # Ensure tables exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS learning_history (
                id SERIAL PRIMARY KEY,
                trade_date DATE NOT NULL,
                signal_type VARCHAR(100) NOT NULL,
                predicted_direction VARCHAR(10),
                was_correct BOOLEAN,
                actual_pnl_pct REAL,
                market_regime VARCHAR(20),
                vix_at_time REAL,
                trade_type VARCHAR(30),
                session_type VARCHAR(20),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS strategy_weights (
                id SERIAL PRIMARY KEY,
                signal_type VARCHAR(100) UNIQUE NOT NULL,
                base_weight REAL DEFAULT 1.0,
                user_override REAL,
                win_count INTEGER DEFAULT 0,
                loss_count INTEGER DEFAULT 0,
                avg_pnl_when_correct REAL,
                avg_pnl_when_wrong REAL,
                last_updated TIMESTAMP DEFAULT NOW()
            )
        """)

        for result in eod_results:
            predicted_direction = result["predicted_direction"]
            actual_pnl = result["actual_pnl_pct"]
            was_correct = result["was_correct"]
            trade_type = result.get("trade_type", "INTRADAY")
            signals_used = result.get("signals_used", [])

            for signal_text in signals_used:
                signal_type = _extract_signal_type(signal_text)

                # ── 1. Insert into learning_history ──────────
                cur.execute("""
                    INSERT INTO learning_history
                    (trade_date, signal_type, predicted_direction, was_correct,
                     actual_pnl_pct, market_regime, vix_at_time, trade_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    report_date, signal_type, predicted_direction,
                    was_correct, actual_pnl, market_regime, vix, trade_type
                ))

                # ── 2. Update strategy_weights ───────────────
                if was_correct:
                    cur.execute("""
                        INSERT INTO strategy_weights (signal_type, win_count, base_weight)
                        VALUES (%s, 1, 1.0)
                        ON CONFLICT (signal_type) DO UPDATE SET
                            win_count = strategy_weights.win_count + 1,
                            avg_pnl_when_correct = COALESCE(
                                (strategy_weights.avg_pnl_when_correct * strategy_weights.win_count + %s)
                                / (strategy_weights.win_count + 1),
                                %s
                            ),
                            base_weight = CASE
                                WHEN strategy_weights.user_override IS NOT NULL
                                    THEN strategy_weights.base_weight
                                WHEN (strategy_weights.win_count + 1.0) /
                                     NULLIF(strategy_weights.win_count + strategy_weights.loss_count + 1, 0) > 0.6
                                    THEN LEAST(strategy_weights.base_weight + 0.05, 2.0)
                                ELSE strategy_weights.base_weight
                            END,
                            last_updated = NOW()
                    """, (signal_type, actual_pnl, actual_pnl))
                else:
                    cur.execute("""
                        INSERT INTO strategy_weights (signal_type, loss_count, base_weight)
                        VALUES (%s, 1, 1.0)
                        ON CONFLICT (signal_type) DO UPDATE SET
                            loss_count = strategy_weights.loss_count + 1,
                            avg_pnl_when_wrong = COALESCE(
                                (strategy_weights.avg_pnl_when_wrong * strategy_weights.loss_count + %s)
                                / (strategy_weights.loss_count + 1),
                                %s
                            ),
                            base_weight = CASE
                                WHEN strategy_weights.user_override IS NOT NULL
                                    THEN strategy_weights.base_weight
                                WHEN (strategy_weights.win_count::float) /
                                     NULLIF(strategy_weights.win_count + strategy_weights.loss_count + 1, 0) < 0.4
                                    THEN GREATEST(strategy_weights.base_weight - 0.05, 0.3)
                                ELSE strategy_weights.base_weight
                            END,
                            last_updated = NOW()
                    """, (signal_type, actual_pnl, actual_pnl))

                learnings.append({
                    "signal_type": signal_type,
                    "was_correct": was_correct,
                    "actual_pnl": actual_pnl,
                    "trade_type": trade_type,
                    "market_regime": market_regime,
                })

        conn.commit()

        # ── 3. Log final weight state ────────────────────────
        cur.execute("""
            SELECT signal_type, base_weight, win_count, loss_count
            FROM strategy_weights
            ORDER BY base_weight DESC
        """)
        logging.info(f"\n  ── UPDATED STRATEGY WEIGHTS ──")
        for row in cur.fetchall():
            total = (row[2] or 0) + (row[3] or 0)
            wr = (row[2] or 0) / total if total > 0 else 0
            emoji = "🟢" if row[1] >= 1.1 else "🔴" if row[1] <= 0.9 else "⚪"
            logging.info(
                f"  {emoji} {row[0]}: weight={row[1]:.2f} | "
                f"W/L={row[2] or 0}/{row[3] or 0} ({wr:.0%})"
            )

        cur.close()
        conn.close()

    except Exception as e:
        logging.error(f"  Self-learning error: {e}")
        return {
            "learning_updates": [],
            "errors": [f"self_learning_node: {str(e)}"],
        }

    logging.info(f"  ✅ Recorded {len(learnings)} signal-level learnings")

    return {"learning_updates": learnings}
