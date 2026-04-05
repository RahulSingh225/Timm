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

def _get_spy_200_sma():
    import yfinance as yf
    try:
        spy = yf.Ticker("SPY")
        df = spy.history(period="1y")
        if not df.empty and len(df) >= 200:
            return df['Close'].rolling(200).mean().iloc[-1], df['Close'].iloc[-1]
    except Exception as e:
        logging.warning(f"Failed to fetch SPY data for SMA context: {e}")
    return None, None

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
    defense_mode = False

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
            raw_bias = row[0] or "NEUTRAL"
            context = {
                "overall_bias": raw_bias,
                "vix_value": row[1],
                "vix_change_pct": row[2],
                "spy_change_pct": row[3],
                "qqq_change_pct": row[4],
                "dji_change_pct": row[5],
                "gift_nifty": row[6],
                "usd_inr": row[7],
                "captured_at": str(row[8]) if row[8] else None,
            }
            vix = context["vix_value"]

            # Define advanced Market Regime explicitly for Critic and Agents
            spy_pct = context["spy_change_pct"] or 0
            
            if vix is not None and spy_pct is not None:
                if vix > 25 and spy_pct < -1.0:
                    market_regime = "BEARISH_HIGH_VOL"
                elif vix > 25 and spy_pct >= 0:
                    market_regime = "CHOPPY_HIGH_VOL"
                elif 15 <= vix <= 25 and abs(spy_pct) < 0.5:
                    market_regime = "CHOPPY"
                elif spy_pct > 0.5:
                    market_regime = "TRENDING_BULLISH"
                elif spy_pct < -0.5:
                    market_regime = "TRENDING_BEARISH"
                else:
                    market_regime = raw_bias
            else:
                market_regime = raw_bias
                
            # Compute SPY 200-SMA
            spy_sma, spy_close = _get_spy_200_sma()
            if spy_sma and spy_close and vix and vix > 30 and spy_close < spy_sma:
                defense_mode = True
                logging.info(f"  🛡️ DEFENSE MODE ACTIVATED: VIX={vix} (>30) and SPY ({spy_close:.2f}) < 200-SMA ({spy_sma:.2f})")
            elif spy_sma and spy_close:
                logging.info(f"  SPY 200-SMA context: Close={spy_close:.2f}, SMA={spy_sma:.2f}")

            logging.info(
                f"  Regime: {market_regime} (Raw: {raw_bias}) | VIX: {vix} "
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
            "defense_mode": False,
            "vix": None,
            "global_cues": context,
            "errors": [f"global_cues_node: {str(e)}"],
        }

    return {
        "market_regime": market_regime,
        "defense_mode": defense_mode,
        "vix": vix,
        "global_cues": context,
    }
