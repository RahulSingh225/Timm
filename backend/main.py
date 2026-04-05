import os
import sys
from dotenv import load_dotenv
load_dotenv()
import logging
import subprocess
from fastapi import FastAPI, BackgroundTasks, HTTPException
import uvicorn
from contextlib import asynccontextmanager
import pika
import json
import psycopg2

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [MAIN API] - %(message)s')

# Workers that still run as RabbitMQ consumers.
# Analysis workers (swing, options, head, vector, screener) are RETIRED —
# their logic is now orchestrated by LangGraph nodes.
workers_registry = {
    "vault": "db_vault_worker.py",
    "manager": "system_manager.py",
    "cues": "global_cues_producer.py",
    "monitor": "price_monitor_worker.py",
    "scheduler": "scheduler_worker.py"
}

SCHEDULER_URL = os.getenv("SCHEDULER_URL", "http://localhost:4501")

active_processes = {} # {id: subprocess.Popen}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Starting background worker processes...")
    
    for worker_id, filename in workers_registry.items():
        logging.info(f"Starting {filename}...")
        try:
            p = subprocess.Popen([sys.executable, filename])
            active_processes[worker_id] = p
        except Exception as e:
            logging.error(f"Failed to start {filename}: {e}")
        
    yield # API is running
    
    logging.info("Shutting down background workers...")
    for worker_id in list(active_processes.keys()):
        p = active_processes.pop(worker_id)
        logging.info(f"Terminating {worker_id}...")
        p.terminate()
        p.wait()

app = FastAPI(title="Timm Agent Web Framework", lifespan=lifespan)

@app.get("/")
def read_root():
    return {
        "status": "Agent Timm API is running.", 
        "workers_active": len(active_processes),
        "available_workers": list(workers_registry.keys())
    }

@app.get("/workers")
def get_workers():
    status = {}
    # Use a copy of keys to avoid RuntimeError if we pop items during iteration
    for worker_id, filename in list(workers_registry.items()):
        proc = active_processes.get(worker_id)
        is_alive = False
        if proc:
            try:
                # Check if process is still running
                if proc.poll() is None:
                    is_alive = True
                else:
                    # Remove it if it finished/crashed
                    active_processes.pop(worker_id, None)
            except Exception as e:
                logging.error(f"Error checking status for {worker_id}: {e}")
                active_processes.pop(worker_id, None)
        
        status[worker_id] = {
            "name": filename,
            "status": "RUNNING" if is_alive else "STOPPED",
            "pid": proc.pid if (proc and is_alive) else None
        }
    return status

@app.post("/workers/{worker_id}/start")
def start_worker(worker_id: str):
    if worker_id not in workers_registry:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    if worker_id in active_processes and active_processes[worker_id].poll() is None:
        return {"message": f"Worker {worker_id} already running."}
    
    filename = workers_registry[worker_id]
    logging.info(f"Starting worker: {filename}")
    p = subprocess.Popen([sys.executable, filename])
    active_processes[worker_id] = p
    return {"message": f"Worker {worker_id} started.", "pid": p.pid}

@app.post("/workers/{worker_id}/stop")
def stop_worker(worker_id: str):
    if worker_id not in active_processes:
        return {"message": f"Worker {worker_id} is not running."}
    
    p = active_processes.pop(worker_id)
    logging.info(f"Stopping worker: {worker_id}")
    p.terminate()
    p.wait()
    return {"message": f"Worker {worker_id} stopped."}

@app.post("/trigger/{task}")
def trigger_task(task: str, background_tasks: BackgroundTasks):
    """
    Trigger various system tasks.
    Valid tasks: sync_fii, sync_nsdl, seed_db
    """
    valid_tasks = ["sync_fii", "sync_nsdl", "seed_db", "sync_yfinance"]
    if task not in valid_tasks:
        raise HTTPException(status_code=400, detail=f"Invalid task. Valid: {valid_tasks}")

    def push_to_system_manager():
        try:
            credentials = pika.PlainCredentials(os.getenv('RABBITMQ_USER', 'admin'), os.getenv('RABBITMQ_PASS', 'supersecretpassword'))
            connection = pika.BlockingConnection(pika.ConnectionParameters(os.getenv('RABBITMQ_HOST', 'localhost'), 5672, '/', credentials))
            channel = connection.channel()
            channel.queue_declare(queue='system_commands', durable=True)
            channel.basic_publish(
                exchange='', 
                routing_key='system_commands', 
                body=json.dumps({"task": task})
            )
            connection.close()
            logging.info(f"Task '{task}' successfully pushed to RabbitMQ for the system manager.")
        except Exception as e:
            logging.error(f"Failed to publish to RabbitMQ: {e}")

    background_tasks.add_task(push_to_system_manager)
    return {"message": f"Task '{task}' has been queued."}

