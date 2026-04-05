"""
TIMM LangGraph Runner — CLI entry point for graph execution.

Usage:
  python run_graph.py --phase premarket    # Run pre-market analysis
  python run_graph.py --phase eod          # Run EOD review + learning

Triggered by:
  - scheduler_worker.py (cron jobs)
  - main.py API endpoints (manual trigger)
  - Direct CLI execution (testing)
"""

import os
import sys
import json
import time
import argparse
import logging
import psycopg2
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [GRAPH RUNNER] - %(message)s'
)

DB_URL = os.getenv("DATABASE_URL")
IST = ZoneInfo("Asia/Kolkata")


def _get_conn():
    return psycopg2.connect(DB_URL)


def _ensure_graph_runs_table():
    """Create graph_runs table if it doesn't exist."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS graph_runs (
                id SERIAL PRIMARY KEY,
                graph_type VARCHAR(30) NOT NULL,
                run_date DATE NOT NULL,
                started_at TIMESTAMP DEFAULT NOW(),
                finished_at TIMESTAMP,
                duration_ms INTEGER,
                state_snapshot JSONB,
                phase_completed VARCHAR(30),
                total_setups INTEGER,
                total_accepted INTEGER,
                status VARCHAR(20) DEFAULT 'RUNNING',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.warning(f"Could not ensure graph_runs table: {e}")


def _log_graph_start(graph_type: str, run_date: str) -> int | None:
    """Insert a RUNNING row and return the ID."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO graph_runs (graph_type, run_date, status)
            VALUES (%s, %s, 'RUNNING')
            RETURNING id
        """, (graph_type, run_date))
        run_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return run_id
    except Exception as e:
        logging.warning(f"Failed to log graph start: {e}")
        return None


def _log_graph_finish(run_id: int, status: str, duration_ms: int,
                      state_snapshot: dict = None, error: str = None,
                      total_setups: int = 0):
    """Update the graph_runs row with final state."""
    try:
        conn = _get_conn()
        cur = conn.cursor()

        # Slim down state snapshot (don't store massive analysis dicts)
        slim_snapshot = None
        if state_snapshot:
            slim_snapshot = {
                "market_regime": state_snapshot.get("market_regime"),
                "vix": state_snapshot.get("vix"),
                "fii_net": state_snapshot.get("fii_net"),
                "watchlist_count": len(state_snapshot.get("watchlist", [])),
                "intraday_setups_count": len(state_snapshot.get("intraday_setups", [])),
                "options_setups_count": len(state_snapshot.get("options_setups", [])),
                "top_picks_count": len(state_snapshot.get("top_picks", [])),
                "avoid_list": state_snapshot.get("avoid_list", []),
                "head_analyst_brief": state_snapshot.get("head_analyst_brief"),
                "errors": state_snapshot.get("errors", []),
            }

        cur.execute("""
            UPDATE graph_runs SET
                status = %s,
                finished_at = NOW(),
                duration_ms = %s,
                state_snapshot = %s,
                total_setups = %s,
                error_message = %s,
                phase_completed = 'COMPLETE'
            WHERE id = %s
        """, (
            status, duration_ms,
            json.dumps(slim_snapshot, default=str) if slim_snapshot else None,
            total_setups, error, run_id
        ))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.warning(f"Failed to log graph finish: {e}")


def _store_daily_report(state: dict, report_date: str):
    """Store the graph output in the daily_reports table for dashboard consumption."""
    try:
        conn = _get_conn()
        cur = conn.cursor()

        # Ensure daily_reports table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_reports (
                id SERIAL PRIMARY KEY,
                report_date DATE NOT NULL,
                market_regime VARCHAR(20),
                vix REAL,
                fii_net VARCHAR(50),
                dii_net VARCHAR(50),
                watchlist_analysis JSONB,
                top_picks JSONB,
                avoid_list JSONB,
                head_analyst_brief TEXT,
                total_stocks_analyzed INTEGER,
                total_signals INTEGER,
                intraday_setups JSONB,
                options_setups JSONB,
                evidence_chain JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Upsert
        cur.execute("DELETE FROM daily_reports WHERE report_date = %s", (report_date,))

        # Prepare setups for storage (slim down for DB)
        intraday = state.get("intraday_setups", [])
        options = state.get("options_setups", [])
        top_picks = state.get("top_picks", [])

        # Slim down top_picks (remove heavy fields)
        slim_picks = []
        for p in top_picks[:20]:
            slim_picks.append({
                "symbol": p.get("symbol"),
                "signal_type": p.get("signal_type"),
                "confidence": p.get("confidence"),
                "close_price": p.get("close_price"),
                "trade_idea": p.get("trade_idea"),
                "signals": p.get("signals", [])[:5],
                "move_potential_pct": p.get("move_potential_pct"),
            })

        total_signals = sum(
            len(p.get("signals", [])) for p in top_picks
        )

        cur.execute("""
            INSERT INTO daily_reports
            (report_date, market_regime, vix, fii_net, dii_net,
             watchlist_analysis, top_picks, avoid_list, head_analyst_brief,
             total_stocks_analyzed, total_signals, intraday_setups, options_setups,
             evidence_chain)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            report_date,
            state.get("market_regime"),
            state.get("vix"),
            state.get("fii_net"),
            state.get("dii_net"),
            json.dumps(slim_picks, default=str),
            json.dumps([p.get("symbol") for p in top_picks[:10]], default=str),
            json.dumps(state.get("avoid_list", []), default=str),
            state.get("head_analyst_brief"),
            len(state.get("watchlist", [])),
            total_signals,
            json.dumps(intraday, default=str),
            json.dumps(options, default=str),
            json.dumps(state.get("all_evidence", [])[:50], default=str),
        ))

        conn.commit()
        cur.close()
        conn.close()
        logging.info(f"💾 Daily report stored for {report_date}")

    except Exception as e:
        logging.error(f"Failed to store daily report: {e}")


