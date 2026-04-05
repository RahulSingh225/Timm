"""
Timm Scheduler Worker — Central Cron Scheduler for All Scrapers & Producers

Runs on port 4501. Uses APScheduler with PostgreSQL-backed job execution logging.
Every scraper execution is tracked in the `agent_runs` table for full observability.
"""

import os
import sys
import time
import subprocess
import logging
import json
import psycopg2
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ─── Config ────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SCHEDULER] - %(message)s')

DB_URL = os.getenv("DATABASE_URL")
IST = ZoneInfo("Asia/Kolkata")

# ─── Job Registry ─────────────────────────────────────────────
# Each job maps to a script and a cron schedule.
JOB_REGISTRY = {
    "yfinance_eod": {
        "script": "yfinance_producer.py",
        "description": "YFinance EOD + Intraday Data",
        "cron": {"hour": "16", "minute": "0", "day_of_week": "mon-fri"},
        "category": "producer",
    },
    "nse_flows": {
        "script": "nse_flows_scraper.py",
        "description": "NSE FII/DII Cash Flows",
        "cron": {"hour": "18", "minute": "30", "day_of_week": "mon-fri"},
        "category": "scraper",
    },
    "nse_participants": {
        "script": "nse_participant_scraper.py",
        "description": "NSE Participant OI Data",
        "cron": {"hour": "18", "minute": "30", "day_of_week": "mon-fri"},
        "category": "scraper",
    },
    "nsdl_sectors": {
        "script": "nsdl_sector_scraper.py",
        "description": "NSDL Fortnightly Sector Flows",
        "cron": {"day": "1,16", "hour": "9", "minute": "0"},
        "category": "scraper",
    },
    "nsdl_tradewise": {
        "script": "nsdl_tradewise_scraper.py",
        "description": "NSDL Monthly Trade-wise Flows",
        "cron": {"day": "5", "hour": "9", "minute": "0"},
        "category": "scraper",
    },
    "option_footprint": {
        "script": "option_footprint_producer.py",
        "description": "NSE Options Footprint (Bhavcopy)",
        "cron": {"hour": "17", "minute": "0", "day_of_week": "mon-fri"},
        "category": "scraper",
    },
    "news_scraper": {
        "script": "news_scraper_producer.py",
        "description": "Macro News (RSS Feeds)",
        "cron": {"hour": "9-18", "minute": "0,30", "day_of_week": "mon-fri"},
        "category": "scraper",
    },
    "global_cues": {
        "script": "global_cues_producer.py",
        "description": "US Markets & VIX Global Cues",
        # Runs with --single-run flag so it doesn't start its own loop
        "args": ["--single-run"],
        "cron": {"hour": "8,13", "minute": "30"},
        "category": "producer",
    },
    "yfinance_backfill": {
        "script": "yfinance_producer.py",
        "description": "Historical Backfill (since 2020)",
        "args": ["--backfill"],
        "cron": {"day": "1", "hour": "6", "minute": "0"},
        "category": "producer",
    },
    "premarket_graph": {
        "script": "run_graph.py",
        "args": ["--phase", "premarket"],
        "description": "LangGraph Pre-Market Analysis",
        "cron": {"hour": "8", "minute": "0", "day_of_week": "mon-fri"},
        "category": "agent",
    },
    "eod_review_graph": {
        "script": "run_graph.py",
        "args": ["--phase", "eod"],
        "description": "LangGraph EOD Review + Learning",
        "cron": {"hour": "16", "minute": "30", "day_of_week": "mon-fri"},
        "category": "agent",
    },
}

# ─── In-memory run tracking ────────────────────────────────────
# Stores the last run result per job for fast API access.
# DB is the source of truth but this avoids a query on every poll.
_last_runs: dict[str, dict] = {}

# ─── Database Helpers ──────────────────────────────────────────
def _get_conn():
    return psycopg2.connect(DB_URL)