@app.post("/seed")
def seed_database(background_tasks: BackgroundTasks):
    """
    Direct endpoint to start the historical background seeding process.
    """
    def run_seed():
        logging.info("Running historical DB seed script...")
        subprocess.run([sys.executable, "seed_historical.py"], check=False)
        logging.info("Historical seed finished.")
        
    background_tasks.add_task(run_seed)
    return {"message": "Database seeding initiated in the background."}

@app.post("/ingest")
def run_ingestion(background_tasks: BackgroundTasks):
    """
    Trigger the yfinance data ingestion pipeline.
    Fetches EOD data for all active watchlist symbols and publishes to RabbitMQ.
    """
    def run_yfinance():
        logging.info("Running yfinance producer...")
        subprocess.run([sys.executable, "yfinance_producer.py"], check=False)
        logging.info("yfinance ingestion finished.")

    background_tasks.add_task(run_yfinance)
    return {"message": "Data ingestion initiated in the background."}

# ─── Scheduler Proxy Endpoints ─────────────────────────────
@app.get("/scheduler")
def get_scheduler_status():
    """Proxy to the scheduler worker's status endpoint."""
    import httpx
    try:
        r = httpx.get(f"{SCHEDULER_URL}/scheduler", timeout=5.0)
        return r.json()
    except Exception as e:
        return {"success": False, "error": f"Scheduler unreachable: {e}", "jobs": []}

@app.post("/scheduler/trigger/{job_id}")
def trigger_scheduler_job(job_id: str):
    """Proxy to trigger a specific scheduler job."""
    import httpx
    try:
        r = httpx.post(f"{SCHEDULER_URL}/scheduler/trigger/{job_id}", timeout=5.0)
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Scheduler unreachable: {e}")


# ─── LangGraph Workflow Endpoints ──────────────────────────────

@app.post("/graph/premarket")
def trigger_premarket(background_tasks: BackgroundTasks):
    """Trigger the pre-market analysis LangGraph (Phase 1+2)."""
    def run():
        from run_graph import run_premarket
        run_premarket()

    background_tasks.add_task(run)
    return {"message": "Pre-market graph triggered.", "status": "QUEUED"}


@app.post("/graph/eod-review")
def trigger_eod(background_tasks: BackgroundTasks):
    """Trigger the EOD review + self-learning graph (Phase 5)."""
    def run():
        from run_graph import run_eod
        run_eod()

    background_tasks.add_task(run)
    return {"message": "EOD review graph triggered.", "status": "QUEUED"}


@app.post("/graph/training")
def trigger_training(background_tasks: BackgroundTasks):
    """Trigger the offline Heavy ML parameter optimization."""
    def run():
        from run_graph import run_training
        run_training()

    background_tasks.add_task(run)
    return {"message": "ML training graph triggered.", "status": "QUEUED"}


