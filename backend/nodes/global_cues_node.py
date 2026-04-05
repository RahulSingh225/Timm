"""
Global Cues Node — Fetches latest global market context from DB.

Reads the most recent row from the global_cues table (populated by
global_cues_producer.py via RabbitMQ → DB Vault).
"""

import os
import logging
import psycopg2
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:GLOBAL_CUES] - %(message)s')

DB_URL = os.getenv("DATABASE_URL")


def _get_conn():
    return psycopg2.connect(DB_URL)


def global_cues_node(state: dict) -> dict:
    """
    Fetch the latest global cues from DB and determine market regime.

    Writes:
      - market_regime: RISK_ON / RISK_OFF / NEUTRAL
      - vix: float
      - global_cues: full context dict
    """
    logging.info("🌍 Fetching global market cues from DB...")

    context = {
        "overall_bias": "NEUTRAL",
        "vix_value": None,
        "vix_change_pct": None,
        "spy_change_pct": None,
        "qqq_change_pct": None,
        "dji_change_pct": None,
        "gift_nifty": None,
        "usd_inr": None,
        "captured_at": None,
    }
    market_regime = "NEUTRAL"
    vix = None

    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT overall_bias, vix_value, vix_change_pct, spy_change_pct,
                   qqq_change_pct, dji_change_pct, gift_nifty, usd_inr, captured_at
            FROM global_cues
            ORDER BY captured_at DESC
            LIMIT 1
        """)
        row = cur.fetchone()

        if row:
            context = {
                "overall_bias": row[0] or "NEUTRAL",
                "vix_value": row[1],
                "vix_change_pct": row[2],
                "spy_change_pct": row[3],
                "qqq_change_pct": row[4],
                "dji_change_pct": row[5],
                "gift_nifty": row[6],
                "usd_inr": row[7],
                "captured_at": str(row[8]) if row[8] else None,
            }
            market_regime = context["overall_bias"]
            vix = context["vix_value"]

            logging.info(
                f"  Regime: {market_regime} | VIX: {vix} "
                f"| SPY: {context['spy_change_pct']}% | GIFT Nifty: {context['gift_nifty']}"
            )
        else:
            logging.warning("  No global cues data found in DB. Using defaults.")

        cur.close()
        conn.close()

    except Exception as e:
        logging.error(f"  Failed to fetch global cues: {e}")
        return {
            "market_regime": "NEUTRAL",
            "vix": None,
            "global_cues": context,
            "errors": [f"global_cues_node: {str(e)}"],
        }

    return {
        "market_regime": market_regime,
        "vix": vix,
        "global_cues": context,
    }
