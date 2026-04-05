"""
FII/DII Context Node — Fetches institutional flows + sector rotation data from DB.
"""

import os
import logging
import psycopg2
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:FII_DII] - %(message)s')

DB_URL = os.getenv("DATABASE_URL")


def _get_conn():
    return psycopg2.connect(DB_URL)


def fii_dii_node(state: dict) -> dict:
    """
    Fetch latest FII/DII cash flows and top sector allocations from DB.

    Writes:
      - fii_net: formatted string like "+2340 Cr"
      - dii_net: formatted string
      - sector_leaders: list of {sector, net_cr}
    """
    logging.info("💰 Fetching FII/DII flows and sector data from DB...")

    fii_net = None
    dii_net = None
    sectors = []

    try:
        conn = _get_conn()
        cur = conn.cursor()

        # FII/DII flows
        cur.execute("""
            SELECT fii_net_cash, dii_net_cash, pcr, sentiment_score, trade_date
            FROM fii_dii_flows
            ORDER BY trade_date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            fii_val = row[0]
            dii_val = row[1]
            fii_net = f"{'+' if fii_val and fii_val > 0 else ''}{fii_val} Cr" if fii_val else None
            dii_net = f"{'+' if dii_val and dii_val > 0 else ''}{dii_val} Cr" if dii_val else None
            logging.info(f"  FII: {fii_net} | DII: {dii_net} | PCR: {row[2]} | Date: {row[4]}")

        # Top sectors by FII flow
        cur.execute("""
            SELECT sector_name, net_investment_cr
            FROM sector_flows
            WHERE trade_date = (SELECT MAX(trade_date) FROM sector_flows)
            ORDER BY net_investment_cr DESC
            LIMIT 5
        """)
        sectors = [{"sector": r[0], "net_cr": r[1]} for r in cur.fetchall()]
        if sectors:
            logging.info(f"  Top sectors: {', '.join(s['sector'] for s in sectors[:3])}")

        cur.close()
        conn.close()

    except Exception as e:
        logging.error(f"  Failed to fetch FII/DII data: {e}")
        return {
            "fii_net": None,
            "dii_net": None,
            "sector_leaders": [],
            "errors": [f"fii_dii_node: {str(e)}"],
        }

    return {
        "fii_net": fii_net,
        "dii_net": dii_net,
        "sector_leaders": sectors,
    }