def _ensure_agent_runs_table():
    """Create the agent_runs table if it doesn't exist."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agent_runs (
                id SERIAL PRIMARY KEY,
                agent_name VARCHAR(50) NOT NULL,
                run_status VARCHAR(20) DEFAULT 'RUNNING' NOT NULL,
                started_at TIMESTAMP DEFAULT NOW() NOT NULL,
                finished_at TIMESTAMP,
                duration_ms INTEGER,
                llm_model VARCHAR(50),
                llm_prompt_tokens INTEGER,
                llm_completion_tokens INTEGER,
                llm_prompt_preview TEXT,
                llm_response_preview TEXT,
                symbol_processed VARCHAR(50),
                message_count INTEGER,
                error_message TEXT,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT NOW() NOT NULL
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        logging.info("✅ agent_runs table verified.")
    except Exception as e:
        logging.error(f"Failed to ensure agent_runs table: {e}")


def _log_run_start(agent_name: str) -> int | None:
    """Insert a RUNNING row and return the row id."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO agent_runs (agent_name, run_status, started_at)
            VALUES (%s, 'RUNNING', NOW())
            RETURNING id;
        """, (agent_name,))
        run_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return run_id
    except Exception as e:
        logging.error(f"Failed to log run start for {agent_name}: {e}")
        return None


def _log_run_finish(run_id: int, status: str, duration_ms: int, error_msg: str | None = None):
    """Update the row with final status."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE agent_runs SET 
                run_status = %s, finished_at = NOW(), duration_ms = %s, error_message = %s
            WHERE id = %s;
        """, (status, duration_ms, error_msg, run_id))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to log run finish for id={run_id}: {e}")


# ─── Job Executor ──────────────────────────────────────────────
def execute_job(job_id: str):
    """Run a scraper script and log the result to agent_runs."""
    job = JOB_REGISTRY.get(job_id)
    if not job:
        logging.error(f"Unknown job_id: {job_id}")
        return

    script = job["script"]
    args = job.get("args", [])
    logging.info(f"🚀 Starting job: {job_id} ({script})")

    run_id = _log_run_start(f"scheduler.{job_id}")
    start_time = time.monotonic()

    try:
        result = subprocess.run(
            [sys.executable, script] + args,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute max per job
        )
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        if result.returncode == 0:
            status = "SUCCESS"
            error = None
            logging.info(f"✅ Job {job_id} completed in {elapsed_ms}ms")
        else:
            status = "FAILED"
            error = (result.stderr or result.stdout)[-500:]  # Last 500 chars
            logging.error(f"❌ Job {job_id} failed (exit {result.returncode}): {error[:100]}")

        if run_id:
            _log_run_finish(run_id, status, elapsed_ms, error)

        _last_runs[job_id] = {
            "status": status,
            "finished_at": datetime.now(IST).isoformat(),
            "duration_ms": elapsed_ms,
            "error": error,
        }

    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logging.error(f"⏰ Job {job_id} timed out after {elapsed_ms}ms")
        if run_id:
            _log_run_finish(run_id, "TIMEOUT", elapsed_ms, "Job exceeded 600s timeout")
        _last_runs[job_id] = {
            "status": "TIMEOUT",
            "finished_at": datetime.now(IST).isoformat(),
            "duration_ms": elapsed_ms,
            "error": "Exceeded 600s timeout",
        }

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logging.error(f"💥 Job {job_id} crashed: {e}")
        if run_id:
            _log_run_finish(run_id, "FAILED", elapsed_ms, str(e)[:500])
        _last_runs[job_id] = {
            "status": "FAILED",
            "finished_at": datetime.now(IST).isoformat(),
            "duration_ms": elapsed_ms,
            "error": str(e)[:500],
        }


# ─── APScheduler Setup ────────────────────────────────────────
scheduler = BackgroundScheduler(timezone=IST)


def setup_scheduler():
    """Register all jobs from the registry."""
    for job_id, job_config in JOB_REGISTRY.items():
        trigger = CronTrigger(timezone=IST, **job_config["cron"])
        scheduler.add_job(
            execute_job,
            trigger=trigger,
            args=[job_id],
            id=job_id,
            name=job_config["description"],
            replace_existing=True,
            misfire_grace_time=300,  # 5 min grace for misfires
        )
        logging.info(f"📅 Registered: {job_id} → {job_config['cron']}")


# ─── FastAPI Application ──────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_agent_runs_table()
    setup_scheduler()
    scheduler.start()
    logging.info(f"🕐 Scheduler started with {len(JOB_REGISTRY)} jobs.")
    yield
    scheduler.shutdown(wait=False)
    logging.info("Scheduler stopped.")


app = FastAPI(title="Timm Scheduler Worker", lifespan=lifespan)


@app.get("/")
def root():
    return {"status": "Timm Scheduler Worker is running.", "jobs": len(JOB_REGISTRY)}


@app.get("/scheduler")
def get_scheduler_status():
    """
    Returns the full state of every scheduled job:
    - next_run_time, cron expression, last run status, category
    """
    jobs_status = []

    for job_id, config in JOB_REGISTRY.items():
        apscheduler_job = scheduler.get_job(job_id)
        next_run = None
        if apscheduler_job and apscheduler_job.next_run_time:
            next_run = apscheduler_job.next_run_time.isoformat()

        last = _last_runs.get(job_id, {})

        # Build human-readable cron
        cron = config["cron"]
        cron_str = _cron_to_human(cron)

        jobs_status.append({
            "id": job_id,
            "description": config["description"],
            "script": config["script"],
            "category": config["category"],
            "cron": cron,
            "cron_human": cron_str,
            "next_run_time": next_run,
            "last_run": {
                "status": last.get("status"),
                "finished_at": last.get("finished_at"),
                "duration_ms": last.get("duration_ms"),
                "error": last.get("error"),
            } if last else None,
            "is_paused": apscheduler_job.next_run_time is None if apscheduler_job else True,
        })

    return {"success": True, "jobs": jobs_status, "timezone": "Asia/Kolkata"}


@app.post("/scheduler/trigger/{job_id}")
def trigger_job(job_id: str):
    """Force-run a job immediately (in background thread)."""
    if job_id not in JOB_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    # Run in a thread so the API responds instantly
    import threading
    thread = threading.Thread(target=execute_job, args=(job_id,), daemon=True)
    thread.start()

    return {"message": f"Job '{job_id}' triggered.", "status": "QUEUED"}


@app.post("/scheduler/pause/{job_id}")
def pause_job(job_id: str):
    """Pause a scheduled job."""
    if job_id not in JOB_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    scheduler.pause_job(job_id)
    return {"message": f"Job '{job_id}' paused."}


@app.post("/scheduler/resume/{job_id}")
def resume_job(job_id: str):
    """Resume a paused job."""
    if job_id not in JOB_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    scheduler.resume_job(job_id)
    return {"message": f"Job '{job_id}' resumed."}


def _cron_to_human(cron: dict) -> str:
    """Convert a cron dict to a rough human-readable string."""
    parts = []
    if "day_of_week" in cron:
        dow = cron["day_of_week"]
        parts.append(dow.replace("mon-fri", "Mon–Fri").capitalize())
    if "day" in cron:
        parts.append(f"Day {cron['day']}")
    if "hour" in cron:
        h = cron["hour"]
        if "-" in h:
            parts.append(f"{h} hrs")
        elif "," in h:
            hours = [f"{int(x)}:{'00' if 'minute' not in cron else cron['minute'].split(',')[0]}" for x in h.split(",")]
            parts.append(" & ".join(hours))
        else:
            m = cron.get("minute", "0")
            if "," in m:
                parts.append(f"{h}:{m.split(',')[0]} & {h}:{m.split(',')[1]}")
            else:
                parts.append(f"{int(h)}:{m.zfill(2)}")
    elif "minute" in cron:
        parts.append(f"Every {cron['minute']} min")

    return " · ".join(parts) if parts else "Custom"


# ─── Entrypoint ────────────────────────────────────────────────
if __name__ == "__main__":
    logging.info("Starting Scheduler Worker on port 4501...")
    uvicorn.run("scheduler_worker:app", host="0.0.0.0", port=4501)
