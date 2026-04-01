"""
Daily Report Generator — Batch Intelligence Orchestrator

Runs all agents in batch mode across the watchlist and produces
a consolidated JSON report stored in the daily_reports table.

Can be triggered:
- Manually from dashboard ("Run Now" button)
- Automatically by scheduler (post-market @ 16:30 IST)

Flow:
1. Fetch active watchlist from DB
2. Fetch latest global cues + FII/DII context
3. Run Swing TA analysis on every symbol
4. Run Options analysis on top candidates (confidence > 40)
5. Combine into structured report
6. Rank top picks by confidence
7. (Optional) Generate LLM brief via Head Analyst
8. Store report in daily_reports table
"""

import os
import sys
import json
import time
import logging
import psycopg2
import yfinance as yf
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [DAILY REPORT] - %(message)s')

DB_URL = os.getenv('DATABASE_URL')
IST = ZoneInfo("Asia/Kolkata")

# LLM Config (optional - for Head Analyst brief)
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:11434/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama")
AI_MODEL = os.getenv("AI_MODEL", "llama3.2")


def _get_conn():
    return psycopg2.connect(DB_URL)


def _fetch_watchlist() -> list[str]:
    """Fetch active symbols from the watchlist table."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM watchlist WHERE is_active = TRUE ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        logging.info(f"📋 Watchlist: {len(symbols)} active symbols")
        return symbols
    except Exception as e:
        logging.error(f"Failed to fetch watchlist: {e}")
        return []


def _fetch_global_context() -> dict:
    """Fetch latest global cues and FII/DII data."""
    ctx = {"market_regime": "NEUTRAL", "vix": None, "fii_net": None, "dii_net": None, "sectors": []}

    try:
        conn = _get_conn()
        cur = conn.cursor()

        # Global cues
        cur.execute("""
            SELECT overall_bias, vix_value, spy_change_pct, gift_nifty
            FROM global_cues ORDER BY captured_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            ctx["market_regime"] = row[0] or "NEUTRAL"
            ctx["vix"] = row[1]
            ctx["spy_pct"] = row[2]
            ctx["gift_nifty"] = row[3]

        # FII/DII
        cur.execute("""
            SELECT fii_net_cash, dii_net_cash, pcr
            FROM fii_dii_flows ORDER BY trade_date DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            ctx["fii_net"] = f"{'+' if row[0] and row[0] > 0 else ''}{row[0]} Cr" if row[0] else None
            ctx["dii_net"] = f"{'+' if row[1] and row[1] > 0 else ''}{row[1]} Cr" if row[1] else None
            ctx["pcr"] = row[2]

        # Top sectors
        cur.execute("""
            SELECT sector_name, net_investment_cr
            FROM sector_flows
            WHERE trade_date = (SELECT MAX(trade_date) FROM sector_flows)
            ORDER BY net_investment_cr DESC LIMIT 5
        """)
        ctx["sectors"] = [{"sector": r[0], "net_cr": r[1]} for r in cur.fetchall()]

        cur.close()
        conn.close()
    except Exception as e:
        logging.warning(f"Failed to fetch global context: {e}")

    return ctx


def _run_swing_analysis(symbol: str) -> dict | None:
    """Run swing TA on a single symbol."""
    from swing_agent_ta import analyze_swing_setups

    yf_symbol = f"{symbol}.NS"
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period="1y", interval="1d")

        if df.empty or len(df) < 200:
            logging.warning(f"  ⚠️ {symbol}: Insufficient data ({len(df)} candles)")
            return None

        report = analyze_swing_setups(df, symbol)
        return report

    except Exception as e:
        logging.error(f"  ❌ {symbol}: Swing analysis error: {e}")
        return None


def _run_options_analysis(symbol: str, price: float) -> dict | None:
    """Run options analysis on a single symbol."""
    from options_agent_worker import analyze_option_chain

    try:
        result = analyze_option_chain(symbol, price)
        if result and result.get('signals'):
            return result
        return None
    except Exception as e:
        logging.error(f"  ❌ {symbol}: Options analysis error: {e}")
        return None


def _generate_llm_brief(report_data: dict) -> str | None:
    """Generate a market brief using the LLM (optional, fails gracefully)."""
    try:
        from openai import OpenAI
        client = OpenAI(base_url=OPENAI_API_BASE, api_key=OPENAI_API_KEY)

        top_picks = report_data.get("top_picks", [])
        market_regime = report_data.get("market_regime", "NEUTRAL")
        vix = report_data.get("vix", "N/A")
        fii_net = report_data.get("fii_net", "N/A")
        total_analyzed = report_data.get("total_stocks_analyzed", 0)
        total_signals = report_data.get("total_signals", 0)

        # Build context for top picks
        picks_context = ""
        for item in report_data.get("watchlist_analysis", []):
            if item["symbol"] in top_picks:
                picks_context += f"\n{item['symbol']}: {item['signal_type']} | {item['signals_count']} signals | Confidence: {item['confidence']}%"
                if item.get("trade_idea"):
                    idea = item["trade_idea"]
                    picks_context += f" | Entry ₹{idea.get('entry')} → Target ₹{idea.get('target')} | SL ₹{idea.get('stoploss')}"
                picks_context += f"\n  Key: {', '.join(item.get('key_signals', [])[:3])}"

        prompt = f"""You are a senior prop desk analyst writing the MORNING BRIEF.

MARKET REGIME: {market_regime}
VIX: {vix}
FII: {fii_net}
WATCHLIST: {total_analyzed} stocks analyzed, {total_signals} total signals detected.

TOP PICKS FOR TODAY:
{picks_context}

Write a concise 4-5 sentence morning brief. Cover:
1. Market bias and what it means for today's session
2. Your top 2 conviction trades with reason
3. Key risk to watch

Be direct. No pleasantries. Sound like a fast-paced trading desk."""

        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "You are a prop desk morning briefing analyst. Be punchy and actionable."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logging.warning(f"LLM brief generation failed (graceful fallback): {e}")
        return None


def _store_report(report_data: dict):
    """Store the daily report in the database."""
    try:
        conn = _get_conn()
        cur = conn.cursor()

        report_date = report_data["report_date"]

        # Upsert: delete existing report for today, insert new
        cur.execute("DELETE FROM daily_reports WHERE report_date = %s", (report_date,))

        cur.execute("""
            INSERT INTO daily_reports 
            (report_date, market_regime, vix, fii_net, dii_net,
             watchlist_analysis, top_picks, avoid_list, head_analyst_brief,
             total_stocks_analyzed, total_signals)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            report_date,
            report_data.get("market_regime"),
            report_data.get("vix"),
            report_data.get("fii_net"),
            report_data.get("dii_net"),
            json.dumps(report_data.get("watchlist_analysis", [])),
            json.dumps(report_data.get("top_picks", [])),
            json.dumps(report_data.get("avoid_list", [])),
            report_data.get("head_analyst_brief"),
            report_data.get("total_stocks_analyzed", 0),
            report_data.get("total_signals", 0),
        ))

        conn.commit()
        cur.close()
        conn.close()
        logging.info(f"💾 Report stored for {report_date}")
    except Exception as e:
        logging.error(f"Failed to store report: {e}")


