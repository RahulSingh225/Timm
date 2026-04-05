"""
Temporal Context Node — Loads the system's own performance history.

This is what makes the system self-aware: before analyzing today's data,
it checks how each signal type has performed historically, and loads the
adjusted confidence weights from the strategy_weights table.
"""

import os
import logging
import psycopg2
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:TEMPORAL] - %(message)s')

DB_URL = os.getenv("DATABASE_URL")


def _get_conn():
    return psycopg2.connect(DB_URL)


def temporal_context_node(state: dict) -> dict:
    """
    Load historical performance data to inform today's analysis.

    Reads:
      - strategy_weights table: per-signal confidence multipliers
      - learning_history table: recent performance by regime + trade type

    Writes:
      - strategy_weights: {signal_type: {weight, win_rate, sample_size}}
      - recent_performance: {regime_tradetype: {win_rate, avg_win_pnl, avg_loss_pnl}}
    """
    logging.info("🧠 Loading temporal context (past performance + learned weights)...")

    weights = {}
    recent = {}

    try:
        conn = _get_conn()
        cur = conn.cursor()

        # ── Strategy Weights ──────────────────────────────────
        # Check if the table exists first (may not yet on first run)
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'strategy_weights'
            )
        """)
        table_exists = cur.fetchone()[0]

        if table_exists:
            cur.execute("""
                SELECT signal_type, base_weight, user_override, win_count, loss_count,
                       avg_pnl_when_correct, avg_pnl_when_wrong
                FROM strategy_weights
            """)
            for row in cur.fetchall():
                signal_type = row[0]
                effective_weight = row[2] if row[2] is not None else row[1]  # user_override takes priority
                total = (row[3] or 0) + (row[4] or 0)
                win_rate = (row[3] or 0) / total if total > 0 else 0.5

                weights[signal_type] = {
                    "weight": effective_weight,
                    "win_rate": round(win_rate, 3),
                    "sample_size": total,
                    "avg_win_pnl": row[5],
                    "avg_loss_pnl": row[6],
                }

            if weights:
                logging.info(f"  Loaded {len(weights)} signal weights from history")
                # Log top/bottom performers
                sorted_w = sorted(weights.items(), key=lambda x: x[1]["weight"], reverse=True)
                if len(sorted_w) >= 2:
                    best = sorted_w[0]
                    worst = sorted_w[-1]
                    logging.info(
                        f"  Best signal: {best[0]} (weight={best[1]['weight']:.2f}, "
                        f"win_rate={best[1]['win_rate']:.0%})"
                    )
                    logging.info(
                        f"  Worst signal: {worst[0]} (weight={worst[1]['weight']:.2f}, "
                        f"win_rate={worst[1]['win_rate']:.0%})"
                    )
            else:
                logging.info("  No strategy weights yet (first run). Using defaults.")
        else:
            logging.info("  strategy_weights table not found. First run — using defaults.")

        # ── Recent Performance by Regime + Trade Type ─────────
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'learning_history'
            )
        """)
        lh_exists = cur.fetchone()[0]

        if lh_exists:
            cur.execute("""
                SELECT
                    market_regime,
                    trade_type,
                    COUNT(*) FILTER (WHERE was_correct = TRUE) AS wins,
                    COUNT(*) FILTER (WHERE was_correct = FALSE) AS losses,
                    AVG(actual_pnl_pct) FILTER (WHERE was_correct = TRUE) AS avg_win,
                    AVG(actual_pnl_pct) FILTER (WHERE was_correct = FALSE) AS avg_loss
                FROM learning_history
                WHERE trade_date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY market_regime, trade_type
            """)
            for row in cur.fetchall():
                regime = row[0] or "UNKNOWN"
                trade_type = row[1] or "UNKNOWN"
                key = f"{regime}_{trade_type}"
                total = (row[2] or 0) + (row[3] or 0)

                recent[key] = {
                    "win_rate": round((row[2] or 0) / total, 3) if total > 0 else 0.5,
                    "avg_win_pnl": round(row[4], 2) if row[4] else None,
                    "avg_loss_pnl": round(row[5], 2) if row[5] else None,
                    "total_trades": total,
                }

            if recent:
                logging.info(f"  Loaded performance data for {len(recent)} regime/type combos")
        else:
            logging.info("  learning_history table not found. First run — no historical context.")

        cur.close()
        conn.close()

    except Exception as e:
        logging.warning(f"  Failed to load temporal context (non-fatal): {e}")
        # Non-fatal — graph continues with empty weights
        return {
            "strategy_weights": {},
            "recent_performance": {},
        }

    return {
        "strategy_weights": weights,
        "recent_performance": recent,
    }