def run_premarket():
    """Execute the pre-market analysis graph."""
    from langgraph_workflow import build_premarket_graph

    today = datetime.now(IST).strftime("%Y-%m-%d")

    logging.info(f"\n{'=' * 60}")
    logging.info(f"🚀 STARTING PRE-MARKET GRAPH — {today}")
    logging.info(f"{'=' * 60}\n")

    _ensure_graph_runs_table()
    run_id = _log_graph_start("PREMARKET", today)
    start = time.monotonic()

    try:
        graph = build_premarket_graph()

        initial_state = {
            "report_date": today,
            "current_phase": "premarket",
            "market_regime": "NEUTRAL",
            "global_cues": {},
            "sector_leaders": [],
            "watchlist": [],
            "swing_analyses": {},
            "options_analyses": {},
            "vector_analyses": {},
            "strategy_weights": {},
            "recent_performance": {},
            "intraday_setups": [],
            "options_setups": [],
            "all_evidence": [],
            "top_picks": [],
            "avoid_list": [],
            "accepted_trades": [],
            "skipped_trades": [],
            "eod_results": [],
            "learning_updates": [],
            "errors": [],
            "graph_run_id": run_id,
        }

        result = graph.invoke(initial_state)

        elapsed_ms = int((time.monotonic() - start) * 1000)

        # Count setups
        intraday_count = len(result.get("intraday_setups", []))
        options_count = len(result.get("options_setups", []))
        total_setups = intraday_count + options_count

        # Store results
        _store_daily_report(result, today)

        if run_id:
            _log_graph_finish(run_id, "SUCCESS", elapsed_ms, result, total_setups=total_setups)

        # Print summary
        logging.info(f"\n{'=' * 60}")
        logging.info(f"✅ PRE-MARKET GRAPH COMPLETE — {elapsed_ms}ms")
        logging.info(f"{'=' * 60}")
        logging.info(f"  Market Regime: {result.get('market_regime')} | VIX: {result.get('vix')}")
        logging.info(f"  Watchlist: {len(result.get('watchlist', []))} symbols")
        logging.info(f"  Intraday Setups: {intraday_count}")
        logging.info(f"  Options Setups: {options_count}")
        logging.info(f"  Avoid List: {result.get('avoid_list', [])}")

        errors = result.get("errors", [])
        if errors:
            logging.warning(f"  Errors: {len(errors)}")
            for err in errors:
                logging.warning(f"    ⚠️ {err}")

        brief = result.get("head_analyst_brief")
        if brief:
            logging.info(f"\n  📝 MORNING BRIEF:")
            logging.info(f"  {brief}")

        logging.info(f"{'=' * 60}\n")

        return result

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logging.error(f"💥 Pre-market graph failed: {e}")
        import traceback
        traceback.print_exc()

        if run_id:
            _log_graph_finish(run_id, "FAILED", elapsed_ms, error=str(e)[:500])

        return None


