import os
import sys
import time
import json
import argparse
import logging
import psycopg2
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SIMULATOR] - %(message)s')
DB_URL = os.getenv("DATABASE_URL")

# Transaction costs (Indian equity intraday)
BROKERAGE_BPS = 3       # 0.03% per side
STT_BPS = 2.5           # 0.025% on sell (intraday)
SLIPPAGE_BPS = 2        # 2 bps average slippage
TOTAL_COST_BPS = BROKERAGE_BPS * 2 + STT_BPS + SLIPPAGE_BPS  # ~10.5 bps round-trip


def _get_conn():
    return psycopg2.connect(DB_URL)


def _ensure_tables():
    """Create backtest results tables if they don't exist."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id SERIAL PRIMARY KEY,
                start_date DATE, end_date DATE,
                total_days INTEGER, total_trades INTEGER,
                total_return REAL, annualized_return REAL,
                sharpe REAL, calmar REAL, max_drawdown REAL,
                win_rate REAL, profit_factor REAL,
                avg_win REAL, avg_loss REAL,
                max_consecutive_losses INTEGER,
                transaction_costs_total REAL,
                regime_breakdown JSONB,
                equity_curve JSONB,
                monthly_returns JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS backtest_trades (
                id SERIAL PRIMARY KEY,
                run_id INTEGER REFERENCES backtest_runs(id),
                trade_date DATE, symbol VARCHAR(20),
                direction VARCHAR(10), signal_type VARCHAR(50),
                confidence INTEGER,
                entry_price REAL, exit_price REAL,
                pnl_pct REAL, pnl_net_pct REAL,
                regime VARCHAR(30),
                was_correct BOOLEAN
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to create backtest tables: {e}")


def get_business_days(start_date: str, end_date: str):
    dates = pd.date_range(start=start_date, end=end_date, freq='B')
    return [d.strftime("%Y-%m-%d") for d in dates]


def simulate_day(target_date: str, run_state: dict):
    """Run pre-market graph for a historical date and collect results."""
    from langgraph_workflow import build_premarket_graph

    graph = build_premarket_graph()

    initial_state = {
        "report_date": target_date,
        "target_date": target_date,
        "profile": "simulated",
        "current_phase": "premarket",
        "market_regime": "NEUTRAL",
        "global_cues": {}, "sector_leaders": [], "watchlist": [],
        "swing_analyses": {}, "options_analyses": {}, "vector_analyses": {},
        "strategy_weights": run_state.get("strategy_weights", {}),
        "recent_performance": {},
        "intraday_setups": [], "options_setups": [],
        "all_evidence": [], "top_picks": [], "avoid_list": [],
        "accepted_trades": [], "skipped_trades": [],
        "eod_results": [], "learning_updates": [], "errors": [],
        "detected_regime": {}, "defense_mode": False,
        "volatility_forecast": {},
    }

    start = time.monotonic()
    try:
        result = graph.invoke(initial_state)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        setups = result.get("intraday_setups", [])
        regime = result.get("detected_regime", {}).get("regime_label", "UNKNOWN")
        logging.info(f"✅ {target_date} [{regime}] → {len(setups)} setups ({elapsed_ms}ms)")
        return result
    except Exception as e:
        logging.error(f"❌ {target_date} failed: {e}")
        return None


def evaluate_setups(setups: list, target_date: str, regime: str):
    """Evaluate T+1 performance with transaction costs."""
    if not setups:
        return []

    td = datetime.strptime(target_date, "%Y-%m-%d")
    next_day = td + timedelta(days=1)
    if next_day.weekday() >= 5:
        next_day += timedelta(days=(7 - next_day.weekday()))

    next_day_str = next_day.strftime("%Y-%m-%d")
    end_str = (next_day + timedelta(days=1)).strftime("%Y-%m-%d")
    trades = []

    for setup in setups:
        symbol = setup.get("symbol")
        confidence = setup.get("confidence", 0)
        signal = setup.get("trade_type", "")

        if confidence < 60:
            continue

        yf_symbol = f"{symbol}.NS"
        if symbol == "NIFTY": yf_symbol = "^NSEI"
        if symbol == "BANKNIFTY": yf_symbol = "^NSEBANK"

        try:
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(start=next_day_str, end=end_str, interval="1d")
            if df.empty:
                continue

            open_p = float(df.iloc[0]['Open'])
            close_p = float(df.iloc[0]['Close'])
            pnl_pct = ((close_p - open_p) / open_p) * 100

            if "SHORT" in signal or "BEARISH" in signal:
                pnl_pct = -pnl_pct

            # Deduct transaction costs
            cost_pct = TOTAL_COST_BPS / 100
            pnl_net = pnl_pct - cost_pct
            was_correct = pnl_net > 0

            trades.append({
                "date": target_date, "symbol": symbol,
                "direction": "SHORT" if "SHORT" in signal else "LONG",
                "signal_type": setup.get("signals", ["UNKNOWN"])[0] if setup.get("signals") else "UNKNOWN",
                "confidence": confidence,
                "entry": open_p, "exit": close_p,
                "pnl_pct": round(pnl_pct, 4), "pnl_net_pct": round(pnl_net, 4),
                "regime": regime, "was_correct": was_correct,
            })
        except Exception:
            pass

    return trades


def compute_run_metrics(all_trades: list, start_date: str, end_date: str) -> dict:
    """Compute comprehensive backtest metrics."""
    if not all_trades:
        return {"error": "no_trades"}

    returns = np.array([t["pnl_net_pct"] / 100 for t in all_trades])
    n_days = len(set(t["date"] for t in all_trades))

    # Equity curve
    equity = [100000.0]
    for r in returns:
        equity.append(equity[-1] * (1 + r))
    equity = np.array(equity)

    total_return = (equity[-1] / equity[0]) - 1
    ann_return = (1 + total_return) ** (252 / max(n_days, 1)) - 1
    ann_vol = np.std(returns) * np.sqrt(252)
    sharpe = ann_return / (ann_vol + 1e-8)

    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / (peak + 1e-8)
    max_dd = float(np.max(drawdown))
    calmar = ann_return / (max_dd + 1e-8)

    winners = returns[returns > 0]
    losers = returns[returns < 0]
    win_rate = len(winners) / max(len(returns), 1)
    profit_factor = abs(winners.sum()) / (abs(losers.sum()) + 1e-8)

    # Consecutive losses
    max_consec = 0
    streak = 0
    for r in returns:
        if r < 0:
            streak += 1
            max_consec = max(max_consec, streak)
        else:
            streak = 0

    # Regime breakdown
    regime_breakdown = {}
    for t in all_trades:
        r = t["regime"]
        if r not in regime_breakdown:
            regime_breakdown[r] = {"trades": 0, "wins": 0, "total_pnl": 0}
        regime_breakdown[r]["trades"] += 1
        if t["was_correct"]:
            regime_breakdown[r]["wins"] += 1
        regime_breakdown[r]["total_pnl"] += t["pnl_net_pct"]

    for r in regime_breakdown:
        b = regime_breakdown[r]
        b["win_rate"] = round(b["wins"] / max(b["trades"], 1), 3)
        b["avg_pnl"] = round(b["total_pnl"] / max(b["trades"], 1), 4)

    # Monthly returns
    monthly = {}
    for t in all_trades:
        month = t["date"][:7]
        monthly.setdefault(month, [])
        monthly[month].append(t["pnl_net_pct"])
    monthly_returns = {m: round(sum(v), 2) for m, v in sorted(monthly.items())}

    # Equity curve sampled (for chart)
    n_points = min(500, len(equity))
    indices = np.linspace(0, len(equity) - 1, n_points, dtype=int)
    equity_sampled = [{"idx": int(i), "equity": round(float(equity[i]), 2)} for i in indices]

    return {
        "start_date": start_date, "end_date": end_date,
        "total_days": n_days, "total_trades": len(all_trades),
        "total_return": round(total_return, 4),
        "annualized_return": round(ann_return, 4),
        "annualized_vol": round(ann_vol, 4),
        "sharpe": round(sharpe, 3), "calmar": round(calmar, 3),
        "max_drawdown": round(max_dd, 4),
        "win_rate": round(win_rate, 4), "profit_factor": round(profit_factor, 3),
        "avg_win": round(float(winners.mean()), 4) if len(winners) > 0 else 0,
        "avg_loss": round(float(losers.mean()), 4) if len(losers) > 0 else 0,
        "max_consecutive_losses": max_consec,
        "transaction_costs_bps": TOTAL_COST_BPS,
        "regime_breakdown": regime_breakdown,
        "monthly_returns": monthly_returns,
        "equity_curve": equity_sampled,
    }


def persist_run(metrics: dict, trades: list):
    """Save backtest results and trades to DB."""
    _ensure_tables()
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO backtest_runs
            (start_date, end_date, total_days, total_trades,
             total_return, annualized_return, sharpe, calmar, max_drawdown,
             win_rate, profit_factor, avg_win, avg_loss,
             max_consecutive_losses, transaction_costs_total,
             regime_breakdown, equity_curve, monthly_returns)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            metrics["start_date"], metrics["end_date"],
            metrics["total_days"], metrics["total_trades"],
            metrics["total_return"], metrics["annualized_return"],
            metrics["sharpe"], metrics["calmar"], metrics["max_drawdown"],
            metrics["win_rate"], metrics["profit_factor"],
            metrics["avg_win"], metrics["avg_loss"],
            metrics["max_consecutive_losses"],
            metrics["transaction_costs_bps"],
            json.dumps(metrics["regime_breakdown"]),
            json.dumps(metrics["equity_curve"]),
            json.dumps(metrics["monthly_returns"]),
        ))
        run_id = cur.fetchone()[0]

        for t in trades:
            cur.execute("""
                INSERT INTO backtest_trades
                (run_id, trade_date, symbol, direction, signal_type,
                 confidence, entry_price, exit_price, pnl_pct, pnl_net_pct,
                 regime, was_correct)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                run_id, t["date"], t["symbol"], t["direction"],
                t["signal_type"], t["confidence"],
                t["entry"], t["exit"], t["pnl_pct"], t["pnl_net_pct"],
                t["regime"], t["was_correct"],
            ))

        conn.commit()
        cur.close()
        conn.close()
        logging.info(f"💾 Saved backtest run #{run_id}: {len(trades)} trades")
        return run_id
    except Exception as e:
        logging.error(f"Failed to persist backtest: {e}")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Timm LangGraph Historical Simulator")
    parser.add_argument("--start-date", type=str, required=True)
    parser.add_argument("--end-date", type=str, required=True)
    parser.add_argument("--min-confidence", type=int, default=60)
    args = parser.parse_args()

    dates = get_business_days(args.start_date, args.end_date)
    logging.info(f"Starting simulation: {len(dates)} days ({args.start_date} → {args.end_date})")

    all_trades = []
    run_state = {"strategy_weights": {}}

    for d in dates:
        result = simulate_day(d, run_state)
        if result:
            setups = result.get("intraday_setups", [])
            regime = result.get("detected_regime", {}).get("regime_label", "UNKNOWN")
            day_trades = evaluate_setups(setups, d, regime)
            all_trades.extend(day_trades)

            # Feed learning
            for t in day_trades:
                adjust_sim_weight(t["signal_type"], t["was_correct"], t["pnl_net_pct"], run_state)

        time.sleep(1)

    # Compute and persist metrics
    if all_trades:
        metrics = compute_run_metrics(all_trades, args.start_date, args.end_date)
        run_id = persist_run(metrics, all_trades)

        logging.info(f"\n{'='*60}")
        logging.info(f"🎯 BACKTEST RESULTS ({args.start_date} → {args.end_date})")
        logging.info(f"{'='*60}")
        logging.info(f"  Total trades: {metrics['total_trades']}")
        logging.info(f"  Return: {metrics['total_return']:.1%} (Ann: {metrics['annualized_return']:.1%})")
        logging.info(f"  Sharpe: {metrics['sharpe']:.3f} | Calmar: {metrics['calmar']:.3f}")
        logging.info(f"  Max DD: {metrics['max_drawdown']:.1%}")
        logging.info(f"  Win Rate: {metrics['win_rate']:.1%} | PF: {metrics['profit_factor']:.2f}")
        logging.info(f"  Max Consec Losses: {metrics['max_consecutive_losses']}")
        logging.info(f"  Costs: {metrics['transaction_costs_bps']} bps round-trip")
        for r, b in metrics["regime_breakdown"].items():
            logging.info(f"  Regime {r}: {b['trades']} trades, WR={b['win_rate']:.0%}, Avg={b['avg_pnl']:.2f}%")
    else:
        logging.warning("No trades generated during simulation")

    logging.info("\n🎉 Simulation Complete!")


def adjust_sim_weight(signal_type, was_correct, pnl_pct, run_state):
    """In-memory weight adjustment for simulation."""
    weights = run_state.setdefault("strategy_weights", {})
    w = weights.setdefault(signal_type, {"weight": 1.0, "wins": 0, "losses": 0})
    if was_correct:
        w["wins"] += 1
        w["weight"] *= 1.03
    else:
        w["losses"] += 1
        w["weight"] *= 0.97
    w["win_rate"] = w["wins"] / max(w["wins"] + w["losses"], 1)
