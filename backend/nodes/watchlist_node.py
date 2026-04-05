"""
Watchlist Node — Loads active symbols from the watchlist table.
"""

import os
import logging
import psycopg2
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:WATCHLIST] - %(message)s')

DB_URL = os.getenv("DATABASE_URL")


def _get_conn():
    return psycopg2.connect(DB_URL)


def watchlist_node(state: dict) -> dict:
    """
    Fetch active watchlist symbols from DB.

    Writes:
      - watchlist: list of symbol strings
    """
    logging.info("📋 Loading active watchlist from DB...")

    symbols = []

    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM watchlist WHERE is_active = TRUE ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()

        logging.info(f"  Loaded {len(symbols)} symbols: {', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}")

    except Exception as e:
        logging.error(f"  Failed to fetch watchlist: {e}")
        return {
            "watchlist": [],
            "errors": [f"watchlist_node: {str(e)}"],
        }

    if not symbols:
        logging.warning("  ⚠️ No active symbols in watchlist!")
        return {
            "watchlist": [],
            "errors": ["watchlist_node: No active symbols found in watchlist table"],
        }

    return {"watchlist": symbols}
