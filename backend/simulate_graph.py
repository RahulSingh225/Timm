import os
import sys
import time
import argparse
import logging
import psycopg2
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SIMULATOR] - %(message)s')
DB_URL = os.getenv("DATABASE_URL")

def _get_conn():
    return psycopg2.connect(DB_URL)

def get_business_days(start_date: str, end_date: str):
    """Generate a list of business days between start and end dates."""
    dates = pd.date_range(start=start_date, end=end_date, freq='B')
    return [d.strftime("%Y-%m-%d") for d in dates]

def simulate_day(target_date: str):
    """Run the pre-market graph for a specific historical date."""
    from langgraph_workflow import build_premarket_graph
    
    logging.info(f"\n{'=' * 60}")
    logging.info(f"🕰️ SIMULATING TRADING DAY: {target_date}")
    logging.info(f"{'=' * 60}")
    
    graph = build_premarket_graph()
    
    # 1. State Injection
    # We pass target_date and profile to force nodes to behave historically and securely
    initial_state = {
        "report_date": target_date,
        "target_date": target_date,
        "profile": "simulated",
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
    }
    
    start = time.monotonic()
    
    try:
        # Run the graph
        result = graph.invoke(initial_state)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        
        setups = result.get("intraday_setups", [])
        logging.info(f"✅ Simulation for {target_date} complete in {elapsed_ms}ms")
        logging.info(f"  Found {len(setups)} setups.")
        
        # 2. Auto-Execution & Evaluation (The 'Time Machine' advantage)
        # We auto-accept high confidence setups and peek into the next day to see if they won.
        evaluate_setups(setups, target_date)
        
    except Exception as e:
        logging.error(f"❌ Simulation failed for {target_date}: {e}")

def evaluate_setups(setups: list, target_date: str):
    """Simulate entering trades and evaluating T+1 performance."""
    if not setups:
        return
        
    logging.info(f"🔮 Evaluating {len(setups)} setups for T+1 performance...")
    
    # Next business day
    td = datetime.strptime(target_date, "%Y-%m-%d")
    next_day = (td + timedelta(days=1))
    
    # Hack for weekends if the logic produced Friday
    if next_day.weekday() >= 5:
        next_day += timedelta(days=(7 - next_day.weekday()))
        
    next_day_str = next_day.strftime("%Y-%m-%d")
    end_fetch_str = (next_day + timedelta(days=1)).strftime("%Y-%m-%d")
    
    conn = _get_conn()
    cur = conn.cursor()
    
    for setup in setups:
        symbol = setup.get("symbol")
        confidence = setup.get("confidence", 0)
        signal = setup.get("trade_type", "")
        
        if confidence < 75:  # Only auto-trade high conviction
            continue
            
        yf_symbol = f"{symbol}.NS"
        if symbol == "NIFTY": yf_symbol = "^NSEI"
        if symbol == "BANKNIFTY": yf_symbol = "^NSEBANK"
        
        try:
            ticker = yf.Ticker(yf_symbol)
            # Fetch just the next day's candle to see what happened
            df = ticker.history(start=next_day_str, end=end_fetch_str, interval="1d")
            
            if df.empty:
                continue
                
            open_p = float(df.iloc[0]['Open'])
            close_p = float(df.iloc[0]['Close'])
            
            # Simple simulation logic: enter at open, exit at close
            pnl_pct = ((close_p - open_p) / open_p) * 100
            
            if "SHORT" in signal or "BEARISH" in signal:
                pnl_pct = -pnl_pct  # Invert PnL for short trades
                
            was_correct = pnl_pct > 0.5  # Need at least 0.5% buffer to call it a "win"
            
            logging.info(f"  [SIM-TRADE] {symbol} {signal}: PnL {pnl_pct:+.2f}% -> {'WIN' if was_correct else 'LOSS'}")
            
            # 3. Feed the learning system directly
            # We record this in learning_history as 'is_simulated = True'
            primary_reason = setup.get("signals", ["UNKNOWN_PATTERN"])[0] if setup.get("signals") else "UNKNOWN_PATTERN"
            
            cur.execute("""
                INSERT INTO learning_history 
                (trade_date, signal_type, predicted_direction, was_correct, actual_pnl_pct, trade_type, is_simulated)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """, (
                target_date,
                primary_reason,
                "BULLISH" if "LONG" in signal else "BEARISH",
                was_correct,
                pnl_pct,
                "INTRADAY"
            ))
            
            # Auto-update the sim weights based on this trade
            adjust_sim_weight(cur, primary_reason, was_correct, pnl_pct)
            
        except Exception as e:
            logging.error(f"    Failed to evaluate {symbol}: {e}")
            
    conn.commit()
    cur.close()
    conn.close()

def adjust_sim_weight(cur, signal_type, was_correct, pnl_pct):
    """Adjust the strategy_weights strictly for the 'simulated' profile."""
    cur.execute("""
        INSERT INTO strategy_weights (signal_type, profile, base_weight, win_count, loss_count)
        VALUES (%s, 'simulated', 1.0, %s, %s)
        ON CONFLICT (signal_type, profile) DO UPDATE SET
            win_count = strategy_weights.win_count + EXCLUDED.win_count,
            loss_count = strategy_weights.loss_count + EXCLUDED.loss_count,
            base_weight = strategy_weights.base_weight * %s
    """, (
        signal_type,
        1 if was_correct else 0,
        1 if not was_correct else 0,
        1.05 if was_correct else 0.95  # +5% weight on win, -5% weight on loss
    ))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Timm LangGraph Historical Simulator")
    parser.add_argument("--start-date", type=str, required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, required=True, help="End date (YYYY-MM-DD)")
    
    args = parser.parse_args()
    
    dates = get_business_days(args.start_date, args.end_date)
    logging.info(f"Starting simulation run for {len(dates)} business days...")
    
    for d in dates:
        simulate_day(d)
        time.sleep(2)  # Avoid rate limiting yfinance
        
    logging.info("\n🎉 Simulation Engine Run Complete!")
