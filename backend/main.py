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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [MAIN API] - %(message)s')

workers_registry = {
    "vault": "db_vault_worker.py",
    "manager": "system_manager.py",
    "options": "options_agent_worker.py",
    "swing": "swing_agent_worker.py",
    "head": "head_analyst_worker.py",
    "vector": "vector_agent_worker.py",
    "screener": "screener_agent_worker.py",
    "cues": "global_cues_producer.py",
    "monitor": "price_monitor_worker.py"
}

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
    for worker_id, filename in workers_registry.items():
        proc = active_processes.get(worker_id)
        is_alive = False
        if proc:
            # Check if process crashed or finished
            if proc.poll() is None:
                is_alive = True
            else:
                # Remove it if it died
                active_processes.pop(worker_id)
        
        status[worker_id] = {
            "name": filename,
            "status": "RUNNING" if is_alive else "STOPPED",
            "pid": proc.pid if is_alive else None
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

if __name__ == "__main__":
    logging.info("Starting Web Server. Access the API at http://localhost:4500")
    uvicorn.run("main:app", host="0.0.0.0", port=4500)