def _log_run(status, duration_ms, error=None):
    """Log to agent_runs."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO agent_runs (agent_name, run_status, duration_ms, error_message, finished_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, ('daily_report', status, duration_ms, error))
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


def generate_daily_report():
    """Main pipeline: orchestrates all agents and produces the daily report."""
    start = time.monotonic()
    today = datetime.now(IST).strftime("%Y-%m-%d")

    logging.info(f"{'='*60}")
    logging.info(f"📊 GENERATING DAILY REPORT — {today}")
    logging.info(f"{'='*60}")

    # 1. Fetch watchlist
    watchlist = _fetch_watchlist()
    if not watchlist:
        logging.error("No active symbols in watchlist. Aborting.")
        _log_run("FAILED", 0, "Empty watchlist")
        return None

    # 2. Fetch global context
    global_ctx = _fetch_global_context()
    logging.info(f"🌍 Market Regime: {global_ctx['market_regime']} | VIX: {global_ctx.get('vix')} | FII: {global_ctx.get('fii_net')}")

    # 3. Run Swing TA on each symbol
    watchlist_analysis = []
    total_signals = 0

    for i, symbol in enumerate(watchlist):
        logging.info(f"  [{i+1}/{len(watchlist)}] Analyzing {symbol}...")

        swing_report = _run_swing_analysis(symbol)

        if swing_report:
            sig_count = len(swing_report.get("signals", []))
            total_signals += sig_count

            analysis = {
                "symbol": symbol,
                "close_price": swing_report.get("close_price"),
                "daily_trend": swing_report.get("trend", {}).get("daily", "NEUTRAL"),
                "micro_trend": swing_report.get("trend", {}).get("micro", "NEUTRAL"),
                "trend_alignment": swing_report.get("trend", {}).get("alignment", "FLAT"),
                "signals_count": sig_count,
                "confidence": swing_report.get("confidence", 0),
                "signal_type": swing_report.get("signal_type", "NEUTRAL"),
                "move_potential_pct": swing_report.get("move_potential_pct", 0),
                "trade_idea": swing_report.get("trade_idea"),
                "key_signals": swing_report.get("signals", []),
                "support_resistance": swing_report.get("support_resistance"),
                "bollinger": swing_report.get("bollinger"),
                "indicators": swing_report.get("indicators"),
            }

            # 4. Run Options on high-confidence stocks
            if swing_report.get("confidence", 0) >= 40 and swing_report.get("close_price"):
                options_data = _run_options_analysis(symbol, swing_report["close_price"])
                if options_data:
                    analysis["options"] = {
                        "max_pain": options_data.get("max_pain"),
                        "call_wall": options_data.get("call_wall"),
                        "put_wall": options_data.get("put_wall"),
                        "pcr_volume": options_data.get("pcr_volume"),
                        "expected_move_pct": options_data.get("expected_move_pct"),
                        "verdict": options_data.get("verdict"),
                    }

            watchlist_analysis.append(analysis)
        else:
            # No signals but still include for completeness
            watchlist_analysis.append({
                "symbol": symbol,
                "close_price": None,
                "daily_trend": "NEUTRAL",
                "signals_count": 0,
                "confidence": 0,
                "signal_type": "NEUTRAL",
                "key_signals": [],
                "trade_idea": None,
            })

    # 5. Rank and pick top candidates
    ranked = sorted(
        [a for a in watchlist_analysis if a["confidence"] > 0],
        key=lambda x: x["confidence"],
        reverse=True
    )
    top_picks = [a["symbol"] for a in ranked[:5]]
    avoid_list = [
        a["symbol"] for a in watchlist_analysis
        if a.get("signal_type") == "BEARISH" and a.get("confidence", 0) >= 50
    ]

    logging.info(f"\n📈 Top Picks: {', '.join(top_picks) if top_picks else 'None'}")
    logging.info(f"🚫 Avoid List: {', '.join(avoid_list) if avoid_list else 'None'}")

    # 6. Assemble report
    report = {
        "report_date": today,
        "market_regime": global_ctx.get("market_regime", "NEUTRAL"),
        "vix": global_ctx.get("vix"),
        "fii_net": global_ctx.get("fii_net"),
        "dii_net": global_ctx.get("dii_net"),
        "watchlist_analysis": watchlist_analysis,
        "top_picks": top_picks,
        "avoid_list": avoid_list,
        "total_stocks_analyzed": len(watchlist),
        "total_signals": total_signals,
        "head_analyst_brief": None,
    }

    # 7. Generate LLM brief (optional)
    if top_picks:
        logging.info("🧠 Generating Head Analyst brief...")
        brief = _generate_llm_brief(report)
        report["head_analyst_brief"] = brief
        if brief:
            logging.info(f"\n{'─'*60}")
            logging.info(f"📝 MORNING BRIEF:")
            logging.info(brief)
            logging.info(f"{'─'*60}\n")
        else:
            logging.info("   LLM offline — skipping narrative brief.")

    # 8. Store report
    _store_report(report)

    elapsed = int((time.monotonic() - start) * 1000)
    _log_run("SUCCESS", elapsed)

    logging.info(f"\n{'='*60}")
    logging.info(f"✅ DAILY REPORT COMPLETE — {len(watchlist)} stocks | {total_signals} signals | {elapsed}ms")
    logging.info(f"{'='*60}")

    return report


# ── Entrypoint ───────────────────────────────────────
if __name__ == "__main__":
    report = generate_daily_report()

    if report and '--json' in sys.argv:
        print(json.dumps(report, indent=2, default=str))