@app.get("/graph/setups")
def get_today_setups():
    """Get today's trade setups with evidence chains."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")

    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cur = conn.cursor()
        cur.execute("""
            SELECT intraday_setups, options_setups, head_analyst_brief, 
                   market_regime, vix, avoid_list, evidence_chain
            FROM daily_reports WHERE report_date = %s
            ORDER BY id DESC LIMIT 1
        """, (today,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return {"message": "No setups generated yet today.", "setups": None}

        return {
            "report_date": today,
            "intraday_setups": row[0] if row[0] else [],
            "options_setups": row[1] if row[1] else [],
            "head_analyst_brief": row[2],
            "market_regime": row[3],
            "vix": row[4],
            "avoid_list": row[5] if row[5] else [],
            "evidence_chain": row[6] if row[6] else [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch setups: {e}")


@app.post("/graph/accept-trade")
def accept_trade(payload: dict):
    """
    User accepts a trade setup. Creates entry in trade_journal.
    Expected payload: {symbol, trade_type, entry_price, stoploss, target, confidence, signals, evidence, notes}
    """
    import psycopg2
    from datetime import datetime
    from zoneinfo import ZoneInfo

    required = ["symbol", "trade_type", "entry_price"]
    for field in required:
        if field not in payload:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    today = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")

    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cur = conn.cursor()

        # Ensure table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trade_journal (
                id SERIAL PRIMARY KEY, trade_date DATE NOT NULL,
                symbol VARCHAR(50) NOT NULL, trade_type VARCHAR(30) NOT NULL,
                entry_price REAL NOT NULL, exit_price REAL, stoploss REAL, target REAL,
                actual_pnl_pct REAL, status VARCHAR(20) DEFAULT 'OPEN',
                predicted_confidence REAL, signals_used JSONB, evidence_chain JSONB,
                user_notes TEXT, entered_at TIMESTAMP DEFAULT NOW(),
                exited_at TIMESTAMP, session_type VARCHAR(20),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        cur.execute("""
            INSERT INTO trade_journal
            (trade_date, symbol, trade_type, entry_price, stoploss, target,
             predicted_confidence, signals_used, evidence_chain, user_notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            today,
            payload["symbol"],
            payload["trade_type"],
            payload["entry_price"],
            payload.get("stoploss"),
            payload.get("target"),
            payload.get("confidence"),
            json.dumps(payload.get("signals", [])),
            json.dumps(payload.get("evidence", [])),
            payload.get("notes"),
        ))
        trade_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        logging.info(f"📝 Trade accepted: {payload['symbol']} ({payload['trade_type']}) → ID {trade_id}")
        return {"message": "Trade accepted.", "trade_id": trade_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to accept trade: {e}")


@app.post("/graph/skip-trade")
def skip_trade(payload: dict):
    """User skips a trade. Logged for missed-opportunity learning."""
    logging.info(f"⏭️ Trade skipped: {payload.get('symbol')} — Reason: {payload.get('reason', 'none given')}")
    # Skipped trades are tracked in the daily graph state for EOD review
    return {"message": "Skip logged.", "symbol": payload.get("symbol")}


@app.get("/graph/learning-stats")
def learning_stats():
    """Get the system's learning statistics."""
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cur = conn.cursor()

        # Strategy weights
        cur.execute("""
            SELECT signal_type, base_weight, user_override, win_count, loss_count,
                   avg_pnl_when_correct, avg_pnl_when_wrong, last_updated
            FROM strategy_weights ORDER BY base_weight DESC
        """)
        weights = []
        for row in cur.fetchall():
            total = (row[3] or 0) + (row[4] or 0)
            weights.append({
                "signal_type": row[0],
                "weight": row[2] if row[2] is not None else row[1],
                "win_count": row[3] or 0,
                "loss_count": row[4] or 0,
                "win_rate": round((row[3] or 0) / total, 3) if total > 0 else None,
                "avg_pnl_correct": row[5],
                "avg_pnl_wrong": row[6],
                "last_updated": str(row[7]) if row[7] else None,
            })

        # Recent performance summary
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE was_correct) as wins,
                COUNT(*) FILTER (WHERE NOT was_correct) as losses,
                AVG(actual_pnl_pct) as avg_pnl,
                MIN(trade_date) as from_date,
                MAX(trade_date) as to_date
            FROM learning_history
            WHERE trade_date >= CURRENT_DATE - INTERVAL '30 days'
        """)
        perf = cur.fetchone()
        total_trades = (perf[0] or 0) + (perf[1] or 0)

        cur.close()
        conn.close()

        return {
            "strategy_weights": weights,
            "recent_30d": {
                "wins": perf[0] or 0,
                "losses": perf[1] or 0,
                "win_rate": round((perf[0] or 0) / total_trades, 3) if total_trades > 0 else None,
                "avg_pnl": round(perf[2], 3) if perf[2] else None,
                "from_date": str(perf[3]) if perf[3] else None,
                "to_date": str(perf[4]) if perf[4] else None,
            },
        }
    except Exception as e:
        return {"error": str(e), "strategy_weights": [], "recent_30d": {}}


@app.get("/graph/runs")
def get_graph_runs():
    """Get history of graph executions."""
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cur = conn.cursor()
        cur.execute("""
            SELECT id, graph_type, run_date, started_at, finished_at,
                   duration_ms, total_setups, status, error_message
            FROM graph_runs ORDER BY id DESC LIMIT 20
        """)
        runs = []
        for row in cur.fetchall():
            runs.append({
                "id": row[0], "graph_type": row[1], "run_date": str(row[2]),
                "started_at": str(row[3]), "finished_at": str(row[4]) if row[4] else None,
                "duration_ms": row[5], "total_setups": row[6],
                "status": row[7], "error": row[8],
            })
        cur.close()
        conn.close()
        return {"runs": runs}
    except Exception as e:
        return {"error": str(e), "runs": []}


if __name__ == "__main__":
    logging.info("Starting Web Server. Access the API at http://localhost:4500")
    uvicorn.run("main:app", host="0.0.0.0", port=4500)