def run_eod():
    """Execute the EOD review + self-learning graph."""
    from langgraph_workflow import build_eod_graph

    today = datetime.now(IST).strftime("%Y-%m-%d")

    logging.info(f"\n{'=' * 60}")
    logging.info(f"🌙 STARTING EOD REVIEW GRAPH — {today}")
    logging.info(f"{'=' * 60}\n")

    _ensure_graph_runs_table()
    run_id = _log_graph_start("EOD_REVIEW", today)
    start = time.monotonic()

    try:
        graph = build_eod_graph()

        # Load today's market context from the premarket run
        initial_state = {
            "report_date": today,
            "current_phase": "eod",
            "market_regime": "NEUTRAL",
            "errors": [],
            "eod_results": [],
            "learning_updates": [],
            "graph_run_id": run_id,
        }

        # Try to load context from today's premarket run
        try:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT state_snapshot FROM graph_runs
                WHERE graph_type = 'PREMARKET' AND run_date = %s AND status = 'SUCCESS'
                ORDER BY id DESC LIMIT 1
            """, (today,))
            row = cur.fetchone()
            if row and row[0]:
                snapshot = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                initial_state["market_regime"] = snapshot.get("market_regime", "NEUTRAL")
                initial_state["vix"] = snapshot.get("vix")
            cur.close()
            conn.close()
        except Exception:
            pass

        result = graph.invoke(initial_state)

        elapsed_ms = int((time.monotonic() - start) * 1000)

        if run_id:
            _log_graph_finish(run_id, "SUCCESS", elapsed_ms, result)

        logging.info(f"\n{'=' * 60}")
        logging.info(f"✅ EOD REVIEW COMPLETE — {elapsed_ms}ms")
        logging.info(f"  Trades reviewed: {len(result.get('eod_results', []))}")
        logging.info(f"  Learnings recorded: {len(result.get('learning_updates', []))}")
        logging.info(f"{'=' * 60}\n")

        return result

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logging.error(f"💥 EOD graph failed: {e}")
        import traceback
        traceback.print_exc()

        if run_id:
            _log_graph_finish(run_id, "FAILED", elapsed_ms, error=str(e)[:500])

        return None


# ── CLI Entry Point ──────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="TIMM LangGraph Runner")
    parser.add_argument(
        "--phase",
        choices=["premarket", "eod"],
        required=True,
        help="Which graph phase to run"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full result as JSON"
    )

    args = parser.parse_args()

    if args.phase == "premarket":
        result = run_premarket()
    elif args.phase == "eod":
        result = run_eod()

    if result and args.json:
        # Print a slim version (exclude huge analysis dicts)
        slim = {
            "report_date": result.get("report_date"),
            "market_regime": result.get("market_regime"),
            "vix": result.get("vix"),
            "fii_net": result.get("fii_net"),
            "intraday_setups": result.get("intraday_setups", []),
            "options_setups": result.get("options_setups", []),
            "avoid_list": result.get("avoid_list", []),
            "head_analyst_brief": result.get("head_analyst_brief"),
            "errors": result.get("errors", []),
        }
        print(json.dumps(slim, indent=2, default=str))


if __name__ == "__main__":
    main()
